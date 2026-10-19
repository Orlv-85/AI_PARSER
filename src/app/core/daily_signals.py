"""Daily AI Signals run: membership, bounded extraction, reconciliation and snapshot recompute.

The digest is never written here; signals have their own tables, ledger and run report.
Code map, tables, versions and invariants: daily_signals.md next to this file.
"""
import json
import logging
import time
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.daily_signals_brief import (
    BRIEF_MAX_USD_PER_DAY,
    BRIEF_PRICES,
    BRIEF_VERSION,
    MAX_OUTPUT,
    BriefInvalid,
    PacketTooLarge,
    brief_packet,
    brief_payload,
    input_hash,
    parse_brief,
)
from app.core.daily_signals_brief import request_body as brief_body
from app.core.daily_signals_brief import request_key as brief_key
from app.core.daily_signals_entities import is_stopped, join, name_tokens
from app.core.daily_signals_extract import (
    EXTRACTION_VERSION,
    MAX_INPUT_BYTES,
    ExtractionInvalid,
    byte_bound,
    input_kind,
    parse_extraction,
    request_body,
    reservation_micro,
    signals_request_key,
    source_text,
)
from app.storage.daily_signals import DailySignalRepo
from app.storage.daily_signals_ledger import LedgerStop, SignalsLedger
from app.storage.legacy_cleanup import fingerprint, private_write
from app.storage.models_sql import AIEntity, AIEntityOverride, Article
from app.storage.reenrich_pilot_journal import microdollars

LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class RunOptions:  # pylint: disable=too-many-instance-attributes
    report_date: date
    backfill_days: int = 1
    max_calls: int = 200
    max_seconds: int = 2700
    max_usd: str = "0.50"
    cache_dir: Path = Path("data/daily-signals")
    recompute_only: bool = False
    recompute_all: bool = False
    retry_skipped: bool = False


def run_days(options: RunOptions) -> list[date]:
    """Target days, oldest first (backfill includes history-only days)."""
    return [options.report_date - timedelta(days=i)
            for i in range(options.backfill_days - 1, -1, -1)]


class _Extractor:
    def __init__(self, repo: DailySignalRepo, ledger: SignalsLedger, counts: Counter[str]):
        self.repo = repo
        self.ledger = ledger
        self.counts = counts

    def pending(self, article: Article, content_hash: str, retry_skipped: bool) -> bool:
        if self.repo.get_cached(article, content_hash) is not None:
            self.counts["cached"] += 1
            return False
        row = self.repo.get_signal(article)
        if row is not None and row.status == "skipped" and row.content_hash == content_hash:
            if retry_skipped and not row.retry_used and (row.reason or "").startswith(
                    "invalid_output"):
                return True
            self.counts["skipped_before"] += 1
            return False
        return True

    def call(self, article: Article, body: dict[str, Any], scope_day: date) -> Any:
        """Provider answer data for a 200 response, or None (attempt failed, stays pending)."""
        result = self.ledger.dispatch(
            body, request_key=signals_request_key(body), reserved_micro=reservation_micro(body),
            article_id=article.id, version=EXTRACTION_VERSION, scope_day=scope_day.isoformat())
        self.counts["replayed" if result.replayed else "dispatched"] += 1
        if result.state != "response":
            self.counts[f"attempt_{result.state}"] += 1
            return None
        return result.data

    def extract(self, article: Article, scope_day: date, retry: bool) -> str:
        text = source_text(article.title, article.content, article.summary)
        content_hash = fingerprint(text)
        published = article.published_at.date() if article.published_at else None
        base = request_body(text, retry=retry)
        if byte_bound(base) > MAX_INPUT_BYTES:
            self.repo.save_failure(article, content_hash=content_hash, status="skipped",
                                   reason="input_too_large")
            return "skipped"
        reasons = []
        # A retry's recovery body differs too, so a saved invalid answer is never replayed.
        for body in (base, request_body(text, recovery=True, retry=retry)):
            data = self.call(article, body, scope_day)
            if data is None:
                # An incomplete retry keeps the row skipped with its retry unused (F11); the
                # next --retry-skipped sends the same retry bodies again.
                if not retry:
                    self.repo.save_failure(article, content_hash=content_hash, status="failed",
                                           reason="attempt_incomplete")
                return "pending"
            try:
                extraction = parse_extraction(text, data, published)
            except ExtractionInvalid as error:
                reasons.append(str(error))
                continue
            self.repo.save_extraction(article, extraction, content_hash=content_hash,
                                      provenance={"model": data.get("model"),
                                                  "recovered": bool(reasons), "retry": retry,
                                                  "input": input_kind(article.content,
                                                                      article.summary,
                                                                      article.title)})
            return "ok"
        self.repo.save_failure(article, content_hash=content_hash, status="skipped",
                               reason="invalid_output:" + ",".join(reasons), retry_used=retry)
        return "skipped"


