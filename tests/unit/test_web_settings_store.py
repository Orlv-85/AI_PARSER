from app.web.models import WebUpdateSettings
from app.web.settings_store import UpdateSettingsStore


def test_settings_store_loads_defaults_and_persists(tmp_path) -> None:
    path = tmp_path / "data" / "web_update_settings.json"
    store = UpdateSettingsStore(path)

    defaults = store.load()
    assert defaults.max_retries == 3

    saved = store.save(
        WebUpdateSettings(
            request_timeout_seconds=10.0,
            max_retries=2,
            per_source_min_interval_seconds=0.5,
            concurrency_limit=4,
        )
    )
    loaded = store.load()

    assert loaded == saved
