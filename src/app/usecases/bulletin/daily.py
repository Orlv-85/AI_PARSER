"""Daily orchestration; behavior and decisions: src/app/usecases/bulletin/daily.md."""
import sqlite3
from collections import Counter
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import asdict, dataclass, field
from datetime import date
from logging import Logger
from typing import Any, cast

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.core.bulletin.builder import READY_STATUSES, Bulletin, DayInput, build_bulletin
from app.core.bulletin.phrases import PhraseLibrary, load_phrases
from app.core.bulletin.repeats import RepeatsResult, check_repeats
from app.core.bulletin.world_change import ASSESS_DEFAULT_MAX_USD, run_assessment
from app.core.bulletin.writer import SourceText, WriterResult, write_bulletin
from app.observability.logging import log_event
from app.storage.bulletin_store import BulletinRepo
from app.storage.bulletin_texts import load_sources
from app.storage.world_change import WorldChangeRepo
from app.usecases.bulletin.day_input import load_day_input, published_stories
from app.usecases.bulletin.writer_run import WRITER_MAX_USD_PER_DAY

JOURNAL_UNAVAILABLE = "journal_unavailable"
JOURNAL_ERRORS = (OSError, sqlite3.Error, ValueError)  # a journal that cannot open or close


@dataclass
class PreparedBulletin:
    bulletin: Bulletin | None
    reason: str | None
    library: PhraseLibrary
    numbers: dict[str, Any]
    texts: dict[str, SourceText] = field(default_factory=dict)


@dataclass(frozen=True)
class BulletinEnv:
    """What the bulletin steps share besides the session: settings, logger, provider openers."""

    settings: Settings
    logger: Logger
    assessor_factory: Callable[..., Any] | None = None
    writer_factory: Callable[..., Any] | None = None


def assess_day(session: Session, env: BulletinEnv, day: date, *,
               max_usd: str = ASSESS_DEFAULT_MAX_USD,
               dry_run: bool = False) -> dict[str, Any] | None:
    """Shared assessment path; existing answers and journal caps remain authoritative."""
    repo = WorldChangeRepo(session)
    summary: dict[str, Any] | None
    if dry_run:
        summary = run_assessment(session, repo, None, day, dry_run=True)
    else:
        opener = cast(Callable[..., Any], env.assessor_factory)
        with opener(env.settings, env.logger, day, max_usd) as assessor:
            summary = run_assessment(session, repo, assessor, day)
    return summary


def prepare_bulletin(session: Session, settings: Settings, logger: Logger, day: date, *,
                     write: bool) -> PreparedBulletin:
    """Read and build once, optionally loading the writer's source texts."""
    data = load_day_input(session, day, include_world=settings.world_stream_in_bulletin)
    return prepare_from_input(session, logger, day, data, write=write)


def prepare_from_input(session: Session, logger: Logger, day: date, data: DayInput | None, *,
                       write: bool) -> PreparedBulletin:
    """Build from a loaded day input (None: no digest), optionally loading source texts."""
    library = load_phrases()
    if data is None:
        return PreparedBulletin(None, "no_digest", library, {"assessed": 0, "digest_articles": 0})
    result = build_bulletin(data, library)
    counts = {
        "assessed": data.digest_left_out + sum(1 for c in data.candidates if c.origin == "digest"),
        "digest_articles": data.digest_articles}
    log_event(logger, event="bulletin_assessed_share", date=day.isoformat(), **counts)
    kinds = Counter(c.kind for c in data.candidates if c.world_change != "none")
    numbers: dict[str, Any] = {**counts, "kinds": dict(kinds),
                               "told_before": [asdict(t) for t in data.told_before]}
    texts = load_sources(session, result.bulletin) if write and result.bulletin else {}
    return PreparedBulletin(result.bulletin, result.reason, library, numbers, texts)


def write_prepared(prepared: PreparedBulletin, env: BulletinEnv, today: date, *,
                   max_usd: str = WRITER_MAX_USD_PER_DAY) -> None:
    """Apply the existing writer and keep its summary beside the builder's counts."""
    if prepared.bulletin is None:
        return
    logger = env.logger
    written = _write_with_journal(prepared.bulletin, prepared.texts, env, today, max_usd)
    prepared.bulletin = written.bulletin
    prepared.numbers["writer"] = written.summary
    log_event(logger, event="bulletin_writer", date=prepared.bulletin.date, **written.summary)


