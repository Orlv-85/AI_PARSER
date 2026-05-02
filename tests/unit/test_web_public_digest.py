from datetime import UTC, datetime
from importlib import import_module

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.storage.models_sql import Base
from app.web.app import create_app


def test_public_digest_page_renders_digest_shell_with_yesterday_selected(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path}/public-digest-page.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 1, 9, 30, tzinfo=tz or UTC)

    def _create_all_local() -> None:
        Base.metadata.create_all(bind=engine)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", _create_all_local)
    monkeypatch.setattr(web_app_module, "SessionLocal", session_local)
    monkeypatch.setattr(web_app_module, "datetime", _FrozenDateTime)

    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "Yesterday&#39;s Digest" in response.text or "Yesterday's Digest" in response.text
    assert 'type="date"' in response.text
    assert 'value="2026-02-28"' in response.text
    assert 'href="/news-stats"' in response.text


def test_public_digest_page_shows_clean_empty_state_when_digest_missing(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path}/public-digest-empty.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 2, 8, 0, tzinfo=tz or UTC)

    def _create_all_local() -> None:
        Base.metadata.create_all(bind=engine)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", _create_all_local)
    monkeypatch.setattr(web_app_module, "SessionLocal", session_local)
    monkeypatch.setattr(web_app_module, "datetime", _FrozenDateTime)

    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "No digest has been published for this date yet." in response.text


def test_public_digest_page_keeps_explicit_query_date_selected(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path}/public-digest-query-date.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _create_all_local() -> None:
        Base.metadata.create_all(bind=engine)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 1, 9, 30, tzinfo=tz or UTC)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", _create_all_local)
    monkeypatch.setattr(web_app_module, "SessionLocal", session_local)
    monkeypatch.setattr(web_app_module, "datetime", _FrozenDateTime)

    client = TestClient(create_app())

    response = client.get("/?date=2026-02-27")

    assert response.status_code == 200
    assert "Digest for 2026-02-27" in response.text
    assert 'value="2026-02-27"' in response.text
    assert '"?date=2026-02-27"' in response.text
    assert '"2026-02-28"' in response.text
    assert "history.replaceState" in response.text
    assert "updateHeroTitle" in response.text


def test_public_digest_page_stays_public_when_auth_is_enabled(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AINEWS_AUTH_ENABLED", "true")
    monkeypatch.setenv("AINEWS_AUTH_USERNAME", "admin")
    monkeypatch.setenv(
        "AINEWS_AUTH_PASSWORD_HASH",
        "$2b$12$abcdefghijklmnopqrstuuuuuuuuuuuuuuuuuuuuuuuuuu",
    )
    monkeypatch.setenv("AINEWS_AUTH_SECRET", "12345678901234567890123456789012")
    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path}/public-digest-auth.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 3, 8, 0, tzinfo=tz or UTC)

    def _create_all_local() -> None:
        Base.metadata.create_all(bind=engine)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", _create_all_local)
    monkeypatch.setattr(web_app_module, "SessionLocal", session_local)
    monkeypatch.setattr(web_app_module, "datetime", _FrozenDateTime)

    client = TestClient(create_app())

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 200
    assert "Yesterday&#39;s Digest" in response.text or "Yesterday's Digest" in response.text
