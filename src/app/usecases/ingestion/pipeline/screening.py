"""Semantic admission screening of one candidate, cache reuse and admission counters."""
import json
from logging import Logger
from math import isfinite
from typing import Any, cast

from app.config.settings import Settings
from app.core.categories import READABLE_CATEGORIES
from app.core.ingestion.admission import (
    admission_cache_key,
    bounded_evidence,
    decision_from_assessment,
    evidence_hash,
)
from app.core.jev import JevAssessment, JevRelevanceScorer
from app.storage.admission import (
    get_cached_decision,
    record_decision,
    upsert_pending,
)
from app.storage.models_sql import AdmissionDecision
from app.usecases.ingestion.pipeline.models import AdmissionState, SourceRun
from app.usecases.ingestion.pipeline.rows import (
    _assessment_payload,
    _build_article_row,
    _candidate_payload,
)


def _pause(
    state: AdmissionState, logger: Logger | None, reason: str,
) -> tuple[str, JevAssessment | None]:
    state.paused = True
    if logger:
        logger.error("semantic_paused", {"reason": reason})
    return ("paused", None)


def _resolve_cached(
    cached: AdmissionDecision | None, admission_state: AdmissionState, logger: Logger | None,
) -> tuple[str, JevAssessment | None] | None:
    """Result for a usable cached decision, or None when the candidate must be rescored."""
    if cached is None or cached.provider_status != "ok" or cached.decision is None:
        return None
    decision = cached.decision
    if decision == "accept":
        assessment = _assessment_from_cached(cached)
        if assessment is not None:
            admission_state.cache_hits += 1
            if logger:
                logger.info("semantic_cache_hit", {"decision": "accept"})
            return ("accept", assessment)
        if logger:
            logger.error("semantic_cache_corrupt", {"decision": "accept"})
        return None
    admission_state.cache_hits += 1
    if decision == "reject":
        admission_state.rejected += 1
    else:
        admission_state.unresolved += 1
    if logger:
        logger.info("semantic_cache_hit", {"decision": decision})
    return (decision, None)


def _score_and_record(
    run: SourceRun, item: object, key: str, logger: Logger | None,
) -> tuple[str, JevAssessment | None]:
    """Screen with the provider; the caller has checked that the scorer and admission exist."""
    relevance_scorer = cast(JevRelevanceScorer, run.relevance_scorer)
    admission_state = cast(AdmissionState, run.admission_state)
    was_cached = relevance_scorer.state(item) in relevance_scorer.cache
    assessment = relevance_scorer.classify(item)
    if assessment is None:
        if relevance_scorer.input_held:
            admission_state.unresolved += 1
            return ("unresolved", None)
        return _pause(admission_state, logger, "provider_failed")
    decision = decision_from_assessment(assessment)
    if decision is None:
        return _pause(admission_state, logger, "invalid_assessment")
    if not was_cached:
        admission_state.fresh_success = True
    record_decision(
        run.article_repo.session,
        key=key,
        decision=decision.status,
        reason=decision.reason,
        provider_status="ok",
        payload=_assessment_payload(assessment),
    )
    if decision.accepted:
        return ("accept", assessment)
    if decision.status == "reject":
        admission_state.rejected += 1
    else:
        admission_state.unresolved += 1
    if logger:
        logger.info("semantic_decision", {"decision": decision.status, "reason": decision.reason})
    return (decision.status, None)


