"""Period AI Signals run: pick the periods, compute them from stored data, store changed ones.

The numbers involve no provider. The optional brief step (period_brief_run.py) is the only paid
step; nothing is written outside `period_signal_*` (signals_period.md).
"""
import logging
import time
from dataclasses import dataclass
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
from app.core.periodic.period_model import WEEK, period_bounds, week_start
from app.storage.period_signals import PeriodSignalRepo

LOGGER = logging.getLogger(__name__)
BACKFILL_MAX = 200
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


def brief_targets(options: PeriodRunOptions, weeks: list[date], *, today: date) -> list[date]:
    """Weeks that get a brief: every run week with `--with-brief`; otherwise only the latest
    completed week when the run computed it (the nightly default)."""
    if options.with_brief:
        return weeks
    latest = latest_completed_week(today)
    return [latest] if latest in weeks else []


def run_periods(session: Session, settings: Any, options: PeriodRunOptions, *,
                now: datetime | None = None, transport: httpx.BaseTransport | None = None
                ) -> dict[str, Any]:
    """One run; returns the run report. The flag off or the month kind do nothing."""
    started = time.monotonic()
    moment = now or datetime.now(UTC)
    report: dict[str, Any] = {
        "state": "ok", "kind": options.kind, "methodology_version": PERIOD_METHODOLOGY_VERSION,
        "periods": {}, "written": [], "unchanged": 0, "skipped_before_first": [],
        "brief": None}
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
