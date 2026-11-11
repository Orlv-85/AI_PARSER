"""Stored daily signals for the web: indexed reads only, never a provider call; see signals.md."""

from collections.abc import Callable
from datetime import date

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.storage.daily_signals import DailySignalRepo
from app.storage.models_sql import DailySignalBrief, DailySignalReport


def stored_signals(session_factory: Callable[[], Session], report_date: date
                   ) -> tuple[DailySignalReport | None, DailySignalBrief | None]:
    """The stored snapshot of a day and, when it exists, its brief."""
    with session_factory() as session:
        repo = DailySignalRepo(session,
                               comparable_from=get_settings().daily_signals_comparable_from)
        row = repo.get_report(report_date)
        return row, repo.get_brief(report_date) if row is not None else None
