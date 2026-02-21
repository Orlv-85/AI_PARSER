import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from importlib import import_module
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config.settings import Settings, get_settings
from app.web.app import create_app


def _build_authenticated_client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    auth_module = import_module("app.web.auth")
    password_hash = auth_module.hash_password("s3cret-pass")

    monkeypatch.setenv("AINEWS_AUTH_USERNAME", "operator")
    monkeypatch.setenv("AINEWS_AUTH_PASSWORD_HASH", password_hash)
    monkeypatch.setenv("AINEWS_AUTH_SECRET", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("AINEWS_AUTH_SESSION_TTL_SECONDS", "60")

    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def list_for_view(self, **_kwargs):
            row = SimpleNamespace(
                title="Auth Test News",
                published_at=datetime(2026, 2, 21, 12, 0, tzinfo=UTC),
                rank_score=0.9,
                url_canonical="https://example.com/auth-test",
                source_id=1,
            )
            return [(row, "auth-src", "Auth Source")]

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "ArticleRepo", _ArticleRepo)

    return TestClient(create_app())


def test_password_verify_success_and_fail() -> None:
    auth_module = import_module("app.web.auth")

    password_hash = auth_module.hash_password("s3cret-pass")

    assert password_hash != "s3cret-pass"
    assert auth_module.verify_password("s3cret-pass", password_hash) is True
    assert auth_module.verify_password("wrong-pass", password_hash) is False


def test_session_sign_verify_and_expiration() -> None:
    auth_module = import_module("app.web.auth")

    signer = auth_module.SessionSigner(
        secret="0123456789abcdef0123456789abcdef",
        ttl_seconds=5,
    )
    issued_at = datetime(2026, 2, 21, 10, 0, tzinfo=UTC)

    token = signer.sign(subject="operator", now=issued_at)

    valid_payload = signer.verify(token, now=issued_at + timedelta(seconds=4))
    assert valid_payload is not None
    assert valid_payload["sub"] == "operator"

    expired_payload = signer.verify(token, now=issued_at + timedelta(seconds=6))
    assert expired_payload is None


def test_unauthenticated_api_news_returns_401(monkeypatch, tmp_path) -> None:
    client = _build_authenticated_client(monkeypatch, tmp_path)

    response = client.get("/api/news")

    assert response.status_code == 401


def test_unauthenticated_root_redirects_to_login(monkeypatch, tmp_path) -> None:
    client = _build_authenticated_client(monkeypatch, tmp_path)

    response = client.get("/", follow_redirects=False)

    assert response.status_code in {302, 303, 307, 308}
    assert response.headers["location"].endswith("/login")


def test_login_success_sets_cookie_and_grants_access(monkeypatch, tmp_path) -> None:
    client = _build_authenticated_client(monkeypatch, tmp_path)

    login = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "s3cret-pass"},
        follow_redirects=False,
    )

    assert login.status_code in {200, 204, 302, 303}
    assert any(name for name in client.cookies.keys())

    response = client.get("/api/news")
    assert response.status_code == 200


def test_login_fail_returns_generic_error(monkeypatch, tmp_path) -> None:
    client = _build_authenticated_client(monkeypatch, tmp_path)

    login = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "wrong-pass"},
    )

    assert login.status_code == 401
    detail = login.json()["detail"].lower()
    assert "invalid" in detail
    assert "wrong password" not in detail
    assert "unknown user" not in detail


def test_logout_invalidates_session(monkeypatch, tmp_path) -> None:
    client = _build_authenticated_client(monkeypatch, tmp_path)

    login = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "s3cret-pass"},
    )
    assert login.status_code in {200, 204, 302, 303}

    granted = client.get("/api/news")
    assert granted.status_code == 200

    logout = client.post("/api/auth/logout", follow_redirects=False)
    assert logout.status_code in {200, 204, 302, 303}

    denied = client.get("/api/news")
    assert denied.status_code == 401


def test_expired_session_on_protected_api_returns_401(monkeypatch, tmp_path) -> None:
    client = _build_authenticated_client(monkeypatch, tmp_path)
    auth_module = import_module("app.web.auth")
    signer = auth_module.SessionSigner(
        secret="0123456789abcdef0123456789abcdef",
        ttl_seconds=60,
    )
    expired_token = signer.sign(
        subject="operator",
        now=datetime(2020, 1, 1, 0, 0, tzinfo=UTC),
    )
    client.cookies.set("ainews_session", expired_token)

    response = client.get("/api/news")

    assert response.status_code == 401


