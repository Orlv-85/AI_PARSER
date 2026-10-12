"""Additive weekly evidence ledger and durable, frozen-input job storage."""
# pylint: disable=too-many-locals

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.config.sources import SourceConfig
from app.core.canonicalize import canonical_url_hash
from app.core.weekly_analytics import DEFAULT_THRESHOLDS, METHODOLOGY_VERSION, Coverage, windows
from app.core.weekly_input import compatible_admission, publication
from app.core.weekly_topics import TAXONOMY_VERSION, topic_registry
from app.storage.models_sql import (
    AdmissionDecision,
    Article,
    Source,
    WeeklyCoverageAttempt,
    WeeklyDecision,
    WeeklyInputObservation,
    WeeklyJob,
    WeeklyPublication,
    WeeklySnapshot,
    WeeklySourceVersion,
    WeeklyTopicVersion,
)


def encoded(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False, default=str)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def insert_once(session: Session, model: Any, values: dict) -> None:
    factory = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    session.execute(factory(model).values(**values).on_conflict_do_nothing())


def publisher_group(url: str, overrides: dict[str, str]) -> str:
    host = (urlsplit(url).hostname or "unknown").lower()
    if host in overrides:
        return overrides[host]
    parts = host.split(".")
    suffixes = {"co.uk", "org.uk", "com.au", "co.jp", "com.br", "co.nz", "co.in"}
    domain = ".".join(parts[-3:] if ".".join(parts[-2:]) in suffixes else parts[-2:])
    return overrides.get(domain, domain)


def register_source(session: Session, source_id: int, config: SourceConfig,
                    settings: Settings, now: datetime) -> str:
    data = config.model_dump(mode="json")
    publisher = publisher_group(str(config.url), settings.weekly_publisher_overrides)
    key = fingerprint({"source_id": source_id, "configuration": data, "publisher": publisher})
    insert_once(session, WeeklySourceVersion, {
        "id": key, "source_id": source_id, "publisher": publisher, "configured_at": now,
        "interval_minutes": config.fetch_interval_minutes, "configuration": encoded(data),
    })
    return key


def record_attempt(session: Session, *, run_id: str, source_id: int, version_id: str,
                   interval: int, outcome: str, complete: bool, now: datetime) -> None:
    insert_once(session, WeeklyCoverageAttempt, {
        "run_id": run_id, "source_id": source_id, "version_id": version_id,
        "day": now.date(), "outcome": outcome, "complete": complete,
        "expected_attempts": max(1, math.ceil(1440 / max(1, interval))), "checked_at": now,
    })


def record_observation(session: Session, source_id: int, item: Any) -> None:
    published = (getattr(item, "publication_evidence_at", None) or item.published_at)
    if getattr(item, "publication_date_kind", "published") != "published":
        published = None
    if published is not None:
        published = published.replace(tzinfo=UTC) if published.tzinfo is None else (
            published.astimezone(UTC))
    canonical = canonical_url_hash(str(item.url))
    key = fingerprint([source_id, canonical, published])
    insert_once(session, WeeklyInputObservation, {
        "id": key, "source_id": source_id, "canonical_hash": canonical,
        "published_at": published, "discovered_at": datetime.now(UTC),
        "payload": encoded({"title": item.title, "summary": item.summary,
                            "content": item.content, "url": str(item.url),
                            "publication_provenance": "source" if published else "unknown"}),
    })


