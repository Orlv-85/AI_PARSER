"""Page view counter of the public pages; see src/app/web/pages.md."""

from collections.abc import Callable
from datetime import date

from sqlalchemy.orm import Session

from app.storage.page_views import PageViewRepo


def count_page_view(session_factory: Callable[[], Session], day: date, route: str) -> None:
    """One atomic increment in its own session, committed."""
    with session_factory() as session:
        PageViewRepo(session).increment(day, route)
        session.commit()
