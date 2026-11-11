"""Stored period signals for the web: reads only, one session each; see
src/app/core/periodic/signals_period.md."""

from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy import Row
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.storage.models_sql import PeriodSignalBrief, PeriodSignalReport
from app.storage.period_signals import PeriodSignalRepo

# A default read shows the newest period that carries comparable numbers, else any stored one.
SHOWN_STATUSES = ("ready", "building_history")

type StoredPeriod = tuple[PeriodSignalReport | None, PeriodSignalBrief | None]


def _repo(session: Session) -> PeriodSignalRepo:
    return PeriodSignalRepo(session, comparable_from=get_settings().daily_signals_comparable_from)


def _report_and_brief(repo: PeriodSignalRepo, kind: str, start: date | None,
                      latest: bool) -> StoredPeriod:
    if start is not None:
        row = repo.get_report(kind, start)
    elif latest:
        row = repo.latest(kind, SHOWN_STATUSES) or repo.latest(kind)
    else:
        row = None
    return row, repo.get_brief(kind, row.period_start) if row is not None else None


def period_index(session_factory: Callable[[], Session], kind: str | None) -> list[Row[Any]]:
    """Stored periods of `kind` (any kind for None), newest first."""
    with session_factory() as session:
        rows: list[Row[Any]] = _repo(session).index(kind)
        return rows


def stored_period(session_factory: Callable[[], Session], kind: str,
                  start: date | None) -> StoredPeriod:
    """The period starting at `start`, or the default one when `start` is None, with its brief."""
    with session_factory() as session:
        return _report_and_brief(_repo(session), kind, start, latest=True)


def period_page(session_factory: Callable[[], Session], kind: str, start: date | None,
                *, latest: bool) -> tuple[list[Row[Any]], PeriodSignalReport | None,
                                          PeriodSignalBrief | None]:
    """Index, report and brief of a page in one session; without `start` the report is the
    default one when `latest`, else None."""
    with session_factory() as session:
        repo = _repo(session)
        return repo.index(kind), *_report_and_brief(repo, kind, start, latest)
