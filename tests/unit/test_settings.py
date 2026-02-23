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


def test_settings_is_auth_enabled_true_when_all_auth_material_present() -> None:
    settings = Settings(
        auth_username="operator",
        auth_password_hash="hash",
        auth_secret="0123456789abcdef0123456789abcdef",
        _env_file=None,
    )
    assert settings.is_auth_enabled is True


def test_settings_validation_rejects_missing_auth_fields_when_auth_enabled() -> None:
    with pytest.raises(ValidationError, match="missing required auth settings"):
        Settings(
            auth_enabled=True,
            _env_file=None,
        )


def test_settings_validation_rejects_non_positive_ttl() -> None:
    with pytest.raises(ValidationError, match="must be greater than 0"):
        Settings(
            auth_username="operator",
            auth_password_hash="hash",
            auth_secret="0123456789abcdef0123456789abcdef",
            auth_session_ttl_seconds=0,
        )


def test_settings_validation_rejects_missing_mcp_auth_material_when_enabled() -> None:
    with pytest.raises(ValidationError, match="missing required mcp auth settings"):
        Settings(
            mcp_auth_enabled=True,
            _env_file=None,
        )


def test_settings_validation_rejects_short_mcp_auth_token_when_enabled() -> None:
    with pytest.raises(ValidationError, match="at least 16 characters long"):
        Settings(
            mcp_auth_enabled=True,
            mcp_auth_token="short-token",
            _env_file=None,
        )


def test_settings_allow_mcp_without_token_when_auth_disabled() -> None:
    settings = Settings(
        mcp_auth_enabled=False,
        _env_file=None,
    )
    assert settings is not None


def test_settings_allow_mcp_with_valid_token_when_enabled() -> None:
    settings = Settings(
        mcp_auth_enabled=True,
        mcp_auth_token="0123456789abcdef",
        _env_file=None,
    )
    assert settings.mcp_auth_enabled is True
