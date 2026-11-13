"""Source check job and bulk approval (SourceIntakeService); see onboarding.md next to this file."""

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TypedDict, cast
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.core.sources.candidates import candidate_url_key
from app.core.sources.review import (
    SourceReviewer,
    evidence_fingerprint,
    probe_source,
    source_http_client,
)
from app.storage.models_sql import Source, SourceCandidate, SourceImportBatch
from app.storage.source_candidate_repo import SourceCandidateRepo
from app.usecases.sources.candidate_review import SourceOnboardingService

_LOGGER = logging.getLogger(__name__)


class IntakeJob(TypedDict):
    status: str
    batch_id: int | None
    completed: int
    total: int
    error: str | None


@dataclass(frozen=True)
class _Row:
    """A draft candidate as `_run` read it; `_save` writes only if it is still unchanged."""

    id: int
    url: str
    raw_input: str
    cached: dict[str, object]
    validated_at: datetime | None


def _url_key(url: str) -> str:
    return str(candidate_url_key(url))


def _reusable_review(review: dict[str, object]) -> bool:
    # Only successful decisions are reused; a Jev "review" means DeepSeek did not answer.
    if review.get("provider") == "deepseek":
        return True
    return review.get("provider") == "jev" and review.get("decision") in {"ready", "reject"}


def review_details(candidate: SourceCandidate) -> dict[str, object]:
    try:
        details = json.loads(candidate.validation_details or "{}")
        review: object = details.get("source_review", {})
        return review if isinstance(review, dict) else {}
    except (ValueError, AttributeError):
        return {}


def _reviewed_at(cached: dict[str, object], validated_at: datetime | None) -> datetime | None:
    # Reviews saved before reviewed_at existed age from their last save.
    value: datetime | None
    try:
        value = datetime.fromisoformat(str(cached["reviewed_at"]))
    except (KeyError, ValueError):
        value = validated_at
    return value.replace(tzinfo=value.tzinfo or UTC) if value is not None else None


