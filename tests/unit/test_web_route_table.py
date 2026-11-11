"""Pins the web route table, parameters, thin handlers and auth coverage so moving routes between
modules changes none of them."""

import ast
import inspect
import re
from importlib import import_module
from typing import Any, cast

import pytest
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
    ('GET', '/daily', 'daily', 'str', 'HTMLResponse', None, False),
    ('GET', '/bulletin', 'bulletin_page', None, 'HTMLResponse', None, False),
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
    ('GET', '/api/news/bulletin', 'get_bulletin', 'dict[str, typing.Any]', 'JSONResponse', None,
     False),
    ('GET', '/weekly', 'weekly_page', None, 'HTMLResponse', None, False),
    ('GET', '/monthly', 'monthly_page', None, 'HTMLResponse', None, False),
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
    ("GET", "/daily"),
    ("GET", "/bulletin"),
    ("GET", "/weekly-ai-analytics"),
    ("GET", "/weekly-ai-analytics/reports"),
    ("GET", "/news-stats"),
    ("GET", "/weekly"),
    ("GET", "/monthly"),
    ("GET", "/login"),
    ("GET", "/health"),
    ("GET", "/api/news/collection-status"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/news/links"),
    ("GET", "/api/news/digests"),
    ("GET", "/api/news/daily-signals"),
    ("GET", "/api/news/bulletin"),
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


# Query and path parameters of the news, weekly and source onboarding routers, from OpenAPI:
# (method, path, name, required, default, (minimum, maximum)).
_ROUTE_PARAMS: list[tuple[object, ...]] = [
    ('GET', '/api/news', 'hours', False, 24, (1, 720)),
    ('GET', '/api/news', 'limit', False, 30, (1, 200)),
    ('GET', '/api/news', 'min_ai_relevance', False, 0.2, (0.0, 1.0)),
    ('GET', '/api/news', 'query', False, None, (None, None)),
    ('GET', '/api/news', 'days', False, 7, (1, 365)),
    ('GET', '/api/news', 'sort', False, 'rank', (None, None)),
    ('GET', '/api/news', 'category', False, None, (None, None)),
    ('GET', '/api/news', 'date_from', False, None, (None, None)),
    ('GET', '/api/news', 'date_to', False, None, (None, None)),
    ('GET', '/api/news/export', 'hours', False, 24, (1, 720)),
    ('GET', '/api/news/export', 'limit', False, 30, (1, 200)),
    ('GET', '/api/news/export', 'min_ai_relevance', False, 0.2, (0.0, 1.0)),
    ('GET', '/api/news/export', 'query', False, None, (None, None)),
    ('GET', '/api/news/export', 'days', False, 7, (1, 365)),
    ('GET', '/api/news/export', 'sort', False, 'rank', (None, None)),
    ('GET', '/api/news/export', 'category', False, None, (None, None)),
    ('GET', '/api/news/export', 'include_content', False, False, (None, None)),
    ('GET', '/api/news/export', 'date_from', False, None, (None, None)),
    ('GET', '/api/news/export', 'date_to', False, None, (None, None)),
    ('GET', '/api/news/links', 'date', True, None, (None, None)),
    ('GET', '/api/news/links', 'limit', False, 30, (1, 200)),
    ('GET', '/api/news/links', 'offset', False, 0, (0, None)),
    ('GET', '/api/news/links', 'min_ai_relevance', False, 0.2, (0.0, 1.0)),
    ('GET', '/api/news/links', 'include_content', False, False, (None, None)),
    ('GET', '/api/news/weekly-analytics', 'date', False, None, (None, None)),
    ('GET', '/api/news/weekly-analytics/reports', 'limit', False, 52, (1, 260)),
    ('GET', '/api/news/weekly-analytics/freshness', 'date', False, None, (None, None)),
    ('GET', '/api/news/{article_id}', 'article_id', True, None, (None, None)),
    ('POST', '/api/source-onboarding/batches/{batch_id}/check', 'batch_id', True, None, (1, None)),
    ('POST', '/api/source-onboarding/batches/{batch_id}/approve-ready', 'batch_id',
     True, None, (1, None)),
    ('GET', '/api/source-onboarding/overlaps', 'batch_id', False, None, (1, None)),
    ('GET', '/api/source-onboarding/overlaps', 'candidate_id', False, [], (None, None)),
    ('GET', '/api/source-onboarding/candidates', 'batch_id', False, None, (1, None)),
    ('GET', '/api/source-onboarding/candidates', 'status', False, None, (None, None)),
    ('GET', '/api/source-onboarding/candidates', 'validation_status', False, None, (None, None)),
    ('GET', '/api/source-onboarding/batches/{batch_id}/summary', 'batch_id',
     True, None, (None, None)),
    ('POST', '/api/source-onboarding/candidates/{candidate_id}/approve', 'candidate_id',
     True, None, (1, None)),
    ('POST', '/api/source-onboarding/candidates/{candidate_id}/disable', 'candidate_id',
     True, None, (1, None)),
    ('POST', '/api/source-onboarding/candidates/{candidate_id}/reject', 'candidate_id',
     True, None, (1, None)),
    ('POST', '/api/source-onboarding/candidates/{candidate_id}/mark-duplicate', 'candidate_id',
     True, None, (1, None)),
    ('PATCH', '/api/source-onboarding/candidates/{candidate_id}', 'candidate_id',
     True, None, (1, None)),
]

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
    """Stopped by the auth middleware; the login's own 401 for bad credentials is not a block."""
    location: str | None = response.headers.get("location")
    if response.status_code == 401:
        return bool(response.json() == {"detail": "Unauthorized"})
    return response.status_code == 303 and location == "/login"


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


def test_auth_rule_covers_paths_outside_the_route_table() -> None:
    requires_auth = import_module("app.web.app")._requires_auth
    assert not requires_auth("HEAD", "/api/news/links")
    assert requires_auth("POST", "/api/news/links")
    assert requires_auth("GET", "/api/unknown")
    assert not requires_auth("POST", "/api/auth/logout")
    assert not requires_auth("GET", "/unknown-page")
    assert requires_auth("GET", "/static//Admin/../admin/app.js")
    assert not requires_auth("GET", "/static/app.css")


def test_publish_token_opens_only_post_to_publish_paths() -> None:
    is_allowed = import_module("app.web.app")._is_allowed
    assert is_allowed("POST", "/api/news/digests", has_token=True)
    assert not is_allowed("POST", "/api/news/digests", has_token=False)
    assert not is_allowed("PUT", "/api/news/weekly-analytics", has_token=True)
    assert not is_allowed("POST", "/api/update/run", has_token=True)
    assert is_allowed("GET", "/api/news/digests", has_token=False)


def _param_rows(app, paths: set[str]) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for path, operations in app.openapi()["paths"].items():
        if path not in paths:
            continue
        for method, operation in operations.items():
            for param in operation.get("parameters", []):
                schema = param["schema"]
                bounds = schema.get("anyOf", [schema])[0]
                rows.append((method.upper(), path, param["name"], param.get("required", False),
                             schema.get("default"),
                             (bounds.get("minimum"), bounds.get("maximum"))))
    return rows


def test_route_parameters_are_pinned(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    paths = {str(row[1]) for row in _ROUTE_PARAMS}
    assert _param_rows(client.app, paths) == _ROUTE_PARAMS


@pytest.mark.parametrize("module,factory", [
    ("pages", "build_pages_router"),
    ("sources", "build_sources_router"),
    ("news", "build_news_router"),
    ("news", "build_news_article_router"),
    ("weekly", "build_weekly_router"),
])
def test_router_handlers_only_delegate(module: str, factory: str) -> None:
    builder = getattr(import_module(f"app.web.routes.{module}"), factory)
    tree = ast.parse(inspect.getsource(builder))
    handlers = [node for node in cast(ast.FunctionDef, tree.body[0]).body
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)]
    assert handlers
    for handler in handlers:
        assert len(handler.body) == 1, handler.name
        statement = handler.body[0]
        assert isinstance(statement, ast.Return), handler.name
        assert isinstance(statement.value, ast.Call | ast.Await), handler.name
