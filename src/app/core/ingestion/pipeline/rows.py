"""Candidate payloads and article row building."""
import json
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from typing import Any, cast

from app.config.sources import SourceConfig
from app.core.daily.rubric import RUBRIC_VERSION
from app.core.ingestion.pipeline.models import COMPARISON_MIN_CONFIDENCE
from app.core.ingestion.scoring import ai_relevance_score, freshness_score, rank_score
from app.core.jev import JevAssessment, jev_state
from app.core.models import Article as CoreArticle
from app.ingest.page_filter import (
    text_exclusion_reason,
    url_exclusion_reason,
)
from app.storage.article_repo import ArticleRepo

# A publication time further ahead than this is not a timezone skew; it is replaced.
FUTURE_DATE_TOLERANCE = timedelta(hours=24)


def _clamp_future(value: datetime | None, now: datetime | None = None) -> datetime | None:
    """Return the collection time for a date beyond `FUTURE_DATE_TOLERANCE` ahead."""
    if value is None:
        return None
    now = now or datetime.now(UTC)
    aware = value if value.tzinfo else value.replace(tzinfo=UTC)
    return now if aware - now > FUTURE_DATE_TOLERANCE else value


def _candidate_payload(
    item: object, config: SourceConfig, canonical_url: str | None = None,
) -> dict[str, object]:
    published = _clamp_future(getattr(item, "published_at", None))
    evidence_at = _clamp_future(getattr(item, "publication_evidence_at", None))
    modified = getattr(item, "modified_at", None)
    return {
        "kind": "article",
        "title": getattr(item, "title", None),
        "url": str(getattr(item, "url", "")),
        "canonical_url": canonical_url or getattr(item, "ingestion_canonical_url", None),
        "summary": getattr(item, "summary", None),
        "content": getattr(item, "content", None),
        "published_at": published.isoformat() if published else None,
        "publication_evidence_at": evidence_at.isoformat() if evidence_at else None,
        "publication_date_kind": getattr(item, "publication_date_kind", "published"),
        "modified_at": modified.isoformat() if modified else None,
        "date_evidence": getattr(item, "date_evidence", None),
        "page_eligibility_checked": bool(getattr(item, "page_eligibility_checked", False)),
        "source_key": config.id,
    }


def _parse_dt(value: object) -> datetime | None:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _article_from_candidate(candidate: dict[str, object], source_key: str) -> CoreArticle:
    kind = str(candidate.get("publication_date_kind") or "published")
    if kind not in {"published", "updated", "unknown"}:
        kind = "published"
    return CoreArticle(
        source_key=source_key,
        title=str(candidate.get("title") or ""),
        url=str(candidate.get("url") or ""),
        published_at=_parse_dt(candidate.get("published_at")),
        summary=candidate.get("summary") if isinstance(candidate.get("summary"), str) else None,
        content=candidate.get("content") if isinstance(candidate.get("content"), str) else None,
        publication_evidence_at=_parse_dt(candidate.get("publication_evidence_at")),
        publication_date_kind=cast(Any, kind),
        modified_at=_parse_dt(candidate.get("modified_at")),
        date_evidence=candidate.get("date_evidence")
        if isinstance(candidate.get("date_evidence"), dict) else None,
        page_eligibility_checked=bool(candidate.get("page_eligibility_checked", False)),
        ingestion_canonical_url=(
            candidate.get("canonical_url")
            if isinstance(candidate.get("canonical_url"), str) else None
        ),
    )


def _assessment_payload(assessment: JevAssessment) -> dict[str, object]:
    return {
        "relevance_score": assessment.relevance_score,
        "category": assessment.category,
        "category_confidence": assessment.category_confidence,
        "admission_choice": assessment.admission_choice,
        "admission_confidence": assessment.admission_confidence,
        "comparison_choice": assessment.comparison_choice,
        "comparison_confidence": assessment.comparison_confidence,
    }


def _build_article_row(
    *, item: object, config: SourceConfig, db_source_id: int, canonical: str,
    canonical_hash: str, assessment: JevAssessment | None, admission_enabled: bool,
) -> dict[str, object] | None:
    if admission_enabled:
        if assessment is None:
            return None
        relevance = assessment.relevance_score
    else:
        relevance = (
            assessment.relevance_score if assessment is not None else ai_relevance_score(item)
        )
    published = getattr(item, "published_at", None)
    if getattr(item, "publication_date_kind", "published") != "published":
        published = None
    published = published or getattr(item, "publication_evidence_at", None)
    original = published
    published = _clamp_future(published)
    provenance = getattr(item, "date_evidence", None)
    if published is not original and original is not None:
        provenance = {**(provenance or {}), "future_date_replaced": original.isoformat()}
    dates = getattr(item, "date_evidence", None) or {}
    resolution = dates.get("published", {})
    if resolution.get("status") in {"unknown", "conflict"}:
        published = None
    selected_date = resolution.get("selected") or {}
    freshness = freshness_score(published)
    rank = rank_score(
        relevance=relevance,
        freshness=freshness,
        source_weight=config.source_weight,
    )
    row: dict[str, object] = {
        "source_id": db_source_id,
        "title": getattr(item, "title", None),
        "url": str(getattr(item, "url", "")),
        "url_canonical": canonical,
        "url_canonical_hash": canonical_hash,
        "published_at": published,
        "publication_day": date.fromisoformat(selected_date["value"][:10])
        if selected_date.get("value") and published is None else None,
        "modified_at": getattr(item, "modified_at", None),
        "publication_status": resolution.get("status") or (
            "confirmed" if published is not None else "unknown"),
        "publication_precision": selected_date.get("precision") or (
            dates.get("precision") or "normalized_source_timestamp"
            if published is not None else None),
        "date_provenance": json.dumps(provenance),
        "summary": getattr(item, "summary", None),
        "content": getattr(item, "content", None),
        "ai_relevance_score": relevance,
        "freshness_score": freshness,
        "rank_score": rank,
    }
    if assessment is not None and assessment.category is not None:
        row["category"] = assessment.category
        row["category_confidence"] = assessment.category_confidence
    if assessment is not None and assessment.comparison_choice == "Comparison":
        if (assessment.comparison_confidence or 0) >= COMPARISON_MIN_CONFIDENCE:
            row["material_type"] = "Comparison"
    if assessment is not None and assessment.comparison_choice is not None:
        # Same text the daily rubric sent; daily enrichment re-checks it before reuse.
        state = jev_state(item, with_summary=False)
        source_hash = sha256(json.dumps(state, ensure_ascii=True).encode()).hexdigest()
        row["enrichment_provenance"] = json.dumps({
            "rubric": RUBRIC_VERSION, "admission_source_hash": source_hash,
            "admission_assessment": _assessment_payload(assessment),
        })
    return row


def _upsert_article_rows(
    *, article_repo: ArticleRepo, rows: list[dict[str, object]],
) -> tuple[int, int]:
    if not rows:
        return 0, 0
    counts: tuple[int, int] = article_repo.upsert_articles_batch(cast(list[dict[str, Any]], rows))
    return counts


def _item_exclusion_reason(item: Any) -> str | None:
    if getattr(item, "page_eligibility_checked", False):
        reason = url_exclusion_reason(str(item.url))
    else:
        reason = text_exclusion_reason(
            str(item.url), item.title, item.content or item.summary or "")
    return cast(str | None, reason)
