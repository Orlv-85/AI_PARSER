"""Pins the web route table and auth coverage so moving routes between modules changes neither."""

import re
from importlib import import_module
from typing import Any

from fastapi.datastructures import DefaultPlaceholder
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.storage.models_sql import Base
from app.web.app import create_app

_PUBLISH_TOKEN = "publish-token-0123456789abcdef0123"

# (methods, path, endpoint name, response model, response class, status code,
#  response_model_exclude_unset) in registration order.
_ROUTE_TABLE = [
    ('GET', '/', 'index', 'str', 'HTMLResponse', None, False),
    ('GET', '/weekly-ai-analytics', 'legacy_weekly_redirect', None, 'JSONResponse', None, False),
    ('GET', '/weekly-ai-analytics/reports', 'legacy_weekly_redirect', None, 'JSONResponse', None,
     False),
    ('GET', '/news-stats', 'news_stats_page', 'str', 'HTMLResponse', None, False),
    ('GET', '/admin', 'admin_index', 'str', 'HTMLResponse', None, False),
    ('GET', '/login', 'login_page', None, 'HTMLResponse', None, False),
    ('GET', '/health', 'health', 'dict[str, str]', 'JSONResponse', None, False),
    ('GET', '/api/news/collection-status', 'get_collection_status_api',
     'NewsCollectionStatusResponse', 'JSONResponse', None, False),
    ('POST', '/api/auth/login', 'login', None, 'JSONResponse', None, False),
    ('POST', '/api/auth/logout', 'logout', None, 'JSONResponse', None, False),
    ('GET', '/api/update/settings', 'get_update_settings', 'WebUpdateSettings', 'JSONResponse',
     None, False),
    ('PUT', '/api/update/settings', 'put_update_settings', 'WebUpdateSettings', 'JSONResponse',
     None, False),
    ('POST', '/api/update/run', 'run_update', 'UpdateStatus', 'JSONResponse', None, False),
    ('GET', '/api/update/status', 'get_update_status', 'UpdateStatus', 'JSONResponse', None, False),
    ('GET', '/api/news', 'list_news', 'list[app.web.models.NewsItem]', 'JSONResponse', None, True),
    ('GET', '/api/news/export', 'export_news', None, 'JSONResponse', None, False),
    ('GET', '/api/news/links', 'list_news_links', 'list[app.web.models.DigestLinkFeedItem]',
     'JSONResponse', None, True),
    ('POST', '/api/news/digests', 'save_news_digest', 'NewsDigestResponse', 'JSONResponse', None,
     False),
    ('GET', '/api/news/digests', 'get_news_digest', 'NewsDigestResponse', 'JSONResponse', None,
     False),
    ('GET', '/api/news/daily-signals', 'get_daily_signals', 'DailySignalsResponse', 'JSONResponse',
     None, False),
    ('GET', '/api/news/stats/daily', 'get_news_daily_stats', 'NewsDailyStatsResponse',
     'JSONResponse', None, False),
    ('GET', '/weekly', 'weekly_page', None, 'HTMLResponse', None, False),
    ('GET', '/api/news/period-signals', 'get_period_signals', 'PeriodSignalsResponse',
     'JSONResponse', None, False),
    ('GET', '/api/news/period-signals/index', 'get_period_signals_index',
     'PeriodSignalsIndexResponse', 'JSONResponse', None, False),
    ('GET', '/api/news/weekly-analytics', 'get_weekly_ai_analytics', 'WeeklyAnalyticsResponse',
     'JSONResponse', None, True),
    ('POST', '/api/news/weekly-analytics', 'save_weekly_ai_analytics', 'WeeklyAnalyticsResponse',
     'JSONResponse', None, True),
    ('GET', '/api/news/weekly-analytics/reports', 'list_weekly_ai_analytics_reports',
     'WeeklyAnalyticsReportListResponse', 'JSONResponse', None, False),
    ('GET', '/api/news/weekly-analytics/freshness', 'get_weekly_ai_analytics_freshness',
     'WeeklyAnalyticsFreshnessResponse', 'JSONResponse', None, False),
    ('GET', '/api/news/{article_id}', 'get_news_article', 'NewsArticleDetail', 'JSONResponse', None,
     False),
    ('POST', '/api/source-onboarding/import', 'import_source_onboarding_batch', None,
     'JSONResponse', None, False),
    ('GET', '/api/source-onboarding/latest', 'latest_source_batch', 'dict[str, typing.Any]',
     'JSONResponse', None, False),
    ('GET', '/api/source-onboarding/check-status', 'source_check_status', 'dict[str, typing.Any]',
     'JSONResponse', None, False),
    ('POST', '/api/source-onboarding/batches/{batch_id}/check', 'check_source_batch',
     'dict[str, typing.Any]', 'JSONResponse', 202, False),
    ('POST', '/api/source-onboarding/batches/{batch_id}/approve-ready', 'approve_ready_sources',
     'dict[str, typing.Any]', 'JSONResponse', None, False),
    ('POST', '/api/source-onboarding/validate', 'validate_source_onboarding_batch', None,
     'JSONResponse', None, False),
    ('GET', '/api/source-onboarding/overlaps', 'get_source_onboarding_overlaps', None,
     'JSONResponse', None, False),
    ('GET', '/api/source-onboarding/candidates', 'list_source_onboarding_candidates',
     'SourceOnboardingCandidateListResponse', 'JSONResponse', None, False),
    ('GET', '/api/source-onboarding/batches/{batch_id}/summary',
     'get_source_onboarding_batch_summary', 'SourceOnboardingBatchSummary', 'JSONResponse', None,
     False),
    ('POST', '/api/source-onboarding/candidates/{candidate_id}/approve',
     'approve_source_onboarding_candidate', 'SourceOnboardingApproveResponse', 'JSONResponse', None,
     False),
    ('POST', '/api/source-onboarding/candidates/{candidate_id}/disable',
     'disable_source_onboarding_candidate', 'SourceOnboardingDisableResponse', 'JSONResponse', None,
     False),
    ('POST', '/api/source-onboarding/candidates/{candidate_id}/reject',
     'reject_source_onboarding_candidate', 'SourceOnboardingRejectResponse', 'JSONResponse', None,
     False),
    ('POST', '/api/source-onboarding/candidates/{candidate_id}/mark-duplicate',
     'mark_source_onboarding_candidate_duplicate', 'SourceOnboardingDuplicateResponse',
     'JSONResponse', None, False),
    ('PATCH', '/api/source-onboarding/candidates/{candidate_id}',
     'edit_source_onboarding_candidate', 'SourceOnboardingEditResponse', 'JSONResponse', None,
     False),
]

