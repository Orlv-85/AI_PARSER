"""Storage for Daily AI Signals (plan Decision 4, Data Model): membership, extractions, evidence,
derived entities, overrides and stored snapshots."""
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.canonicalize import canonical_url_hash
from app.core.daily_enrichment import digest_title
from app.core.daily_signals_compute import (
    METHODOLOGY_VERSION,
    ArticleObs,
    DayCoverage,
    EntityMention,
    LexicalHistory,
    SnapshotInput,
    Thresholds,
    compute_snapshot,
    payload_hash,
)
from app.core.daily_signals_entities import (
    Mention,
    Override,
    Reconciliation,
    evidence_classes,
    join,
    name_tokens,
    reconcile,
    selectors_conflict,
    type_group,
)
from app.core.daily_signals_extract import EXTRACTION_VERSION, EXTRACTION_VERSIONS, Extraction
from app.storage.models_sql import (
    AIEntity,
    AIEntityOverride,
    Article,
    ArticleSignal,
    DailySignalReport,
    DailySignalScope,
    NewsDigestGroup,
    NewsDigestItem,
    NewsDigestReport,
    SignalMention,
)
from app.storage.weekly import publisher_group

RECOMPUTE_DAYS = 400


class OverrideConflict(ValueError):
    """A selector of the new override is already owned by another override."""


def _now() -> datetime:
    return datetime.now(UTC)


def _same_article(table: Any) -> Any:
    """Join condition on the article identity (id and canonical URL hash, F9)."""
    return (Article.id == table.article_id) & \
        (Article.url_canonical_hash == table.url_canonical_hash)


def _version_rank(version: str) -> int:
    return EXTRACTION_VERSIONS.index(version) if version in EXTRACTION_VERSIONS else -1


@dataclass(frozen=True)
class RecomputeResult:
    written: list[date]
    unchanged: int
    entities: int
    reconciliation: Reconciliation