def _write_with_journal(bulletin: Bulletin, texts: dict[str, SourceText], env: BulletinEnv,
                        today: date, max_usd: str) -> WriterResult:
    """The writer on the journal of the real day; a journal that cannot open gives title-only."""
    opener = cast(Callable[..., Any], env.writer_factory)
    limit = float(max_usd)  # a bad limit is a caller error, not a journal fault
    with ExitStack() as stack:
        try:
            writer = stack.enter_context(opener(env.settings, today, max_usd=limit))
        except JOURNAL_ERRORS:
            # Without the journal the day still gets its bulletin, from titles only.
            env.logger.exception("bulletin_writer_journal_failed")
            written = write_bulletin(bulletin, texts,
                                     lambda _body: (None, JOURNAL_UNAVAILABLE))
            written.summary["cost_usd"] = 0.0
            return written
        written = write_bulletin(bulletin, texts, writer.ask)
        written.summary["cost_usd"] = writer.cost_usd()
        opened = stack.pop_all()
    _close_journal(opened, env.logger, "bulletin_writer_journal_close_failed")
    return written


def _close_journal(opened: ExitStack, logger: Logger, event: str) -> None:
    """Close a journal after its answer is in hand; a close fault must not lose the day."""
    try:
        opened.close()
    except JOURNAL_ERRORS:
        logger.exception(event)


def has_provider_key(settings: Settings, name: str) -> bool:
    key = getattr(settings, name)
    return key is not None and bool(key.get_secret_value().strip())


def _daily_assess(session: Session, env: BulletinEnv, day: date) -> dict[str, Any]:
    if not has_provider_key(env.settings, "jev_api_key"):
        log_event(env.logger, event="bulletin_assess_skipped", date=day.isoformat(),
                  reason="missing_jev_key")
        return {"reason": "missing_jev_key"}
    return assess_day(session, env, day) or {"reason": "no_digest"}


def _daily_write(prepared: PreparedBulletin, env: BulletinEnv, today: date) -> dict[str, Any]:
    if prepared.bulletin is None:
        return {"reason": prepared.reason}
    if not has_provider_key(env.settings, "ds_api_key"):
        log_event(env.logger, event="bulletin_writer_skipped", date=prepared.bulletin.date,
                  reason="missing_ds_key")
        return {"reason": "missing_ds_key"}
    write_prepared(prepared, env, today)
    return dict(prepared.numbers["writer"])


def _repeat_check(session: Session, env: BulletinEnv, day: date, today: date,
                  data: DayInput) -> RepeatsResult:
    """The repeat check on the writer's journal of the real day; the journal opens on a call."""
    published = published_stories(session, day)
    opener = cast(Callable[..., Any], env.writer_factory)
    with ExitStack() as stack:
        writers: list[Any] = []

        def ask(body: dict[str, Any]) -> tuple[object, str | None]:
            if not writers:
                try:
                    writers.append(stack.enter_context(
                        opener(env.settings, today, max_usd=float(WRITER_MAX_USD_PER_DAY))))
                except JOURNAL_ERRORS:
                    # The check is optional: the bulletin is built without it.
                    env.logger.exception("bulletin_repeats_journal_failed")
                    return None, JOURNAL_UNAVAILABLE
            answered: tuple[object, str | None] = writers[0].ask(body)
            return answered

        result = check_repeats(data, published, ask)
        opened = stack.pop_all()
    _close_journal(opened, env.logger, "bulletin_repeats_journal_close_failed")
    return result


def run_daily(session: Session, env: BulletinEnv, day: date,
              today: Callable[[], date]) -> dict[str, Any]:
    """Assess, build, optionally write, store, and return the one command summary."""
    settings = env.settings
    assessment = _daily_assess(session, env, day)
    now = today()  # one real UTC day for the repeat check and the writer
    keyed = has_provider_key(settings, "ds_api_key")
    data = load_day_input(session, day, include_world=settings.world_stream_in_bulletin)
    # A day the builder skips gets no paid check.
    check = keyed and data is not None and data.status in READY_STATUSES
    checked = _repeat_check(session, env, day, now, data) if check and data else None
    prepared = prepare_from_input(session, env.logger, day, checked.data if checked else data,
                                  write=keyed)
    if checked:
        prepared.numbers["repeats"] = checked.summary
        log_event(env.logger, event="bulletin_repeats", date=day.isoformat(), **checked.summary)
    writer = _daily_write(prepared, env, now)
    stored = BulletinRepo(session).save(day, bulletin=prepared.bulletin, reason=prepared.reason,
                                       numbers=prepared.numbers)
    session.commit()
    return {"date": day.isoformat(), "status": "ready" if prepared.bulletin else "skipped",
            "reason": prepared.reason, "assess": assessment, "writer": writer,
            "stored": stored, "refused": not stored}
