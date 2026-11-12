"""Daily orchestration; behavior and decisions: src/app/usecases/bulletin/daily.md."""
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from logging import Logger
from typing import Any, cast

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.core.bulletin.builder import Bulletin, build_bulletin
from app.core.bulletin.phrases import load_phrases
from app.core.bulletin.world_change import ASSESS_DEFAULT_MAX_USD, run_assessment
from app.core.bulletin.writer import SourceText, write_bulletin
from app.observability.logging import log_event
from app.storage.bulletin_store import BulletinRepo
from app.storage.bulletin_texts import load_sources
from app.storage.world_change import WorldChangeRepo
from app.usecases.bulletin.day_input import load_day_input
from app.usecases.bulletin.writer_run import WRITER_MAX_USD_PER_DAY


@dataclass
class PreparedBulletin:
    bulletin: Bulletin | None
    reason: str | None
    library: dict[str, Any]
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
    library = load_phrases()
    if data is None:
        return PreparedBulletin(None, "no_digest", library, {"assessed": 0, "digest_articles": 0})
    result = build_bulletin(data, library)
    numbers = {"assessed": sum(1 for c in data.candidates if c.origin == "digest"),
               "digest_articles": data.digest_articles}
    log_event(logger, event="bulletin_assessed_share", date=day.isoformat(), **numbers)
    texts = load_sources(session, result.bulletin) if write and result.bulletin else {}
    return PreparedBulletin(result.bulletin, result.reason, library, numbers, texts)


def write_prepared(prepared: PreparedBulletin, env: BulletinEnv, today: date, *,
                   max_usd: str = WRITER_MAX_USD_PER_DAY) -> None:
    """Apply the existing writer and keep its summary beside the builder's counts."""
    if prepared.bulletin is None:
        return
    logger = env.logger
    opener = cast(Callable[..., Any], env.writer_factory)
    with opener(env.settings, today, max_usd=float(max_usd)) as writer:
        written = write_bulletin(prepared.bulletin, prepared.texts, writer.ask)
        written.summary["cost_usd"] = writer.cost_usd()
    prepared.bulletin = written.bulletin
    prepared.numbers["writer"] = written.summary
    log_event(logger, event="bulletin_writer", date=prepared.bulletin.date, **written.summary)


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


def run_daily(session: Session, env: BulletinEnv, day: date,
              today: Callable[[], date]) -> dict[str, Any]:
    """Assess, build, optionally write, store, and return the one command summary."""
    settings = env.settings
    assessment = _daily_assess(session, env, day)
    prepared = prepare_bulletin(session, settings, env.logger, day,
                                write=has_provider_key(settings, "ds_api_key"))
    writer = _daily_write(prepared, env, today())
    stored = BulletinRepo(session).save(day, bulletin=prepared.bulletin, reason=prepared.reason,
                                       numbers=prepared.numbers)
    session.commit()
    return {"date": day.isoformat(), "status": "ready" if prepared.bulletin else "skipped",
            "reason": prepared.reason, "assess": assessment, "writer": writer,
            "stored": stored, "refused": not stored}
