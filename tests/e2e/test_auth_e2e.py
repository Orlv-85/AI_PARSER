from datetime import UTC, datetime, timedelta
from importlib import import_module
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.storage.models_sql import Base
from app.web.app import create_app


def test_e2e_login_protected_logout_denied(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    auth_module = import_module("app.web.auth")
    password_hash = auth_module.hash_password("e2e-pass")

    monkeypatch.setenv("AINEWS_AUTH_USERNAME", "operator")
    monkeypatch.setenv("AINEWS_AUTH_PASSWORD_HASH", password_hash)
    monkeypatch.setenv("AINEWS_AUTH_SECRET", "fedcba9876543210fedcba9876543210")
    monkeypatch.setenv("AINEWS_AUTH_SESSION_TTL_SECONDS", "60")

    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def list_for_view(self, **_kwargs):
            row = SimpleNamespace(
                title="E2E Auth Item",
                published_at=datetime(2026, 2, 21, 15, 0, tzinfo=UTC),
                rank_score=0.8,
                url_canonical="https://example.com/e2e-auth",
                source_id=1,
            )
            return [(row, "e2e-auth", "E2E Auth")]

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "ArticleRepo", _ArticleRepo)

    client = TestClient(create_app())

    denied = client.get("/api/news")
    assert denied.status_code == 401

    login = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "e2e-pass"},
        follow_redirects=False,
    )
    assert login.status_code in {200, 204, 302, 303}
    assert any(name for name in client.cookies.keys())

    allowed = client.get("/api/news")
    assert allowed.status_code == 200

    logout = client.post("/api/auth/logout", follow_redirects=False)
    assert logout.status_code in {200, 204, 302, 303}

    denied_again = client.get("/api/news")
    assert denied_again.status_code == 401


def test_e2e_second_login_immediately_invalidates_previous_session_token(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    auth_module = import_module("app.web.auth")
    password_hash = auth_module.hash_password("e2e-pass")
    original_sign = auth_module.SessionSigner.sign
    issued_count = {"value": 0}
    base_issued_at = datetime.now(tz=UTC).replace(microsecond=0)

    def _deterministic_sign(self, *, subject: str, now=None):
        if now is None:
            now = base_issued_at + timedelta(seconds=issued_count["value"])
            issued_count["value"] += 1
        return original_sign(self, subject=subject, now=now)

    monkeypatch.setattr(auth_module.SessionSigner, "sign", _deterministic_sign)

    monkeypatch.setenv("AINEWS_AUTH_USERNAME", "operator")
    monkeypatch.setenv("AINEWS_AUTH_PASSWORD_HASH", password_hash)
    monkeypatch.setenv("AINEWS_AUTH_SECRET", "fedcba9876543210fedcba9876543210")
    monkeypatch.setenv("AINEWS_AUTH_SESSION_TTL_SECONDS", "60")

    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def list_for_view(self, **_kwargs):
            row = SimpleNamespace(
                title="E2E Rotation Item",
                published_at=datetime(2026, 2, 21, 15, 10, tzinfo=UTC),
                rank_score=0.75,
                url_canonical="https://example.com/e2e-rotation",
                source_id=3,
            )
            return [(row, "e2e-rotation", "E2E Rotation")]

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "ArticleRepo", _ArticleRepo)

    client = TestClient(create_app())

    first_login = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "e2e-pass"},
    )
    assert first_login.status_code in {200, 204, 302, 303}
    first_token = client.cookies.get("ainews_session")
    assert first_token is not None

    second_login = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "e2e-pass"},
    )
    assert second_login.status_code in {200, 204, 302, 303}
    second_token = client.cookies.get("ainews_session")
    assert second_token is not None
    assert second_token != first_token

    client.cookies.set("ainews_session", first_token)
    old_token_response = client.get("/api/news")
    assert old_token_response.status_code == 401

    client.cookies.set("ainews_session", second_token)
    new_token_response = client.get("/api/news")
    assert new_token_response.status_code == 200