class WeeklyStore:
    def __init__(self, session: Session) -> None:
        self.session = session

    def decision(self, key: str) -> dict | None:
        row = self.session.get(WeeklyDecision, key)
        return json.loads(row.payload) if row else None

    def save_decision(self, key: str, task: str, payload: dict) -> None:
        insert_once(self.session, WeeklyDecision, {
            "key": key, "task": task, "payload": encoded(payload), "created_at": datetime.now(UTC),
        })
        # Progress survives worker exit and expired leases.
        self.session.commit()

    def published(self, report_date: date) -> dict | None:
        row = self.session.execute(select(WeeklySnapshot).join(
            WeeklyPublication, WeeklyPublication.snapshot_id == WeeklySnapshot.id
        ).where(WeeklyPublication.report_date == report_date)).scalar_one_or_none()
        return json.loads(row.payload) if row else None

    def lock_date(self, report_date: date) -> None:
        insert_once(self.session, WeeklyPublication, {"report_date": report_date,
                                                      "snapshot_id": None})
        self.session.execute(select(WeeklyPublication).where(
            WeeklyPublication.report_date == report_date).with_for_update()).scalar_one()

    def _coverage(self, start: datetime, end: datetime, cutoff: datetime) -> list[dict]:
        attempts = self.session.scalars(select(WeeklyCoverageAttempt).where(
            WeeklyCoverageAttempt.day >= start.date(), WeeklyCoverageAttempt.day < end.date(),
            WeeklyCoverageAttempt.checked_at <= cutoff,
        ).order_by(WeeklyCoverageAttempt.id)).all()
        versions = {v.id: v for v in self.session.scalars(select(WeeklySourceVersion)).all()}
        sources_by_publisher: dict[str, set[int]] = defaultdict(set)
        for version in versions.values():
            if version.configured_at <= cutoff:
                sources_by_publisher[version.publisher].add(version.source_id)
        days: dict[tuple[str, date], list[WeeklyCoverageAttempt]] = defaultdict(list)
        for row in attempts:
            version = versions[row.version_id]
            days[(version.publisher, row.day)].append(row)
        result = []
        for (publisher, day), rows in sorted(days.items()):
            source_ids = {row.source_id for row in rows}
            configs = [versions[row.version_id] for row in rows]
            expected = sum(max(row.expected_attempts for row in rows if row.source_id == sid)
                           for sid in source_ids)
            # A changed definition/ownership resets comparability conservatively.
            configured_at = max(v.configured_at.date() for v in configs)
            slots = {(r.source_id, (r.checked_at.hour * 60 + r.checked_at.minute)
                      // max(1, versions[r.version_id].interval_minutes))
                     for r in rows if r.outcome in {"success", "empty", "not_modified"}}
            result.append({"publisher": publisher, "day": day.isoformat(), "expected": expected,
                           "successful": len(slots),
                           "configured_at": configured_at.isoformat(),
                           "complete": (all(row.complete for row in rows)
                                        and source_ids == sources_by_publisher[publisher]),
                           "daily": all(v.interval_minutes <= 1440 for v in configs)})
        return result

    def freeze_input(self, report_date: date, settings: Settings) -> dict:
        cutoff = datetime.now(UTC)
        topics = topic_registry()
        known_topics = {topic["id"] for topic in topics}
        accepted_topics = self.session.scalars(select(WeeklyTopicVersion).order_by(
            WeeklyTopicVersion.topic_id, WeeklyTopicVersion.taxonomy_version)).all()
        for version in accepted_topics:
            if version.topic_id.startswith("emerging-") and version.topic_id not in known_topics:
                topics.append(json.loads(version.definition))
                known_topics.add(version.topic_id)
        taxonomy = (TAXONOMY_VERSION if len(topics) == len(topic_registry())
                    else "topics-" + fingerprint(topics)[:24])
        periods = windows(report_date)
        start, end = periods[-1][0], periods[0][1]
        sources = {s.id: s for s in self.session.scalars(select(Source)).all()}
        provenance = list(self.session.scalars(select(WeeklyInputObservation).where(
            WeeklyInputObservation.discovered_at <= cutoff,
        ).order_by(WeeklyInputObservation.id)).all())
        articles = list(self.session.scalars(select(Article).where(
            Article.discovered_at <= cutoff,
        ).order_by(Article.id)).all())
        current = {(row.source_id, row.url_canonical_hash): row for row in articles}
        current_canonicals = {row.url_canonical_hash for row in articles}
        admissions: dict[str, list[dict]] = defaultdict(list)
        for decision in self.session.scalars(select(AdmissionDecision).where(
                AdmissionDecision.updated_at <= cutoff)).all():
            admissions[decision.url_canonical_hash].append({
                column.name: getattr(decision, column.name)
                for column in AdmissionDecision.__table__.columns})
        histories: dict[tuple[int, str], list[str]] = defaultdict(list)
        rows = []
        invalid_dates = 0
        excluded_observations = []
        for row in provenance:
            identity = (row.source_id, row.canonical_hash)
            if identity not in current:
                excluded_observations.append({"id": row.id, "source_id": row.source_id,
                    "reason": "orphan_article" if row.canonical_hash not in current_canonicals
                    else "unverified_alias_source"})
            else:
                histories[identity].append(row.id)
        legacy_dates = 0
        unassigned = []
        for row in articles:
            data = {column.name: getattr(row, column.name) for column in Article.__table__.columns}
            temporal = publication(data, periods)
            if temporal["window_index"] is None:
                if temporal["date_reason"] != "outside_scope":
                    invalid_dates += 1
                    legacy_dates += temporal["date_reason"] == "legacy_unverified"
                    unassigned.append({"article_id": row.id, **temporal})
                continue
            source = sources.get(row.source_id or -1)
            refs = compatible_admission(data, admissions[row.url_canonical_hash])
            rows.append({"id": f"article-{row.id}", "article_id": row.id,
                         "canonical_hash": row.url_canonical_hash,
                         "source_id": row.source_id, **temporal,
                         "title": row.title, "summary": row.summary, "content": row.content,
                         "url": row.url_canonical, "publication_provenance": "current_article",
                         "historical_observation_ids": histories[(row.source_id,
                                                                    row.url_canonical_hash)],
                         "admission_required": True, "admission_refs": refs,
                         "admission_state": "accepted_compatible" if refs else "unresolved",
                         "publisher": publisher_group(source.url if source else row.url_canonical,
                                                      settings.weekly_publisher_overrides)})
        cap = settings.weekly_input_safety_cap
        complete = len(rows) <= cap
        return {"report_date": report_date.isoformat(), "data_cutoff": cutoff.isoformat(),
                "observations": rows[:cap], "included_ids": [r["id"] for r in rows[:cap]],
                "excluded_observations": excluded_observations,
                "unassigned_articles": unassigned,
                "coverage": self._coverage(start, end, cutoff), "topics": topics,
                "taxonomy_version": taxonomy, "methodology_version": METHODOLOGY_VERSION,
                "thresholds": asdict(DEFAULT_THRESHOLDS),
                "input_complete": complete, "quality_counters": {
                    "retrieved": len(rows), "invalid_dates": invalid_dates,
                    "articles_accounted": len(articles),
                    "orphan_observations": sum(r["reason"] == "orphan_article"
                                               for r in excluded_observations),
                    "unverified_alias_observations": sum(r["reason"] == "unverified_alias_source"
                                                         for r in excluded_observations),
                    "admission_unresolved": sum(r["admission_state"] != "accepted_compatible"
                                                for r in rows),
                    "legacy_unverified_dates": legacy_dates,
                    "unavailable_text": sum(not r.get("summary") and not r.get("content")
                                            for r in rows),
                    "safety_cap_excluded": max(0, len(rows)-cap)},
                "window_complete": cutoff >= end,
                "history_complete": not invalid_dates and not legacy_dates,
                "provider_configuration": {name: getattr(settings, name) for name in (
                    "weekly_jev_model", "weekly_deepseek_model", "weekly_prompt_version",
                    "jev_timeout_seconds", "weekly_deepseek_timeout_seconds",
                    "weekly_input_token_cap", "weekly_output_token_cap",
                    "weekly_narrative_prompt_version", "weekly_narrative_input_byte_cap",
                    "weekly_narrative_output_token_cap",
                    "weekly_publisher_overrides")}}

    def enqueue(self, report_date: date, settings: Settings) -> str:
        self.lock_date(report_date)
        packet = self.freeze_input(report_date, settings)
        # Cutoff is provenance, not a reason to duplicate unchanged input.
        content = {k: v for k, v in packet.items() if k != "data_cutoff"}
        key = fingerprint(content)
        insert_once(self.session, WeeklyJob, {
            "id": key, "report_date": report_date, "methodology_version": METHODOLOGY_VERSION,
            "input_fingerprint": key, "input_payload": encoded(packet), "status": "pending",
            "attempts": 0, "created_at": datetime.now(UTC),
        })
        for topic in packet["topics"]:
            insert_once(self.session, WeeklyTopicVersion, {
                "id": f"{packet['taxonomy_version']}:{topic['id']}",
                "taxonomy_version": packet["taxonomy_version"],
                "topic_id": topic["id"], "definition": encoded(topic),
            })
        return key

    def save_taxonomy(self, topics: list[dict], version: str) -> None:
        for topic in topics:
            insert_once(self.session, WeeklyTopicVersion, {
                "id": f"{version}:{topic['id']}", "taxonomy_version": version,
                "topic_id": topic["id"], "definition": encoded(topic),
            })
        self.session.commit()

    def claim(self, seconds: int, *, job_id: str | None = None) -> tuple[str, str] | None:
        now = datetime.now(UTC)
        available = or_(WeeklyJob.status.in_(["pending", "retry"]),
                        (WeeklyJob.status == "running") & (WeeklyJob.lease_until < now))
        query = select(WeeklyJob.id).where(available)
        if job_id is not None:
            query = query.where(WeeklyJob.id == job_id)
        ids = self.session.scalars(query.order_by(WeeklyJob.created_at, WeeklyJob.id)).all()
        for candidate_id in ids:
            token = uuid4().hex
            result = self.session.execute(update(WeeklyJob).where(
                WeeklyJob.id == candidate_id, available,
            ).values(status="running", lease_token=token,
                     lease_until=now + timedelta(seconds=seconds + 120),
                     attempts=WeeklyJob.attempts + 1))
            self.session.commit()
            if result.rowcount:  # type: ignore[attr-defined]
                return candidate_id, token
        return None

    def publish(self, job_id: str, token: str, payload: dict, packet: dict) -> None:
        job = self.session.get(WeeklyJob, job_id)
        if job is None:
            raise ValueError("Missing weekly job")
        # Date-wide lock serializes revisions and legacy/manual publication.
        self.lock_date(job.report_date)
        owns_lease = self.session.execute(update(WeeklyJob).where(
            WeeklyJob.id == job_id, WeeklyJob.lease_token == token,
            WeeklyJob.status == "running", WeeklyJob.lease_until > datetime.now(UTC),
        ).values(status="complete", lease_token=None, lease_until=None))
        if not owns_lease.rowcount:  # type: ignore[attr-defined]
            self.session.rollback()
            raise ValueError("Weekly job lease expired")
        revision = (self.session.scalar(select(func.max(WeeklySnapshot.revision)).where(
            WeeklySnapshot.report_date == job.report_date)) or 0) + 1
        now = datetime.now(UTC)
        payload.update({"snapshot_id": job_id, "revision": revision,
                        "generated_at": now.isoformat(), "data_cutoff": packet["data_cutoff"],
                        "taxonomy_version": packet["taxonomy_version"]})
        self.session.add(WeeklySnapshot(id=job_id, report_date=job.report_date, revision=revision,
                                        generated_at=now,
                                        data_cutoff=datetime.fromisoformat(packet["data_cutoff"]),
                                        payload=encoded(payload)))
        self.session.flush()
        current = self.published(job.report_date)
        # Insufficient regeneration cannot replace a previously ready report.
        newer = not current or datetime.fromisoformat(packet["data_cutoff"]) >= (
            datetime.fromisoformat(current["data_cutoff"]))
        if newer and (not current or current["status"] != "ready" or payload["status"] == "ready"):
            pointer = self.session.get(WeeklyPublication, job.report_date)
            if pointer is None:
                self.session.add(WeeklyPublication(report_date=job.report_date, snapshot_id=job_id))
            else:
                pointer.snapshot_id = job_id
        self.session.commit()

    def retry(self, job_id: str, token: str, reason: str) -> None:
        self.session.rollback()
        self.session.execute(update(WeeklyJob).where(
            WeeklyJob.id == job_id, WeeklyJob.lease_token == token,
        ).values(status="retry", error=reason[:255], lease_token=None, lease_until=None))
        self.session.commit()


def hydrate_coverage(rows: list[dict]) -> list[Coverage]:
    return [Coverage(**{**row, "day": date.fromisoformat(row["day"]),
                        "configured_at": date.fromisoformat(row["configured_at"])}) for row in rows]
