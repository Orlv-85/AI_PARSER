"""Daily AI Signals run: membership, bounded extraction, reconciliation and snapshot recompute.

The digest is never written here; signals have their own tables, ledger and run report.
"""
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

from app.core.daily_signals_entities import is_stopped, join, name_tokens
from app.core.daily_signals_extract import (
    EXTRACTION_VERSION,
    MAX_INPUT_BYTES,
    ExtractionInvalid,
    byte_bound,
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
        if self.repo.get_cached(article.id, content_hash) is not None:
            self.counts["cached"] += 1
            return False
        row = self.repo.get_signal(article.id)
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
        text = source_text(article.title, article.content)
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
                self.repo.save_failure(article, content_hash=content_hash, status="failed",
                                       reason="attempt_incomplete", retry_used=retry)
                return "pending"
            try:
                extraction = parse_extraction(text, data, published)
            except ExtractionInvalid as error:
                reasons.append(str(error))
                continue
            self.repo.save_extraction(article, extraction, content_hash=content_hash,
                                      provenance={"model": data.get("model"),
                                                  "recovered": bool(reasons), "retry": retry})
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
                  options: RunOptions, report: dict[str, Any], counts: Counter[str]) -> None:
    extractor = _Extractor(repo, ledger, counts)
    try:
        for day in run_days(options):
            for article in repo.scope_articles(day):
                content_hash = fingerprint(source_text(article.title, article.content))
                if not extractor.pending(article, content_hash, options.retry_skipped):
                    continue
                row = repo.get_signal(article.id)
                retry = bool(options.retry_skipped and row is not None
                             and row.status == "skipped" and not row.retry_used)
                outcome = extractor.extract(article, day, retry)
                counts[outcome] += 1
                report["progress"] += outcome in ("ok", "skipped")
                session.commit()
    except LedgerStop as stop:
        session.rollback()
        report["state"] = report["terminal_reason"] = str(stop)
    finally:
        report["run"] = {"calls": ledger.run_calls(),
                         "usd": round(ledger.run_spend_micro() / 1_000_000, 6),
                         "states": ledger.run_states()}
        ledger.close()


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
        "incomplete_days": {}, "reports_written": [], "reports_unchanged": 0}
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
    if options.recompute_only:
        report["state"] = "recompute_only"
    else:
        options.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        ledger = SignalsLedger(options.cache_dir / "ledger.sqlite3", run_id=run_id, api_key=key,
                               max_calls=options.max_calls,
                               max_usd_micro=microdollars(options.max_usd),
                               deadline=started + options.max_seconds, clock=clock,
                               transport=transport)
        _extract_days(session, repo, ledger, options=options, report=report, counts=counts)
    result = repo.recompute_reports(options.report_date, all_days=options.recompute_all,
                                    now=now())
    session.commit()
    report.update(reports_written=[d.isoformat() for d in result.written],
                  reports_unchanged=result.unchanged, entities=result.entities,
                  articles=dict(sorted(counts.items())),
                  incomplete_days=_incomplete_days(repo, days, report["terminal_reason"]),
                  seconds=round(clock() - started, 1))
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