# Routes the auth middleware lets through without a session (auth on).
_OPEN_ROUTES = {
    ("GET", "/"),
    ("GET", "/weekly-ai-analytics"),
    ("GET", "/weekly-ai-analytics/reports"),
    ("GET", "/news-stats"),
    ("GET", "/weekly"),
    ("GET", "/login"),
    ("GET", "/health"),
    ("GET", "/api/news/collection-status"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/news/links"),
    ("GET", "/api/news/digests"),
    ("GET", "/api/news/daily-signals"),
    ("GET", "/api/news/period-signals"),
    ("GET", "/api/news/period-signals/index"),
    ("GET", "/api/news/stats/daily"),
    ("GET", "/api/news/weekly-analytics"),
    ("GET", "/api/news/weekly-analytics/reports"),
}

# Routes the publish bearer token opens (auth on, no session).
_PUBLISH_ROUTES = {
    ("POST", "/api/news/digests"),
    ("POST", "/api/news/weekly-analytics"),
}


def _type_name(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, DefaultPlaceholder):
        value = value.value
    text = str(value)
    if "[" in text:  # generic aliases such as list[NewsItem] or dict[str, Any]
        return text
    return getattr(value, "__name__", text)


def _route_rows(app) -> list[tuple[object, ...]]:
    return [
        (",".join(sorted(route.methods or ())), route.path, route.name,
         _type_name(route.response_model), _type_name(route.response_class),
         route.status_code, route.response_model_exclude_unset)
        # Included routers are resolved lazily (FastAPI 0.143); contexts give the effective routes.
        for route in iter_route_contexts(app.routes)
        if isinstance(route.original_route, APIRoute)
    ]


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.chdir(tmp_path)
    for name in ("AINEWS_AUTH_ENABLED", "AINEWS_PUBLISH_API_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AINEWS_AUTH_USERNAME", "operator")
    monkeypatch.setenv("AINEWS_AUTH_PASSWORD_HASH",
                       import_module("app.web.auth").hash_password("s3cret-pass"))
    monkeypatch.setenv("AINEWS_AUTH_SECRET", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("AINEWS_PUBLISH_API_TOKEN", _PUBLISH_TOKEN)
    get_settings.cache_clear()
    engine = create_engine(f"sqlite:///{tmp_path}/route-table.db", future=True)
    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all",
                        lambda: Base.metadata.create_all(bind=engine))
    monkeypatch.setattr(web_app_module, "SessionLocal", sessionmaker(bind=engine, future=True))
    client = TestClient(create_app(), raise_server_exceptions=False)
    get_settings.cache_clear()
    return client


def _is_blocked(response: Any) -> bool:
    location: str | None = response.headers.get("location")
    return response.status_code == 401 or (response.status_code == 303 and location == "/login")


def _concrete(path: str) -> str:
    return re.sub(r"\{[a-z_]+\}", "1", path)


def test_route_table_order_names_and_models_are_pinned(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    assert _route_rows(client.app) == _ROUTE_TABLE


def test_auth_middleware_coverage_is_pinned(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    open_routes: set[tuple[str, str]] = set()
    publish_routes: set[tuple[str, str]] = set()
    for method, path, *_rest in _ROUTE_TABLE:
        url = _concrete(path)
        if not _is_blocked(client.request(method, url, follow_redirects=False)):
            open_routes.add((method, path))
        bearer = client.request(method, url, follow_redirects=False,
                                headers={"Authorization": f"Bearer {_PUBLISH_TOKEN}"})
        if (method, path) not in open_routes and not _is_blocked(bearer):
            publish_routes.add((method, path))
    assert open_routes == _OPEN_ROUTES
    assert publish_routes == _PUBLISH_ROUTES
