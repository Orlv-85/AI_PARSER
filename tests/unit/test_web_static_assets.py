import asyncio
import re
from importlib import import_module

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.storage.models_sql import Base
from app.web.app import create_app

# Exact asset tags of each page, in order; a later edit that drops or renames one fails here.
PAGE_ASSETS = {
    "/": ["/static/css/digest.css", "/static/js/digest.js"],
    "/admin": [
        "/static/admin/admin.css",
        "/static/admin/core.js",
        "/static/admin/updates.js",
        "/static/admin/news.js",
        "/static/admin/sources.js",
    ],
    "/weekly": ["/static/css/digest.css", "/static/css/period.css"],
    "/news-stats": ["/static/css/news_stats.css", "/static/js/news_stats.js"],
    "/login": ["/static/css/login.css", "/static/js/login.js"],
}
_ASSET_TAG = re.compile(r'<(?:script src|link rel="stylesheet" href)="([^"]+)"')


def _client(monkeypatch, tmp_path, *, auth: bool = False) -> TestClient:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    engine = create_engine(f"sqlite:///{tmp_path}/static-assets.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    if auth:
        password_hash = import_module("app.web.auth").hash_password("s3cret-pass")
        monkeypatch.setenv("AINEWS_AUTH_USERNAME", "operator")
        monkeypatch.setenv("AINEWS_AUTH_PASSWORD_HASH", password_hash)
        monkeypatch.setenv("AINEWS_AUTH_SECRET", "0123456789abcdef0123456789abcdef")
    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: Base.metadata.create_all(bind=engine))
    monkeypatch.setattr(web_app_module, "SessionLocal", session_local)
    return TestClient(create_app())


@pytest.mark.parametrize("page", PAGE_ASSETS)
def test_page_references_exactly_its_static_assets(monkeypatch, tmp_path, page) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.get(page)

    assert response.status_code == 200
    assert _ASSET_TAG.findall(response.text) == PAGE_ASSETS[page]
    assert "<style>" not in response.text


@pytest.mark.parametrize("path", [path for paths in PAGE_ASSETS.values() for path in paths])
def test_static_asset_is_served_with_type_and_no_cache(monkeypatch, tmp_path, path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.get(path)

    assert response.status_code == 200
    expected_type = "text/css" if path.endswith(".css") else "javascript"
    assert expected_type in response.headers["content-type"]
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers.get("etag")
    assert response.text.strip()


def test_digest_placeholders_stay_inline_before_its_script(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    page = client.get("/?date=2026-02-27").text
    script = client.get("/static/js/digest.js").text

    assert 'const initialDigestUrl = "?date=2026-02-27";' in page
    assert page.index("const defaultReportDate") < page.index('src="/static/js/digest.js"')
    assert not re.search(r"__[A-Z_]+__", script)
    assert "initialDigestUrl" in script and "defaultReportDate" in script


def test_admin_assets_need_a_session_like_admin(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path, auth=True)

    for path in ("/admin", "/static/admin/core.js", "/static/admin/admin.css"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303, path
        assert response.headers["location"] == "/login"

    for path in ("/static/css/digest.css", "/static/js/login.js", "/static/js/news_stats.js"):
        assert client.get(path).status_code == 200, path

    login = client.post("/api/auth/login", json={"username": "operator", "password": "s3cret-pass"})
    assert login.status_code == 200
    response = client.get("/static/admin/core.js")
    assert response.status_code == 200
    assert "function showPage(name)" in response.text


@pytest.mark.parametrize(
    "path",
    [
        "/static/css/../admin/core.js",
        "/static//admin/core.js",
        "/static/./admin/core.js",
        "/static/ADMIN/core.js",
    ],
)
def test_admin_assets_check_uses_normalized_path(monkeypatch, tmp_path, path) -> None:
    app = _client(monkeypatch, tmp_path, auth=True).app
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(b"host", b"testserver")],
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 1),
        "root_path": "",
        "http_version": "1.1",
    }
    asyncio.run(app(scope, receive, send))

    assert sent[0]["status"] == 303
    assert (b"location", b"/login") in sent[0]["headers"]
