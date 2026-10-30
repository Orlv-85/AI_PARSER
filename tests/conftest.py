from app.config.settings import Settings

# Tests never read the developer's .env, as in CI (no .env there). Set at import: app.storage.db
# builds its engine from get_settings() when imported, before any fixture runs. A test that needs
# a file passes `_env_file=` explicitly; environment variables still apply.
Settings.model_config["env_file"] = None