def _gate(settings: Any, options: RunOptions, key: str) -> str | None:
    """Terminal state before any work, or None. The flag gates paid extraction only."""
    if options.recompute_only:
        return None
    if not settings.daily_signals_enabled:
        return "disabled"
    return None if key else "missing_provider_key"


def _extract_days(session: Session, repo: DailySignalRepo, ledger: SignalsLedger, *,
                  options: RunOptions, report: dict[str, Any], counts: Counter[str]) -> int:
    """Extract pending articles of the run days; returns the run spend in microdollars."""
    extractor = _Extractor(repo, ledger, counts)
    attempted: set[tuple[int, str, str]] = set()
    try:
        for day in run_days(options):
            for article in repo.scope_articles(day):
                content_hash = fingerprint(source_text(article.title, article.content,
                                                       article.summary))
                if not extractor.pending(article, content_hash, options.retry_skipped):
                    continue
                # An article on several backfill days is attempted once per invocation (F12).
                identity = (article.id, article.url_canonical_hash, content_hash)
                if identity in attempted:
                    counts["attempted_before"] += 1
                    continue
                attempted.add(identity)
                row = repo.get_signal(article)
                retry = bool(options.retry_skipped and row is not None
                             and row.status == "skipped" and not row.retry_used
                             and row.content_hash == content_hash)
                outcome = extractor.extract(article, day, retry)
                counts[outcome] += 1
                report["progress"] += outcome in ("ok", "skipped")
                session.commit()
    except LedgerStop as stop:
        session.rollback()
        report["state"] = report["terminal_reason"] = str(stop)
    finally:
        spend = int(ledger.run_spend_micro())
        report["run"] = {"calls": ledger.run_calls(), "usd": round(spend / 1_000_000, 6),
                         "states": ledger.run_states()}
        ledger.close()
    return spend


@dataclass(frozen=True)
class _BriefRun:
    ledger: SignalsLedger
    model: str
    now: Callable[[], datetime]


def _brief_targets(repo: DailySignalRepo, options: RunOptions) -> list[date]:
    """Run days with a usable snapshot, plus D-1 in a one-day run without a current `ok` brief."""
    days = run_days(options)
    if options.backfill_days == 1:
        before = options.report_date - timedelta(days=1)
        row = repo.get_brief(before)
        if row is None or row.status != "ok" or row.brief_version != BRIEF_VERSION:
            days.insert(0, before)
    targets = []
    for day in days:
        stored = repo.get_report(day)
        if repo.kind(day) == "signals" and stored is not None and stored.status != "unavailable":
            targets.append(day)
    return targets


def _brief_day(session: Session, repo: DailySignalRepo, run: _BriefRun, day: date) -> str:
    """Generate (or reuse) one day's brief; returns its report state."""
    stored = repo.get_report(day)
    assert stored is not None
    try:
        packet, id_map = brief_packet(json.loads(stored.payload), repo.digest_items(day))
    except PacketTooLarge:
        return "skipped:packet_too_large"
    digest = input_hash(packet, run.model)
    row = repo.get_brief(day)
    if row is not None and row.input_hash == digest:
        return "cached"
    reasons: list[str] = []
    for _ in range(2):
        body = brief_body(packet, run.model, recovery=reasons[-1] if reasons else None)
        result = run.ledger.dispatch(body, request_key=brief_key(body),
                                     reserved_micro=run.ledger.bound_micro(body, MAX_OUTPUT),
                                     version=BRIEF_VERSION, scope_day=day.isoformat())
        if result.state != "response":
            return f"skipped:attempt_{result.state}"
        try:
            sentences = parse_brief(result.data, packet, run.model)
        except BriefInvalid as error:
            reasons.append(str(error))
            continue
        repo.save_brief(day, brief_version=BRIEF_VERSION, model=run.model, input_hash=digest,
                        status="ok", payload=brief_payload(sentences, id_map))
        session.commit()
        return "ok"
    repo.save_brief(day, brief_version=BRIEF_VERSION, model=run.model, input_hash=digest,
                    status="invalid", payload={}, reason=",".join(reasons)[:1000])
    session.commit()
    return "invalid"


