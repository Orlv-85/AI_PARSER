import logging
from datetime import UTC, date, datetime, timedelta
from html import escape
from pathlib import Path
from typing import SupportsIndex, SupportsInt, cast

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi import Path as FastAPIPath
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.core.source_onboarding import (
    import_source_candidates,
    review_candidate_overlaps,
    run_source_validation_batch,
)
from app.storage import SessionLocal, create_all
from app.storage.models_sql import Base, NewsDigestReport
from app.storage.repos import (
    ArticleRepo,
    NewsDigestRepo,
    SourceCandidateRepo,
    SourceImportBatchRepo,
    WeeklyAnalyticsItem,
    WeeklyAnalyticsRepo,
    WeeklyAnalyticsReport,
    WeeklyAnalyticsReportIndexEntry,
)
from app.web.auth import SessionSigner, verify_password
from app.web.models import (
    DigestLinkFeedItem,
    NewsArticleDetail,
    NewsDigestGroupPayload,
    NewsDigestItemPayload,
    NewsDigestPayload,
    NewsDigestResponse,
    NewsItem,
    SourceOnboardingApproveResponse,
    SourceOnboardingBatchSummary,
    SourceOnboardingCandidateListResponse,
    SourceOnboardingDisableResponse,
    SourceOnboardingDuplicateRequest,
    SourceOnboardingDuplicateResponse,
    SourceOnboardingEditRequest,
    SourceOnboardingEditResponse,
    SourceOnboardingRejectRequest,
    SourceOnboardingRejectResponse,
    UpdateStatus,
    WebUpdateSettings,
    WeeklyAnalyticsReportListItem,
    WeeklyAnalyticsReportListResponse,
    WeeklyAnalyticsResponse,
)
from app.web.service import SourceOnboardingService, UpdateRunService
from app.web.settings_store import UpdateSettingsStore

_TEMPLATE = Path(__file__).with_name("index.html")
_DIGEST_TEMPLATE = Path(__file__).with_name("digest.html")
_LOGIN_TEMPLATE = Path(__file__).with_name("login.html")
_WEEKLY_ANALYTICS_TEMPLATE = Path(__file__).with_name("weekly_analytics.html")
_WEEKLY_ANALYTICS_REPORTS_TEMPLATE = Path(__file__).with_name("weekly_analytics_reports.html")
_LOGGER = logging.getLogger(__name__)
_SOURCE_ONBOARDING_OVERLAP_BATCH_QUERY = Query(None, ge=1)
_SOURCE_ONBOARDING_OVERLAP_CANDIDATE_QUERY = Query(default=[])
_NEWS_LINKS_DATE_QUERY = Query(alias="date")
_NEWS_DIGEST_DATE_QUERY = Query(alias="date")
_OPTIONAL_NEWS_DIGEST_DATE_QUERY = Query(default=None, alias="date")
_OPTIONAL_WEEKLY_ANALYTICS_DATE_QUERY = Query(default=None, alias="date")


def _render_index() -> str:
    return _TEMPLATE.read_text(encoding="utf-8")


def _render_digest(*, report_date: date, digest: NewsDigestReport | None) -> str:
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

    return (
        _DIGEST_TEMPLATE.read_text(encoding="utf-8")
        .replace("__HERO_TITLE__", hero_title)
        .replace("__REPORT_DATE__", report_date.isoformat())
        .replace("__REPORT_DATE_QUERY__", f"?date={report_date.isoformat()}")
        .replace("__DEFAULT_REPORT_DATE__", default_report_date.isoformat())
        .replace("__EMPTY_STATE_CLASS__", empty_state_class)
        .replace("__DIGEST_CONTENT__", digest_content)
    )


def _render_login() -> str:
    return _LOGIN_TEMPLATE.read_text(encoding="utf-8")


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