def test_tampered_session_token_is_denied(monkeypatch, tmp_path) -> None:
    client = _build_authenticated_client(monkeypatch, tmp_path)

    login = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "s3cret-pass"},
    )
    assert login.status_code in {200, 204, 302, 303}

    token = client.cookies.get("ainews_session")
    assert token is not None
    replacement = "A" if token[-1] != "A" else "B"
    client.cookies.set("ainews_session", f"{token[:-1]}{replacement}")

    response = client.get("/api/news")

    assert response.status_code == 401


def test_second_login_immediately_invalidates_previous_session_token(monkeypatch, tmp_path) -> None:
    auth_module = import_module("app.web.auth")
    original_sign = auth_module.SessionSigner.sign
    issued_count = {"value": 0}
    base_issued_at = datetime.now(tz=UTC).replace(microsecond=0)

    def _deterministic_sign(self, *, subject: str, now=None):
        if now is None:
            now = base_issued_at + timedelta(seconds=issued_count["value"])
            issued_count["value"] += 1
        return original_sign(self, subject=subject, now=now)

    monkeypatch.setattr(auth_module.SessionSigner, "sign", _deterministic_sign)
    client = _build_authenticated_client(monkeypatch, tmp_path)

    first_login = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "s3cret-pass"},
    )
    assert first_login.status_code in {200, 204, 302, 303}
    first_token = client.cookies.get("ainews_session")
    assert first_token is not None

    second_login = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "s3cret-pass"},
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


def test_settings_validation_fails_when_auth_enabled_missing_required_fields(
    monkeypatch,
) -> None:
    monkeypatch.delenv("AINEWS_AUTH_USERNAME", raising=False)
    monkeypatch.delenv("AINEWS_AUTH_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("AINEWS_AUTH_SECRET", raising=False)
    with pytest.raises(ValidationError, match="missing required auth settings"):
        Settings(auth_enabled=True, _env_file=None)


def test_hash_password_uses_argon2_when_available(monkeypatch) -> None:
    auth_module = import_module("app.web.auth")

    class _FakeArgon2:
        def hash(self, password: str) -> str:
            assert password == "s3cret-pass"
            return "$argon2id$v=19$m=1,t=1,p=1$fake$hash"

    monkeypatch.setattr(auth_module, "_ARGON2_HASHER", _FakeArgon2())
    monkeypatch.setattr(auth_module, "bcrypt", None)

    assert auth_module.hash_password("s3cret-pass").startswith("$argon2id$")


def test_hash_password_uses_bcrypt_when_argon2_missing(monkeypatch) -> None:
    auth_module = import_module("app.web.auth")

    class _FakeBcrypt:
        @staticmethod
        def gensalt() -> bytes:
            return b"salt"

        @staticmethod
        def hashpw(password: bytes, salt: bytes) -> bytes:
            assert password == b"s3cret-pass"
            assert salt == b"salt"
            return b"$2b$12$abcdefghijklmnopqrstuvabcdefghijklmno1234567890"

    monkeypatch.setattr(auth_module, "_ARGON2_HASHER", None)
    monkeypatch.setattr(auth_module, "bcrypt", _FakeBcrypt())

    assert auth_module.hash_password("s3cret-pass").startswith("$2b$")


def test_verify_password_dispatches_and_error_branches(monkeypatch) -> None:
    auth_module = import_module("app.web.auth")

    class _RaisingArgon2:
        def verify(self, _password_hash: str, _password: str) -> bool:
            raise RuntimeError("boom")

    monkeypatch.setattr(auth_module, "_ARGON2_HASHER", None)
    assert auth_module.verify_password("x", "$argon2id$fake") is False
    monkeypatch.setattr(auth_module, "_ARGON2_HASHER", _RaisingArgon2())
    assert auth_module.verify_password("x", "$argon2id$fake") is False

    class _FakeBcrypt:
        @staticmethod
        def checkpw(_password: bytes, _password_hash: bytes) -> bool:
            raise ValueError("bad hash")

    monkeypatch.setattr(auth_module, "bcrypt", None)
    assert auth_module.verify_password("x", "$2b$bad") is False
    monkeypatch.setattr(auth_module, "bcrypt", _FakeBcrypt())
    assert auth_module.verify_password("x", "$2b$bad") is False


def test_verify_scrypt_non_scrypt_and_invalid_format() -> None:
    auth_module = import_module("app.web.auth")

    assert auth_module.verify_password("pass", "pbkdf2$1$2$3$4$5") is False
    assert auth_module.verify_password("pass", "scrypt$missing-parts") is False


def test_login_page_redirects_when_session_valid(monkeypatch, tmp_path) -> None:
    client = _build_authenticated_client(monkeypatch, tmp_path)

    login = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "s3cret-pass"},
    )
    assert login.status_code == 200

    page = client.get("/login", follow_redirects=False)
    assert page.status_code == 303
    assert page.headers["location"] == "/"


