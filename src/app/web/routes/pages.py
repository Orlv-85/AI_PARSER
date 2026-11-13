"""HTML pages, health, collection status and login/logout.

Behavior, decisions, invariants and code map: `src/app/web/pages.md`.
"""

import logging
import re
from datetime import UTC, date, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import TypeAdapter, ValidationError, WithJsonSchema
from sqlalchemy.exc import SQLAlchemyError

from app.storage.models_sql import NewsDigestReport
from app.usecases.bulletin.stored import stored_bulletin
from app.usecases.collection_status import collection_status
from app.usecases.digest import stored_digest
from app.usecases.page_views import count_page_view
from app.web.auth import verify_password
from app.web.bulletin_view import render_bulletin_page
from app.web.models import LoginRequest, NewsCollectionStatusResponse, json_body
from app.web.period_view import home_line, month_nav_link, nav_link
from app.web.routes import WebDeps
from app.web.routes.bulletin import parse_day
from app.web.routes.common import (
    _read_daily_signals,
)
from app.web.routes.period import has_month, latest_week
from app.web.signals_view import render_signals

_WEB_DIR = Path(__file__).resolve().parent.parent
_TEMPLATE = _WEB_DIR / "index.html"
_DIGEST_TEMPLATE = _WEB_DIR / "digest.html"
_PLACEHOLDER = re.compile(r"__[A-Z_]+__")
_LOGIN_TEMPLATE = _WEB_DIR / "login.html"
_NEWS_STATS_TEMPLATE = _WEB_DIR / "news_stats.html"
_LOGGER = logging.getLogger(__name__)
_OPTIONAL_NEWS_DIGEST_DATE_QUERY = Query(default=None, alias="date")


def _render_index() -> str:
    return _TEMPLATE.read_text(encoding="utf-8")


def _render_digest(*, report_date: date, digest: NewsDigestReport | None,
                   signals_html: str = "", week: tuple[date, date] | None = None,
                   monthly: bool = False) -> str:
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
        "__WEEKLY_NAV__": (nav_link() if week else "") + (month_nav_link() if monthly else ""),
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


def _bulletin_response(deps: WebDeps, target_date: str | None, *,
                       preview: bool = True) -> HTMLResponse | None:
    day = parse_day(target_date)
    try:
        deps.create_all()
        row = stored_bulletin(deps.SessionLocal, day)
        if not preview and day is None and row is None:
            return None
        selected_day = row.day if row is not None else day
        return HTMLResponse(render_bulletin_page(row, selected_day, preview=preview),
                            status_code=404 if row is None else 200)
    except SQLAlchemyError:
        return HTMLResponse(render_bulletin_page(None, day,
                            message="News storage is unavailable.", preview=preview),
                            status_code=503)


def _digest_response(deps: WebDeps, selected_date: date | None) -> str:
    report_date = selected_date or (datetime.now(UTC).date() - timedelta(days=1))
    try:
        deps.create_all()
        digest = stored_digest(deps.SessionLocal, report_date)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="News storage is unavailable") from exc
    # Separate read: a signals failure never takes the digest page down.
    try:
        signals_html = render_signals(
            _read_daily_signals(report_date, session_local=deps.SessionLocal))
    except Exception as exc:  # any signals failure (F5): the digest page stays up
        _LOGGER.error("daily_signals_read_failed report_date=%s error=%s",
                      report_date.isoformat(), type(exc).__name__, exc_info=True)
        signals_html = render_signals(None, read_error=True)
    return _render_digest(report_date=report_date, digest=digest, signals_html=signals_html,
                          week=latest_week(deps), monthly=has_month(deps))


def _digest_date(value: str | None) -> date | None:
    """Keep FastAPI's digest date validation when home switches between two date contracts."""
    try:
        result: date | None = TypeAdapter(date | None).validate_python(value)
        return result
    except ValidationError as exc:
        errors = [{**error, "loc": ("query", "date", *error["loc"])}
                  for error in exc.errors(include_url=False)]
        raise RequestValidationError(errors) from exc


def _count_page(deps: WebDeps, route: str) -> None:
    try:
        count_page_view(deps.SessionLocal, datetime.now(UTC).date(), route)
    except Exception as exc:  # Measurement must never take down a public page.
        _LOGGER.error("page_views_increment_failed route=%s error=%s", route, type(exc).__name__,
                      exc_info=True)


def _digest_page(deps: WebDeps, background_tasks: BackgroundTasks,
                 selected_date: date | None, route: str) -> str:
    content = _digest_response(deps, selected_date)
    background_tasks.add_task(_count_page, deps, route)
    return content