def _screen_candidate(
    run: SourceRun, item: object, *, canonical_hash: str, logger: Logger | None = None,
    canonical_url: str | None = None,
) -> tuple[str, JevAssessment | None]:
    settings, article_repo = run.settings, run.article_repo
    relevance_scorer, admission_state = run.relevance_scorer, run.admission_state
    if admission_state is None or not admission_state.enabled:
        assessment = relevance_scorer.classify(item) if relevance_scorer is not None else None
        return ("accept", assessment)
    admission_state.observed += 1
    evidence = bounded_evidence(item)
    ev_hash = evidence_hash(evidence)
    key = admission_cache_key(
        url_canonical_hash=canonical_hash,
        evidence_hash=ev_hash,
        model=settings.jev_model,
        policy_version=settings.semantic_admission_policy_version,
        prompt_version=settings.semantic_admission_prompt_version,
    )
    cached = get_cached_decision(article_repo.session, key)
    resolved = _resolve_cached(cached, admission_state, logger)
    if resolved is not None:
        return resolved
    upsert_pending(
        article_repo.session,
        key=key,
        url_canonical_hash=canonical_hash,
        source_id=run.db_source_id,
        payload=_candidate_payload(item, run.config, canonical_url),
        evidence_hash=ev_hash,
        policy_version=settings.semantic_admission_policy_version,
        model=settings.jev_model,
        force_pending=cached is not None and cached.decision == "accept",
    )
    if relevance_scorer is None:
        return _pause(admission_state, logger, "provider_missing")
    return _score_and_record(run, item, key, logger)


def _assessed_row(
    run: SourceRun, item: Any, *, canonical: str, canonical_hash: str,
) -> tuple[str, dict[str, object] | None]:
    """Screen (or, without admission, classify) one new item; the row is None unless stored."""
    if run.admission_enabled:
        action, assessment = _screen_candidate(
            run, item, canonical_hash=canonical_hash, canonical_url=canonical,
        )
        if action != "accept":
            return action, None
    else:
        assessment = (
            run.relevance_scorer.classify(item) if run.relevance_scorer is not None else None
        )
    return "accept", _build_article_row(
        run, item, canonical=canonical, canonical_hash=canonical_hash, assessment=assessment,
    )


def _html_placeholder_key(settings: Settings, canonical_hash: str) -> str:
    return cast(str, admission_cache_key(
        url_canonical_hash=canonical_hash,
        evidence_hash="",
        model=settings.jev_model,
        policy_version=settings.semantic_admission_policy_version,
        prompt_version=settings.semantic_admission_prompt_version,
    ))


def _admission_snapshot(state: AdmissionState) -> tuple[int, int, int, int, bool]:
    return (
        state.cache_hits,
        state.rejected,
        state.unresolved,
        state.observed,
        state.fresh_success,
    )


def _restore_admission(
    state: AdmissionState, snapshot: tuple[int, int, int, int, bool],
) -> None:
    state.cache_hits = snapshot[0]
    state.rejected = snapshot[1]
    state.unresolved = snapshot[2]
    state.observed = snapshot[3]
    state.fresh_success = snapshot[4]


def _valid_cached_probability(value: object) -> bool:
    return (
        not isinstance(value, bool) and isinstance(value, (int, float))
        and isfinite(value) and 0.0 <= value <= 1.0
    )


def _cached_score(assessment: dict) -> float | None:
    score = assessment.get("relevance_score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    value = float(score)
    if not isfinite(value) or not 0.0 <= value <= 1.0:
        return None
    return value


def _cached_category(assessment: dict) -> tuple[str | None, object]:
    category = assessment.get("category")
    confidence = assessment.get("category_confidence")
    if (
        not isinstance(category, str) or category not in READABLE_CATEGORIES
        or not _valid_cached_probability(confidence)
    ):
        return None, None
    return category, confidence


def _assessment_from_cached(cached: object) -> JevAssessment | None:
    try:
        payload = json.loads(getattr(cached, "payload", "") or "{}")
        assessment = payload.get("assessment") if isinstance(payload, dict) else None
        if not isinstance(assessment, dict):
            return None
        value = _cached_score(assessment)
        if value is None:
            return None
        if assessment.get("admission_choice") != "accepted_ai_editorial":
            return None
        admission_confidence = assessment.get("admission_confidence")
        if admission_confidence is not None and not _valid_cached_probability(admission_confidence):
            return None
        category, confidence = _cached_category(assessment)
        return JevAssessment(
            value, category, confidence, "accepted_ai_editorial", admission_confidence,
            assessment.get("comparison_choice"), assessment.get("comparison_confidence"),
        )
    except (TypeError, ValueError):
        return None
