"""Period AI Signals run: pick the periods, compute them from stored data, store changed ones.

No provider is involved and nothing is written outside `period_signal_*` (signals_period.md).
"""
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.periodic.period_compute import (
    PERIOD_METHODOLOGY_VERSION,
    compute_period,
    payload_hash,
)
from app.core.periodic.period_model import WEEK, period_bounds, week_start
from app.storage.period_signals import PeriodSignalRepo

BACKFILL_MAX = 200


class PeriodRunError(ValueError):
    """The requested period cannot be computed; the message says why."""


@dataclass(frozen=True)
class PeriodRunOptions:
    kind: str = WEEK
    period: date | None = None
    backfill: int = 1
    recompute_all: bool = False


def first_week(comparable_from: date) -> date:
    """First computable week: the first full Monday-Sunday week inside the comparable range."""
    monday: date = week_start(comparable_from)
    return monday if monday == comparable_from else monday + timedelta(days=7)


def latest_completed_week(today: date) -> date:
    """Monday of the latest week that ended before `today` (UTC)."""
    monday: date = week_start(today)
    return monday - timedelta(days=7)


def target_weeks(options: PeriodRunOptions, *, today: date, comparable_from: date
                 ) -> tuple[list[date], list[date]]:
    """(weeks to compute oldest first, weeks dropped for being before the first week)."""
    first, latest = first_week(comparable_from), latest_completed_week(today)
    if options.period is not None:
        end = week_start(options.period)
        if end > latest:
            raise PeriodRunError("only completed weeks can be computed")
        if end < first:
            raise PeriodRunError(f"weeks before {first.isoformat()} are history only")
    else:
        end = latest
    if options.recompute_all:
        wanted = [first + timedelta(days=7 * i) for i in range((latest - first).days // 7 + 1)]
    else:
        wanted = [end - timedelta(days=7 * i) for i in range(options.backfill - 1, -1, -1)]
    return [w for w in wanted if w >= first], [w for w in wanted if w < first]


def run_periods(session: Session, settings: Any, options: PeriodRunOptions, *,
                now: datetime | None = None) -> dict[str, Any]:
    """One run; returns the run report. The flag off or the month kind do nothing."""
    started = time.monotonic()
    moment = now or datetime.now(UTC)
    report: dict[str, Any] = {
        "state": "ok", "kind": options.kind, "methodology_version": PERIOD_METHODOLOGY_VERSION,
        "periods": {}, "written": [], "unchanged": 0, "skipped_before_first": []}
    if not settings.period_signals_enabled:
        report["state"] = "disabled"
        return report
    if options.kind != WEEK:
        report["state"] = "not_built"
        return report
    weeks, early = target_weeks(options, today=moment.date(),
                                comparable_from=settings.daily_signals_comparable_from)
    report["skipped_before_first"] = [w.isoformat() for w in early]
    repo = PeriodSignalRepo(session, comparable_from=settings.daily_signals_comparable_from,
                            publisher_overrides=settings.weekly_publisher_overrides)
    ctx = repo.context()
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
    report["seconds"] = round(time.monotonic() - started, 1)
    return report
