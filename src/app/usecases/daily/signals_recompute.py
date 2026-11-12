"""Recompute of the stored Daily AI Signals reports; behavior in usecases/daily/signals.md."""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta

from app.core.daily.signals_brief import digest_summary
from app.core.daily.signals_compute import (
    ArticleObs,
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
    all_days, since = scope.all_days, scope.since
    start = repo.comparable_from if all_days else \
        max(repo.comparable_from, until - timedelta(days=RECOMPUTE_DAYS))
    targets = sorted(d for d, c in coverage.items()
                     if start <= d <= until and c.kind == "signals")
    keep, lost = repo.stored_days_to_keep(targets, coverage, all_days=all_days, settled_before=min(
        since or until, until - timedelta(days=SETTLED_DAYS)))
    targets = [d for d in targets if d not in keep]
    t = thresholds or Thresholds()
    span = 2 * t.window_days
    needed = {d - timedelta(days=i) for d in targets for i in range(span)}
    observations = digest_text(repo.observations(result, rows, needed))
    history = LexicalHistory(repo.history_texts(until))
    written, unchanged = [], 0
    generated = now or datetime.now(UTC)
    for day in targets:
        payload = compute_snapshot(SnapshotInput(
            day=day, observations=observations, coverage=coverage, entities=result.entities,
            entity_ids=ids, extraction_version=EXTRACTION_VERSION, generated_at=generated,
            comparable_from=repo.comparable_from, thresholds=t, history=history))
        digest = payload_hash(payload)
        stored = repo.get_report(day)
        if stored is not None and stored.payload_hash == digest:
            unchanged += 1
            continue
        repo.save_report(day, payload, digest)
        written.append(day)
    return RecomputeResult(written=written, unchanged=unchanged,
                           entities=len(result.entities), reconciliation=result,
                           kept=len(keep), lost_articles=tuple(sorted(lost)))
