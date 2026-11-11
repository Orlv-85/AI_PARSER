"""Whether news collection is paused, read for the web."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.storage import SessionLocal
from app.storage.admission import PAUSED_MESSAGE, read_collection_status

__all__ = ["PAUSED_MESSAGE", "collection_status"]


def collection_status(session_factory: Callable[[], Session] | None = None
                      ) -> tuple[bool, str | None]:
    """(paused, message) of the stored collection status; the default database without a
    session factory (the update service)."""
    with (session_factory or SessionLocal)() as session:
        status: tuple[bool, str | None] = read_collection_status(session)
        return status
