"""Characterization tests for pipeline.screening: _screen_candidate, _assessment_from_cached."""
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import Settings
from app.config.sources import SourceConfig
from app.core.categories import READABLE_CATEGORIES
from app.core.ingestion.admission import (
    admission_cache_key,
    bounded_evidence,
    evidence_hash,
)
from app.core.ingestion.pipeline.models import AdmissionState
from app.core.ingestion.pipeline.screening import (
    _assessment_from_cached,
    _screen_candidate,
)
from app.core.jev import JevAssessment
from app.storage.admission import get_cached_decision
from app.storage.models_sql import AdmissionDecision as Row
from app.storage.models_sql import Base

ACCEPTED = "accepted_ai_editorial"
CATEGORY = sorted(READABLE_CATEGORIES)[0]


class FakeScorer:
    def __init__(self, result=None, held=False):
        self.result = result
        self.input_held = held
        self.cache = {}
        self.calls = 0

    def state(self, item):
        return item.title

    def classify(self, _item):
        self.calls += 1
        return self.result


class Log:
    def __init__(self):
        self.events = []

    def info(self, name, data=None):
        self.events.append(("info", name, data))

    def error(self, name, data=None):
        self.events.append(("error", name, data))


@pytest.fixture(name="session")
def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, autoflush=False)() as session:
        yield session


SETTINGS = Settings(_env_file=None)
CONFIG = SourceConfig(id="s1", name="s1", type="rss", url="https://example.com/feed")
ITEM = SimpleNamespace(title="AI story", url="https://example.com/a", summary="s", content="c")


def _key():
    return admission_cache_key(
        url_canonical_hash="h", evidence_hash=evidence_hash(bounded_evidence(ITEM)),
        model=SETTINGS.jev_model, policy_version=SETTINGS.semantic_admission_policy_version,
        prompt_version=SETTINGS.semantic_admission_prompt_version,
    )


def _screen(session, scorer, state, logger=None):
    return _screen_candidate(
        item=ITEM, config=CONFIG, db_source_id=1, article_repo=SimpleNamespace(session=session),
        settings=SETTINGS, relevance_scorer=scorer, admission_state=state,
        canonical_hash="h", logger=logger, canonical_url="https://example.com/a",
    )


def _assessment(choice=ACCEPTED, score=0.9):
    return JevAssessment(score, CATEGORY, 0.8, choice, 0.7, "x", 0.6)


def _seed(session, decision, payload=None, provider_status="ok"):
    session.add(Row(
        key=_key(), url_canonical_hash="h", source_id=None, payload=json.dumps(payload or {}),
        evidence_hash="e", policy_version="p", model="m", provider_status=provider_status,
        decision=decision, reason="r", attempts=1,
    ))
    session.flush()


def _counters(state):
    return (
        state.observed, state.cache_hits, state.rejected, state.unresolved,
        state.paused, state.fresh_success,
    )


@pytest.mark.parametrize("state", [None, AdmissionState(enabled=False)])
def test_screen_disabled_accepts_with_scorer_assessment_and_counts_nothing(session, state):
    scorer = FakeScorer(_assessment())
    assert _screen(session, scorer, state) == ("accept", scorer.result)
    assert _screen(session, None, state) == ("accept", None)
    if state is not None:
        assert _counters(state) == (0, 0, 0, 0, False, False)


def test_screen_cached_accept_hit_returns_cached_assessment(session):
    payload = {"assessment": {
        "relevance_score": 0.5, "category": CATEGORY, "category_confidence": 0.4,
        "admission_choice": ACCEPTED, "admission_confidence": 0.3,
    }}
    _seed(session, "accept", payload)
    state, log, scorer = AdmissionState(enabled=True), Log(), FakeScorer()
    decision, assessment = _screen(session, scorer, state, log)
    assert decision == "accept" and assessment.relevance_score == 0.5
    assert _counters(state) == (1, 1, 0, 0, False, False)
    assert log.events == [("info", "semantic_cache_hit", {"decision": "accept"})]
    assert scorer.calls == 0


def test_screen_cached_accept_corrupt_falls_through_to_rescoring(session):
    _seed(session, "accept", {"assessment": {"relevance_score": 1.1}})
    state, log, scorer = AdmissionState(enabled=True), Log(), FakeScorer(_assessment())
    decision, assessment = _screen(session, scorer, state, log)
    assert decision == "accept" and assessment is scorer.result
    assert state.cache_hits == 0 and state.fresh_success is True
    assert log.events == [("error", "semantic_cache_corrupt", {"decision": "accept"})]
    row = get_cached_decision(session, _key())
    assert row.attempts == 2  # force_pending re-opened the accepted row
    assert json.loads(row.payload)["assessment"]["relevance_score"] == 0.9