def test_login_page_renders_login_form_when_not_authenticated(monkeypatch, tmp_path) -> None:
    client = _build_authenticated_client(monkeypatch, tmp_path)

    page = client.get("/login")
    assert page.status_code == 200
    assert "<form id=\"login-form\">" in page.text


def test_login_api_returns_ok_when_auth_disabled(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    monkeypatch.setenv("AINEWS_AUTH_ENABLED", "false")
    monkeypatch.delenv("AINEWS_AUTH_USERNAME", raising=False)
    monkeypatch.delenv("AINEWS_AUTH_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("AINEWS_AUTH_SECRET", raising=False)

    client = TestClient(create_app())
    response = client.post("/api/auth/login", json={"username": "x", "password": "y"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_logout_returns_ok_when_auth_disabled(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    monkeypatch.setenv("AINEWS_AUTH_ENABLED", "false")
    monkeypatch.delenv("AINEWS_AUTH_USERNAME", raising=False)
    monkeypatch.delenv("AINEWS_AUTH_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("AINEWS_AUTH_SECRET", raising=False)

    client = TestClient(create_app())
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_login_page_renders_when_auth_disabled(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    monkeypatch.setenv("AINEWS_AUTH_ENABLED", "false")
    monkeypatch.delenv("AINEWS_AUTH_USERNAME", raising=False)
    monkeypatch.delenv("AINEWS_AUTH_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("AINEWS_AUTH_SECRET", raising=False)

    client = TestClient(create_app())
    page = client.get("/login")
    assert page.status_code == 200
    assert "<form id=\"login-form\">" in page.text


def test_logout_without_cookie_skips_revoke(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    auth_module = import_module("app.web.auth")
    password_hash = auth_module.hash_password("s3cret-pass")

    monkeypatch.setenv("AINEWS_AUTH_USERNAME", "operator")
    monkeypatch.setenv("AINEWS_AUTH_PASSWORD_HASH", password_hash)
    monkeypatch.setenv("AINEWS_AUTH_SECRET", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("AINEWS_AUTH_SESSION_TTL_SECONDS", "60")

    revoke_calls = {"count": 0}
    original_revoke = auth_module.SessionSigner.revoke

    def _track_revoke(self, token: str) -> None:
        revoke_calls["count"] += 1
        original_revoke(self, token)

    monkeypatch.setattr(auth_module.SessionSigner, "revoke", _track_revoke)
    client = TestClient(create_app())

    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    assert revoke_calls["count"] == 0


def test_session_verify_invalid_token_and_nondict_payload() -> None:
    auth_module = import_module("app.web.auth")
    signer = auth_module.SessionSigner(
        secret="0123456789abcdef0123456789abcdef",
        ttl_seconds=60,
    )

    assert signer.verify("not-a-token") is None

    payload_str = base64.urlsafe_b64encode(
        json.dumps(["not-a-dict"]).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = base64.urlsafe_b64encode(
        hmac.new(
            b"0123456789abcdef0123456789abcdef",
            payload_str.encode("ascii"),
            hashlib.sha256,
        ).digest()
    ).decode("ascii").rstrip("=")
    token = f"{payload_str}.{signature}"
    assert signer.verify(token) is None


def test_session_verify_returns_none_for_revoked_token() -> None:
    auth_module = import_module("app.web.auth")
    signer = auth_module.SessionSigner(
        secret="0123456789abcdef0123456789abcdef",
        ttl_seconds=60,
    )
    token = signer.sign(subject="operator", now=datetime(2026, 2, 21, 10, 0, tzinfo=UTC))
    signer.revoke(token)
    assert signer.verify(token, now=datetime(2026, 2, 21, 10, 0, tzinfo=UTC)) is None
