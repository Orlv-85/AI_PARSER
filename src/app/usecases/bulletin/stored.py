"""Stored bulletin read of the public API; contract: src/app/storage/bulletin_store.md."""

from collections.abc import Callable
from datetime import date

from sqlalchemy.orm import Session

from app.core.bulletin.builder import Bulletin
from app.storage.bulletin_store import BulletinRepo
from app.storage.models_sql import BulletinRow


def stored_bulletin(session_factory: Callable[[], Session], day: date | None) -> BulletinRow | None:
    """The stored row of `day`, or the latest ready one when `day` is None."""
    with session_factory() as session:
        repo = BulletinRepo(session)
        return repo.get(day) if day is not None else repo.latest_ready()


def store_bulletin(session_factory: Callable[[], Session], day: date, *,
                   bulletin: Bulletin | None, reason: str | None,
                   numbers: dict[str, object]) -> None:
    """Upserts an unposted day and commits (a posted day is kept)."""
    with session_factory() as session:
        BulletinRepo(session).save(day, bulletin=bulletin, reason=reason, numbers=numbers)
        session.commit()