def _briefs(session: Session, repo: DailySignalRepo, settings: Any, options: RunOptions, *,
            extraction_micro: int, ledger_options: dict[str, Any]) -> dict[str, Any]:
    """The brief step of a paid run (007 FR-001..FR-003, FR-008). `--max-usd` is the run total:
    briefs get what extraction left, at most BRIEF_MAX_USD_PER_DAY per target day."""
    model = settings.daily_signals_brief_model
    out: dict[str, Any] = {"model": model, "days": {}, "run": {"calls": 0, "usd": 0.0},
                           "terminal_reason": None}
    targets = _brief_targets(repo, options)
    if not targets:
        return out
    cap = min(microdollars(BRIEF_MAX_USD_PER_DAY) * len(targets),
              microdollars(options.max_usd) - extraction_micro)
    prices = BRIEF_PRICES.get(model)
    skip = "brief_model_unpriced" if prices is None else \
        "brief_budget_exhausted" if cap <= 0 else None
    if skip is not None:
        out["days"] = {d.isoformat(): f"skipped:{skip}" for d in targets}
        out["terminal_reason"] = skip
        return out
    assert prices is not None
    ledger = SignalsLedger(max_calls=2 * len(targets), max_usd_micro=cap, prices=prices,
                           **ledger_options)
    run = _BriefRun(ledger=ledger, model=model, now=lambda: datetime.now(UTC))
    try:
        for index, day in enumerate(targets):
            try:
                out["days"][day.isoformat()] = _brief_day(session, repo, run, day)
            except LedgerStop as stop:
                session.rollback()
                out["terminal_reason"] = str(stop)
                for rest in targets[index:]:
                    out["days"][rest.isoformat()] = f"skipped:{stop}"
                break
    finally:
        out["run"] = {"calls": ledger.run_calls(),
                      "usd": round(ledger.run_spend_micro() / 1_000_000, 6)}
        ledger.close()
    return out


def _incomplete_days(repo: DailySignalRepo, days: list[date],
                     terminal: str | None) -> dict[str, dict[str, Any]]:
    out = {}
    coverage = repo.coverage()
    for day in days:
        cov = coverage.get(day)
        if cov is not None and not cov.complete():
            out[day.isoformat()] = {
                "items": cov.items, "matched": cov.matched, "extracted": cov.extracted,
                "failed": cov.failed, "skipped": cov.skipped, "pending": cov.pending,
                "reason": terminal or ("pending" if cov.pending else "skipped_or_unmatched")}
    return out


