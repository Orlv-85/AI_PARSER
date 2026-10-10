# pylint: disable=redefined-outer-name,protected-access
from datetime import UTC, datetime
from importlib import import_module
from logging import getLogger

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import Settings
from app.core.pipeline import run_fetch_cycle
from app.storage.admission import (
    PAUSED_MESSAGE,
    clear_collection_paused,
    get_collection_status,
    read_collection_status,
    set_collection_paused,
)
from app.storage.models_sql import Base, CollectionStatus
from app.web import service as service_module
from app.web.auth import hash_password
from app.web.models import UpdateStatus, WebUpdateSettings
from app.web.service import UpdateRunService

app_module = import_module("app.web.app")


@pytest.mark.parametrize("jev_enabled", [False, True])
def test_missing_provider_pauses_with_exact_notice(tmp_path, monkeypatch, jev_enabled) -> None:
    engine = create_engine("sqlite:///" + str(tmp_path / "notice.db"))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", sessions)
    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: [])
    settings = Settings(
        _env_file=None,
        semantic_admission_enabled=True,
        jev_enabled=jev_enabled,
        jev_api_key="",
        weekly_v2_enabled=False,
        auth_enabled=False,
    )
    summary = run_fetch_cycle(settings=settings, logger=getLogger("notice-test"))
    assert summary.screening_paused == 1
    with sessions() as session:
        status = get_collection_status(session)
        assert status.paused is True
        assert status.message == PAUSED_MESSAGE


def test_public_collection_status_returns_primitives(tmp_path) -> None:
    engine = create_engine("sqlite:///" + str(tmp_path / "status.db"))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    with sessions() as session:
        set_collection_paused(session)
        session.commit()
    with sessions() as session:
        paused, message = read_collection_status(session)
    assert paused is True
    assert message == PAUSED_MESSAGE


@pytest.fixture()
def sessions(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "notice.db"))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(app_module, "create_all", lambda: None)
    monkeypatch.setattr(app_module, "SessionLocal", sessions)
    monkeypatch.setattr(service_module, "SessionLocal", sessions)
    monkeypatch.setattr(
        service_module,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            semantic_admission_enabled=False,
            jev_enabled=False,
            weekly_v2_enabled=False,
            auth_enabled=False,
        ),
    )
    monkeypatch.setattr(app_module, "get_settings", service_module.get_settings)
    return sessions


def test_public_collection_status_read_only_does_not_create_row(sessions) -> None:
    client = TestClient(app_module.create_app())
    response = client.get("/api/news/collection-status")
    assert response.status_code == 200
    assert response.json() == {"paused": False, "message": None}
    with sessions() as session:
        assert session.get(CollectionStatus, 1) is None


def test_public_collection_status_exposes_persisted_pause(sessions) -> None:
    with sessions() as session:
        set_collection_paused(session)
        session.commit()
    client = TestClient(app_module.create_app())
    response = client.get("/api/news/collection-status")
    assert response.status_code == 200
    assert response.json() == {"paused": True, "message": PAUSED_MESSAGE}


def test_admin_update_status_includes_persisted_pause(
    sessions,
) -> None:
    with sessions() as session:
        set_collection_paused(session)
        session.commit()
    client = TestClient(app_module.create_app())
    response = client.get("/api/update/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["screening_paused"] is True
    assert payload["screening_message"] == PAUSED_MESSAGE


def test_new_service_sees_same_persisted_notice(sessions) -> None:
    with sessions() as session:
        set_collection_paused(session)
        session.commit()
    first = UpdateRunService().current_status()
    second = UpdateRunService().current_status()
    assert first.screening_paused is True
    assert first.screening_message == PAUSED_MESSAGE
    assert second.screening_paused is True
    assert second.screening_message == PAUSED_MESSAGE


def test_start_preserves_persisted_notice(sessions, monkeypatch) -> None:
    with sessions() as session:
        set_collection_paused(session)
        session.commit()
    service = UpdateRunService()
    monkeypatch.setattr(service, "_start_thread_locked", lambda *_: None)
    status = service.start(WebUpdateSettings(update_execution_mode="thread"))
    assert status is not None
    assert status.screening_paused is True
    assert status.screening_message == PAUSED_MESSAGE


def test_process_harvest_maps_pause_and_counters() -> None:
    service = UpdateRunService()
    service._status = UpdateStatus(
        run_id="run-1",
        status="running",
        started_at=datetime.now(UTC),
    )
    service._finalize_harvested_status_locked(
        {
            "status": "finished",
            "source_count": 2,
            "fetched": 4,
            "new": 3,
            "duplicates": 1,
            "errors": 0,
            "screening_paused": 1,
            "screening_message": PAUSED_MESSAGE,
        }
    )
    assert service._status.status == "finished"
    assert service._status.source_count == 2
    assert service._status.fetched == 4
    assert service._status.new == 3
    assert service._status.duplicates == 1
    assert service._status.errors == 0
    assert service._status.screening_paused is True
    assert service._status.screening_message == PAUSED_MESSAGE


def test_clear_persisted_state_removes_notice_but_empty_harvest_does_not(
    sessions,
) -> None:
    with sessions() as session:
        set_collection_paused(session)
        session.commit()
    service = UpdateRunService()
    service._status = UpdateStatus(run_id="run-2", status="running")
    service._finalize_harvested_status_locked(
        {
            "status": "finished",
            "fetched": 0,
            "new": 0,
            "duplicates": 0,
            "errors": 0,
            "error_message": None,
        }
    )
    assert service.current_status().screening_paused is True
    with sessions() as session:
        clear_collection_paused(session)
        session.commit()
    assert service.current_status().screening_paused is False
    assert service.current_status().screening_message is None


def test_status_is_public_when_admin_auth_enabled(sessions, monkeypatch) -> None:
    settings = Settings(
        _env_file=None, auth_enabled=True, auth_username="operator",
        auth_password_hash=hash_password("offline-test"),
        auth_secret="0123456789abcdef0123456789abcdef",
        jev_enabled=False, weekly_v2_enabled=False,
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    with sessions() as session:
        set_collection_paused(session)
        session.commit()
    client = TestClient(app_module.create_app())
    assert client.get("/api/news/collection-status").json() == {
        "paused": True, "message": PAUSED_MESSAGE,
    }
    assert client.get("/api/update/status").status_code == 401
