"""Web app: builds the shared objects, the auth middleware and the routers of `app.web.routes`."""

import logging
import posixpath
from collections.abc import Awaitable, Callable
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import sessionmaker
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import Scope

from app.config.settings import Settings, get_settings
from app.storage import SessionLocal, create_all
from app.storage.models_sql import Base
from app.usecases.sources.intake import SourceIntakeService
from app.web.auth import SessionSigner, verify_bearer_token
from app.web.routes import WebDeps
from app.web.routes.bulletin import build_bulletin_router
from app.web.routes.news import build_news_article_router, build_news_router
from app.web.routes.pages import build_pages_router
from app.web.routes.period import build_period_router
from app.web.routes.signals import build_signals_router
from app.web.routes.sources import build_sources_router
from app.web.routes.updates import build_updates_router
from app.web.routes.weekly import build_weekly_router
from app.web.service import UpdateRunService
from app.web.settings_store import UpdateSettingsStore

_LOGGER = logging.getLogger(__name__)
_PUBLIC_READ_METHODS = frozenset({"GET", "HEAD"})
# The machine publish token only grants POST to these paths (least privilege).
_PUBLISH_API_PATHS = frozenset({"/api/news/digests", "/api/news/weekly-analytics"})
# Open for every method: public pages and the auth routes.
_PUBLIC_PATHS = frozenset({
    "/health", "/", "/daily", "/news-stats", "/weekly", "/monthly", "/bulletin",
    "/login", "/api/auth/login", "/api/auth/logout",
})
# Public API paths are read-only; write methods on them require auth.
_PUBLIC_NEWS_API_PATHS = frozenset({
    "/api/news/links",
    "/api/news/digests",
    "/api/news/daily-signals",
    "/api/news/bulletin",
    "/api/news/period-signals",
    "/api/news/period-signals/index",
    "/api/news/stats/daily",
    "/api/news/weekly-analytics",
    "/api/news/weekly-analytics/reports",
    "/api/news/collection-status",
})
_STATIC_DIR = Path(__file__).resolve().parent / "static"


class _NoCacheStaticFiles(StaticFiles):
    """`/static/` assets with no-cache: browsers revalidate by ETag, so a deploy never mixes
    new HTML with old JS."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def _once(create: Callable[[], None], lock: Lock) -> Callable[[], None]:
    """Initialize until one call succeeds; see `src/app/web/pages.md`."""
    done = False

    def initialize() -> None:
        nonlocal done
        if done:  # after success, never wait on the lock held by the other initializer
            return
        with lock:
            if done:
                return
            create()
            done = True

    return initialize


def _requires_auth(method: str, path: str) -> bool:
    """With auth on: every `/api/` path, `/admin` and `/static/admin/`, minus the public ones."""
    if path in _PUBLIC_PATHS or (method in _PUBLIC_READ_METHODS
                                 and path in _PUBLIC_NEWS_API_PATHS):
        return False
    # Normalized because StaticFiles resolves `..`, `//` and `.` itself;
    # lower() for case-insensitive file systems.
    static_path = posixpath.normpath(path).lower()
    return path.startswith("/api/") or path == "/admin" or static_path.startswith("/static/admin/")


def _is_allowed(method: str, path: str, *, has_token: bool) -> bool:
    """Open without a session: public paths, and POST to a publish path with the token."""
    return not _requires_auth(method, path) or (
        has_token and method == "POST" and path in _PUBLISH_API_PATHS
    )


def _auth_middleware(
    settings: Settings, signer: SessionSigner | None
) -> Callable[[Request, RequestResponseEndpoint], Awaitable[Response]]:
    """The `http` middleware; `signer` is None when auth is off."""

    async def auth_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
        if signer is None:
            request.state.full_text_allowed = True
            return await call_next(request)

        session_cookie = request.cookies.get(settings.auth_cookie_name)
        has_session = bool(session_cookie and signer.verify(session_cookie) is not None)
        has_token = verify_bearer_token(
            request.headers.get("authorization"), settings.publish_api_token
        )
        # Stored article text is internal: routes return it only to a session or the publish token.
        request.state.full_text_allowed = has_session or has_token
        path = request.url.path
        if has_session or _is_allowed(request.method, path, has_token=has_token):
            return await call_next(request)

        if session_cookie:
            _LOGGER.info("session_expired")
        if path.startswith("/api/"):
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return RedirectResponse(url="/login", status_code=303)

    return auth_middleware


def _onboarding_engine(database_url: str) -> Engine:
    """Engine of the onboarding tables; creates the folder of a SQLite file database."""
    url = make_url(database_url)
    if url.drivername.startswith("sqlite") and url.database and url.database != ":memory:":
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url, future=True)


def _signer(settings: Settings) -> SessionSigner | None:
    if not settings.is_auth_enabled:
        return None
    return SessionSigner(secret=settings.auth_secret or "",
                         ttl_seconds=settings.auth_session_ttl_seconds)


def create_app() -> FastAPI:
    settings = get_settings()
    onboarding_engine = _onboarding_engine(settings.database_url)
    onboarding_session_local = sessionmaker(
        bind=onboarding_engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )
    signer = _signer(settings)

    api = FastAPI(title="AI News Collector Web")
    api.middleware("http")(_auth_middleware(settings, signer))

    table_lock = Lock()
    deps = WebDeps(
        settings=settings,
        settings_store=UpdateSettingsStore(Path("data") / "web_update_settings.json"),
        update_service=UpdateRunService(),
        onboarding_engine=onboarding_engine,
        onboarding_session_local=onboarding_session_local,
        source_intake=SourceIntakeService(onboarding_session_local, settings),
        auth_enabled=settings.is_auth_enabled,
        signer=signer,
        SessionLocal=SessionLocal,
        create_all=_once(create_all, table_lock),
        create_onboarding_tables=_once(
            lambda: Base.metadata.create_all(bind=onboarding_engine), table_lock
        ),
    )
    api.mount("/static", _NoCacheStaticFiles(directory=_STATIC_DIR), name="static")
    # Order matters: `/api/news/{article_id}` comes after every fixed `/api/news/<name>` path.
    for router in (
        build_pages_router(deps),
        build_updates_router(deps),
        build_news_router(deps),
        build_signals_router(deps),
        build_bulletin_router(deps),
        build_period_router(deps),
        build_weekly_router(deps),
        build_news_article_router(deps),
        build_sources_router(deps),
    ):
        api.include_router(router)
    return api


app = create_app()