@pytest.mark.parametrize(
    ("cached", "rejected", "unresolved"),
    [("reject", 1, 0), ("unresolved", 0, 1), ("other", 0, 1)],
)
def test_screen_cached_non_accept_counts_hit(session, cached, rejected, unresolved):
    _seed(session, cached)
    state, log, scorer = AdmissionState(enabled=True), Log(), FakeScorer()
    assert _screen(session, scorer, state, log) == (cached, None)
    assert _counters(state) == (1, 1, rejected, unresolved, False, False)
    assert log.events == [("info", "semantic_cache_hit", {"decision": cached})]
    assert scorer.calls == 0


@pytest.mark.parametrize(
    ("provider_status", "decision"), [("pending", "reject"), ("ok", None), ("failed", "reject")],
)
def test_screen_uncacheable_rows_are_rescored(session, provider_status, decision):
    _seed(session, decision, provider_status=provider_status)
    state, scorer = AdmissionState(enabled=True), FakeScorer(_assessment())
    assert _screen(session, scorer, state)[0] == "accept"
    assert scorer.calls == 1 and state.cache_hits == 0


def test_screen_without_scorer_pauses_and_stores_pending(session):
    state, log = AdmissionState(enabled=True), Log()
    assert _screen(session, None, state, log) == ("paused", None)
    assert _counters(state) == (1, 0, 0, 0, True, False)
    assert log.events == [("error", "semantic_paused", {"reason": "provider_missing"})]
    row = get_cached_decision(session, _key())
    assert row.provider_status == "pending" and row.decision is None


def test_screen_no_assessment_input_held_is_unresolved(session):
    state, log = AdmissionState(enabled=True), Log()
    assert _screen(session, FakeScorer(None, held=True), state, log) == ("unresolved", None)
    assert _counters(state) == (1, 0, 0, 1, False, False)
    assert not log.events


def test_screen_no_assessment_provider_failed_pauses(session):
    state, log = AdmissionState(enabled=True), Log()
    assert _screen(session, FakeScorer(None), state, log) == ("paused", None)
    assert _counters(state) == (1, 0, 0, 0, True, False)
    assert log.events == [("error", "semantic_paused", {"reason": "provider_failed"})]


def test_screen_invalid_choice_pauses(session):
    state, log = AdmissionState(enabled=True), Log()
    scorer = FakeScorer(_assessment(choice="bogus"))
    assert _screen(session, scorer, state, log) == ("paused", None)
    assert state.paused is True and state.fresh_success is False
    assert log.events == [("error", "semantic_paused", {"reason": "invalid_assessment"})]


@pytest.mark.parametrize("was_cached", [False, True])
def test_screen_fresh_accept_records_decision(session, was_cached):
    scorer = FakeScorer(_assessment())
    if was_cached:
        scorer.cache[ITEM.title] = scorer.result
    state, log = AdmissionState(enabled=True), Log()
    assert _screen(session, scorer, state, log) == ("accept", scorer.result)
    assert _counters(state) == (1, 0, 0, 0, False, not was_cached)
    assert not log.events
    row = get_cached_decision(session, _key())
    assert (row.decision, row.reason, row.provider_status) == ("accept", "AI_EDITORIAL", "ok")
    assert json.loads(row.payload)["assessment"]["relevance_score"] == 0.9


@pytest.mark.parametrize(
    ("choice", "reason", "decision", "rejected", "unresolved"),
    [
        ("non_ai", "NON_AI", "reject", 1, 0),
        ("non_editorial", "NON_EDITORIAL", "reject", 1, 0),
        ("insufficient_evidence", "INSUFFICIENT_EVIDENCE", "unresolved", 0, 1),
    ],
)
def test_screen_fresh_non_accept_counts_and_logs(  # pylint: disable=too-many-positional-arguments
    session, choice, reason, decision, rejected, unresolved,
):
    state, log = AdmissionState(enabled=True), Log()
    assert _screen(session, FakeScorer(_assessment(choice)), state, log) == (decision, None)
    assert _counters(state) == (1, 0, rejected, unresolved, False, True)
    assert log.events == [("info", "semantic_decision", {"decision": decision, "reason": reason})]
    assert get_cached_decision(session, _key()).reason == reason


def test_screen_runs_without_logger(session):
    _seed(session, "reject")
    assert _screen(session, FakeScorer(), AdmissionState(enabled=True)) == ("reject", None)


# _assessment_from_cached

def _cached(assessment=None, raw=None):
    payload = raw if raw is not None else json.dumps({"assessment": assessment})
    return SimpleNamespace(payload=payload)


def _valid(**over):
    base = {
        "relevance_score": 0.5, "category": CATEGORY, "category_confidence": 0.4,
        "admission_choice": ACCEPTED, "admission_confidence": 0.3,
        "comparison_choice": "c", "comparison_confidence": 0.2,
    }
    base.update(over)
    return base


