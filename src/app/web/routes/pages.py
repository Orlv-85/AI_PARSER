"""HTML pages, health, collection status and login/logout.

Behavior, decisions, invariants and code map: `src/app/web/pages.md`.
"""

import logging
import re
from datetime import UTC, date, datetime, timedelta
from html import escape
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.exc import SQLAlchemyError

from app.storage.admission import read_collection_status
from app.storage.digest_repo import NewsDigestRepo
from app.storage.models_sql import NewsDigestReport
from app.storage.repos import WeeklyAnalyticsRepo
from app.web.auth import verify_password
from app.web.models import NewsCollectionStatusResponse
from app.web.period_view import home_line, nav_link
from app.web.routes import WebDeps
from app.web.routes.common import (
    _OPTIONAL_WEEKLY_ANALYTICS_DATE_QUERY,
    _read_daily_signals,
    _resolve_weekly_default_report_date,
)
from app.web.routes.period import latest_week
from app.web.signals_view import render_signals

_WEB_DIR = Path(__file__).resolve().parent.parent
_TEMPLATE = _WEB_DIR / "index.html"
_DIGEST_TEMPLATE = _WEB_DIR / "digest.html"
_PLACEHOLDER = re.compile(r"__[A-Z_]+__")
_LOGIN_TEMPLATE = _WEB_DIR / "login.html"
_NEWS_STATS_TEMPLATE = _WEB_DIR / "news_stats.html"
_WEEKLY_ANALYTICS_TEMPLATE = _WEB_DIR / "weekly_analytics.html"
_WEEKLY_ANALYTICS_REPORTS_TEMPLATE = _WEB_DIR / "weekly_analytics_reports.html"
_LOGGER = logging.getLogger(__name__)
_OPTIONAL_NEWS_DIGEST_DATE_QUERY = Query(default=None, alias="date")


def _render_index() -> str:
    return _TEMPLATE.read_text(encoding="utf-8")


def _render_digest(*, report_date: date, digest: NewsDigestReport | None,
                   signals_html: str = "", week: tuple[date, date] | None = None) -> str:
    default_report_date = datetime.now(UTC).date() - timedelta(days=1)
    hero_title = (
        "Yesterday's Digest"
        if report_date == default_report_date
        else f"Digest for {report_date.isoformat()}"
    )
    empty_state_class = "empty-state"
    if digest is None or not digest.groups:
        digest_content = ""
    else:
        empty_state_class = "empty-state hidden"
        sections: list[str] = []
        for group in digest.groups:
            items = "".join(
                (
                    '<li class="digest-item">'
                    f'<a href="{escape(item.url, quote=True)}">{escape(item.title)}</a>'
                    f"<p>{escape(item.summary)}</p>"
                    "</li>"
                )
                for item in group.items
            )
            sections.append(
                '<section class="digest-group">'
                f"<h2>{escape(group.title)}</h2>"
                f'<ul class="digest-list">{items}</ul>'
                "</section>"
            )
        digest_content = "".join(sections)

    values = {
        "__HERO_TITLE__": hero_title,
        "__REPORT_DATE__": report_date.isoformat(),
        "__REPORT_DATE_QUERY__": f"?date={report_date.isoformat()}",
        "__DEFAULT_REPORT_DATE__": default_report_date.isoformat(),
        "__EMPTY_STATE_CLASS__": empty_state_class,
        "__DIGEST_CONTENT__": digest_content,
        "__SIGNALS_CONTENT__": signals_html,
        "__WEEKLY_NAV__": nav_link() if week else "",
        "__WEEKLY_LINE__": home_line(*week) if week else "",
    }
    # One pass: placeholder names inside inserted digest or signals text stay literal (N1).
    return _PLACEHOLDER.sub(lambda m: values.get(m.group(0), m.group(0)),
                            _DIGEST_TEMPLATE.read_text(encoding="utf-8"))


def _render_login() -> str:
    return _LOGIN_TEMPLATE.read_text(encoding="utf-8")


def _render_news_stats(*, date_from: date, date_to: date) -> str:
    return (
        _NEWS_STATS_TEMPLATE.read_text(encoding="utf-8")
        .replace("__DAILY_DIGEST_QUERY__", f"?date={date_to.isoformat()}")
        .replace("__DATE_FROM__", date_from.isoformat())
        .replace("__DATE_TO__", date_to.isoformat())
    )


def _render_weekly_analytics(*, report_date: date) -> str:
    default_report_date = report_date
    return (
        _WEEKLY_ANALYTICS_TEMPLATE.read_text(encoding="utf-8")
        .replace("__REPORT_DATE__", report_date.isoformat())
        .replace("__REPORT_DATE_QUERY__", f"?date={report_date.isoformat()}")
        .replace("__DEFAULT_REPORT_DATE__", default_report_date.isoformat())
    )


