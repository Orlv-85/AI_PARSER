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


def test_settings_fetch_optimization_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.fetch_execution_profile == "balanced"
    assert settings.fetch_rss_concurrency_limit is None
    assert settings.fetch_html_concurrency_limit is None
    assert settings.html_link_parser == "auto"
    assert settings.fetch_http_max_connections == 20
    assert settings.fetch_http_max_keepalive_connections == 10
    assert settings.fetch_emit_source_metrics is True
    assert settings.fetch_conditional_rss_enabled is True
    assert settings.fetch_conditional_html_list_enabled is False
    assert settings.html_known_streak_stop == 20
    assert settings.html_max_links_per_source == 50
    assert settings.article_batch_upsert_enabled is False


def test_settings_reads_fetch_optimization_flags_from_env(monkeypatch) -> None:
    monkeypatch.setenv("AINEWS_FETCH_EXECUTION_PROFILE", "rss_fast")
    monkeypatch.setenv("AINEWS_FETCH_RSS_CONCURRENCY_LIMIT", "6")
    monkeypatch.setenv("AINEWS_FETCH_HTML_CONCURRENCY_LIMIT", "2")
    monkeypatch.setenv("AINEWS_HTML_LINK_PARSER", "lxml")
    monkeypatch.setenv("AINEWS_FETCH_HTTP_MAX_CONNECTIONS", "40")
    monkeypatch.setenv("AINEWS_FETCH_HTTP_MAX_KEEPALIVE_CONNECTIONS", "12")
    monkeypatch.setenv("AINEWS_FETCH_EMIT_SOURCE_METRICS", "false")
    monkeypatch.setenv("AINEWS_FETCH_CONDITIONAL_RSS_ENABLED", "false")
    monkeypatch.setenv("AINEWS_FETCH_CONDITIONAL_HTML_LIST_ENABLED", "true")
    monkeypatch.setenv("AINEWS_HTML_KNOWN_STREAK_STOP", "7")
    monkeypatch.setenv("AINEWS_HTML_MAX_LINKS_PER_SOURCE", "25")
    monkeypatch.setenv("AINEWS_ARTICLE_BATCH_UPSERT_ENABLED", "true")

    settings = Settings(_env_file=None)

    assert settings.fetch_execution_profile == "rss_fast"
    assert settings.fetch_rss_concurrency_limit == 6
    assert settings.fetch_html_concurrency_limit == 2
    assert settings.html_link_parser == "lxml"
    assert settings.fetch_http_max_connections == 40
    assert settings.fetch_http_max_keepalive_connections == 12
    assert settings.fetch_emit_source_metrics is False
    assert settings.fetch_conditional_rss_enabled is False
    assert settings.fetch_conditional_html_list_enabled is True
    assert settings.html_known_streak_stop == 7
    assert settings.html_max_links_per_source == 25
    assert settings.article_batch_upsert_enabled is True


def test_settings_read_jev_key_from_dotenv_and_mask_it(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("AINEWS_JEV_API_KEY", raising=False)
    monkeypatch.delenv("AINEWS_JEV_ENABLED", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("JEV_API_KEY=test-private-key\nAINEWS_JEV_ENABLED=true\n")
    settings = Settings(_env_file=env_file)
    assert settings.jev_enabled is True
    assert settings.jev_api_key is not None
    assert settings.jev_api_key.get_secret_value() == "test-private-key"
    assert "test-private-key" not in repr(settings)
    assert "test-private-key" not in settings.model_dump_json()


def test_settings_jev_environment_overrides_dotenv(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("JEV_API_KEY=file-key\nAINEWS_JEV_ENABLED=true\n")
    monkeypatch.setenv("JEV_API_KEY", "environment-key")
    monkeypatch.setenv("AINEWS_JEV_ENABLED", "false")
    monkeypatch.setenv("AINEWS_JEV_MODEL", "jev-latest")
    monkeypatch.setenv("AINEWS_JEV_TIMEOUT_SECONDS", "1.5")
    monkeypatch.setenv("AINEWS_JEV_CATEGORY_MIN_CONFIDENCE", "0.85")
    settings = Settings(_env_file=env_file)
    assert settings.jev_enabled is False
    assert settings.jev_api_key is not None
    assert settings.jev_api_key.get_secret_value() == "environment-key"
    assert settings.jev_model == "jev-latest"
    assert settings.jev_timeout_seconds == 1.5
    assert settings.jev_category_min_confidence == 0.85


@pytest.mark.parametrize("confidence", [-0.1, 1.1, float("nan"), float("inf")])
def test_settings_reject_invalid_jev_category_confidence(confidence) -> None:
    with pytest.raises(ValidationError):
        Settings(jev_category_min_confidence=confidence, _env_file=None)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_settings_reject_invalid_jev_timeout(timeout) -> None:
    with pytest.raises(ValidationError):
        Settings(jev_timeout_seconds=timeout, _env_file=None)


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


def test_daily_signals_defaults_and_env(monkeypatch) -> None:
    settings = Settings(_env_file=None)
    assert settings.daily_signals_enabled is False
    assert str(settings.daily_signals_comparable_from) == "2026-10-10"
    assert (settings.daily_signals_max_calls, settings.daily_signals_max_seconds,
            settings.daily_signals_max_usd) == (200, 2700, "0.50")
    monkeypatch.setenv("AINEWS_DAILY_SIGNALS_ENABLED", "true")
    monkeypatch.setenv("AINEWS_DAILY_SIGNALS_COMPARABLE_FROM", "2026-11-01")
    monkeypatch.setenv("AINEWS_DAILY_SIGNALS_MAX_CALLS", "5")
    monkeypatch.setenv("AINEWS_DAILY_SIGNALS_MAX_SECONDS", "600")
    monkeypatch.setenv("AINEWS_DAILY_SIGNALS_MAX_USD", "1.25")
    settings = Settings(_env_file=None)
    assert settings.daily_signals_enabled is True
    assert str(settings.daily_signals_comparable_from) == "2026-11-01"
    assert (settings.daily_signals_max_calls, settings.daily_signals_max_seconds,
            settings.daily_signals_max_usd) == (5, 600, "1.25")


@pytest.mark.parametrize("value", ["abc", "0", "-1", "nan", "inf", "0.0000001"])
def test_daily_signals_rejects_invalid_usd(value) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, daily_signals_max_usd=value)
