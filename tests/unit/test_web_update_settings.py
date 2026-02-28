from pathlib import Path
from types import SimpleNamespace
from typing import cast

from app.web.models import WebUpdateSettings
from app.web.service import UpdateRunService
from app.web.settings_store import UpdateSettingsStore


def test_update_settings_store_round_trips_extended_optimization_fields(tmp_path: Path) -> None:
    store = UpdateSettingsStore(tmp_path / "settings.json")
    settings = WebUpdateSettings(
        request_timeout_seconds=9.0,
        max_retries=1,
        per_source_min_interval_seconds=0.2,
        concurrency_limit=3,
        fetch_http_max_connections=33,
        fetch_http_max_keepalive_connections=11,
        rss_known_streak_stop=7,
        html_known_streak_stop=8,
        html_max_links_per_source=44,
        article_batch_upsert_enabled=True,
        fetch_emit_source_metrics=False,
    )

    store.save(settings)
    loaded = store.load()

    assert loaded == settings


def test_update_run_service_propagates_extended_runtime_settings(monkeypatch) -> None:
    service = UpdateRunService(
        logger=SimpleNamespace(
            info=lambda *_a, **_k: None,
            warning=lambda *_a, **_k: None,
            error=lambda *_a, **_k: None,
        )
    )
    captured: dict[str, SimpleNamespace] = {}

    class _ImmediateThread:
        def __init__(self, *, target, args, daemon):
            self._target = target
            self._args = args
            self._daemon = daemon

        def start(self) -> None:
            self._target(*self._args)

    class _BaseSettings:
        def model_copy(self, *, update):
            merged = SimpleNamespace(**update)
            captured["merged"] = merged
            return merged

    def _get_settings():
        return _BaseSettings()

    def _run_fetch_cycle(**kwargs):
        captured["settings"] = kwargs["settings"]
        return SimpleNamespace(fetched=0, new=0, duplicates=0, errors=0)

    monkeypatch.setattr("app.web.service.get_settings", _get_settings)
    monkeypatch.setattr("app.web.service.threading.Thread", _ImmediateThread)
    monkeypatch.setattr("app.web.service.run_fetch_cycle", _run_fetch_cycle)

    runtime_settings = WebUpdateSettings(
        fetch_http_max_connections=55,
        fetch_http_max_keepalive_connections=21,
        rss_known_streak_stop=9,
        html_known_streak_stop=10,
        html_max_links_per_source=66,
        article_batch_upsert_enabled=True,
        fetch_emit_source_metrics=False,
    )

    started = service.start(runtime_settings)
    assert started is not None
    merged = cast(SimpleNamespace, captured["settings"])

    assert merged.fetch_http_max_connections == 55
    assert merged.fetch_http_max_keepalive_connections == 21
    assert merged.rss_known_streak_stop == 9
    assert merged.html_known_streak_stop == 10
    assert merged.html_max_links_per_source == 66
    assert merged.article_batch_upsert_enabled is True
    assert merged.fetch_emit_source_metrics is False