def _raw(**fields):
    base = {"relevance_score": 0.5, "admission_choice": ACCEPTED}
    base.update(fields)
    return json.dumps({"assessment": base})  # json.dumps writes NaN/Infinity literals


def test_cached_valid_assessment_round_trips():
    assert _assessment_from_cached(_cached(_valid())) == JevAssessment(
        0.5, CATEGORY, 0.4, ACCEPTED, 0.3, "c", 0.2,
    )


def test_cached_score_is_converted_to_float():
    result = _assessment_from_cached(_cached(_valid(relevance_score=1)))
    assert result.relevance_score == 1.0 and isinstance(result.relevance_score, float)


@pytest.mark.parametrize("raw", ["", "{}", "[]", "null", '{"assessment": []}', '{"assessment": 1}'])
def test_cached_missing_or_non_dict_payload_is_none(raw):
    assert _assessment_from_cached(_cached(raw=raw)) is None


def test_cached_payload_none_or_absent_is_none():
    assert _assessment_from_cached(SimpleNamespace(payload=None)) is None
    assert _assessment_from_cached(object()) is None


@pytest.mark.parametrize("raw", ["{bad", "\x00"])
def test_cached_invalid_json_is_none(raw):
    assert _assessment_from_cached(_cached(raw=raw)) is None


@pytest.mark.parametrize(
    ("score", "ok"),
    [
        (0.0, True), (1.0, True), (0, True), (1, True), (0.0000001, True), (0.9999999, True),
        (-0.0000001, False), (1.0000001, False), (-1, False), (2, False),
        (True, False), (False, False), ("0.5", False), (None, False), ([], False),
    ],
)
def test_cached_score_boundaries(score, ok):
    result = _assessment_from_cached(_cached(_valid(relevance_score=score)))
    assert (result is not None) is ok


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf")])
def test_cached_non_finite_score_is_none(score):
    assert _assessment_from_cached(_cached(raw=_raw(relevance_score=score))) is None


def test_cached_missing_score_is_none():
    data = _valid()
    del data["relevance_score"]
    assert _assessment_from_cached(_cached(data)) is None


@pytest.mark.parametrize("choice", ["non_ai", "non_editorial", "insufficient_evidence", None, ""])
def test_cached_only_accepted_choice_is_usable(choice):
    assert _assessment_from_cached(_cached(_valid(admission_choice=choice))) is None


@pytest.mark.parametrize(
    ("conf", "ok"),
    [
        (None, True), (0.0, True), (1.0, True), (0, True), (1, True),
        (-0.0000001, False), (1.0000001, False), (True, False), (False, False),
        ("0.5", False), ([], False),
    ],
)
def test_cached_admission_confidence_boundaries(conf, ok):
    result = _assessment_from_cached(_cached(_valid(admission_confidence=conf)))
    assert (result is not None) is ok
    if ok:
        assert result.admission_confidence == conf


@pytest.mark.parametrize("conf", [float("nan"), float("inf"), float("-inf")])
def test_cached_non_finite_admission_confidence_is_none(conf):
    assert _assessment_from_cached(_cached(raw=_raw(admission_confidence=conf))) is None


@pytest.mark.parametrize(
    ("conf", "kept"),
    [
        (0.0, True), (1.0, True), (0, True), (1, True),
        (-0.0000001, False), (1.0000001, False), (True, False), (None, False), ("0.5", False),
    ],
)
def test_cached_category_confidence_boundaries_drop_category_pair(conf, kept):
    result = _assessment_from_cached(_cached(_valid(category_confidence=conf)))
    assert result is not None
    if kept:
        assert (result.category, result.category_confidence) == (CATEGORY, conf)
    else:
        assert (result.category, result.category_confidence) == (None, None)
    assert result.relevance_score == 0.5 and result.admission_confidence == 0.3


@pytest.mark.parametrize("category", ["not-a-category", None, 5, ""])
def test_cached_unknown_category_drops_category_pair(category):
    result = _assessment_from_cached(_cached(_valid(category=category)))
    assert (result.category, result.category_confidence) == (None, None)


@pytest.mark.parametrize("conf", [float("nan"), float("inf")])
def test_cached_non_finite_category_confidence_drops_pair(conf):
    result = _assessment_from_cached(_cached(raw=_raw(category=CATEGORY, category_confidence=conf)))
    assert (result.category, result.category_confidence) == (None, None)


def test_cached_comparison_fields_are_passed_through_unchecked():
    result = _assessment_from_cached(_cached(_valid(comparison_choice=7, comparison_confidence=9)))
    assert (result.comparison_choice, result.comparison_confidence) == (7, 9)