class DailySignalRepo:
    def __init__(self, session: Session, *, comparable_from: date,
                 publisher_overrides: Mapping[str, str] | None = None) -> None:
        self.session = session
        self.comparable_from = comparable_from
        self.publisher_overrides = dict(publisher_overrides or {})

    def kind(self, day: date) -> str:
        return "signals" if day >= self.comparable_from else "history"

    # Membership --------------------------------------------------------------------------------
    def digest_urls(self, day: date) -> list[str] | None:
        """Digest item URLs of a published day, or None when no digest exists (missing day)."""
        report_id = self.session.scalar(
            select(NewsDigestReport.id).where(NewsDigestReport.report_date == day))
        if report_id is None:
            return None
        return list(self.session.scalars(
            select(NewsDigestItem.url).join(NewsDigestGroup)
            .where(NewsDigestGroup.report_id == report_id)
            .order_by(NewsDigestGroup.position, NewsDigestItem.position)))

    def _match(self, urls: list[str]) -> dict[str, Article]:
        exact = self.session.scalars(select(Article).where(Article.url.in_(urls)))
        found = {a.url: a for a in exact}
        missing = {canonical_url_hash(u): u for u in urls if u not in found}
        if missing:
            for article in self.session.scalars(
                    select(Article).where(Article.url_canonical_hash.in_(list(missing)))):
                found[missing[article.url_canonical_hash]] = article
        return found

    def replace_membership(self, day: date) -> bool:
        """Replace day D's scope from its stored digest; False for a missing day."""
        urls = self.digest_urls(day)
        if urls is None:
            return False
        matched = self._match(urls)
        wanted: dict[int, tuple[str, str, str]] = {}
        for url in urls:
            article = matched.get(url)
            if article is not None and article.id not in wanted:
                wanted[article.id] = (publisher_group(url, self.publisher_overrides), url,
                                      article.url_canonical_hash)
        current = {row.article_id: row for row in self.session.scalars(
            select(DailySignalScope).where(DailySignalScope.scope_day == day))}
        removed = [aid for aid in current if aid not in wanted]
        for aid in removed:
            self.session.delete(current[aid])
        kind = self.kind(day)
        added = []
        for aid, (publisher, url, url_hash) in wanted.items():
            row = current.get(aid)
            if row is None:
                self.session.add(DailySignalScope(scope_day=day, article_id=aid,
                                                  url_canonical_hash=url_hash, kind=kind,
                                                  publisher=publisher, item_url=url))
                added.append(aid)
            elif (row.kind, row.publisher, row.item_url, row.url_canonical_hash) != \
                    (kind, publisher, url, url_hash):
                row.kind, row.publisher, row.item_url = kind, publisher, url
                row.url_canonical_hash = url_hash  # a stale row of a reused id is taken over
                added.append(aid)
        self.session.flush()
        for aid in removed:
            article = self.session.get(Article, aid)
            if article is not None:
                self.session.execute(delete(SignalMention).where(
                    SignalMention.scope_day == day, SignalMention.article_id == aid,
                    SignalMention.url_canonical_hash == article.url_canonical_hash))
        for aid in added:
            self._rewrite_day_rows(day, aid)
        self.session.flush()
        return True

    def scope_articles(self, day: date) -> list[Article]:
        return list(self.session.scalars(
            select(Article).join(DailySignalScope, _same_article(DailySignalScope))
            .where(DailySignalScope.scope_day == day).order_by(Article.id)))

    # Extractions and evidence ------------------------------------------------------------------
    def _signal(self, article_id: int, version: str) -> ArticleSignal | None:
        return self.session.scalar(select(ArticleSignal).where(
            ArticleSignal.article_id == article_id, ArticleSignal.extraction_version == version))

    def get_signal(self, article: Article,
                   version: str = EXTRACTION_VERSION) -> ArticleSignal | None:
        """The article's extraction row; a row left by a deleted article with the same id
        (SQLite reuses ids and does not enforce the cascade here) does not count."""
        row = self._signal(article.id, version)
        return row if row is not None and \
            row.url_canonical_hash == article.url_canonical_hash else None

    def get_cached(self, article: Article, content_hash: str,
                   version: str = EXTRACTION_VERSION) -> ArticleSignal | None:
        """An `ok` extraction of the same content, reusable without a provider call."""
        row = self.get_signal(article, version)
        return row if row is not None and row.status == "ok" and \
            row.content_hash == content_hash else None

    def _signal_row(self, article: Article, version: str, content_hash: str) -> ArticleSignal:
        row = self._signal(article.id, version)
        if row is None:
            row = ArticleSignal(article_id=article.id, extraction_version=version)
            self.session.add(row)
        if row.url_canonical_hash != article.url_canonical_hash:
            # New row, or the stale row of a deleted article whose id was reused: start over.
            row.url_canonical_hash = article.url_canonical_hash
            row.status, row.reason, row.attempts, row.retry_used = "failed", None, 0, False
            row.event_type = row.novelty_claim = None
            row.payload, row.provenance = "{}", "{}"
        row.content_hash = content_hash
        row.updated_at = _now()
        return row

    def save_extraction(self, article: Article, extraction: Extraction, *, content_hash: str,
                        version: str = EXTRACTION_VERSION,
                        provenance: Mapping[str, Any] | None = None) -> ArticleSignal:
        row = self._signal_row(article, version, content_hash)
        row.status, row.reason = "ok", None
        row.attempts += 1
        row.event_type, row.novelty_claim = extraction.event_type, extraction.novelty_claim
        row.payload = json.dumps(extraction.payload(), sort_keys=True)
        row.provenance = json.dumps(dict(provenance or {}), sort_keys=True)
        self.session.flush()
        # A re-extraction in version X replaces all version-X rows of the article (every day).
        self.session.execute(delete(SignalMention).where(
            SignalMention.article_id == article.id,
            SignalMention.url_canonical_hash == article.url_canonical_hash,
            SignalMention.extraction_version == version))
        days = self.session.scalars(select(DailySignalScope.scope_day).where(
            DailySignalScope.article_id == article.id,
            DailySignalScope.url_canonical_hash == article.url_canonical_hash))
        for day in sorted(set(days)):
            self._insert_rows(article, day, version, extraction.payload())
        self.session.flush()
        return row

    def save_failure(self, article: Article, *, content_hash: str, status: str, reason: str,
                     version: str = EXTRACTION_VERSION, retry_used: bool = False) -> ArticleSignal:
        if status not in ("failed", "skipped"):
            raise ValueError(status)
        row = self._signal_row(article, version, content_hash)
        row.status, row.reason = status, reason[:255]
        row.attempts += 1
        row.retry_used = row.retry_used or retry_used
        self.session.flush()
        return row

    def _rewrite_day_rows(self, day: date, article_id: int) -> None:
        article = self.session.get(Article, article_id)
        if article is None:
            return
        self.session.execute(delete(SignalMention).where(
            SignalMention.scope_day == day, SignalMention.article_id == article_id,
            SignalMention.url_canonical_hash == article.url_canonical_hash))
        for row in self.session.scalars(select(ArticleSignal).where(
                ArticleSignal.article_id == article_id,
                ArticleSignal.url_canonical_hash == article.url_canonical_hash,
                ArticleSignal.status == "ok")):
            self._insert_rows(article, day, row.extraction_version, json.loads(row.payload))

    def _insert_rows(self, article: Article, day: date, version: str,
                     payload: Mapping[str, Any]) -> None:
        scope = self.session.scalar(select(DailySignalScope).where(
            DailySignalScope.scope_day == day, DailySignalScope.article_id == article.id,
            DailySignalScope.url_canonical_hash == article.url_canonical_hash))
        publisher = scope.publisher if scope is not None else \
            publisher_group(article.url, self.publisher_overrides)
        seen: set[tuple[str, str]] = set()
        for entity in payload.get("entities", []):
            key = join(name_tokens(entity["canonical_name"], entity["entity_type"]))
            if (key, type_group(entity["entity_type"])) in seen:
                continue  # validation merges duplicates; never violate the unique key
            seen.add((key, type_group(entity["entity_type"])))
            self.session.add(SignalMention(
                article_id=article.id, url_canonical_hash=article.url_canonical_hash,
                scope_day=day, kind=self.kind(day), extraction_version=version,
                publisher=publisher, surface_name=entity["name"],
                canonical_name=entity["canonical_name"], name_key=key, base_key=key,
                family_key=key, type_group=type_group(entity["entity_type"]),
                entity_type=entity["entity_type"], vendor=entity["vendor"], vendor_key="",
                vendor_inferred=False, role=entity["role"], is_new=bool(entity["is_new"]),
                novelty_quote=entity["novelty_quote"], entity_key=None))

    def purge_evidence(self, article_id: int) -> int:
        """Remove the stored evidence of a deleted article (OD6); refuses for existing articles."""
        article = self.session.get(Article, article_id)
        condition = [SignalMention.article_id == article_id]
        if article is not None:
            condition.append(SignalMention.url_canonical_hash != article.url_canonical_hash)
            has_own = self.session.scalar(select(func.count(SignalMention.id)).where(
                SignalMention.article_id == article_id,
                SignalMention.url_canonical_hash == article.url_canonical_hash))
            if has_own:
                raise ValueError(f"article {article_id} still exists; its evidence is not purged")
        result = self.session.execute(delete(SignalMention).where(*condition))
        return int(getattr(result, "rowcount", 0) or 0)

    def load_evidence(self) -> tuple[list[Mention], dict[int, SignalMention]]:
        """Evidence set: per article identity, rows of its newest `ok` extraction version, even
        when that extraction has no entities (F10). An identity without an `ok` extraction row
        (deleted article) keeps the rows of its newest stored version."""
        rows = list(self.session.scalars(select(SignalMention).order_by(SignalMention.id)))
        newest: dict[tuple[int, str], int] = {}
        for article_id, url_hash, version in self.session.execute(
                select(ArticleSignal.article_id, ArticleSignal.url_canonical_hash,
                       ArticleSignal.extraction_version).where(ArticleSignal.status == "ok")):
            identity = (article_id, url_hash)
            newest[identity] = max(newest.get(identity, -2), _version_rank(version))
        stored: dict[tuple[int, str], int] = {}
        for row in rows:
            identity = (row.article_id, row.url_canonical_hash)
            if identity not in newest:
                stored[identity] = max(stored.get(identity, -2),
                                       _version_rank(row.extraction_version))
        newest.update(stored)
        chosen = {row.id: row for row in rows if _version_rank(row.extraction_version)
                  == newest[(row.article_id, row.url_canonical_hash)]}
        mentions = [Mention(
            mention_id=row.id, scope_day=row.scope_day, article_id=row.article_id,
            publisher=row.publisher, name=row.surface_name, canonical_name=row.canonical_name,
            entity_type=row.entity_type, vendor=row.vendor, role=row.role, is_new=row.is_new,
            novelty_quote=row.novelty_quote) for row in chosen.values()]
        return mentions, chosen

    # Entities and overrides --------------------------------------------------------------------
    def apply_reconciliation(self, result: Reconciliation,
                             rows: Mapping[int, SignalMention]) -> dict[str, int]:
        """Persist derived entities (stable ids) and changed mention keys; returns key -> id."""
        stored = {e.entity_key: e for e in self.session.scalars(select(AIEntity))}
        now = _now()
        for key, entity in result.entities.items():
            values = {"display_name": entity.display_name[:255], "type_group": entity.type_group,
                      "type": entity.entity_type, "vendor": entity.vendor,
                      "vendor_class": entity.vendor_class, "base_key": entity.base_key,
                      "family_key": entity.family_key, "first_seen_day": entity.first_seen_day,
                      "needs_review": entity.needs_review, "active": True}
            row = stored.get(key)
            if row is None:
                row = AIEntity(entity_key=key, created_at=now, updated_at=now, **values)
                self.session.add(row)
                stored[key] = row
            elif any(getattr(row, k) != v for k, v in values.items()):
                for k, v in values.items():
                    setattr(row, k, v)
                row.updated_at = now
        for key, row in stored.items():
            if key not in result.entities and row.active:
                row.active, row.updated_at = False, now
        for mention_id, keys in result.keys.items():
            mention = rows[mention_id]
            values = {"entity_key": result.assignments[mention_id], "base_key": keys.base_key,
                      "family_key": keys.family_key, "vendor_key": keys.vendor_key,
                      "vendor_inferred": keys.vendor_inferred, "name_key": keys.name_key}
            for k, v in values.items():
                if getattr(mention, k) != v:
                    setattr(mention, k, v)
        self.session.flush()
        return {key: row.id for key, row in stored.items()}

    def overrides(self) -> list[Override]:
        return [Override(override_id=o.id, kind=o.kind, type_group=o.type_group,
                         match_key=o.match_key, vendor_class=o.vendor_class,
                         target_base_key=o.target_base_key,
                         target_vendor_class=o.target_vendor_class,
                         target_entity_key=o.target_entity_key)
                for o in self.session.scalars(
                    select(AIEntityOverride).order_by(AIEntityOverride.id))]

    def add_override(self, *, kind: str, type_group_: str, match_key: str, target_base_key: str,
                     vendor_class: str = "", target_vendor_class: str = "",
                     target_entity_key: str | None = None,
                     note: str | None = None) -> AIEntityOverride:
        if kind not in ("alias", "merge"):
            raise ValueError(kind)
        existing = self.overrides()
        if target_entity_key is None:
            # Reuse the manual entity that already owns the target selector, if any.
            target_entity_key = next(
                (o.target_entity_key for o in existing if o.type_group == type_group_
                 and o.target_base_key == target_base_key
                 and o.target_vendor_class == target_vendor_class), None)
        candidate = Override(override_id=0, kind=kind, type_group=type_group_,
                             match_key=match_key, vendor_class=vendor_class,
                             target_base_key=target_base_key,
                             target_vendor_class=target_vendor_class,
                             target_entity_key=target_entity_key or "manual:new")
        if (match_key, vendor_class) == (target_base_key, target_vendor_class) and kind == "merge":
            raise OverrideConflict("source and target are the same selector")
        evidence = self.load_evidence()[0]
        conflict = selectors_conflict(existing, candidate, evidence_classes(evidence).resolve,
                                      reconcile(evidence).resolve_base)
        if conflict is not None:
            raise OverrideConflict(f"selector owned by override {conflict.override_id}")
        row = AIEntityOverride(kind=kind, type_group=type_group_, match_key=match_key,
                               vendor_class=vendor_class, target_base_key=target_base_key,
                               target_vendor_class=target_vendor_class,
                               target_entity_key=target_entity_key or "manual:pending",
                               note=note)
        try:
            with self.session.begin_nested():
                self.session.add(row)
                self.session.flush()
        except IntegrityError as error:
            raise OverrideConflict("an override with this selector exists") from error
        if target_entity_key is None:
            row.target_entity_key = f"manual:{row.id}"
            self.session.flush()
        return row

    def delete_override(self, override_id: int) -> bool:
        row = self.session.get(AIEntityOverride, override_id)
        if row is None:
            return False
        self.session.delete(row)
        self.session.flush()
        return True

    # Coverage, observations and reports --------------------------------------------------------
    def coverage(self) -> dict[date, DayCoverage]:
        """Per published day (digest exists): items, matched, extracted, failed, skipped."""
        items: dict[date, int] = dict(self.session.execute(
            select(NewsDigestReport.report_date, func.count(NewsDigestItem.id))
            .select_from(NewsDigestReport)
            .outerjoin(NewsDigestGroup, NewsDigestGroup.report_id == NewsDigestReport.id)
            .outerjoin(NewsDigestItem, NewsDigestItem.group_id == NewsDigestGroup.id)
            .group_by(NewsDigestReport.report_date)).all())
        scope = self.session.execute(
            select(DailySignalScope.scope_day, DailySignalScope.article_id,
                   DailySignalScope.url_canonical_hash)
            .join(Article, _same_article(DailySignalScope))).all()
        statuses: dict[tuple[int, str], str] = {}
        best: dict[tuple[int, str], int] = {}
        for article_id, url_hash, version, status in self.session.execute(
                select(ArticleSignal.article_id, ArticleSignal.url_canonical_hash,
                       ArticleSignal.extraction_version, ArticleSignal.status)):
            rank = 1000 if status == "ok" else _version_rank(version)
            if rank > best.get((article_id, url_hash), -2):
                best[(article_id, url_hash)], statuses[(article_id, url_hash)] = rank, status
        counts: dict[date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for day, article_id, url_hash in scope:
            counts[day]["matched"] += 1
            status = statuses.get((article_id, url_hash))
            if status == "ok":
                counts[day]["extracted"] += 1
            elif status in ("failed", "skipped"):
                counts[day][status] += 1
        return {day: DayCoverage(day=day, kind=self.kind(day), published=True, items=int(n),
                                 matched=counts[day]["matched"],
                                 extracted=counts[day]["extracted"],
                                 failed=counts[day]["failed"], skipped=counts[day]["skipped"])
                for day, n in items.items()}

    def observations(self, result: Reconciliation, evidence: Mapping[int, SignalMention],
                     days: Iterable[date]) -> dict[date, list[ArticleObs]]:
        wanted = set(days)
        if not wanted:
            return {}
        by_article_day: dict[tuple[int, str, date], list[EntityMention]] = defaultdict(list)
        for mention_id, row in evidence.items():
            if row.scope_day in wanted:
                keys = result.keys[mention_id]
                by_article_day[(row.article_id, row.url_canonical_hash, row.scope_day)].append(
                    EntityMention(
                        entity_key=result.assignments[mention_id], type_group=keys.type_group,
                        base_key=keys.base_key, role=row.role, is_new=row.is_new,
                        novelty_quote=row.novelty_quote))
        events: dict[tuple[int, str], tuple[int, str]] = {}
        for article_id, url_hash, version, event in self.session.execute(
                select(ArticleSignal.article_id, ArticleSignal.url_canonical_hash,
                       ArticleSignal.extraction_version, ArticleSignal.event_type)
                .where(ArticleSignal.status == "ok")):
            rank = _version_rank(version)
            if rank >= events.get((article_id, url_hash), (-2, ""))[0]:
                events[(article_id, url_hash)] = (rank, event or "other")
        out: dict[date, list[ArticleObs]] = defaultdict(list)
        for scope, article in self.session.execute(
                select(DailySignalScope, Article)
                .join(Article, _same_article(DailySignalScope))
                .where(DailySignalScope.scope_day.in_(sorted(wanted)))
                .order_by(DailySignalScope.scope_day, Article.id)):
            identity = (article.id, article.url_canonical_hash)
            if identity not in events:
                continue
            mentions = sorted(by_article_day.get((*identity, scope.scope_day), []),
                              key=lambda m: (m.entity_key, m.role))
            out[scope.scope_day].append(ArticleObs(
                article_id=article.id, scope_day=scope.scope_day,
                title=str(digest_title(article.title)), url=scope.item_url,
                publisher=scope.publisher, published_at=article.published_at,
                event_type=events[identity][1], mentions=tuple(mentions)))
        return dict(out)

    def history_texts(self, until: date) -> list[tuple[date, str]]:
        """Published digest item titles and summaries up to `until` (F19: what we published, not
        article RSS summaries; the window is the digest history in the database)."""
        return [(day, f"{title} {summary or ''}") for day, title, summary in self.session.execute(
            select(NewsDigestReport.report_date, NewsDigestItem.title, NewsDigestItem.summary)
            .join(NewsDigestGroup, NewsDigestGroup.report_id == NewsDigestReport.id)
            .join(NewsDigestItem, NewsDigestItem.group_id == NewsDigestGroup.id)
            .where(NewsDigestReport.report_date <= until))]

    def get_report(self, day: date) -> DailySignalReport | None:
        return self.session.scalar(select(DailySignalReport).where(
            DailySignalReport.report_date == day))

    def save_report(self, day: date, payload: Mapping[str, Any], digest: str) -> DailySignalReport:
        values = {"methodology_version": str(payload["methodology_version"]),
                  "extraction_version": str(payload["extraction_version"]),
                  "status": str(payload["status"]), "payload_hash": digest,
                  "thresholds": json.dumps(payload["thresholds"], sort_keys=True),
                  "payload": json.dumps(payload, sort_keys=True),
                  "coverage": json.dumps(payload["coverage"], sort_keys=True),
                  "updated_at": _now()}
        row = self.get_report(day)
        if row is None:
            try:
                with self.session.begin_nested():
                    row = DailySignalReport(report_date=day, created_at=_now(), **values)
                    self.session.add(row)
                    self.session.flush()
                return row
            except IntegrityError:
                row = self.get_report(day)
                if row is None:
                    raise
        for k, v in values.items():
            setattr(row, k, v)
        self.session.flush()
        return row

    def recompute_reports(self, until: date, *, all_days: bool = False,
                          now: datetime | None = None,
                          thresholds: Thresholds | None = None) -> RecomputeResult:
        """Reconcile entities and recompute every comparable published day up to `until`;
        write only reports that are missing or whose payload hash changed."""
        evidence, rows = self.load_evidence()
        result = reconcile(evidence, self.overrides())
        ids = self.apply_reconciliation(result, rows)
        coverage = self.coverage()
        start = self.comparable_from if all_days else \
            max(self.comparable_from, until - timedelta(days=RECOMPUTE_DAYS))
        targets = sorted(d for d, c in coverage.items()
                         if start <= d <= until and c.kind == "signals")
        t = thresholds or Thresholds()
        span = 2 * t.window_days
        needed = {d - timedelta(days=i) for d in targets for i in range(span)}
        observations = self.observations(result, rows, needed)
        history = LexicalHistory(self.history_texts(until))
        written, unchanged = [], 0
        generated = now or _now()
        for day in targets:
            payload = compute_snapshot(SnapshotInput(
                day=day, observations=observations, coverage=coverage, entities=result.entities,
                entity_ids=ids, extraction_version=EXTRACTION_VERSION, generated_at=generated,
                comparable_from=self.comparable_from, thresholds=t, history=history))
            digest = payload_hash(payload)
            stored = self.get_report(day)
            if stored is not None and stored.payload_hash == digest:
                unchanged += 1
                continue
            self.save_report(day, payload, digest)
            written.append(day)
        return RecomputeResult(written=written, unchanged=unchanged,
                               entities=len(result.entities), reconciliation=result)


__all__ = ["METHODOLOGY_VERSION", "DailySignalRepo", "OverrideConflict", "RecomputeResult"]
