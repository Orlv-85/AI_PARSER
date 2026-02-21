from app.config.settings import get_settings


def test_settings_read_from_env(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("AINEWS_DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("AINEWS_RESPECT_ROBOTS_TXT", "false")

    settings = get_settings()

    assert settings.database_url == "sqlite:///./test.db"
    assert settings.respect_robots_txt is False
    get_settings.cache_clear()

