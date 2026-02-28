import logging
from datetime import UTC, date, datetime
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
from app.storage.models_sql import Base
from app.storage.repos import ArticleRepo, SourceCandidateRepo, SourceImportBatchRepo
from app.web.auth import SessionSigner, verify_password
from app.web.models import (
    NewsArticleDetail,
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
)
from app.web.service import SourceOnboardingService, UpdateRunService
from app.web.settings_store import UpdateSettingsStore

_TEMPLATE = Path(__file__).with_name("index.html")
_LOGIN_TEMPLATE = Path(__file__).with_name("login.html")
_LOGGER = logging.getLogger(__name__)
_SOURCE_ONBOARDING_OVERLAP_BATCH_QUERY = Query(None, ge=1)
_SOURCE_ONBOARDING_OVERLAP_CANDIDATE_QUERY = Query(default=[])


def _render_index() -> str:
    return _TEMPLATE.read_text(encoding="utf-8")


def _render_login() -> str:
    return _LOGIN_TEMPLATE.read_text(encoding="utf-8")


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
        is_unprotected = path == "/health" or is_auth_route
        is_protected_api = path.startswith("/api/")
        is_protected_ui = path == "/"
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
    def index() -> str:
        return _render_index()

    @api.get("/login", response_class=HTMLResponse)
    def login_page(request: Request) -> Response:
        if auth_enabled:
            session_cookie = request.cookies.get(settings.auth_cookie_name)
            if session_cookie and signer and signer.verify(session_cookie) is not None:
                return RedirectResponse(url="/", status_code=303)
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