class SourceIntakeService:
    def __init__(self, session_factory: Callable[[], Session], settings: Settings) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self._lock = threading.Lock()
        self._job: IntakeJob = {"status": "idle", "batch_id": None,
                                "completed": 0, "total": 0, "error": None}

    def start(self, batch_id: int) -> IntakeJob:
        with self.session_factory() as session:
            if session.get(SourceImportBatch, batch_id) is None:
                raise ValueError("Source batch not found")
        with self._lock:
            if self._job["status"] == "running":
                if self._job["batch_id"] == batch_id:
                    return self._job.copy()
                raise ValueError("Another source batch is being checked; wait for it to finish")
            self._job = {"status": "running", "batch_id": batch_id,
                         "completed": 0, "total": 0, "error": None}
            job = self._job.copy()
            threading.Thread(target=self._run, args=(batch_id,), daemon=True).start()
            return job

    def status(self) -> IntakeJob:
        with self._lock:
            return self._job.copy()

    def latest_batch(self) -> int | None:
        with self.session_factory() as session:
            return session.scalar(select(SourceImportBatch.id).order_by(
                SourceImportBatch.id.desc()
            ).limit(1))

    def approve_ready(self, batch_id: int) -> list[int]:
        with self._lock:
            if self._job["status"] == "running":
                raise ValueError("Wait for source verification to finish before bulk approval")
        with self.session_factory() as session:
            if session.get(SourceImportBatch, batch_id) is None:
                raise ValueError("Source batch not found")
            candidates = SourceCandidateRepo(session).list_candidates(batch_id=batch_id)
            service = SourceOnboardingService(session)
            approved = []
            existing = {_url_key(url) for url in session.scalars(select(Source.url)).all()}
            for candidate in candidates:
                if (candidate.status == "draft" and candidate.validation_status == "validated"
                        and review_details(candidate).get("decision") == "ready"
                        and _url_key(candidate.normalized_url) not in existing):
                    service.approve_candidate(candidate.id)
                    approved.append(candidate.id)
                    existing.add(_url_key(candidate.normalized_url))
            session.commit()
            return approved

    def _run(self, batch_id: int) -> None:
        try:
            with self.session_factory() as session:
                candidates = SourceCandidateRepo(session).list_candidates(batch_id=batch_id)
                rows = [_Row(c.id, c.normalized_url, c.raw_input, review_details(c), c.validated_at)
                        for c in candidates if c.status == "draft"]
                existing = [str(url) for url in session.scalars(select(Source.url)).all()]
            with self._lock:
                self._job["total"] = len(rows)
            with source_http_client() as client:
                reviewer = SourceReviewer(self.settings, client)
                for row in rows:
                    self._check_candidate(row, rows, existing, client, reviewer)
                    with self._lock:
                        self._job["completed"] += 1
            with self._lock:
                self._job["status"] = "finished"
        except Exception as exc:
            _LOGGER.exception("source_intake_check_failed batch_id=%s", batch_id)
            with self._lock:
                self._job.update({"status": "failed",
                                  "error": f"Verification interrupted: {type(exc).__name__}"})

    def _check_candidate(  # pylint: disable=too-many-locals
        self, row: _Row, rows: list[_Row], existing: list[str],
        client: httpx.Client, reviewer: SourceReviewer,
    ) -> None:
        candidate_url = row.url
        key = _url_key(candidate_url)
        duplicate_in_batch = any(
            other.id < row.id and _url_key(other.url) == key for other in rows
        )
        if duplicate_in_batch or any(_url_key(url) == key for url in existing):
            self._save(row, "warning", "unknown", {
                "decision": "duplicate", "reason": "Source URL is already in the registry",
            })
            return
        host = urlsplit(key).hostname
        overlaps = [url for url in existing if urlsplit(_url_key(url)).hostname == host]
        overlaps += [other.url for other in rows
                     if other.id != row.id
                     and urlsplit(_url_key(other.url)).hostname == host]
        try:
            probe = probe_source(client, candidate_url)
            if any(_url_key(url) == _url_key(probe.url) for url in existing):
                self._save(row, "warning", probe.source_type, {
                    "decision": "duplicate", "reason": "Redirect leads to an existing source",
                })
                return
            brief = probe.brief(row.raw_input)
            fingerprint = evidence_fingerprint(brief, self.settings)
            cached = row.cached
            reviewed_at = _reviewed_at(cached, row.validated_at)
            cache_fresh = (
                reviewed_at is not None
                and reviewed_at > datetime.now(UTC) - timedelta(days=7)
            )
            final_host = urlsplit(_url_key(probe.url)).hostname
            overlaps += [url for url in existing
                         if urlsplit(_url_key(url)).hostname == final_host and url not in overlaps]
            review: dict[str, object]
            if overlaps:
                review = {"decision": "review", "reason": "Same-host source: check overlap",
                          "overlap_urls": overlaps[:5]}
            elif (cache_fresh and cached.get("fingerprint") == fingerprint
                  and _reusable_review(cached)):
                review = {**cached, "cached": True,
                          "reviewed_at": cast(datetime, reviewed_at).isoformat()}
            else:
                review = {**reviewer.review(brief),
                          "reviewed_at": datetime.now(UTC).isoformat()}
            review = {**review, "fingerprint": fingerprint, "evidence": json.loads(brief),
                      "requested_url": candidate_url,
                      "checked_at": datetime.now(UTC).isoformat()}
            self._save(row, "validated", probe.source_type, review)
        except Exception as exc:  # the candidate is saved as failed with the reason
            _LOGGER.warning("source_intake_candidate_failed url=%s", row.url, exc_info=True)
            reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            self._save(row, "failed", "unknown", {
                "decision": "reject", "reason": f"Technical verification failed: {reason[:300]}",
            })

    def _save(self, row: _Row, validation: str, source_type: str,
              review: dict[str, object]) -> None:
        with self.session_factory() as session:
            candidate = session.get(SourceCandidate, row.id)
            if (candidate is None or candidate.status != "draft"
                    or candidate.normalized_url != row.url
                    or candidate.raw_input != row.raw_input):
                return
            candidate.validation_status = validation
            candidate.validation_detected_type = source_type
            if source_type in {"rss", "html"}:
                candidate.candidate_type = source_type
            candidate.validation_error = (str(review["reason"]) if validation != "validated"
                                          else None)
            candidate.validation_details = json.dumps({"source_review": review}, ensure_ascii=True)
            candidate.validated_at = datetime.now(UTC)
            if review["decision"] == "duplicate":
                candidate.status = "duplicate"
            session.commit()
