# pylint: disable=too-many-lines
"""Source onboarding: import candidates, review actions, YAML export.

Behavior, decisions, invariants and code map: onboarding.md next to this file.
"""

from dataclasses import dataclass
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.sources.candidates import (
    CandidateOverlapGroup,
    _candidate_value,
    _infer_candidate_type,
    _normalize_candidate_type,
    normalize_candidate_url,
    parse_source_candidates,
)
from app.storage.models_sql import Source, SourceCandidate, SourceImportBatch
from app.storage.source_candidate_repo import SourceCandidateRepo, SourceImportBatchRepo


@dataclass(frozen=True, slots=True)
class SourceImportResult:
    batch: SourceImportBatch
    candidates: list[SourceCandidate]
    parsed_count: int
    accepted_count: int
    rejected_count: int


def import_source_candidates(
    *,
    raw_text: str,
    batch_repo: SourceImportBatchRepo,
    candidate_repo: SourceCandidateRepo,
) -> SourceImportResult:
    normalized_candidates, parsed_count, rejected_count = parse_source_candidates(raw_text)
    batch = batch_repo.create_batch(raw_text=raw_text, parsed_count=parsed_count)
    candidate_rows = [
        {
            "raw_input": candidate.raw_input,
            "normalized_url": candidate.normalized_url,
            "candidate_type": candidate.candidate_type,
        }
        for candidate in normalized_candidates
    ]
    stored_candidates, accepted_count = candidate_repo.create_draft_candidates(
        batch_id=batch.id,
        candidates=candidate_rows,
    )
    total_rejected = rejected_count + (len(candidate_rows) - accepted_count)
    batch_repo.update_counts(
        batch=batch,
        parsed_count=parsed_count,
        accepted_count=accepted_count,
        rejected_count=total_rejected,
    )
    return SourceImportResult(
        batch=batch,
        candidates=stored_candidates,
        parsed_count=parsed_count,
        accepted_count=accepted_count,
        rejected_count=total_rejected,
    )

def review_candidate_overlaps(
    *,
    session: Session,
    batch_id: int | None = None,
    candidate_ids: list[int] | None = None,
) -> list[CandidateOverlapGroup]:
    repo = SourceCandidateRepo(session)
    groups = repo.find_overlap_groups(batch_id=batch_id, candidate_ids=candidate_ids)
    return [group for group in groups if isinstance(group, CandidateOverlapGroup)]

def review_source_candidate(
    *,
    candidate_id: int,
    action: str,
    candidate_repo: object,
    managed_source_repo: object,
    duplicate_of_candidate_id: int | None = None,
    review_note: str | None = None,
    updates: dict[str, str] | None = None,
) -> Any:
    get_candidate = getattr(candidate_repo, "get_candidate", None)
    if not callable(get_candidate):
        raise ValueError("candidate_repo must provide get_candidate")
    candidate = get_candidate(candidate_id)
    if candidate is None:
        raise ValueError(f"source candidate not found: {candidate_id}")

    normalized_action = action.strip().lower()
    handlers = {
        "approve": lambda: _approve_candidate(
            candidate=candidate,
            managed_source_repo=managed_source_repo,
            review_note=review_note,
        ),
        "disable": lambda: _disable_candidate(
            candidate=candidate,
            managed_source_repo=managed_source_repo,
            review_note=review_note,
        ),
        "reject": lambda: _reject_candidate(
            candidate=candidate,
            managed_source_repo=managed_source_repo,
            review_note=review_note,
        ),
        "mark_duplicate": lambda: _mark_duplicate_candidate(
            candidate=candidate,
            candidate_repo=candidate_repo,
            duplicate_of_candidate_id=duplicate_of_candidate_id,
            review_note=review_note,
        ),
        "edit": lambda: _edit_candidate(
            candidate=candidate,
            candidate_id=candidate_id,
            candidate_repo=candidate_repo,
            updates=updates,
            review_note=review_note,
        ),
    }
    handler = handlers.get(normalized_action)
    if handler is None:
        raise ValueError(f"unsupported review action: {action}")
    handler()

    save_review_update = getattr(candidate_repo, "save_review_update", None)
    if callable(save_review_update):
        return save_review_update(candidate)

    return candidate

def export_approved_sources_yaml(*, session: Session) -> str:
    stmt = (
        select(Source)
        .where(Source.enabled.is_(True))
        .order_by(Source.source_key.asc(), Source.id.asc())
    )
    sources = session.execute(stmt).scalars().all()
    payload = {"sources": [_serialize_approved_source(source) for source in sources]}
    return yaml.safe_dump(payload, sort_keys=False)

def _approve_candidate(
    *,
    candidate: Any,
    managed_source_repo: object,
    review_note: str | None,
) -> None:
    if _candidate_value(candidate, "status", default="draft") == "duplicate":
        raise ValueError("Duplicate candidates cannot be approved")
    if _candidate_value(candidate, "validation_status", default="pending") != "validated":
        raise ValueError("Only validated candidates can be approved")
    create_from_candidate = getattr(managed_source_repo, "create_from_candidate", None)
    if not callable(create_from_candidate):
        raise ValueError("managed_source_repo must provide create_from_candidate")
    managed_source = create_from_candidate(candidate)
    candidate.status = "approved"
    candidate.review_note = review_note
    candidate.duplicate_of_candidate_id = None
    managed_source_id = getattr(managed_source, "id", None)
    if managed_source_id is not None:
        candidate.approved_source_id = int(managed_source_id)