def test_e2e_auth_disabled_default_routes_are_open(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    monkeypatch.setenv("AINEWS_AUTH_ENABLED", "false")
    monkeypatch.delenv("AINEWS_AUTH_USERNAME", raising=False)
    monkeypatch.delenv("AINEWS_AUTH_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("AINEWS_AUTH_SECRET", raising=False)

    engine = create_engine(f"sqlite:///{tmp_path}/auth-disabled-open-routes.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def list_for_view(self, **_kwargs):
            row = SimpleNamespace(
                title="Open Access Item",
                published_at=datetime(2026, 2, 21, 16, 0, tzinfo=UTC),
                rank_score=0.7,
                url_canonical="https://example.com/open-access",
                source_id=2,
            )
            return [(row, "open-auth", "Open Auth")]

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: Base.metadata.create_all(bind=engine))
    monkeypatch.setattr(web_app_module, "SessionLocal", session_local)
    monkeypatch.setattr(web_app_module, "ArticleRepo", _ArticleRepo)

    client = TestClient(create_app())

    page = client.get("/")
    assert page.status_code == 200

    api_news = client.get("/api/news")
    assert api_news.status_code == 200


def test_e2e_login_grants_access_to_admin_shell(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    auth_module = import_module("app.web.auth")
    password_hash = auth_module.hash_password("e2e-pass")

    monkeypatch.setenv("AINEWS_AUTH_USERNAME", "operator")
    monkeypatch.setenv("AINEWS_AUTH_PASSWORD_HASH", password_hash)
    monkeypatch.setenv("AINEWS_AUTH_SECRET", "fedcba9876543210fedcba9876543210")
    monkeypatch.setenv("AINEWS_AUTH_SESSION_TTL_SECONDS", "60")

    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def list_for_view(self, **_kwargs):
            row = SimpleNamespace(
                title="Admin Shell Item",
                published_at=datetime(2026, 2, 21, 17, 0, tzinfo=UTC),
                rank_score=0.81,
                url_canonical="https://example.com/admin-shell",
                source_id=4,
            )
            return [(row, "admin-shell", "Admin Shell")]

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "ArticleRepo", _ArticleRepo)

    client = TestClient(create_app())

    denied = client.get("/admin", follow_redirects=False)
    assert denied.status_code in {302, 303, 307, 308}
    assert denied.headers["location"].endswith("/login")

    login = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "e2e-pass"},
        follow_redirects=False,
    )
    assert login.status_code in {200, 204, 302, 303}

    allowed = client.get("/admin")
    assert allowed.status_code == 200
    assert "Update Sources" in allowed.text


def test_e2e_public_digest_apis_stay_open_while_admin_apis_require_auth(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    auth_module = import_module("app.web.auth")
    password_hash = auth_module.hash_password("e2e-pass")

    monkeypatch.setenv("AINEWS_AUTH_USERNAME", "operator")
    monkeypatch.setenv("AINEWS_AUTH_PASSWORD_HASH", password_hash)
    monkeypatch.setenv("AINEWS_AUTH_SECRET", "fedcba9876543210fedcba9876543210")
    monkeypatch.setenv("AINEWS_AUTH_SESSION_TTL_SECONDS", "60")

    engine = create_engine(f"sqlite:///{tmp_path}/phase3-auth-boundary.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _create_all_local() -> None:
        Base.metadata.create_all(bind=engine)

    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def list_for_agent(self, **_kwargs):
            row = SimpleNamespace(
                id=55,
                title="Public Feed Item",
                published_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
                url="https://example.com/public-feed",
                url_canonical="https://example.com/public-feed",
                source_id=8,
            )
            return [(row, "public-feed", "Public Feed")]

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", _create_all_local)
    monkeypatch.setattr(web_app_module, "SessionLocal", session_local)
    monkeypatch.setattr(web_app_module, "ArticleRepo", _ArticleRepo)

    client = TestClient(create_app())

    public_digest = client.get("/api/news/digests?date=2026-03-01")
    public_links = client.get("/api/news/links?date=2026-03-01")
    protected_update = client.get("/api/update/settings")

    assert public_digest.status_code == 200
    assert public_digest.json() == {"report_date": "2026-03-01", "groups": []}
    assert public_links.status_code == 200
    assert public_links.json()[0]["article_id"] == 55
    assert protected_update.status_code == 401
