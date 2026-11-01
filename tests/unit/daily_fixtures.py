"""Shared fixtures for the daily enrichment tests (articles, settings, provider mock)."""
import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.daily import enrichment as daily
from app.core.daily.rubric import QUESTIONS
from app.storage.journal_files import encoded, fingerprint, private_write
from app.storage.models_sql import Article, Base

TARGET = date(2026, 10, 10)
SOURCE = "The company says its AI system handles document extraction for hospitals. " * 8
SUMMARY = "The company says its AI system handles document extraction for hospitals."
EXTRA = "The company also says a second unsupported detail."
REPAIRED = "The company says its AI system extracts documents for hospitals."


@pytest.fixture(name="session")
def daily_session(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "daily.sqlite3"))
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    engine.dispose()


def article(session, index=1, *, proof=False, target=TARGET):
    row = Article(title="AI document extraction", url=f"https://example.org/{index}",
                  url_canonical=f"https://example.org/{index}",
                  url_canonical_hash=f"{index:064x}", content=SOURCE,
                  published_at=datetime.combine(target, datetime.min.time(), tzinfo=UTC),
                  publication_status="confirmed", ai_relevance_score=0.9,
                  freshness_score=0.5, rank_score=0.7)
    if proof:
        row.summary = SUMMARY
        row.category = "AI Applications"
        row.enrichment_provenance = encoded({"rubric": daily.RUBRIC_VERSION,
            "source_content_hash": fingerprint(SOURCE),
            "summary": {"generated_summary": SUMMARY, "support": [
                {"sentence": SUMMARY, "quote": SUMMARY}]}, "summary_review": {"supported": True}})
    session.add(row)
    session.commit()
    return row


def settings():
    return SimpleNamespace(semantic_admission_enabled=True, jev_api_key=SecretStr("test-key"),
                           ds_api_key=SecretStr("test-key"))


def write_report(root, target, state):
    path = root / target.isoformat() / "report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    private_write(path, {"state": state})


async def no_download(*_args):
    pass


def mock_client(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(daily, "acquire", no_download)
    monkeypatch.setattr(daily.httpx, "Client", lambda **_kwargs:
                        real_client(transport=httpx.MockTransport(handler)))


def provider_response(request, *, truncate=False, supported=True, topic="AI Applications",
                      category=("AI Applications", 0.99), comparison=("NotComparison", 0.99),
                      reason=None):
    body = json.loads(request.content)
    if "questions" in body:
        assert body["questions"] == QUESTIONS
        assert "Summary:" not in body["state"]
        return httpx.Response(200, json={"model": "jev-1.13.0", "usage": {"input_tokens": 500},
            "answers": {"ai_relevant": {"noul": 0.99},
                "admission": {"choice": "accepted_ai_editorial", "confidence": 0.99},
                "category": {"choice": category[0], "confidence": category[1]},
                "comparison": {"choice": comparison[0], "confidence": comparison[1]}}})
    system = body["messages"][0]["content"]
    if daily.TOPIC_FALLBACK_VERSION in system:
        value = {"topic": topic, "confidence": 0.8, "reason": "Hospital document extraction."}
    elif "entailment" in system:
        value = {"supported": supported, "english": True}
        if reason:
            value["reason"] = reason
    else:
        value = {"facts": [{"sentence": SUMMARY, "quote": SUMMARY}], "compared_products": []}
    return httpx.Response(200, json={"model": "deepseek-flash",
        "usage": {"prompt_tokens": 500, "completion_tokens": 90},
        "choices": [{"finish_reason": "length" if truncate else "stop",
                     "message": {"content": json.dumps(value)}}]})
