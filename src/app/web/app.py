"""Web app: builds the shared objects, the auth middleware and the routers of `app.web.routes`."""

import logging
import posixpath
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from starlette.responses import Response
from starlette.types import Scope

from app.config.settings import get_settings
from app.storage import SessionLocal, create_all
from app.web.auth import SessionSigner, verify_bearer_token
from app.web.routes import WebDeps
from app.web.routes.news import build_news_article_router, build_news_router
from app.web.routes.pages import build_pages_router
from app.web.routes.signals import build_signals_router
from app.web.routes.sources import build_sources_router
from app.web.routes.updates import build_updates_router
from app.web.routes.weekly import build_weekly_router
from app.web.service import UpdateRunService
from app.web.settings_store import UpdateSettingsStore
from app.web.source_intake import SourceIntakeService

_LOGGER = logging.getLogger(__name__)
_PUBLIC_READ_METHODS = frozenset({"GET", "HEAD"})
# The machine publish token only grants POST to these paths (least privilege).
_PUBLISH_API_PATHS = frozenset({"/api/news/digests", "/api/news/weekly-analytics"})
_STATIC_DIR = Path(__file__).resolve().parent / "static"


class _NoCacheStaticFiles(StaticFiles):
    """`/static/` assets with no-cache: browsers revalidate by ETag, so a deploy never mixes
    new HTML with old JS."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def create_app() -> FastAPI:
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
    source_intake: SourceIntakeService = SourceIntakeService(onboarding_session_local, settings)
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
            request.state.full_text_allowed = True
            return await call_next(request)

        path = request.url.path
        session_cookie = request.cookies.get(settings.auth_cookie_name)
        has_session = bool(session_cookie and signer and signer.verify(session_cookie) is not None)
        # Stored article text is internal: routes return it only to a session or the publish token.
        request.state.full_text_allowed = has_session or verify_bearer_token(
            request.headers.get("authorization"), settings.publish_api_token
        )
        is_auth_route = path in {"/login", "/api/auth/login", "/api/auth/logout"}
        # Public API paths are read-only; write methods on them require auth.
        is_public_news_api = request.method in _PUBLIC_READ_METHODS and path in {
            "/api/news/links",
            "/api/news/digests",
            "/api/news/daily-signals",
            "/api/news/stats/daily",
            "/api/news/weekly-analytics",
            "/api/news/weekly-analytics/reports",
            "/api/news/collection-status",
        }
        is_unprotected = (
            path
            in {
                "/health",
                "/",
                "/news-stats",
                "/weekly-ai-analytics",
                "/weekly-ai-analytics/reports",
            }
            or is_auth_route
            or is_public_news_api
        )
        # Normalized because StaticFiles resolves `..`, `//` and `.` itself;
        # lower() for case-insensitive file systems.
        static_path = posixpath.normpath(path).lower()
        is_protected_ui = path == "/admin" or static_path.startswith("/static/admin/")
        is_protected_api = path.startswith("/api/") and not is_public_news_api
        is_protected = is_protected_api or is_protected_ui

        if not is_protected or is_unprotected:
            return await call_next(request)

        if has_session:
            return await call_next(request)

        if (
            request.method == "POST"
            and path in _PUBLISH_API_PATHS
            and verify_bearer_token(
                request.headers.get("authorization"), settings.publish_api_token
            )
        ):
            return await call_next(request)

        if session_cookie:
            _LOGGER.info("session_expired")
        if is_protected_api:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return RedirectResponse(url="/login", status_code=303)

    deps = WebDeps(
        settings=settings,
        settings_store=settings_store,
        update_service=update_service,
        onboarding_engine=onboarding_engine,
        onboarding_session_local=onboarding_session_local,
        source_intake=source_intake,
        auth_enabled=auth_enabled,
        signer=signer,
        SessionLocal=SessionLocal,
        create_all=create_all,
    )
    api.mount("/static", _NoCacheStaticFiles(directory=_STATIC_DIR), name="static")
    # Order matters: `/api/news/{article_id}` comes after every fixed `/api/news/<name>` path.
    for router in (
        build_pages_router(deps),
        build_updates_router(deps),
        build_news_router(deps),
        build_signals_router(deps),
        build_weekly_router(deps),
        build_news_article_router(deps),
        build_sources_router(deps),
    ):
        api.include_router(router)
    return api


app = create_app()
