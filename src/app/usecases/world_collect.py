"""World stream collect job (spec 018, item 5, step W4); behavior in core/world/world.md.

Reads the GDELT files of a UTC day one at a time, stores the kept candidates and the file state,
commits after every file, then prunes. Lives outside core/world/ because it imports storage.
"""
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.core.world.gdelt import (
    GDELT_BASE_URL,
    KINDS,
    MAX_CONSECUTIVE_MISSING,
    MAX_MISSING_FILES_OK,
    PAUSE_SECONDS,
    RETRY_DELAY_SECONDS,
    DayStats,
    FileResult,
    day_file_names,
    scan_file,
)
from app.observability.logging import log_event
from app.storage.world import FILE_DONE, FILE_MISSING, WorldRepo

FILE_ERROR_MISSING = "download failed or file unreadable"


@dataclass
class CollectSummary:  # pylint: disable=too-many-instance-attributes
    day: str
    files: int = 0
    skipped: int = 0
    missing: int = 0
    partial: bool = False
    rows: int = 0
    matched: int = 0
    kept: int = 0
    new: int = 0
    repeats: int = 0
    pruned_candidates: int = 0
    pruned_files: int = 0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def yesterday_utc(now: datetime | None = None) -> date:
    return ((now or datetime.now(UTC)) - timedelta(days=1)).date()


def _day_names(day: date, max_files: int | None) -> list[tuple[str, str]]:
    names = [(kind, name) for kind in KINDS for name in day_file_names(day, kind)]
    return names if max_files is None else names[:max_files]


def _not_done(names: list[tuple[str, str]], done: set[tuple[str, str]]) -> int:
    return sum(1 for kind, name in names if (name[:14], kind) not in done)


def collect_day(  # pylint: disable=too-many-arguments,too-many-locals
    session: Session,
    day: date,
    *,
    client: httpx.Client,
    own_domains: frozenset[str] = frozenset(),
    max_files: int | None = None,
    tmp_dir: Path | None = None,
    pause: float = PAUSE_SECONDS,
    retry_delay: float = RETRY_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    base_url: str = GDELT_BASE_URL,
    logger: logging.Logger | None = None,
) -> CollectSummary:
    """Collect the files of `day` that are not done yet; commit per file; prune; log a summary."""
    repo = WorldRepo(session)
    names = _day_names(day, max_files)
    done = repo.done_files(day)
    summary = CollectSummary(day=day.isoformat())
    stats = DayStats()
    consecutive_missing = 0
    for index, (kind, name) in enumerate(names):
        if (name[:14], kind) in done:
            summary.skipped += 1
            continue
        if consecutive_missing >= MAX_CONSECUTIVE_MISSING:
            rest = names[index:]
            summary.missing += _not_done(rest, done)
            summary.skipped += len(rest) - _not_done(rest, done)
            break
        if stats.files_read + stats.files_missing:
            sleep(pause)
        result = FileResult()
        found = list(scan_file(
            client, kind, name, stats=stats, result=result, own_domains=own_domains,
            tmp_dir=tmp_dir, retry_delay=retry_delay, sleep=sleep, base_url=base_url,
        ))
        created, repeats = repo.upsert_candidates(found)
        repo.record_file(
            name[:14], kind, FILE_MISSING if result.missing else FILE_DONE,
            rows=result.rows, matched=result.matched,
            error=FILE_ERROR_MISSING if result.missing else None,
        )
        session.commit()
        summary.new += created
        summary.repeats += repeats
        if result.missing:
            summary.missing += 1
            consecutive_missing += 1
        else:
            summary.files += 1
            consecutive_missing = 0
    summary.rows, summary.matched, summary.kept = stats.rows, stats.matched, stats.kept
    summary.partial = summary.missing > MAX_MISSING_FILES_OK
    summary.pruned_candidates, summary.pruned_files = repo.prune()
    session.commit()
    if logger is not None:
        log_event(logger, event="world_collect_finished", **summary.as_dict())
    return summary