def _render_weekly_analytics_reports(*, daily_digest_date: date) -> str:
    return _WEEKLY_ANALYTICS_REPORTS_TEMPLATE.read_text(encoding="utf-8").replace(
        "__DAILY_DIGEST_QUERY__",
        f"?date={daily_digest_date.isoformat()}",
    )


def build_pages_router(deps: WebDeps) -> APIRouter:  # pylint: disable=too-many-statements
    settings = deps.settings
    auth_enabled = deps.auth_enabled
    signer = deps.signer
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    def index(selected_date: date | None = _OPTIONAL_NEWS_DIGEST_DATE_QUERY) -> str:
        report_date = selected_date or (datetime.now(UTC).date() - timedelta(days=1))
        try:
            deps.create_all()
            with deps.SessionLocal() as session:
                digest = NewsDigestRepo(session).get_digest(report_date=report_date)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc
        # Separate read: a signals failure never takes the digest page down.
        try:
            signals_html = render_signals(
                _read_daily_signals(report_date, session_local=deps.SessionLocal))
        except Exception as exc:  # any signals failure (F5): the digest page stays up
            _LOGGER.error("daily_signals_read_failed report_date=%s error=%s",
                          report_date.isoformat(), type(exc).__name__)
            signals_html = render_signals(None, read_error=True)
        return _render_digest(report_date=report_date, digest=digest, signals_html=signals_html,
                              week=latest_week(deps))

    @router.get("/weekly-ai-analytics", response_class=HTMLResponse)
    def weekly_ai_analytics(
        selected_date: date | None = _OPTIONAL_WEEKLY_ANALYTICS_DATE_QUERY,
    ) -> str:
        today = datetime.now(UTC).date()
        try:
            deps.create_all()
            with deps.SessionLocal() as session:
                repo = WeeklyAnalyticsRepo(session)
                report_date = selected_date or _resolve_weekly_default_report_date(
                    repo=repo,
                    today=today,
                )
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc
        return _render_weekly_analytics(report_date=report_date)

    @router.get("/weekly-ai-analytics/reports", response_class=HTMLResponse)
    def weekly_ai_analytics_reports() -> str:
        return _render_weekly_analytics_reports(
            daily_digest_date=datetime.now(UTC).date() - timedelta(days=1),
        )

    @router.get("/news-stats", response_class=HTMLResponse)
    def news_stats_page(
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> str:
        resolved_date_to = date_to or (datetime.now(UTC).date() - timedelta(days=1))
        resolved_date_from = date_from or (resolved_date_to - timedelta(days=59))
        if resolved_date_from > resolved_date_to:
            raise HTTPException(status_code=422, detail="date_from must be <= date_to")
        return _render_news_stats(
            date_from=resolved_date_from,
            date_to=resolved_date_to,
        )

    @router.get("/admin", response_class=HTMLResponse)
    def admin_index() -> str:
        return _render_index()

    @router.get("/login", response_class=HTMLResponse)
    def login_page(request: Request) -> Response:
        if auth_enabled:
            session_cookie = request.cookies.get(settings.auth_cookie_name)
            if session_cookie and signer and signer.verify(session_cookie) is not None:
                return RedirectResponse(url="/admin", status_code=303)
        return HTMLResponse(content=_render_login())

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/api/news/collection-status", response_model=NewsCollectionStatusResponse)
    def get_collection_status_api() -> NewsCollectionStatusResponse:
        try:
            deps.create_all()
            with deps.SessionLocal() as session:
                paused, message = read_collection_status(session)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc
        return NewsCollectionStatusResponse(paused=paused, message=message)

    @router.post("/api/auth/login")
    async def login(request: Request) -> JSONResponse:
        if not auth_enabled:
            return JSONResponse(status_code=200, content={"ok": True})
        payload = await request.json()
        username = str(payload.get("username", ""))
        password = str(payload.get("password", ""))
        username_ok = bool(settings.auth_username) and username == settings.auth_username
        password_ok = bool(settings.auth_password_hash) and verify_password(
            password, settings.auth_password_hash
        )
        if not (username_ok and password_ok):
            _LOGGER.info("login_failed")
            raise HTTPException(status_code=401, detail="Invalid username or password")
        _LOGGER.info("login_success")
        token = signer.sign(subject=username) if signer else ""
        response = JSONResponse(status_code=200, content={"ok": True})
        response.set_cookie(
            key=settings.auth_cookie_name,
            value=token,
            httponly=True,
            secure=settings.auth_cookie_secure,
            samesite="lax",
            max_age=settings.auth_session_ttl_seconds,
        )
        return response

    @router.post("/api/auth/logout")
    def logout(request: Request) -> JSONResponse:
        _LOGGER.info("logout")
        if auth_enabled and signer:
            session_cookie = request.cookies.get(settings.auth_cookie_name)
            if session_cookie:
                signer.revoke(session_cookie)
        response = JSONResponse(status_code=200, content={"ok": True})
        response.delete_cookie(key=settings.auth_cookie_name)
        return response

    return router
