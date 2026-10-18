import re
from importlib import import_module

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import Settings, get_settings
from app.storage.models_sql import Base
from app.web.app import create_app

_PUBLISH_TOKEN = "publish-token-0123456789abcdef0123"
_PUBLISH_PATHS = ("/api/news/digests", "/api/news/weekly-analytics")
_AUTH_ROUTES = {"/api/auth/login", "/api/auth/logout"}


def _build_client(
    monkeypatch,
    tmp_path,
    *,
    auth_enabled: bool = True,
    publish_token: str | None = _PUBLISH_TOKEN,
) -> TestClient:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path}/public-write-auth.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    for name in (
        "AINEWS_AUTH_ENABLED",
        "AINEWS_AUTH_USERNAME",
        "AINEWS_AUTH_PASSWORD_HASH",
        "AINEWS_AUTH_SECRET",
        "AINEWS_PUBLISH_API_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    if auth_enabled:
        password_hash = import_module("app.web.auth").hash_password("s3cret-pass")
        monkeypatch.setenv("AINEWS_AUTH_USERNAME", "operator")
        monkeypatch.setenv("AINEWS_AUTH_PASSWORD_HASH", password_hash)
        monkeypatch.setenv("AINEWS_AUTH_SECRET", "0123456789abcdef0123456789abcdef")
    if publish_token is not None:
        monkeypatch.setenv("AINEWS_PUBLISH_API_TOKEN", publish_token)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: Base.metadata.create_all(bind=engine))
    monkeypatch.setattr(web_app_module, "SessionLocal", session_local)
    return TestClient(create_app())


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login", json={"username": "operator", "password": "s3cret-pass"}
    )
    assert response.status_code == 200


@pytest.mark.parametrize("path", _PUBLISH_PATHS)
def test_unauthenticated_post_to_public_path_returns_401(monkeypatch, tmp_path, path) -> None:
    client = _build_client(monkeypatch, tmp_path)

    response = client.post(path, json={})

    assert response.status_code == 401


@pytest.mark.parametrize(
    "path",
    [
        "/api/news/digests?date=2026-10-17",
        "/api/news/weekly-analytics?date=2026-10-12",
        "/api/news/weekly-analytics/reports",
    ],
)
def test_public_get_stays_open_without_auth(monkeypatch, tmp_path, path) -> None:
    client = _build_client(monkeypatch, tmp_path)

    assert client.get(path).status_code == 200


@pytest.mark.parametrize("path", _PUBLISH_PATHS)
def test_post_with_session_cookie_passes_auth(monkeypatch, tmp_path, path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    _login(client)

    # 422 means the request passed auth and reached payload validation.
    assert client.post(path, json={}).status_code == 422


@pytest.mark.parametrize("path", _PUBLISH_PATHS)
def test_post_with_valid_bearer_token_passes_auth(monkeypatch, tmp_path, path) -> None:
    client = _build_client(monkeypatch, tmp_path)

    response = client.post(
        path, json={}, headers={"Authorization": f"Bearer {_PUBLISH_TOKEN}"}
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "header",
    [
        f"Bearer {_PUBLISH_TOKEN}x",
        "Bearer short",
        "Bearer ",
        f"Basic {_PUBLISH_TOKEN}",
        _PUBLISH_TOKEN,
    ],
)
@pytest.mark.parametrize("path", _PUBLISH_PATHS)
def test_post_with_wrong_token_returns_401(monkeypatch, tmp_path, path, header) -> None:
    client = _build_client(monkeypatch, tmp_path)

    assert client.post(path, json={}, headers={"Authorization": header}).status_code == 401


def test_bearer_token_is_not_accepted_when_not_configured(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path, publish_token=None)

    response = client.post(
        "/api/news/digests", json={}, headers={"Authorization": "Bearer "}
    )

    assert response.status_code == 401


def test_publish_token_does_not_grant_other_protected_api(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_PUBLISH_TOKEN}"}

    assert client.post("/api/update/run", headers=headers).status_code == 401
    assert client.get("/api/update/settings", headers=headers).status_code == 401


def _route_url(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


def test_every_non_get_api_route_requires_auth(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    app = client.app
    assert isinstance(app, FastAPI)
    checked: list[tuple[str, str]] = []

    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/"):
            continue
        if route.path in _AUTH_ROUTES:
            continue
        for method in sorted((route.methods or set()) - {"GET", "HEAD"}):
            response = client.request(method, _route_url(route.path), json={})
            assert response.status_code == 401, (method, route.path, response.status_code)
            checked.append((method, route.path))

    assert ("POST", "/api/news/digests") in checked
    assert ("POST", "/api/news/weekly-analytics") in checked


@pytest.mark.parametrize("path", _PUBLISH_PATHS)
def test_auth_disabled_keeps_post_open(monkeypatch, tmp_path, path) -> None:
    client = _build_client(monkeypatch, tmp_path, auth_enabled=False, publish_token=None)

    assert client.post(path, json={}).status_code == 422


def test_settings_reject_short_publish_token() -> None:
    with pytest.raises(ValidationError, match="AINEWS_PUBLISH_API_TOKEN"):
        Settings(_env_file=None, publish_api_token="too-short")


def test_settings_treat_blank_publish_token_as_unset() -> None:
    settings = Settings(_env_file=None, publish_api_token="   ")

    assert settings.publish_api_token is None