def run_signals(session: Session, settings: Any, options: RunOptions, *,
                transport: httpx.BaseTransport | None = None,
                clock: Callable[[], float] = time.monotonic,
                now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> dict[str, Any]:
    """One bounded signals run; returns the run report (no key, no article text)."""
    started = clock()
    run_id = now().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    days = run_days(options)
    report: dict[str, Any] = {
        "run_id": run_id, "report_date": options.report_date.isoformat(),
        "extraction_version": EXTRACTION_VERSION, "state": "ok", "terminal_reason": None,
        "days": [d.isoformat() for d in days], "missing_days": [],
        "run": {"calls": 0, "usd": 0.0, "states": {}}, "articles": {}, "progress": 0,
        "incomplete_days": {}, "reports_written": [], "reports_unchanged": 0, "brief": None}
    repo = DailySignalRepo(session, comparable_from=settings.daily_signals_comparable_from,
                           publisher_overrides=settings.weekly_publisher_overrides)
    key = settings.ds_api_key.get_secret_value().strip() if settings.ds_api_key else ""
    gate = _gate(settings, options, key)
    if gate is not None:
        report["state"] = gate
        return report
    for day in days:
        if not repo.replace_membership(day):
            report["missing_days"].append(day.isoformat())
        session.commit()
    counts: Counter[str] = Counter()
    extraction_micro = 0
    ledger_options = {"path": options.cache_dir / "ledger.sqlite3", "api_key": key,
                      "deadline": started + options.max_seconds, "clock": clock,
                      "transport": transport}
    if options.recompute_only:
        report["state"] = "recompute_only"
    else:
        options.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        ledger = SignalsLedger(run_id=run_id, max_calls=options.max_calls,
                               max_usd_micro=microdollars(options.max_usd), **ledger_options)
        extraction_micro = _extract_days(session, repo, ledger, options=options, report=report,
                                         counts=counts)
    # Through the latest completed day, so a backfill never leaves later reports stale (F1).
    until = max(options.report_date, now().date() - timedelta(days=1))
    result = repo.recompute_reports(until, all_days=options.recompute_all, now=now())
    session.commit()
    report.update(reports_written=[d.isoformat() for d in result.written],
                  reports_unchanged=result.unchanged, entities=result.entities,
                  articles=dict(sorted(counts.items())),
                  incomplete_days=_incomplete_days(repo, days, report["terminal_reason"]))
    if not options.recompute_only:
        try:
            brief_ledger = {**ledger_options, "run_id": run_id + "-brief"}
            report["brief"] = _briefs(session, repo, settings, options,
                                      extraction_micro=extraction_micro,
                                      ledger_options=brief_ledger)
        except Exception as error:  # pylint: disable=broad-exception-caught
            # A brief failure never changes the extraction result or the stored snapshots.
            session.rollback()
            LOGGER.exception("daily_signals_brief_failed")
            report["brief"] = {"model": getattr(settings, "daily_signals_brief_model", None),
                               "days": {},
                               "run": {"calls": 0, "usd": 0.0},
                               "terminal_reason": f"error:{type(error).__name__}"}
    report["seconds"] = round(clock() - started, 1)
    if not options.recompute_only:
        runs = options.cache_dir / "runs"
        runs.mkdir(parents=True, exist_ok=True, mode=0o700)
        private_write(runs / f"{run_id}.json", report)
    return report


# Operator entity commands (plan Decision 2, "Operator CLI"); no provider calls, flag not needed.
class EntityCommandError(ValueError):
    """The entity command cannot be applied; the message says why."""


def _selector(repo: DailySignalRepo, entity_id: int) -> tuple[AIEntity, str, str, str]:
    """(entity, type_group, base_key, vendor_class) of the selector that resolves to the entity."""
    entity = repo.session.get(AIEntity, entity_id)
    if entity is None:
        raise EntityCommandError(f"entity {entity_id} not found")
    if entity.entity_key.startswith("manual:"):
        owner = next((o for o in repo.overrides()
                      if o.target_entity_key == entity.entity_key), None)
        if owner is None:
            raise EntityCommandError(f"entity {entity_id} has no override; recompute first")
        return entity, owner.type_group, owner.target_base_key, owner.target_vendor_class
    # `auto:<g>:<base>[:<class>|:?]`: the suffix names the vendor part; an unsuffixed entity is
    # named by its class (or "" without one). See `selector_matches`.
    parts = entity.entity_key.split(":")
    vendor = parts[3] if len(parts) > 3 else entity.vendor_class
    return entity, entity.type_group, parts[2], vendor


def merge_entities(repo: DailySignalRepo, source_id: int, target_id: int) -> AIEntityOverride:
    source, group, base, vendor = _selector(repo, source_id)
    target, target_group, target_base, target_vendor = _selector(repo, target_id)
    if source.entity_key.startswith("manual:"):
        raise EntityCommandError(f"entity {source_id} is already an override target; "
                                 "delete that override first")
    if group != target_group:
        raise EntityCommandError(f"type groups differ: {group} vs {target_group}")
    manual = target.entity_key if target.entity_key.startswith("manual:") else None
    return repo.add_override(kind="merge", type_group_=group, match_key=base, vendor_class=vendor,
                             target_base_key=target_base, target_vendor_class=target_vendor,
                             target_entity_key=manual,
                             note=f"merge {source.display_name} -> {target.display_name}"[:255])


def alias_entity(repo: DailySignalRepo, entity_id: int, name: str) -> AIEntityOverride:
    target, group, base, vendor = _selector(repo, entity_id)
    alias = join(name_tokens(name, target.type))
    if is_stopped(name_tokens(name, target.type)):
        raise EntityCommandError(f"alias {name!r} is empty or a generic term")
    manual = target.entity_key if target.entity_key.startswith("manual:") else None
    return repo.add_override(kind="alias", type_group_=group, match_key=alias,
                             target_base_key=base, target_vendor_class=vendor,
                             target_entity_key=manual,
                             note=f"alias {name} -> {target.display_name}"[:255])
