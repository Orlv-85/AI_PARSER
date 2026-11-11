"""Whether news collection is paused, read for the web."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.storage.admission import read_collection_status


def collection_status(session_factory: Callable[[], Session]) -> tuple[bool, str | None]:
    """(paused, message) of the stored collection status."""
    with session_factory() as session:
        status: tuple[bool, str | None] = read_collection_status(session)
        return status
