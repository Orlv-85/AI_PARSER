"""Period AI Signals run: pick the periods, compute them from stored data, store changed ones.

The numbers involve no provider. The optional brief step (period_brief_run.py) is the only paid
step; nothing is written outside `period_signal_*` (signals_period.md).
"""
import logging
import time
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.periodic.period_brief_run import run_briefs
from app.core.periodic.period_compute import (
    PERIOD_METHODOLOGY_VERSION,
    compute_period,
    payload_hash,
)
from app.core.periodic.period_model import (
    MONTH,
    WEEK,
    next_start,
    period_bounds,
    previous_start,
)
from app.storage.period_signals import PeriodSignalRepo

LOGGER = logging.getLogger(__name__)
BRIEF_MAX_SECONDS = 300


class PeriodRunError(ValueError):
    """The requested period cannot be computed; the message says why."""


@dataclass(frozen=True)
class PeriodRunOptions:  # pylint: disable=too-many-instance-attributes
    kind: str = WEEK
    period: date | None = None
    backfill: int = 1
    recompute_all: bool = False
    with_brief: bool = False
    max_usd: str | None = None
    max_seconds: int = BRIEF_MAX_SECONDS
    cache_dir: Path = Path("data/period-signals")


def first_period(kind: str, comparable_from: date) -> date:
    """First computable period: the first full week (Monday-Sunday) or calendar month inside the
    comparable range; a period that starts before it is partial and never computed."""
    start: date = period_bounds(kind, comparable_from)[0]
    return start if start == comparable_from else next_start(kind, start)


def latest_completed(kind: str, today: date) -> date:
    """Start of the latest period that ended before `today` (UTC)."""
    start: date = period_bounds(kind, period_bounds(kind, today)[0] - timedelta(days=1))[0]
    return start


def first_week(comparable_from: date) -> date:
    return first_period(WEEK, comparable_from)


def latest_completed_week(today: date) -> date:
    return latest_completed(WEEK, today)


def first_month(comparable_from: date) -> date:
    return first_period(MONTH, comparable_from)


def latest_completed_month(today: date) -> date:
    return latest_completed(MONTH, today)


def _back(kind: str, start: date, count: int) -> date:
    for _ in range(count):
        start = previous_start(kind, start)
    return start


def target_periods(options: PeriodRunOptions, *, today: date, comparable_from: date
                   ) -> tuple[list[date], list[date]]:
    """(periods to compute oldest first, periods dropped for being before the first one)."""
    kind = options.kind
    first, latest = first_period(kind, comparable_from), latest_completed(kind, today)
    if options.period is not None:
        end = period_bounds(kind, options.period)[0]
        if end > latest:
            raise PeriodRunError(f"only completed {kind}s can be computed")
        if end < first:
            raise PeriodRunError(f"{kind}s before {first.isoformat()} are history only")
    else:
        end = latest
    if options.recompute_all:
        wanted = []
        cursor = first
        while cursor <= latest:
            wanted.append(cursor)
            cursor = next_start(kind, cursor)
    else:
        wanted = [_back(kind, end, i) for i in range(options.backfill - 1, -1, -1)]
    return [w for w in wanted if w >= first], [w for w in wanted if w < first]


def target_weeks(options: PeriodRunOptions, *, today: date, comparable_from: date
                 ) -> tuple[list[date], list[date]]:
    return target_periods(replace(options, kind=WEEK), today=today, comparable_from=comparable_from)


def target_months(options: PeriodRunOptions, *, today: date, comparable_from: date
                  ) -> tuple[list[date], list[date]]:
    return target_periods(replace(options, kind=MONTH), today=today,
                          comparable_from=comparable_from)


def brief_targets(options: PeriodRunOptions, periods: list[date], *, today: date) -> list[date]:
    """Periods that get a brief: every run period with `--with-brief`; otherwise only the latest
    completed one when the run computed it (the nightly default)."""
    if options.with_brief:
        return periods
    latest = latest_completed(options.kind, today)
    return [latest] if latest in periods else []


def run_periods(session: Session, settings: Any, options: PeriodRunOptions, *,
                now: datetime | None = None, transport: httpx.BaseTransport | None = None
                ) -> dict[str, Any]:
    """One run of one kind; returns the run report. The flag off does nothing."""
    started = time.monotonic()
    moment = now or datetime.now(UTC)
    report: dict[str, Any] = {
        "state": "ok", "kind": options.kind, "methodology_version": PERIOD_METHODOLOGY_VERSION,
        "periods": {}, "written": [], "unchanged": 0, "skipped_before_first": [],
        "brief": None}
    if not settings.period_signals_enabled:
        report["state"] = "disabled"
        return report
    weeks, early = target_periods(options, today=moment.date(),
                                  comparable_from=settings.daily_signals_comparable_from)
    report["skipped_before_first"] = [w.isoformat() for w in early]
    repo = PeriodSignalRepo(session, comparable_from=settings.daily_signals_comparable_from,
                            publisher_overrides=settings.weekly_publisher_overrides)
    ctx = repo.context() if weeks else None
    for start in weeks:
        # Oldest first: the next period reads this one as its previous period.
        payload = compute_period(repo.load_input(options.kind, start, ctx=ctx,
                                                 generated_at=moment))
        changed = repo.save_report(payload, payload_hash(payload))
        session.commit()
        report["periods"][start.isoformat()] = {
            "end": period_bounds(options.kind, start)[1].isoformat(),
            "status": payload["status"], "written": changed}
        if changed:
            report["written"].append(start.isoformat())
        else:
            report["unchanged"] += 1
    if options.with_brief or settings.period_signals_brief_enabled:
        report["brief"] = _brief_step(session, settings, options, repo,
                                      brief_targets(options, weeks, today=moment.date()),
                                      transport=transport)
    report["seconds"] = round(time.monotonic() - started, 1)
    return report


def _brief_step(session: Session, settings: Any, options: PeriodRunOptions,
                repo: PeriodSignalRepo, weeks: list[date], *,
                transport: httpx.BaseTransport | None) -> dict[str, Any]:
    """The paid step; a failure never changes the stored numbers or the run result."""
    try:
        result: dict[str, Any] = run_briefs(
            session, repo, settings, [(options.kind, w) for w in weeks],
            max_usd=options.max_usd or settings.period_signals_max_usd,
            cache_dir=options.cache_dir, max_seconds=options.max_seconds, transport=transport)
        return result
    except Exception as error:  # pylint: disable=broad-exception-caught
        session.rollback()
        LOGGER.exception("period_signals_brief_failed")
        return {"state": "error", "terminal_reason": f"error:{type(error).__name__}",
                "periods": {}, "run": {"calls": 0, "usd": 0.0}}
