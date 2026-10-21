from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import cast

from app.core.jev import JevAssessment, jev_state

ACCEPTED = "accepted_ai_editorial"
NON_AI = "non_ai"
NON_EDITORIAL = "non_editorial"
INSUFFICIENT = "insufficient_evidence"
ADMISSION_CHOICES = {ACCEPTED, NON_AI, NON_EDITORIAL, INSUFFICIENT}


@dataclass(frozen=True)
class AdmissionDecision:
    status: str
    reason: str
    accepted: bool
    choice: str | None


def decision_from_assessment(assessment: JevAssessment) -> AdmissionDecision | None:
    choice = assessment.admission_choice
    if choice == ACCEPTED:
        return AdmissionDecision("accept", "AI_EDITORIAL", True, choice)
    if choice == NON_AI:
        return AdmissionDecision("reject", "NON_AI", False, choice)
    if choice == NON_EDITORIAL:
        return AdmissionDecision("reject", "NON_EDITORIAL", False, choice)
    if choice == INSUFFICIENT:
        return AdmissionDecision("unresolved", "INSUFFICIENT_EVIDENCE", False, choice)
    return None


def bounded_evidence(article: object) -> str:
    """Evidence of the admission cache key: the full bounded text, summary included."""
    return cast(str, jev_state(article))


def evidence_hash(evidence: str) -> str:
    return hashlib.sha256(evidence.encode("utf-8", "ignore")).hexdigest()


def admission_cache_key(  # pylint: disable=redefined-outer-name
    *, url_canonical_hash: str, evidence_hash: str, model: str, policy_version: str,
    prompt_version: str = "",
) -> str:
    raw = "|".join((url_canonical_hash, evidence_hash, model, policy_version, prompt_version))
    return hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()
