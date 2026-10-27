import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import urlsplit

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
from app.web.source_onboarding import SourceOnboardingService


def _url_key(url: str) -> str:
    return str(candidate_url_key(url))


def _reusable_review(review: dict[str, Any]) -> bool:
    # Only successful decisions are reused; a Jev "review" means DeepSeek did not answer.
    if review.get("provider") == "deepseek":
        return True
    return review.get("provider") == "jev" and review.get("decision") in {"ready", "reject"}


def review_details(candidate: SourceCandidate) -> dict[str, Any]:
    try:
        details = json.loads(candidate.validation_details or "{}")
        review = details.get("source_review", {})
        return review if isinstance(review, dict) else {}
    except (ValueError, AttributeError):
        return {}


def _reviewed_at(cached: dict[str, Any], validated_at: datetime | None) -> datetime | None:
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
        self._job: dict[str, Any] = {"status": "idle", "batch_id": None,
                                     "completed": 0, "total": 0, "error": None}

    def start(self, batch_id: int) -> dict[str, Any]:
        with self.session_factory() as session:
            if session.get(SourceImportBatch, batch_id) is None:
                raise ValueError("Source batch not found")
        with self._lock:
            if self._job["status"] == "running":
                if self._job["batch_id"] == batch_id:
                    return dict(self._job)
                raise ValueError("Another source batch is being checked; wait for it to finish")
            self._job = {"status": "running", "batch_id": batch_id,
                         "completed": 0, "total": 0, "error": None}
            job = dict(self._job)
            threading.Thread(target=self._run, args=(batch_id,), daemon=True).start()
            return job

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._job)

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
                rows = [{"id": c.id, "url": c.normalized_url, "raw_input": c.raw_input,
                         "cached": review_details(c), "validated_at": c.validated_at}
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
            with self._lock:
                self._job.update(status="failed",
                                 error=f"Verification interrupted: {type(exc).__name__}")

    def _check_candidate(
        self, row: dict[str, Any], rows: list[dict[str, Any]], existing: list[str],
        client: Any, reviewer: SourceReviewer,
    ) -> None:
        candidate_url = str(row["url"])
        key = _url_key(candidate_url)
        duplicate_in_batch = any(
            other["id"] < row["id"] and _url_key(str(other["url"])) == key for other in rows
        )
        if duplicate_in_batch or any(_url_key(url) == key for url in existing):
            self._save(row, "warning", "unknown", {
                "decision": "duplicate", "reason": "Source URL is already in the registry",
            })
            return
        host = urlsplit(key).hostname
        overlaps = [url for url in existing if urlsplit(_url_key(url)).hostname == host]
        overlaps += [str(other["url"]) for other in rows
                     if other["id"] != row["id"]
                     and urlsplit(_url_key(str(other["url"]))).hostname == host]
        try:
            probe = probe_source(client, candidate_url)
            if any(_url_key(url) == _url_key(probe.url) for url in existing):
                self._save(row, "warning", probe.source_type, {
                    "decision": "duplicate", "reason": "Redirect leads to an existing source",
                })
                return
            brief = probe.brief(str(row["raw_input"]))
            fingerprint = evidence_fingerprint(brief, self.settings)
            cached = row["cached"]
            reviewed_at = _reviewed_at(cached, row["validated_at"])
            cache_fresh = (
                reviewed_at is not None
                and reviewed_at > datetime.now(UTC) - timedelta(days=7)
            )
            final_host = urlsplit(_url_key(probe.url)).hostname
            overlaps += [url for url in existing
                         if urlsplit(_url_key(url)).hostname == final_host and url not in overlaps]
            review: dict[str, Any]
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
        except Exception as exc:
            reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            self._save(row, "failed", "unknown", {
                "decision": "reject", "reason": f"Technical verification failed: {reason[:300]}",
            })

    def _save(self, row: dict[str, Any], validation: str, source_type: str,
              review: dict[str, Any]) -> None:
        with self.session_factory() as session:
            candidate = session.get(SourceCandidate, row["id"])
            if (candidate is None or candidate.status != "draft"
                    or candidate.normalized_url != row["url"]
                    or candidate.raw_input != row["raw_input"]):
                return
            candidate.validation_status = validation
            candidate.validation_detected_type = source_type
            if source_type in {"rss", "html"}:
                candidate.candidate_type = source_type
            candidate.validation_error = review["reason"] if validation != "validated" else None
            candidate.validation_details = json.dumps({"source_review": review}, ensure_ascii=True)
            candidate.validated_at = datetime.now(UTC)
            if review["decision"] == "duplicate":
                candidate.status = "duplicate"
            session.commit()
