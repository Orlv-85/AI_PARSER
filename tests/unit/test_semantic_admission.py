import json
from datetime import UTC, datetime
from logging import getLogger

import httpx
import pytest

from app.core.ingestion.admission import admission_cache_key, decision_from_assessment
from app.core.jev import JevAssessment, JevRelevanceScorer
from app.core.models import Article


def _article(index: int = 1) -> Article:
    return Article(
        source_key="test",
        title="AI research release " + str(index),
        url="https://example.com/" + str(index),
        published_at=datetime.now(UTC),
        summary="New model",
        content="AI is central.",
    )


def test_admission_choice_mapping() -> None:
    assert decision_from_assessment(
        JevAssessment(0.5, admission_choice="accepted_ai_editorial")
    ).status == "accept"
    assert decision_from_assessment(
        JevAssessment(0.5, admission_choice="non_ai")
    ).status == "reject"
    assert decision_from_assessment(
        JevAssessment(0.5, admission_choice="non_editorial")
    ).status == "reject"
    assert decision_from_assessment(
        JevAssessment(0.5, admission_choice="insufficient_evidence")
    ).status == "unresolved"


def test_admission_request_only_when_enabled() -> None:
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"answers": {
            "ai_relevant": {"noul": 0.8},
            "category": {"choice": "AI Coding", "confidence": 0.9},
            "admission": {"choice": "accepted_ai_editorial"},
        }})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        scorer = JevRelevanceScorer(
            client, "jev-1.13.0", getLogger("test"),
            semantic_admission_enabled=True,
        )
        result = scorer.classify(_article())
    assert result is not None
    assert result.admission_choice == "accepted_ai_editorial"
    payload = json.loads(requests[0].content)
    assert "admission" in payload["questions"]


def test_malformed_admission_pauses_even_with_valid_category() -> None:
    def respond(_request):
        return httpx.Response(200, json={"answers": {
            "ai_relevant": {"noul": 0.8},
            "category": {"choice": "AI Coding", "confidence": 0.9},
            "admission": "not-a-dict",
        }})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        scorer = JevRelevanceScorer(
            client, "jev-1.13.0", getLogger("test"),
            semantic_admission_enabled=True,
        )
        result = scorer.classify(_article())
    assert result is None
    assert scorer.failed is True


def test_cache_key_changes_with_prompt_version() -> None:
    first = admission_cache_key(
        url_canonical_hash="u", evidence_hash="e", model="m",
        policy_version="p", prompt_version="one",
    )
    second = admission_cache_key(
        url_canonical_hash="u", evidence_hash="e", model="m",
        policy_version="p", prompt_version="two",
    )
    assert first != second


@pytest.mark.parametrize("failure", ["timeout", 429, 503, "json", "admission", "score"])
def test_provider_failure_stops_all_further_requests(failure):
    calls = []

    def respond(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("offline test", request=request)
        if isinstance(failure, int):
            return httpx.Response(failure)
        if failure == "json":
            return httpx.Response(200, content="invalid json")
        return httpx.Response(200, json={"answers": {
            "ai_relevant": {"noul": True if failure == "score" else 0.9},
            "category": {"choice": "AI Coding", "confidence": 0.99},
            "admission": {"choice": "invalid" if failure == "admission" else (
                "accepted_ai_editorial"
            )},
        }})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        scorer = JevRelevanceScorer(
            client, "jev-1.13.0", getLogger("test"), semantic_admission_enabled=True,
        )
        assert scorer.classify(_article(1)) is None
        assert scorer.classify(_article(2)) is None
    assert scorer.failed and len(calls) == 1