def _home_response(deps: WebDeps, background_tasks: BackgroundTasks,
                   target_date: str | None) -> str | HTMLResponse:
    response = None
    if deps.settings.bulletin_home_page:
        response = _bulletin_response(deps, target_date, preview=False)
    if response is None:
        return _digest_page(deps, background_tasks, _digest_date(target_date), "/")
    if response.status_code == 200:
        background_tasks.add_task(_count_page, deps, "/")
    return response


def _news_stats_response(date_from: date | None, date_to: date | None) -> str:
    resolved_date_to = date_to or (datetime.now(UTC).date() - timedelta(days=1))
    resolved_date_from = date_from or (resolved_date_to - timedelta(days=59))
    if resolved_date_from > resolved_date_to:
        raise HTTPException(status_code=422, detail="date_from must be <= date_to")
    return _render_news_stats(date_from=resolved_date_from, date_to=resolved_date_to)


def _login_page_response(deps: WebDeps, request: Request) -> Response:
    if deps.auth_enabled:
        session_cookie = request.cookies.get(deps.settings.auth_cookie_name)
        if session_cookie and deps.signer and deps.signer.verify(session_cookie) is not None:
            return RedirectResponse(url="/admin", status_code=303)
    return HTMLResponse(content=_render_login())


def _health_response() -> dict[str, str]:
    return {"status": "ok"}


def _collection_status_response(deps: WebDeps) -> NewsCollectionStatusResponse:
    try:
        deps.create_all()
        paused, message = collection_status(deps.SessionLocal)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="News storage is unavailable") from exc
    return NewsCollectionStatusResponse(paused=paused, message=message)


async def _login_response(deps: WebDeps, request: Request) -> JSONResponse:
    settings = deps.settings
    signer = deps.signer
    if not deps.auth_enabled:
        return JSONResponse(status_code=200, content={"ok": True})
    try:
        body = LoginRequest.model_validate(json_body(await request.body()))
    except ValueError:  # not JSON or not an object: a failed login
        body = LoginRequest()
    username, password = body.username, body.password
    username_ok = bool(settings.auth_username) and username == settings.auth_username
    password_ok = bool(settings.auth_password_hash and verify_password(
        password, settings.auth_password_hash
    ))
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


def _logout_response(deps: WebDeps, request: Request) -> JSONResponse:
    _LOGGER.info("logout")
    if deps.auth_enabled and deps.signer:
        session_cookie = request.cookies.get(deps.settings.auth_cookie_name)
        if session_cookie:
            deps.signer.revoke(session_cookie)
    response = JSONResponse(status_code=200, content={"ok": True})
    response.delete_cookie(key=deps.settings.auth_cookie_name)
    return response


def build_pages_router(deps: WebDeps) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse, response_model=str)
    def index(
        background_tasks: BackgroundTasks,
        target_date: Annotated[str, WithJsonSchema({"type": "string", "format": "date"})] | None
            = _OPTIONAL_NEWS_DIGEST_DATE_QUERY,
    ) -> str | HTMLResponse:
        return _home_response(deps, background_tasks, target_date)

    @router.get("/daily", response_class=HTMLResponse)
    def daily(background_tasks: BackgroundTasks,
              selected_date: date | None = _OPTIONAL_NEWS_DIGEST_DATE_QUERY) -> str:
        return _digest_page(deps, background_tasks, selected_date, "/daily")

    @router.get("/bulletin", response_class=HTMLResponse, response_model=None,
                include_in_schema=False)
    def bulletin_page(
        target_date: str | None = _OPTIONAL_NEWS_DIGEST_DATE_QUERY,
    ) -> Response | None:
        return _bulletin_response(deps, target_date)

    # Legacy weekly pages retired (017 R5): permanent redirect, query string dropped.
    @router.get("/weekly-ai-analytics/reports", include_in_schema=False)
    @router.get("/weekly-ai-analytics", include_in_schema=False)
    def legacy_weekly_redirect() -> RedirectResponse:
        return RedirectResponse(url="/weekly", status_code=308)

    @router.get("/news-stats", response_class=HTMLResponse)
    def news_stats_page(
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> str:
        return _news_stats_response(date_from, date_to)

    @router.get("/admin", response_class=HTMLResponse)
    def admin_index() -> str:
        return _render_index()

    @router.get("/login", response_class=HTMLResponse)
    def login_page(request: Request) -> Response:
        return _login_page_response(deps, request)

    @router.get("/health")
    def health() -> dict[str, str]:
        return _health_response()

    @router.get("/api/news/collection-status", response_model=NewsCollectionStatusResponse)
    def get_collection_status_api() -> NewsCollectionStatusResponse:
        return _collection_status_response(deps)

    @router.post("/api/auth/login")
    async def login(request: Request) -> JSONResponse:
        return await _login_response(deps, request)

    @router.post("/api/auth/logout")
    def logout(request: Request) -> JSONResponse:
        return _logout_response(deps, request)

    return router
