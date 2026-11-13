"""Recompute of the stored Daily AI Signals reports; behavior in usecases/daily/signals.md."""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta

from app.core.daily.signals_brief import digest_summary
from app.core.daily.signals_compute import (
    ArticleObs,
    DayCoverage,
    LexicalHistory,
    SnapshotInput,
    Thresholds,
    compute_snapshot,
    payload_hash,
)
from app.core.daily.signals_entities import Reconciliation, reconcile
from app.core.daily.signals_extract import EXTRACTION_VERSION
from app.core.daily.titles import digest_title
from app.storage.daily_signals import DailySignalRepo

RECOMPUTE_DAYS = 400
# A stored day this far before the latest day is settled (signals.md, "Scope and days").
SETTLED_DAYS = 14


@dataclass(frozen=True)
class RecomputeResult:
    written: list[date]
    unchanged: int
    entities: int
    reconciliation: Reconciliation
    kept: int = 0  # settled days and days that lost articles, left as stored
    lost_articles: tuple[date, ...] = ()


def digest_text(observations: Mapping[date, Sequence[ArticleObs]]) -> dict[date, list[ArticleObs]]:
    """The stored observations with the digest title and the digest summary."""
    return {day: [replace(obs, title=str(digest_title(obs.title)),
                          summary=digest_summary(obs.summary)) for obs in items]
            for day, items in observations.items()}


@dataclass(frozen=True)
class RecomputeScope:
    """Which stored days a recompute may rewrite: every comparable day (`all_days`), or the
    recent ones from `since` (the run's first day; default `until`)."""

    all_days: bool = False
    since: date | None = None


RECENT_DAYS = RecomputeScope()


@dataclass(frozen=True)
class _DayPlan:
    days: list[date]  # the days to recompute, oldest first
    kept: set[date]
    lost: set[date]


def _plan_days(repo: DailySignalRepo, until: date, scope: RecomputeScope,
               coverage: Mapping[date, DayCoverage]) -> _DayPlan:
    """The comparable signals days up to `until` in scope, minus the stored days to keep."""
    start = repo.comparable_from if scope.all_days else \
        max(repo.comparable_from, until - timedelta(days=RECOMPUTE_DAYS))
    days = sorted(d for d, c in coverage.items()
                  if start <= d <= until and c.kind == "signals")
    keep, lost = repo.stored_days_to_keep(
        days, coverage, all_days=scope.all_days,
        settled_before=min(scope.since or until, until - timedelta(days=SETTLED_DAYS)))
    return _DayPlan(days=[d for d in days if d not in keep], kept=keep, lost=lost)


def _write_changed(repo: DailySignalRepo, days: Sequence[date], base: SnapshotInput) -> list[date]:
    """Compute each day from `base`; save it when missing or its payload hash changed."""
    written = []
    for day in days:
        payload = compute_snapshot(replace(base, day=day))
        digest = payload_hash(payload)
        stored = repo.get_report(day)
        if stored is not None and stored.payload_hash == digest:
            continue
        repo.save_report(day, payload, digest)
        written.append(day)
    return written


def recompute_reports(repo: DailySignalRepo, until: date, scope: RecomputeScope = RECENT_DAYS, *,
                      now: datetime | None = None,
                      thresholds: Thresholds | None = None) -> RecomputeResult:
    """Reconcile entities and recompute every comparable published day up to `until`;
    write only reports that are missing or whose payload hash changed.

    A stored day before `since` (the run's first day; default `until`) and more than
    SETTLED_DAYS before `until` with a settled status is left as stored unless `all_days`.
    A day that lost matched articles since its snapshot is left as stored in every mode."""
    evidence, rows = repo.load_evidence()
    result = reconcile(evidence, repo.overrides())
    ids = repo.apply_reconciliation(result, rows)
    coverage = repo.coverage()
    plan = _plan_days(repo, until, scope, coverage)
    t = thresholds or Thresholds()
    needed = {d - timedelta(days=i) for d in plan.days for i in range(2 * t.window_days)}
    base = SnapshotInput(
        day=until, observations=digest_text(repo.observations(result, rows, needed)),
        coverage=coverage, entities=result.entities, entity_ids=ids,
        extraction_version=EXTRACTION_VERSION, generated_at=now or datetime.now(UTC),
        comparable_from=repo.comparable_from, thresholds=t,
        history=LexicalHistory(repo.history_texts(until)))
    written = _write_changed(repo, plan.days, base)
    return RecomputeResult(written=written, unchanged=len(plan.days) - len(written),
                           entities=len(result.entities), reconciliation=result,
                           kept=len(plan.kept), lost_articles=tuple(sorted(plan.lost)))
