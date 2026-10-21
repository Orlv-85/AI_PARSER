# pylint: disable=too-many-lines
"""Source onboarding: import candidates, overlap groups, validation, review actions, YAML export.

Behavior, decisions, invariants and code map: onboarding.md next to this file.
"""
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest.fetcher import Fetcher
from app.ingest.html import extract_links_from_html
from app.ingest.rss import fetch_rss_with_metadata
from app.storage.models_sql import Source, SourceCandidate, SourceImportBatch
from app.storage.source_candidate_repo import SourceCandidateRepo, SourceImportBatchRepo

_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\((https?://[^\s)]+)\)", re.IGNORECASE)
_PLAIN_URL_RE = re.compile(r"https?://[^\s<>\])]+", re.IGNORECASE)
_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAM_NAMES = {"gclid", "fbclid", "mc_cid", "mc_eid", "ref", "ref_src"}
_TOPIC_SEGMENTS = {"tag", "tags", "topic", "topics", "category", "categories", "section"}
_ROOT_SEGMENTS = {"", "blog", "news", "articles", "feed"}
_REVIEW_REASON_SEARCH_WRAPPER = "search_wrapper"
_REVIEW_REASON_INVALID_URL = "invalid_url"
_REVIEW_REASON_DUPLICATE_URL = "duplicate_url"
_REVIEW_REASON_BROAD_MEDIA_PAGE = "broad_media_page"
_REVIEW_REASON_TOPIC_PAGE = "topic_page"
_REVIEW_REASON_SAME_HOST_PATH_PREFIX = "same_host_path_prefix"
_REVIEW_REASON_SAME_HOST_TOPIC_VARIANT = "same_host_topic_variant"
_REVIEW_REASON_SAME_HOST_FAMILY = "same_host_family"
_REVIEW_REASON_PRIORITIES = {
    _REVIEW_REASON_SAME_HOST_PATH_PREFIX: 3,
    _REVIEW_REASON_SAME_HOST_TOPIC_VARIANT: 2,
    _REVIEW_REASON_TOPIC_PAGE: 2,
    _REVIEW_REASON_SAME_HOST_FAMILY: 1,
}


@dataclass(frozen=True, slots=True)
class NormalizedSourceCandidate:
    raw_input: str
    normalized_url: str
    candidate_type: str


@dataclass(frozen=True, slots=True)
class SourceImportResult:
    batch: SourceImportBatch
    candidates: list[SourceCandidate]
    parsed_count: int
    accepted_count: int
    rejected_count: int


@dataclass(frozen=True, slots=True)
class CandidateOverlapGroup:
    candidate_ids: list[int]
    reason: str
    preferred_candidate_id: int
    candidate_urls: list[str] | None = None
    preferred_url: str | None = None


@dataclass(frozen=True, slots=True)
class BatchRejectedCandidate:
    raw_input: str
    normalized_url: str
    reason: str


@dataclass(frozen=True, slots=True)
class BatchFlaggedCandidate:
    raw_input: str
    normalized_url: str
    reason: str


@dataclass(frozen=True, slots=True)
class BatchCandidateReview:
    rejected_candidates: list[BatchRejectedCandidate]
    flagged_candidates: list[BatchFlaggedCandidate]
    overlap_groups: list[CandidateOverlapGroup]


@dataclass(frozen=True, slots=True)
class ValidationResult:
    candidate_id: int
    status: str
    detected_type: str
    validation_error: str | None
    entry_count: int | None = None
    link_count: int | None = None
    sample_links: list[str] | None = None


def extract_candidate_urls(raw_text: str) -> list[str]:
    records = _json_source_records(raw_text)
    if records is not None:
        return [str(record["url"]) for record in records]
    matches: list[tuple[int, str]] = []
    consumed_ranges: list[tuple[int, int]] = []

    for match in _MARKDOWN_LINK_RE.finditer(raw_text):
        matches.append((match.start(1), match.group(1)))
        consumed_ranges.append((match.start(), match.end()))

    cursor = 0
    for start, end in consumed_ranges:
        matches.extend(_extract_plain_urls(raw_text[cursor:start], offset=cursor))
        cursor = end
    matches.extend(_extract_plain_urls(raw_text[cursor:], offset=cursor))

    matches.sort(key=lambda item: item[0])
    return [url for _, url in matches]


def _json_source_records(raw_text: str) -> list[dict[str, str]] | None:
    text = raw_text.strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    if not text.startswith(("{", "[")):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        if text.startswith("[") and not re.match(r'\[\s*[\{"\]]', text):
            return None
        raise ValueError("Invalid JSON: upload an array or an object with a sources array") from exc
    records = payload.get("sources") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("JSON must contain a sources array")
    if len(records) > 200 or len(text.encode("utf-8")) > 1_000_000:
        raise ValueError("Source JSON is limited to 200 records and 1 MB")
    result: list[dict[str, str]] = []
    for record in records:
        if isinstance(record, str):
            record = {"url": record}
        if not isinstance(record, dict) or not isinstance(record.get("url"), str):
            raise ValueError("Each source record needs a string url")
        if len(record["url"]) > 2048:
            raise ValueError("Source URLs must be at most 2048 characters")
        result.append({
            key: str(record[key])[:limit]
            for key, limit in (("url", 2048), ("name", 128), ("description", 500), ("type", 16))
            if key in record and isinstance(record[key], str)
        })
    return result


def normalize_candidate_url(raw_url: str) -> str:
    candidate = raw_url.strip()
    parts = urlsplit(candidate)
    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()

    if scheme not in {"http", "https"} or not hostname:
        raise ValueError("invalid source candidate URL")
    if _is_search_wrapper(hostname=hostname, path=parts.path, query=parts.query):
        raise ValueError("search wrapper URLs are not valid source candidates")

    netloc = hostname
    if parts.port is not None and parts.port != _default_port(scheme):
        netloc = f"{netloc}:{parts.port}"

    path = re.sub(r"/{2,}", "/", parts.path or "")
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    if path == "/":
        path = ""

    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith(_TRACKING_PARAM_PREFIXES)
        and key.lower() not in _TRACKING_PARAM_NAMES
    ]
    query = urlencode(filtered_query, doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def parse_source_candidates(raw_text: str) -> tuple[list[NormalizedSourceCandidate], int, int]:
    records = _json_source_records(raw_text)
    extracted_urls = extract_candidate_urls(raw_text)
    normalized_candidates: list[NormalizedSourceCandidate] = []
    seen_urls: set[str] = set()
    rejected_count = 0

    for index, raw_url in enumerate(extracted_urls):
        try:
            normalized_url = normalize_candidate_url(raw_url)
        except ValueError:
            rejected_count += 1
            continue

        if normalized_url in seen_urls:
            rejected_count += 1
            continue

        seen_urls.add(normalized_url)
        record = records[index] if records is not None else None
        declared_type = record.get("type", "").lower() if record else ""
        candidate_type = "rss" if declared_type == "atom" else declared_type
        normalized_candidates.append(
            NormalizedSourceCandidate(
                raw_input=json.dumps(record, ensure_ascii=True) if record else raw_url,
                normalized_url=normalized_url,
                candidate_type=(
                    candidate_type if candidate_type in {"rss", "html"}
                    else _infer_candidate_type(normalized_url)
                ),
            )
        )

    return normalized_candidates, len(extracted_urls), rejected_count


def classify_candidate_batch(raw_text: str) -> BatchCandidateReview:
    extracted_urls = extract_candidate_urls(raw_text)
    normalized_candidates: list[NormalizedSourceCandidate] = []
    rejected_candidates: list[BatchRejectedCandidate] = []
    flagged_candidates: list[BatchFlaggedCandidate] = []
    seen_urls: set[str] = set()

    for raw_url in extracted_urls:
        try:
            normalized_url = normalize_candidate_url(raw_url)
        except ValueError:
            reason = (
                _REVIEW_REASON_SEARCH_WRAPPER
                if _is_search_wrapper_url(raw_url)
                else _REVIEW_REASON_INVALID_URL
            )
            rejected_candidates.append(
                BatchRejectedCandidate(
                    raw_input=raw_url,
                    normalized_url=raw_url.strip(),
                    reason=reason,
                )
            )
            continue

        if normalized_url in seen_urls:
            rejected_candidates.append(
                BatchRejectedCandidate(
                    raw_input=raw_url,
                    normalized_url=normalized_url,
                    reason=_REVIEW_REASON_DUPLICATE_URL,
                )
            )
            continue

        seen_urls.add(normalized_url)
        candidate = NormalizedSourceCandidate(
            raw_input=raw_url,
            normalized_url=normalized_url,
            candidate_type=_infer_candidate_type(normalized_url),
        )
        normalized_candidates.append(candidate)
        flag_reason = _batch_flag_reason(candidate)
        if flag_reason is not None:
            flagged_candidates.append(
                BatchFlaggedCandidate(
                    raw_input=candidate.raw_input,
                    normalized_url=_batch_output_url(
                        raw_input=candidate.raw_input,
                        normalized_url=candidate.normalized_url,
                    ),
                    reason=flag_reason,
                )
            )

    overlap_input = [
        {
            "id": index,
            "normalized_url": candidate.normalized_url,
            "candidate_type": candidate.candidate_type,
        }
        for index, candidate in enumerate(normalized_candidates, start=1)
    ]
    overlap_groups = group_candidate_overlaps(overlap_input)
    return BatchCandidateReview(
        rejected_candidates=rejected_candidates,
        flagged_candidates=flagged_candidates,
        overlap_groups=overlap_groups,
    )


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


def group_candidate_overlaps(  # pylint: disable=too-many-branches
    candidates: Sequence[object],
) -> list[CandidateOverlapGroup]:
    grouped_by_host: dict[str, list[object]] = {}
    for candidate in candidates:
        normalized_url = _candidate_value(candidate, "normalized_url")
        hostname = (urlsplit(normalized_url).hostname or "").lower()
        if not hostname:
            continue
        grouped_by_host.setdefault(hostname, []).append(candidate)

    groups: list[CandidateOverlapGroup] = []
    for host_candidates in grouped_by_host.values():
        if len(host_candidates) < 2:
            continue
        overlaps_by_id: dict[int, set[int]] = {}
        reasons_by_pair: dict[frozenset[int], str] = {}
        for index, left in enumerate(host_candidates):
            left_id = int(_candidate_value(left, "id"))
            for right in host_candidates[index + 1 :]:
                reason = _overlap_reason(left, right)
                if reason is None:
                    continue
                right_id = int(_candidate_value(right, "id"))
                overlaps_by_id.setdefault(left_id, set()).add(right_id)
                overlaps_by_id.setdefault(right_id, set()).add(left_id)
                pair_key = frozenset({left_id, right_id})
                reasons_by_pair[pair_key] = _prefer_reason(reasons_by_pair.get(pair_key), reason)
        if len(overlaps_by_id) < 2:
            continue

        candidate_by_id = {
            int(_candidate_value(candidate, "id")): candidate for candidate in host_candidates
        }
        visited: set[int] = set()
        for candidate_id in sorted(overlaps_by_id):
            if candidate_id in visited:
                continue
            component_ids: set[int] = set()
            pending = [candidate_id]
            strongest_reason: str | None = None
            while pending:
                current_id = pending.pop()
                if current_id in visited:
                    continue
                visited.add(current_id)
                component_ids.add(current_id)
                for neighbor_id in overlaps_by_id.get(current_id, ()):
                    pair_key = frozenset({current_id, neighbor_id})
                    strongest_reason = _prefer_reason(
                        strongest_reason,
                        reasons_by_pair.get(pair_key, "same_host_family"),
                    )
                    if neighbor_id not in visited:
                        pending.append(neighbor_id)
            # Defensive guard: graph construction should make this unreachable.
            if len(component_ids) < 2:  # pragma: no cover
                continue

            members = [candidate_by_id[member_id] for member_id in sorted(component_ids)]
            preferred_candidate_id = int(_candidate_value(_pick_preferred_candidate(members), "id"))
            groups.append(
                CandidateOverlapGroup(
                    candidate_ids=sorted(component_ids),
                    reason=strongest_reason or "same_host_family",
                    preferred_candidate_id=preferred_candidate_id,
                    candidate_urls=[
                        _candidate_value(candidate_by_id[member_id], "normalized_url")
                        for member_id in sorted(component_ids)
                    ],
                    preferred_url=_candidate_value(
                        candidate_by_id[preferred_candidate_id],
                        "normalized_url",
                    ),
                )
            )
    return groups


def validate_rss_candidate(
    candidate: object,
    *,
    fetch_feed: Any | None = None,
) -> ValidationResult:
    candidate_id = int(_candidate_value(candidate, "id"))
    normalized_url = _candidate_value(candidate, "normalized_url")
    fetch_feed_fn = fetch_feed or _fetch_feed_with_ingest

    try:
        payload = fetch_feed_fn(normalized_url)
        entries = _extract_feed_entries(payload)
    except Exception as exc:  # pragma: no cover - exercised via integration path
        return ValidationResult(
            candidate_id=candidate_id,
            status="failed",
            detected_type="rss",
            validation_error=_format_validation_error(exc),
            entry_count=0,
        )

    entry_count = len(entries)
    if entry_count < 1:
        return ValidationResult(
            candidate_id=candidate_id,
            status="failed",
            detected_type="rss",
            validation_error="Feed returned no entry items",
            entry_count=0,
        )

    return ValidationResult(
        candidate_id=candidate_id,
        status="validated",
        detected_type="rss",
        validation_error=None,
        entry_count=entry_count,
    )


def validate_html_candidate(
    candidate: object,
    *,
    fetch_html: Any | None = None,
    extract_links: Any | None = None,
) -> ValidationResult:
    candidate_id = int(_candidate_value(candidate, "id"))
    normalized_url = _candidate_value(candidate, "normalized_url")
    fetch_html_fn = fetch_html or _fetch_html_with_ingest
    extract_links_fn = extract_links or _extract_links_with_ingest

    try:
        html_content = str(fetch_html_fn(normalized_url))
        links = list(extract_links_fn(html_content, normalized_url))
    except Exception as exc:  # pragma: no cover - exercised via integration path
        return ValidationResult(
            candidate_id=candidate_id,
            status="failed",
            detected_type="html",
            validation_error=_format_validation_error(exc),
            link_count=0,
            sample_links=[],
        )

    link_count = len(links)
    if link_count < 1:
        return ValidationResult(
            candidate_id=candidate_id,
            status="warning",
            detected_type="html",
            validation_error="HTML page loaded but no article links were extracted",
            link_count=0,
            sample_links=[],
        )

    return ValidationResult(
        candidate_id=candidate_id,
        status="validated",
        detected_type="html",
        validation_error=None,
        link_count=link_count,
        sample_links=links[:5],
    )


def run_source_validation(
    *,
    candidate_id: int,
    session: Session,
    fetch_feed: Any | None = None,
    fetch_html: Any | None = None,
    extract_links: Any | None = None,
) -> ValidationResult:
    repo = SourceCandidateRepo(session)
    candidate = repo.get_candidate(candidate_id)
    if candidate is None:
        raise ValueError(f"source candidate not found: {candidate_id}")

    candidate_type = _candidate_value(candidate, "candidate_type", default="unknown").lower()
    if candidate_type == "unknown":
        candidate_type = _infer_candidate_type(_candidate_value(candidate, "normalized_url"))

    if candidate_type == "rss":
        result = validate_rss_candidate(candidate, fetch_feed=fetch_feed)
    elif candidate_type == "html":
        result = validate_html_candidate(
            candidate,
            fetch_html=fetch_html,
            extract_links=extract_links,
        )
    else:
        result = ValidationResult(
            candidate_id=candidate.id,
            status="failed",
            detected_type="unknown",
            validation_error="Unsupported candidate type",
        )

    repo.record_validation_result(candidate_id=candidate_id, result=result)
    return result


def run_source_validation_batch(
    *,
    session: Session,
    batch_id: int | None = None,
    candidate_ids: list[int] | None = None,
    fetch_feed: Any | None = None,
    fetch_html: Any | None = None,
    extract_links: Any | None = None,
) -> list[ValidationResult]:
    if batch_id is None and not candidate_ids:
        raise ValueError("batch_id or candidate_ids is required")

    repo = SourceCandidateRepo(session)
    candidates = repo.list_candidates(batch_id=batch_id, candidate_ids=candidate_ids)
    return [
        run_source_validation(
            candidate_id=candidate.id,
            session=session,
            fetch_feed=fetch_feed,
            fetch_html=fetch_html,
            extract_links=extract_links,
        )
        for candidate in candidates
    ]


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


def write_approved_sources_yaml_snapshot(*, session: Session, path: Path) -> str:
    snapshot = export_approved_sources_yaml(session=session)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(snapshot, encoding="utf-8")
    return snapshot


def _approve_candidate(
    *,
    candidate: Any,
    managed_source_repo: object,
    review_note: str | None,
) -> None:
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
    # Only an approved candidate owns its source; a duplicate carries the target's id.
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
    candidate.approved_source_id = getattr(duplicate_candidate, "approved_source_id", None)
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


def _normalize_candidate_type(candidate_type: str) -> str:
    normalized_candidate_type = candidate_type.strip().lower()
    if normalized_candidate_type not in {"rss", "html", "unknown"}:
        raise ValueError("candidate_type must be one of: rss, html, unknown")
    return normalized_candidate_type


def _extract_plain_urls(text: str, *, offset: int) -> list[tuple[int, str]]:
    return [
        (offset + match.start(), _strip_trailing_punctuation(match.group(0)))
        for match in _PLAIN_URL_RE.finditer(text)
    ]


def _strip_trailing_punctuation(raw_url: str) -> str:
    return raw_url.rstrip(".,;]")


def _is_search_wrapper(*, hostname: str, path: str, query: str) -> bool:
    is_google_host = hostname.startswith("google.") or hostname.startswith("www.google.")
    if not is_google_host:
        return False
    if path in {"/url", "/search"}:
        return True
    return any(key == "q" and value.startswith("http") for key, value in parse_qsl(query))


def _default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80


def _is_search_wrapper_url(raw_url: str) -> bool:
    parts = urlsplit(raw_url.strip())
    hostname = (parts.hostname or "").lower()
    return _is_search_wrapper(hostname=hostname, path=parts.path, query=parts.query)


def _infer_candidate_type(normalized_url: str) -> str:
    lower_url = normalized_url.lower()
    if lower_url.endswith((".xml", ".rss", ".atom")) or "/feed" in lower_url:
        return "rss"
    return "html"


def _candidate_value(candidate: object, field_name: str, default: str | None = None) -> str:
    if isinstance(candidate, dict):
        value = candidate.get(field_name, default)
    else:
        value = getattr(candidate, field_name, default)
    if value is None:
        raise ValueError(f"candidate field is required: {field_name}")
    return str(value)


def _normalized_path(url: str) -> str:
    path = urlsplit(url).path or "/"
    path = re.sub(r"/{2,}", "/", path)
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return path or "/"


def _path_segments(url: str) -> list[str]:
    path = _normalized_path(url)
    if path == "/":
        return []
    return [segment for segment in path.strip("/").split("/") if segment]


def _overlap_reason(left: object, right: object) -> str | None:
    left_url = _candidate_value(left, "normalized_url")
    right_url = _candidate_value(right, "normalized_url")
    left_path = _normalized_path(left_url)
    right_path = _normalized_path(right_url)

    if _is_strict_path_prefix(left_path, right_path):
        return _REVIEW_REASON_SAME_HOST_PATH_PREFIX
    if _is_topic_path(left_path) or _is_topic_path(right_path):
        return _REVIEW_REASON_SAME_HOST_TOPIC_VARIANT
    if _is_root_family_path(left_path) or _is_root_family_path(right_path):
        return _REVIEW_REASON_SAME_HOST_FAMILY
    return None


def _is_strict_path_prefix(left_path: str, right_path: str) -> bool:
    if left_path == right_path:
        return False
    left_segments = _path_segments(left_path)
    right_segments = _path_segments(right_path)
    if not left_segments or not right_segments:
        return False
    shorter, longer = (
        (left_segments, right_segments)
        if len(left_segments) < len(right_segments)
        else (right_segments, left_segments)
    )
    return len(shorter) < len(longer) and longer[: len(shorter)] == shorter


def _is_topic_path(path: str) -> bool:
    segments = _path_segments(path)
    return any(segment.lower() in _TOPIC_SEGMENTS for segment in segments)


def _is_root_family_path(path: str) -> bool:
    segments = _path_segments(path)
    if not segments:
        return True
    return len(segments) == 1 and segments[0].lower() in _ROOT_SEGMENTS


def _batch_flag_reason(candidate: NormalizedSourceCandidate) -> str | None:
    path = _normalized_path(candidate.normalized_url)
    hostname = (urlsplit(candidate.normalized_url).hostname or "").lower()
    if _is_topic_path(path):
        return _REVIEW_REASON_TOPIC_PAGE
    if _is_broad_media_candidate(hostname=hostname, path=path):
        return _REVIEW_REASON_BROAD_MEDIA_PAGE
    return None


def _is_broad_media_candidate(*, hostname: str, path: str) -> bool:
    if hostname not in {"infoq.com", "www.infoq.com"}:
        return False
    segments = _path_segments(path)
    return bool(segments) and len(segments) <= 2


def _batch_output_url(*, raw_input: str, normalized_url: str) -> str:
    raw_parts = urlsplit(raw_input.strip())
    normalized_parts = urlsplit(normalized_url)
    if (
        raw_parts.query == normalized_parts.query
        and raw_parts.path.endswith("/")
        and normalized_parts.path
        and not normalized_parts.path.endswith("/")
    ):
        return urlunsplit(
            (
                normalized_parts.scheme,
                normalized_parts.netloc,
                f"{normalized_parts.path}/",
                normalized_parts.query,
                "",
            )
        )
    return normalized_url


def _prefer_reason(current_reason: str | None, new_reason: str) -> str:
    normalized_new_reason = new_reason.strip().lower()
    if current_reason is None:
        return normalized_new_reason
    normalized_current_reason = current_reason.strip().lower()
    if _REVIEW_REASON_PRIORITIES.get(normalized_new_reason, 0) > _REVIEW_REASON_PRIORITIES.get(
        normalized_current_reason,
        0,
    ):
        return normalized_new_reason
    return normalized_current_reason


def _pick_preferred_candidate(candidates: list[object]) -> object:
    return min(
        candidates,
        key=lambda candidate: (
            _is_topic_path(_normalized_path(_candidate_value(candidate, "normalized_url"))),
            len(_path_segments(_candidate_value(candidate, "normalized_url"))),
            len(_normalized_path(_candidate_value(candidate, "normalized_url"))),
            _candidate_value(candidate, "candidate_type", default="unknown") != "rss",
            int(_candidate_value(candidate, "id")),
        ),
    )


def _fetch_feed_with_ingest(url: str) -> Any:
    with Fetcher() as fetcher:
        return fetch_rss_with_metadata(
            source_key="source-onboarding-validation",
            url=url,
            fetcher=fetcher,
        )


def _fetch_html_with_ingest(url: str) -> str:
    with Fetcher() as fetcher:
        return cast(
            str,
            fetcher.fetch_text(source_id="source-onboarding-validation", url=url),
        )


def _extract_links_with_ingest(html_content: str, base_url: str) -> list[str]:
    return cast(
        list[str],
        extract_links_from_html(
            html_content=html_content,
            base_url=base_url,
            list_selector=None,
            link_selector="a",
        ),
    )


def _extract_feed_entries(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        return list(payload.get("entries") or [])
    if isinstance(payload, list):
        return payload
    entries = getattr(payload, "entries", None)
    if entries is not None:
        return list(entries)
    items = getattr(payload, "items", None)
    if items is not None and not callable(items):
        return list(items)
    return []


def _format_validation_error(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return f"{type(exc).__name__}: {message}"
    return type(exc).__name__
