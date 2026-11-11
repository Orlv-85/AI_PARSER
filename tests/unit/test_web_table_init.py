"""Per-app table initialization, retries and serialization (spec 020, FR-004)."""

from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from threading import Event, Lock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.storage.models_sql import Base

_PATHS = {"news": "/api/news", "onboarding": "/api/source-onboarding/latest"}
_FIELDS = {"news": "create_all", "onboarding": "create_onboarding_tables"}


class _SpyLock:
    """A lock that tells when a second caller is waiting on it."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._attempts = 0
        self.contended = Event()

    def __enter__(self) -> _SpyLock:
        self._attempts += 1
        if self._attempts > 1:
            self.contended.set()
        self._lock.acquire()  # pylint: disable=consider-using-with
        return self

    def __exit__(self, *_exc: object) -> None:
        self._lock.release()


@pytest.fixture(name="table_apps")
def _table_apps(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AINEWS_DATABASE_URL", f"sqlite:///{tmp_path / 'tables.sqlite'}")
    monkeypatch.setenv("AINEWS_AUTH_ENABLED", "false")
    get_settings.cache_clear()
    web = import_module("app.web.app")
    engine = create_engine(get_settings().database_url)
    create_tables = Base.metadata.create_all
    create_tables(bind=engine)
    initializers = {
        "news": Mock(side_effect=lambda: create_tables(bind=engine)),
        "onboarding": Mock(side_effect=create_tables),
    }
    monkeypatch.setattr(web, "create_all", initializers["news"])
    monkeypatch.setattr(web, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(Base.metadata, "create_all", initializers["onboarding"])
    captured = []
    build_sources_router = web.build_sources_router

    def capture_router(deps):
        captured.append(deps)
        return build_sources_router(deps)

    monkeypatch.setattr(web, "build_sources_router", capture_router)
    locks: list[_SpyLock] = []

    def spy_lock() -> _SpyLock:
        locks.append(_SpyLock())
        return locks[-1]

    monkeypatch.setattr(web, "Lock", spy_lock)

    def build():
        app = web.create_app()
        return TestClient(app), captured[-1]

    yield SimpleNamespace(build=build, initializers=initializers, locks=locks)
    for deps in captured:
        deps.onboarding_engine.dispose()
    engine.dispose()
    get_settings.cache_clear()


@pytest.mark.parametrize("storage", _PATHS)
def test_tables_requests_once(table_apps, storage):
    client, _deps = table_apps.build()
    initializer = table_apps.initializers[storage]
    initializer.assert_not_called()
    with client:
        assert client.get(_PATHS[storage]).status_code == 200
        assert client.get(_PATHS[storage]).status_code == 200
    assert initializer.call_count == 1


@pytest.mark.parametrize("storage", _PATHS)
def test_tables_retry_after_storage_error(table_apps, storage):
    initializer = table_apps.initializers[storage]
    initializer.side_effect = [SQLAlchemyError("unavailable"), None]
    client, _deps = table_apps.build()
    with client:
        first = client.get(_PATHS[storage])
        assert first.status_code == 503
        assert first.json() == {"detail": "News storage is unavailable"}
        assert initializer.call_count == 1
        assert client.get(_PATHS[storage]).status_code == 200
        assert initializer.call_count == 2
        assert client.get(_PATHS[storage]).status_code == 200
    assert initializer.call_count == 2


@pytest.mark.parametrize("storage", _PATHS)
def test_tables_concurrent_calls_once(table_apps, storage):
    entered, release, repeated, second_started = (Event() for _ in range(4))

    def initialize(*_args, **_kwargs):
        if entered.is_set():
            repeated.set()
        entered.set()
        assert release.wait(5)

    initializer = table_apps.initializers[storage]
    initializer.side_effect = initialize
    _client, deps = table_apps.build()
    create = getattr(deps, _FIELDS[storage])

    def second_call():
        second_started.set()
        create()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(create)
        try:
            assert entered.wait(5)
            second = pool.submit(second_call)
            assert second_started.wait(5)
            assert table_apps.locks[-1].contended.wait(5)
            assert not repeated.is_set()
        finally:
            release.set()
        first.result(timeout=5)
        second.result(timeout=5)
    assert initializer.call_count == 1


@pytest.mark.parametrize("storage", _PATHS)
def test_tables_new_app_calls_again(table_apps, storage):
    with table_apps.build()[0] as first:
        assert first.get(_PATHS[storage]).status_code == 200
        assert first.get(_PATHS[storage]).status_code == 200
    assert table_apps.initializers[storage].call_count == 1
    with table_apps.build()[0] as second:
        assert second.get(_PATHS[storage]).status_code == 200
        assert second.get(_PATHS[storage]).status_code == 200
    assert table_apps.initializers[storage].call_count == 2


@pytest.mark.parametrize("storage", _PATHS)
def test_tables_initializers_share_lock(table_apps, storage):
    other = "onboarding" if storage == "news" else "news"
    entered, release, other_started, other_entered = (Event() for _ in range(4))

    def initialize(*_args, **_kwargs):
        entered.set()
        assert release.wait(5)

    table_apps.initializers[storage].side_effect = initialize
    table_apps.initializers[other].side_effect = lambda *_a, **_kw: other_entered.set()
    _client, deps = table_apps.build()

    def other_call():
        other_started.set()
        getattr(deps, _FIELDS[other])()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(getattr(deps, _FIELDS[storage]))
        try:
            assert entered.wait(5)
            second = pool.submit(other_call)
            assert other_started.wait(5)
            assert table_apps.locks[-1].contended.wait(5)
            assert not other_entered.is_set()
        finally:
            release.set()
        first.result(timeout=5)
        second.result(timeout=5)
    assert other_entered.is_set()
    assert table_apps.initializers[storage].call_count == 1
    assert table_apps.initializers[other].call_count == 1
