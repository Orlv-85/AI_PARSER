"""Deterministic validation of source candidates."""

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy.orm import Session

from app.core.sources.candidate_fields import read_str
from app.core.sources.candidates import _infer_candidate_type
from app.ingest.fetcher import Fetcher
from app.ingest.html import extract_links_from_html
from app.ingest.page_filter import html_exclusion_reason
from app.ingest.rss import fetch_rss_with_metadata
from app.storage.source_candidate_repo import SourceCandidateRepo

# A listing is judged by a few of its pages, not by one link that happens to work.
HTML_MIN_LINKS = 2
HTML_SAMPLE_LINKS = 3


@dataclass(frozen=True, slots=True)
class ValidationResult:
    candidate_id: int
    status: str
    detected_type: str
    validation_error: str | None
    entry_count: int | None = None
    link_count: int | None = None
    sample_links: list[str] | None = None


def validate_rss_candidate(
    candidate: object,
    *,
    fetch_feed: Any | None = None,
) -> ValidationResult:
    candidate_id = int(read_str(candidate, "id"))
    normalized_url = read_str(candidate, "normalized_url")
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
    candidate_id = int(read_str(candidate, "id"))
    normalized_url = read_str(candidate, "normalized_url")
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
    problem = (
        f"HTML page has {link_count} article link, at least {HTML_MIN_LINKS} are needed"
        if link_count < HTML_MIN_LINKS
        else _sampled_link_problem(links[:HTML_SAMPLE_LINKS], fetch_html_fn)
    )
    if problem:
        return ValidationResult(
            candidate_id=candidate_id,
            status="warning",
            detected_type="html",
            validation_error=problem,
            link_count=link_count,
            sample_links=links[:5],
        )

    return ValidationResult(
        candidate_id=candidate_id,
        status="validated",
        detected_type="html",
        validation_error=None,
        link_count=link_count,
        sample_links=links[:5],
    )

def _sampled_link_problem(sample: list[str], fetch_html_fn: Any) -> str | None:
    for link in sample:
        try:
            reason = html_exclusion_reason(link, str(fetch_html_fn(link)))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return f"Sampled link {link} could not be checked: {_format_validation_error(exc)}"
        if reason:
            return f"Sampled link {link} is not an article ({reason})"
    return None


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

    candidate_type = read_str(candidate, "candidate_type", default="unknown").lower()
    if candidate_type == "unknown":
        candidate_type = _infer_candidate_type(read_str(candidate, "normalized_url"))

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