def _reject_candidate(
    *,
    candidate: Any,
    managed_source_repo: object,
    review_note: str | None,
) -> None:
    approved_source_id = _candidate_int_value(candidate, "approved_source_id")
    if candidate.status == "approved" and approved_source_id is not None:
        disable_source = getattr(managed_source_repo, "disable_source", None)
        if not callable(disable_source):
            raise ValueError("managed_source_repo must provide disable_source")
        disable_source(approved_source_id)
    candidate.status = "rejected"
    candidate.review_note = review_note

def _disable_candidate(
    *,
    candidate: Any,
    managed_source_repo: object,
    review_note: str | None,
) -> None:
    approved_source_id = _candidate_int_value(candidate, "approved_source_id")
    if approved_source_id is None:
        raise ValueError("Only approved candidates with a managed source can be disabled")
    disable_source = getattr(managed_source_repo, "disable_source", None)
    if not callable(disable_source):
        raise ValueError("managed_source_repo must provide disable_source")
    disable_source(approved_source_id)
    candidate.status = "disabled"
    candidate.duplicate_of_candidate_id = None
    if review_note is not None:
        candidate.review_note = review_note

def _mark_duplicate_candidate(
    *,
    candidate: Any,
    candidate_repo: object,
    duplicate_of_candidate_id: int | None,
    review_note: str | None,
) -> None:
    if duplicate_of_candidate_id is None:
        raise ValueError("duplicate_of_candidate_id is required")
    if duplicate_of_candidate_id == int(_candidate_value(candidate, "id")):
        raise ValueError("candidate cannot be marked duplicate of itself")
    duplicate_candidate = _lookup_candidate(candidate_repo, duplicate_of_candidate_id)
    if duplicate_candidate is None:
        raise ValueError(f"source candidate not found: {duplicate_of_candidate_id}")
    candidate.status = "duplicate"
    candidate.duplicate_of_candidate_id = duplicate_of_candidate_id
    candidate.review_note = review_note

def _edit_candidate(
    *,
    candidate: Any,
    candidate_id: int,
    candidate_repo: object,
    updates: dict[str, str] | None,
    review_note: str | None,
) -> None:
    if _candidate_value(candidate, "status", default="draft") == "approved":
        raise ValueError("Approved candidates cannot be edited")
    normalized_updates = dict(updates or {})
    raw_url = normalized_updates.get("normalized_url")
    if raw_url is not None:
        normalized_updates["normalized_url"] = normalize_candidate_url(raw_url)
        existing = _find_by_normalized_url(candidate_repo, normalized_updates["normalized_url"])
        if existing is not None and int(_candidate_value(existing, "id")) != candidate_id:
            raise ValueError("normalized URL already exists for another candidate")
    candidate_type = normalized_updates.get("candidate_type")
    if candidate_type is not None:
        normalized_updates["candidate_type"] = _normalize_candidate_type(candidate_type)
    elif "normalized_url" in normalized_updates:
        normalized_updates["candidate_type"] = _infer_candidate_type(
            normalized_updates["normalized_url"]
        )
    changed = any(
        field_name in normalized_updates
        and getattr(candidate, field_name, None) != normalized_updates[field_name]
        for field_name in ("raw_input", "normalized_url", "candidate_type")
    )
    for field_name in ("raw_input", "normalized_url", "candidate_type"):
        if field_name in normalized_updates:
            setattr(candidate, field_name, normalized_updates[field_name])
    if changed:
        candidate.validation_status = "pending"
        candidate.validation_details = None
        candidate.validation_error = None
        candidate.validation_detected_type = None
        candidate.validated_at = None
    if review_note is not None:
        candidate.review_note = review_note

def _lookup_candidate(candidate_repo: object, candidate_id: int) -> Any | None:
    get_candidate = getattr(candidate_repo, "get_candidate", None)
    if not callable(get_candidate):
        return None
    return get_candidate(candidate_id)

def _serialize_approved_source(source: Source) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": source.source_key,
        "name": source.name,
        "type": source.type,
        "url": source.url,
        "enabled": source.enabled,
        "fetch_interval_minutes": source.fetch_interval_minutes,
        "source_weight": source.source_weight,
    }
    if source.type == "html":
        payload["parser_options"] = {}
    return payload

def _find_by_normalized_url(candidate_repo: object, normalized_url: str) -> Any | None:
    find_by_normalized_url = getattr(candidate_repo, "find_by_normalized_url", None)
    if not callable(find_by_normalized_url):
        return None
    return find_by_normalized_url(normalized_url)

def _candidate_int_value(candidate: object, field_name: str) -> int | None:
    if isinstance(candidate, dict):
        value = candidate.get(field_name)
    else:
        value = getattr(candidate, field_name, None)
    if value is None:
        return None
    return int(value)