def _resolve_weekly_default_report_date(*, repo: WeeklyAnalyticsRepo, today: date) -> date:
    get_latest = getattr(repo, "get_latest_report_date", None)
    if callable(get_latest):
        try:
            latest_published = get_latest()
        except SQLAlchemyError:
            latest_published = None
        if latest_published is not None:
            return cast(date, latest_published)
    return today - timedelta(days=1)


def _build_digest_response(
    *,
    report_date: date,
    digest: NewsDigestReport | None,
) -> NewsDigestResponse:
    if digest is None:
        return NewsDigestResponse(report_date=report_date, groups=[])

    return NewsDigestResponse(
        report_date=report_date,
        groups=[
            NewsDigestGroupPayload(
                title=group.title,
                items=[
                    NewsDigestItemPayload(
                        title=item.title,
                        summary=item.summary,
                        url=item.url,
                    )
                    for item in group.items
                ],
            )
            for group in digest.groups
        ],
    )


def _build_weekly_analytics_response(
    *,
    report_date: date,
    weekly_report: WeeklyAnalyticsReport | None,
) -> WeeklyAnalyticsResponse:
    if weekly_report is None:
        date_to = report_date
        date_from = report_date - timedelta(days=6)
        return WeeklyAnalyticsResponse(
            report_date=report_date,
            date_from=date_from,
            date_to=date_to,
            summary="Antigravity found no AI news signals for this week.",
            new=[],
            trending_up=[],
            trending_down=[],
        )

    def _serialize_items(items: list[WeeklyAnalyticsItem]) -> list[NewsDigestItemPayload]:
        return [
            NewsDigestItemPayload(
                title=item.title,
                summary=item.summary,
                url=item.url,
            )
            for item in items
        ]

    return WeeklyAnalyticsResponse(
        report_date=weekly_report.report_date,
        date_from=weekly_report.date_from,
        date_to=weekly_report.date_to,
        summary=weekly_report.summary,
        new=_serialize_items(weekly_report.new),
        trending_up=_serialize_items(weekly_report.trending_up),
        trending_down=_serialize_items(weekly_report.trending_down),
    )


def _build_weekly_report_list_response(
    *,
    items: list[WeeklyAnalyticsReportIndexEntry],
) -> WeeklyAnalyticsReportListResponse:
    return WeeklyAnalyticsReportListResponse(
        items=[
            WeeklyAnalyticsReportListItem(
                report_date=item.report_date,
                date_from=item.date_from,
                date_to=item.date_to,
                summary=item.summary,
                created_at=item.created_at,
            )
            for item in items
        ]
    )


