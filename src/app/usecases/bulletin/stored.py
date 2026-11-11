"""Stored bulletin read of the public API; contract: src/app/storage/bulletin_store.md."""

from collections.abc import Callable
from datetime import date

from sqlalchemy.orm import Session

from app.storage.bulletin_store import BulletinRepo
from app.storage.models_sql import BulletinRow


def stored_bulletin(session_factory: Callable[[], Session], day: date | None) -> BulletinRow | None:
    """The stored row of `day`, or the latest ready one when `day` is None."""
    with session_factory() as session:
        repo = BulletinRepo(session)
        return repo.get(day) if day is not None else repo.latest_ready()
