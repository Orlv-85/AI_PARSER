"""Page view counter of the public pages; see src/app/web/pages.md."""

from collections.abc import Callable
from datetime import date

from sqlalchemy.orm import Session

from app.storage.page_views import PAGE_VIEWS_DEFAULT_DAYS, PageViewRepo

__all__ = ["PAGE_VIEWS_DEFAULT_DAYS", "count_page_view", "page_view_totals"]


def count_page_view(session_factory: Callable[[], Session], day: date, route: str) -> None:
    """One atomic increment in its own session, committed."""
    with session_factory() as session:
        PageViewRepo(session).increment(day, route)
        session.commit()


def page_view_totals(session_factory: Callable[[], Session], start: date, end: date
                     ) -> dict[str, dict[str, int]]:
    """Read-only day/route totals of the range (CLI `page-views`)."""
    with session_factory() as session:
        totals: dict[str, dict[str, int]] = PageViewRepo(session).totals(start, end)
        return totals
