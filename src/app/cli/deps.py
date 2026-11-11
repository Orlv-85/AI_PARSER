"""CLI composition root: the only `cli/` module that imports the session factory and the table
initializer (src/app/README.md). Commands read `deps.SessionLocal`, `deps.create_all` and
`deps.get_settings` at call time, so a test patches them in one place."""
from app.config.settings import get_settings
from app.storage import SessionLocal, create_all

__all__ = ["SessionLocal", "create_all", "get_settings"]