def _parse_source_onboarding_identifier(
    value: object,
    *,
    field_name: str,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise HTTPException(status_code=422, detail=f"{field_name} must be an integer")
    try:
        parsed = int(
            cast(
                str | bytes | bytearray | SupportsInt | SupportsIndex,
                value,
            )
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} must be an integer") from exc
    if parsed < 1:
        raise HTTPException(status_code=422, detail=f"{field_name} must be >= 1")
    return parsed


def _parse_source_onboarding_candidate_ids(value: object) -> list[int] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise HTTPException(status_code=422, detail="candidate_ids must be a list of integers")
    parsed_ids: list[int] = []
    for candidate_id in value:
        if candidate_id is None:
            raise HTTPException(status_code=422, detail="candidate_ids must be a list of integers")
        parsed_id = _parse_source_onboarding_identifier(candidate_id, field_name="candidate_ids")
        if parsed_id is None:  # pragma: no cover - guarded above
            raise HTTPException(status_code=422, detail="candidate_ids must be a list of integers")
        parsed_ids.append(parsed_id)
    return parsed_ids


def create_app() -> FastAPI:  # pylint: disable=too-many-statements
    settings = get_settings()
    settings_path = Path("data") / "web_update_settings.json"
    settings_store = UpdateSettingsStore(settings_path)
    update_service = UpdateRunService()
    onboarding_database_url = make_url(settings.database_url)
    if (
        onboarding_database_url.drivername.startswith("sqlite")
        and onboarding_database_url.database
        and onboarding_database_url.database != ":memory:"
    ):
        Path(onboarding_database_url.database).parent.mkdir(parents=True, exist_ok=True)
    onboarding_engine = create_engine(settings.database_url, future=True)
    onboarding_session_local = sessionmaker(
        bind=onboarding_engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )
    auth_enabled = settings.is_auth_enabled
    signer = (
        SessionSigner(
            secret=settings.auth_secret or "",
            ttl_seconds=settings.auth_session_ttl_seconds,
        )
        if auth_enabled
        else None
    )

    api = FastAPI(title="AI News Collector Web")

    @api.middleware("http")
    async def auth_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        if not auth_enabled:
            return await call_next(request)

        path = request.url.path
        is_auth_route = path in {"/login", "/api/auth/login", "/api/auth/logout"}
        is_public_news_api = path in {
            "/api/news/links",
            "/api/news/digests",
            "/api/news/weekly-analytics",
            "/api/news/weekly-analytics/reports",
        }
        is_unprotected = (
            path in {"/health", "/", "/weekly-ai-analytics", "/weekly-ai-analytics/reports"}
            or is_auth_route
            or is_public_news_api
        )
        is_protected_ui = path == "/admin"
        is_protected_api = path.startswith("/api/") and not is_public_news_api
        is_protected = is_protected_api or is_protected_ui

        if not is_protected or is_unprotected:
            return await call_next(request)

        session_cookie = request.cookies.get(settings.auth_cookie_name)
        if session_cookie and signer and signer.verify(session_cookie) is not None:
            return await call_next(request)

        if session_cookie:
            _LOGGER.info("session_expired")
        if is_protected_api:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return RedirectResponse(url="/login", status_code=303)

    @api.get("/", response_class=HTMLResponse)
    def index(selected_date: date | None = _OPTIONAL_NEWS_DIGEST_DATE_QUERY) -> str:
        report_date = selected_date or (datetime.now(UTC).date() - timedelta(days=1))
        try:
            create_all()
            with SessionLocal() as session:
                digest = NewsDigestRepo(session).get_digest(report_date=report_date)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return _render_digest(report_date=report_date, digest=digest)

    @api.get("/weekly-ai-analytics", response_class=HTMLResponse)
    def weekly_ai_analytics(
        selected_date: date | None = _OPTIONAL_WEEKLY_ANALYTICS_DATE_QUERY,
    ) -> str:
        today = datetime.now(UTC).date()
        try:
            create_all()
            with SessionLocal() as session:
                repo = WeeklyAnalyticsRepo(session)
                report_date = selected_date or _resolve_weekly_default_report_date(
                    repo=repo,
                    today=today,
                )
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc
        return _render_weekly_analytics(report_date=report_date)

    @api.get("/weekly-ai-analytics/reports", response_class=HTMLResponse)
    def weekly_ai_analytics_reports() -> str:
        return _render_weekly_analytics_reports(
            daily_digest_date=datetime.now(UTC).date() - timedelta(days=1),
        )

    @api.get("/admin", response_class=HTMLResponse)
    def admin_index() -> str:
        return _render_index()

    @api.get("/login", response_class=HTMLResponse)
    def login_page(request: Request) -> Response:
        if auth_enabled:
            session_cookie = request.cookies.get(settings.auth_cookie_name)
            if session_cookie and signer and signer.verify(session_cookie) is not None:
                return RedirectResponse(url="/admin", status_code=303)
        return HTMLResponse(content=_render_login())

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.post("/api/auth/login")
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

    @api.post("/api/auth/logout")
    def logout(request: Request) -> JSONResponse:
        _LOGGER.info("logout")
        if auth_enabled and signer:
            session_cookie = request.cookies.get(settings.auth_cookie_name)
            if session_cookie:
                signer.revoke(session_cookie)
        response = JSONResponse(status_code=200, content={"ok": True})
        response.delete_cookie(key=settings.auth_cookie_name)
        return response

    @api.get("/api/update/settings", response_model=WebUpdateSettings)
    def get_update_settings() -> WebUpdateSettings:
        return settings_store.load()

    @api.put("/api/update/settings", response_model=WebUpdateSettings)
    def put_update_settings(payload: WebUpdateSettings) -> WebUpdateSettings:
        return settings_store.save(payload)

    @api.post("/api/update/run", response_model=UpdateStatus)
    def run_update() -> UpdateStatus:
        runtime_settings = settings_store.load()
        status = update_service.start(runtime_settings)
        if status is None:
            raise HTTPException(status_code=409, detail="Update run is already active")
        return status

    @api.get("/api/update/status", response_model=UpdateStatus)
    def get_update_status() -> UpdateStatus:
        return update_service.current_status()

    @api.get("/api/news", response_model=list[NewsItem])
    def list_news(
        *,
        hours: int = Query(24, ge=1, le=720),
        limit: int = Query(30, ge=1, le=200),
        min_ai_relevance: float = Query(0.2, ge=0.0, le=1.0),
        query: str | None = None,
        days: int = Query(7, ge=1, le=365),
        sort: str = Query("rank", pattern="^(rank|published)$"),
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[NewsItem]:
        has_date_range = date_from is not None or date_to is not None
        hours_filter = None if has_date_range else hours
        try:
            create_all()
            with SessionLocal() as session:
                repo = ArticleRepo(session)
                list_kwargs: dict[str, object] = {
                    "hours": hours_filter,
                    "limit": limit,
                    "min_ai_relevance": min_ai_relevance,
                    "query": query,
                    "days": days,
                    "sort": sort,
                }
                if has_date_range:
                    list_kwargs["date_from"] = date_from
                    list_kwargs["date_to"] = date_to
                rows = repo.list_for_view(**list_kwargs)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return [
            NewsItem(
                title=article.title,
                published_at=article.published_at,
                rank_score=article.rank_score,
                url_canonical=article.url_canonical,
                source_id=article.source_id,
                source_key=source_key,
                source_name=source_name,
            )
            for article, source_key, source_name in rows
        ]

    @api.get("/api/news/export")
    def export_news(
        *,
        hours: int = Query(24, ge=1, le=720),
        limit: int = Query(30, ge=1, le=200),
        min_ai_relevance: float = Query(0.2, ge=0.0, le=1.0),
        query: str | None = None,
        days: int = Query(7, ge=1, le=365),
        sort: str = Query("rank", pattern="^(rank|published)$"),
        include_content: bool = False,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> JSONResponse:
        has_date_range = date_from is not None or date_to is not None
        hours_filter = None if has_date_range else hours
        try:
            create_all()
            with SessionLocal() as session:
                repo = ArticleRepo(session)
                list_kwargs: dict[str, object] = {
                    "hours": hours_filter,
                    "limit": limit,
                    "min_ai_relevance": min_ai_relevance,
                    "query": query,
                    "days": days,
                    "sort": sort,
                    "include_content": include_content,
                }
                if has_date_range:
                    list_kwargs["date_from"] = date_from
                    list_kwargs["date_to"] = date_to
                rows = repo.list_for_view(**list_kwargs)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        payload: list[dict[str, object | None]] = []
        for article, source_key, source_name in rows:
            item: dict[str, object | None] = {
                "article_id": article.id,
                "title": article.title,
                "published_at": article.published_at,
                "rank_score": article.rank_score,
                "url_canonical": article.url_canonical,
                "source_id": article.source_id,
                "source_key": source_key,
                "source_name": source_name,
            }
            if include_content:
                item["summary"] = article.summary
                item["content"] = article.content
                item["url"] = article.url
            payload.append(item)

        filename = datetime.now(UTC).strftime("news-export-%Y%m%dT%H%M%SZ.json")
        return JSONResponse(
            content=jsonable_encoder(payload),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @api.get("/api/news/links", response_model=list[DigestLinkFeedItem])
    def list_news_links(
        *,
        target_date: date = _NEWS_LINKS_DATE_QUERY,
        limit: int = Query(30, ge=1, le=200),
        min_ai_relevance: float = Query(0.2, ge=0.0, le=1.0),
    ) -> list[DigestLinkFeedItem]:
        try:
            create_all()
            with SessionLocal() as session:
                repo = ArticleRepo(session)
                rows = repo.list_for_agent(
                    hours=None,
                    limit=limit,
                    query=None,
                    days=1,
                    sort="published",
                    min_ai_relevance=min_ai_relevance,
                    date_from=target_date,
                    date_to=target_date,
                )
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return [
            DigestLinkFeedItem(
                article_id=article.id,
                title=article.title,
                published_at=article.published_at,
                url=article.url,
                url_canonical=article.url_canonical,
                source_id=article.source_id,
                source_key=source_key,
                source_name=source_name,
            )
            for article, source_key, source_name in rows
        ]

    @api.post("/api/news/digests", response_model=NewsDigestResponse)
    def save_news_digest(payload: NewsDigestPayload) -> NewsDigestResponse:
        try:
            create_all()
            with SessionLocal() as session:
                repo = NewsDigestRepo(session)
                repo.save_digest(
                    report_date=payload.report_date,
                    groups=[
                        {
                            "title": group.title,
                            "items": [
                                {
                                    "title": item.title,
                                    "summary": item.summary,
                                    "url": item.url,
                                }
                                for item in group.items
                            ],
                        }
                        for group in payload.groups
                    ],
                )
                session.commit()
                stored = repo.get_digest(report_date=payload.report_date)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return _build_digest_response(report_date=payload.report_date, digest=stored)

    @api.get("/api/news/digests", response_model=NewsDigestResponse)
    def get_news_digest(*, target_date: date = _NEWS_DIGEST_DATE_QUERY) -> NewsDigestResponse:
        try:
            create_all()
            with SessionLocal() as session:
                digest = NewsDigestRepo(session).get_digest(report_date=target_date)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return _build_digest_response(report_date=target_date, digest=digest)

    @api.get("/api/news/weekly-analytics", response_model=WeeklyAnalyticsResponse)
    def get_weekly_ai_analytics(
        *,
        target_date: date | None = _OPTIONAL_WEEKLY_ANALYTICS_DATE_QUERY,
    ) -> WeeklyAnalyticsResponse:
        try:
            create_all()
            with SessionLocal() as session:
                repo = WeeklyAnalyticsRepo(session)
                report_date = target_date or _resolve_weekly_default_report_date(
                    repo=repo,
                    today=datetime.now(UTC).date(),
                )
                weekly_report = repo.get_weekly_report(
                    report_date=report_date
                )
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return _build_weekly_analytics_response(
            report_date=report_date,
            weekly_report=weekly_report,
        )

    @api.get(
        "/api/news/weekly-analytics/reports",
        response_model=WeeklyAnalyticsReportListResponse,
    )
    def list_weekly_ai_analytics_reports(
        *,
        limit: int = Query(52, ge=1, le=260),
    ) -> WeeklyAnalyticsReportListResponse:
        try:
            create_all()
            with SessionLocal() as session:
                items = WeeklyAnalyticsRepo(session).list_stored_reports(limit=limit)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc
        return _build_weekly_report_list_response(items=items)

    @api.get("/api/news/{article_id}", response_model=NewsArticleDetail)
    def get_news_article(article_id: int) -> NewsArticleDetail:
        try:
            create_all()
            with SessionLocal() as session:
                repo = ArticleRepo(session)
                row = repo.get_article_for_agent(article_id=article_id)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        if row is None:
            raise HTTPException(status_code=404, detail="Article not found")

        article, source_key, source_name = row
        return NewsArticleDetail(
            article_id=article.id,
            title=article.title,
            summary=article.summary,
            content=article.content,
            published_at=article.published_at,
            rank_score=article.rank_score,
            url=article.url,
            url_canonical=article.url_canonical,
            source_id=article.source_id,
            source_key=source_key,
            source_name=source_name,
        )

    @api.post("/api/source-onboarding/import")
    async def import_source_onboarding_batch(request: Request) -> JSONResponse:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="raw_text is required")
        raw_text = str(payload.get("raw_text", "")).strip()
        if not raw_text:
            raise HTTPException(status_code=422, detail="raw_text is required")

        try:
            Base.metadata.create_all(bind=onboarding_engine)
            with onboarding_session_local() as session:
                result = import_source_candidates(
                    raw_text=raw_text,
                    batch_repo=SourceImportBatchRepo(session),
                    candidate_repo=SourceCandidateRepo(session),
                )
                session.commit()
                batch_id = result.batch.id
                parsed_count = result.parsed_count
                accepted_count = result.accepted_count
                rejected_count = result.rejected_count
                candidate_ids = [candidate.id for candidate in result.candidates]
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return JSONResponse(
            status_code=201,
            content={
                "batch_id": batch_id,
                "parsed_count": parsed_count,
                "accepted_count": accepted_count,
                "rejected_count": rejected_count,
                "candidate_ids": candidate_ids,
            },
        )

    @api.post("/api/source-onboarding/validate")
    async def validate_source_onboarding_batch(request: Request) -> JSONResponse:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="batch_id or candidate_ids is required")

        raw_batch_id = payload.get("batch_id")
        raw_candidate_ids = payload.get("candidate_ids")
        batch_id = _parse_source_onboarding_identifier(raw_batch_id, field_name="batch_id")
        candidate_ids = _parse_source_onboarding_candidate_ids(raw_candidate_ids)
        if batch_id is None and not candidate_ids:
            raise HTTPException(status_code=422, detail="batch_id or candidate_ids is required")

        try:
            Base.metadata.create_all(bind=onboarding_engine)
            with onboarding_session_local() as session:
                results = run_source_validation_batch(
                    session=session,
                    batch_id=batch_id,
                    candidate_ids=candidate_ids,
                )
                session.commit()
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return JSONResponse(
            status_code=200,
            content={
                "validated_count": len(results),
                "results": [
                    {
                        "candidate_id": result.candidate_id,
                        "status": result.status,
                        "detected_type": result.detected_type,
                        "validation_error": result.validation_error,
                        "entry_count": result.entry_count,
                        "link_count": result.link_count,
                        "sample_links": result.sample_links,
                    }
                    for result in results
                ],
            },
        )

    @api.get("/api/source-onboarding/overlaps")
    def get_source_onboarding_overlaps(
        *,
        batch_id: int | None = _SOURCE_ONBOARDING_OVERLAP_BATCH_QUERY,
        candidate_id: list[int] = _SOURCE_ONBOARDING_OVERLAP_CANDIDATE_QUERY,
    ) -> JSONResponse:
        candidate_ids = list(candidate_id)
        try:
            Base.metadata.create_all(bind=onboarding_engine)
            with onboarding_session_local() as session:
                groups = review_candidate_overlaps(
                    session=session,
                    batch_id=batch_id,
                    candidate_ids=candidate_ids or None,
                )
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return JSONResponse(
            status_code=200,
            content={
                "groups": [
                    {
                        "candidate_ids": group.candidate_ids,
                        "reason": group.reason,
                        "preferred_candidate_id": group.preferred_candidate_id,
                    }
                    for group in groups
                ]
            },
        )

    @api.get(
        "/api/source-onboarding/candidates",
        response_model=SourceOnboardingCandidateListResponse,
    )
    def list_source_onboarding_candidates(
        *,
        batch_id: int | None = Query(None, ge=1),
        status: str | None = None,
        validation_status: str | None = None,
    ) -> SourceOnboardingCandidateListResponse:
        try:
            Base.metadata.create_all(bind=onboarding_engine)
            with onboarding_session_local() as session:
                service = SourceOnboardingService(session)
                return service.list_candidates(
                    batch_id=batch_id,
                    status=status,
                    validation_status=validation_status,
                )
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

    @api.get(
        "/api/source-onboarding/batches/{batch_id}/summary",
        response_model=SourceOnboardingBatchSummary,
    )
    def get_source_onboarding_batch_summary(batch_id: int) -> SourceOnboardingBatchSummary:
        try:
            Base.metadata.create_all(bind=onboarding_engine)
            with onboarding_session_local() as session:
                service = SourceOnboardingService(session)
                return service.get_batch_summary(batch_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

    @api.post(
        "/api/source-onboarding/candidates/{candidate_id}/approve",
        response_model=SourceOnboardingApproveResponse,
    )
    def approve_source_onboarding_candidate(
        candidate_id: int = FastAPIPath(..., ge=1),
    ) -> SourceOnboardingApproveResponse:
        try:
            Base.metadata.create_all(bind=onboarding_engine)
            with onboarding_session_local() as session:
                service = SourceOnboardingService(session)
                response = service.approve_candidate(candidate_id)
                session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return response

    @api.post(
        "/api/source-onboarding/candidates/{candidate_id}/disable",
        response_model=SourceOnboardingDisableResponse,
    )
    def disable_source_onboarding_candidate(
        candidate_id: int = FastAPIPath(..., ge=1),
    ) -> SourceOnboardingDisableResponse:
        try:
            Base.metadata.create_all(bind=onboarding_engine)
            with onboarding_session_local() as session:
                service = SourceOnboardingService(session)
                response = service.disable_candidate(candidate_id)
                session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return response

    @api.post(
        "/api/source-onboarding/candidates/{candidate_id}/reject",
        response_model=SourceOnboardingRejectResponse,
    )
    def reject_source_onboarding_candidate(
        payload: SourceOnboardingRejectRequest,
        candidate_id: int = FastAPIPath(..., ge=1),
    ) -> SourceOnboardingRejectResponse:
        try:
            Base.metadata.create_all(bind=onboarding_engine)
            with onboarding_session_local() as session:
                service = SourceOnboardingService(session)
                response = service.reject_candidate(candidate_id, reason=payload.reason)
                session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return response

    @api.post(
        "/api/source-onboarding/candidates/{candidate_id}/mark-duplicate",
        response_model=SourceOnboardingDuplicateResponse,
    )
    def mark_source_onboarding_candidate_duplicate(
        payload: SourceOnboardingDuplicateRequest,
        candidate_id: int = FastAPIPath(..., ge=1),
    ) -> SourceOnboardingDuplicateResponse:
        try:
            Base.metadata.create_all(bind=onboarding_engine)
            with onboarding_session_local() as session:
                service = SourceOnboardingService(session)
                response = service.mark_duplicate(
                    candidate_id,
                    duplicate_of_candidate_id=payload.duplicate_of_candidate_id,
                    reason=payload.reason,
                )
                session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return response

    @api.patch(
        "/api/source-onboarding/candidates/{candidate_id}",
        response_model=SourceOnboardingEditResponse,
    )
    def edit_source_onboarding_candidate(
        payload: SourceOnboardingEditRequest,
        candidate_id: int = FastAPIPath(..., ge=1),
    ) -> SourceOnboardingEditResponse:
        try:
            Base.metadata.create_all(bind=onboarding_engine)
            with onboarding_session_local() as session:
                service = SourceOnboardingService(session)
                response = service.edit_candidate(
                    candidate_id,
                    raw_input=payload.raw_input,
                    normalized_url=payload.normalized_url,
                    candidate_type=payload.candidate_type,
                    review_note=payload.review_note,
                )
                session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return response

    return api


app = create_app()
