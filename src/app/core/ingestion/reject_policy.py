"""Conservative destructive-cleanup policy using the ordinary admission assessment."""
from dataclasses import asdict
from math import isfinite
from types import SimpleNamespace
from typing import Any

from app.core.ingestion.admission import bounded_evidence, decision_from_assessment, evidence_hash
from app.core.jev import JevAssessment
from app.ingest.page_filter import text_exclusion_reason

CLEANUP_POLICY = "legacy-cleanup-1"
MIN_REJECT_CONFIDENCE = 0.95
MAX_NON_AI_RELEVANCE = 0.05


def article_evidence(row: dict[str, Any]) -> str:
    return str(bounded_evidence(SimpleNamespace(**row)))


def article_evidence_hash(row: dict[str, Any]) -> str:
    return str(evidence_hash(article_evidence(row)))


def cleanup_verdict(row: dict[str, Any], assessment: JevAssessment) -> dict[str, Any]:
    prefilter = text_exclusion_reason(
        row["url"], row["title"], row.get("content") or row.get("summary") or "",
    )
    decision = decision_from_assessment(assessment)
    confidence = assessment.admission_confidence
    strong = (isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
              and isfinite(confidence) and MIN_REJECT_CONFIDENCE <= confidence <= 1)
    enough = len((row.get("content") or row.get("summary") or "").strip()) >= 160
    corroborated = (
        assessment.admission_choice == "non_ai" and enough
        and 0 <= assessment.relevance_score <= MAX_NON_AI_RELEVANCE
    ) or (assessment.admission_choice == "non_editorial" and prefilter is not None)
    outcome = "unresolved"
    basis = "ambiguous_or_insufficient_corroboration"
    if decision and decision.accepted:
        outcome, basis = "kept", "AI_EDITORIAL"
    elif decision and decision.status == "reject" and strong and corroborated:
        outcome, basis = "rejected", decision.reason
    return {"outcome": outcome, "reason": basis, "prefilter": prefilter,
            "confidence": confidence, "assessment": asdict(assessment),
            "cleanup_policy": CLEANUP_POLICY}
