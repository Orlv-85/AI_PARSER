import pytest
from pydantic import ValidationError

from app.config.settings import Settings, get_settings


def test_settings_read_from_env(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("AINEWS_DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("AINEWS_RESPECT_ROBOTS_TXT", "false")

    settings = get_settings()

    assert settings.database_url == "sqlite:///./test.db"
    assert settings.respect_robots_txt is False
    get_settings.cache_clear()


def test_settings_validation_rejects_short_auth_secret() -> None:
    with pytest.raises(ValidationError, match="at least 32 characters long"):
        Settings(
            auth_username="operator",
            auth_password_hash="hash",
            auth_secret="too-short",
        )


def test_settings_validation_rejects_non_positive_ttl() -> None:
    with pytest.raises(ValidationError, match="must be greater than 0"):
        Settings(
            auth_username="operator",
            auth_password_hash="hash",
            auth_secret="0123456789abcdef0123456789abcdef",
            auth_session_ttl_seconds=0,
        )
