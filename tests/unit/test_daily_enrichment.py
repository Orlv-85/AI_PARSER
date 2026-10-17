"""Daily publication coverage, grounding, cache reuse and failure isolation."""
import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config.sources import SourceConfig
from app.core import daily_enrichment as daily
from app.core.daily_rubric import QUESTIONS
from app.core.jev import JevRelevanceScorer
from app.core.models import Article as CoreArticle
from app.core.pipeline import _build_article_row
from app.storage.legacy_cleanup import encoded, fingerprint
from app.storage.models_sql import Article, Base
from app.storage.reenrich_pilot_journal import PilotJournal
from app.storage.repos import NewsDigestRepo

TARGET = date(2026, 10, 10)
SOURCE = "The company says its AI system handles document extraction for hospitals. " * 8
SUMMARY = "The company says its AI system handles document extraction for hospitals."


@pytest.fixture(name="session")
def daily_session(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "daily.sqlite3"))
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    engine.dispose()


def article(session, index=1, *, proof=False):
    row = Article(title="AI document extraction", url=f"https://example.org/{index}",
                  url_canonical=f"https://example.org/{index}",
                  url_canonical_hash=f"{index:064x}", content=SOURCE,
                  published_at=datetime(2026, 10, 10, 12, tzinfo=UTC),
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


async def no_download(*_args):
    pass


def mock_client(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(daily, "acquire", no_download)
    monkeypatch.setattr(daily.httpx, "Client", lambda **_kwargs:
                        real_client(transport=httpx.MockTransport(handler)))


def provider_response(request, *, truncate=False, supported=True, topic="AI Applications",
                      category=("AI Applications", 0.99), comparison=("NotComparison", 0.99)):
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
    else:
        value = {"facts": [{"sentence": SUMMARY, "quote": SUMMARY}], "compared_products": []}
    return httpx.Response(200, json={"model": "deepseek-flash",
        "usage": {"prompt_tokens": 500, "completion_tokens": 90},
        "choices": [{"finish_reason": "length" if truncate else "stop",
                     "message": {"content": json.dumps(value)}}]})


def test_complete_day_more_than_200_and_preserves_history(session, tmp_path, monkeypatch):
    for index in range(205):
        article(session, index, proof=True)
    repo = NewsDigestRepo(session)
    repo.save_digest(report_date=date(2026, 10, 9), groups=[
        {"title": "Frozen", "items": [
            {"title": "old", "url": "https://old.org", "summary": "Old"}]}])
    session.commit()
    mock_client(monkeypatch, lambda _r: pytest.fail("Paid request for cached data"))
    result = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert result["scope_count"] == result["published_count"] == 205
    assert result["usage"]["total_committed_usd"] == 0
    assert repo.get_digest(report_date=date(2026, 10, 9)).groups[0].title == "Frozen"


def test_new_summary_review_then_resume_without_provider_calls(session, tmp_path, monkeypatch):
    row = article(session)
    calls = []

    def respond(request):
        calls.append(request)
        return provider_response(request)

    mock_client(monkeypatch, respond)
    first = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert first["state"] == "published" and first["counts"] == {"enriched": 1}
    assert len(calls) == 3
    assert daily.reusable(row)
    second = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert len(calls) == 3
    assert second["counts"] == {"reused": 1}
    assert (tmp_path / "cache" / TARGET.isoformat()).joinpath(
        second["backup_path"].split("/")[-1]).exists()


@pytest.mark.parametrize("failure", ["outage", "truncated", "unsupported"])
def test_failure_retains_good_digest_and_records_reason(session, tmp_path, monkeypatch, failure):
    article(session)
    repo = NewsDigestRepo(session)
    repo.save_digest(report_date=TARGET, groups=[{"title": "Good", "items": [
        {"title": "Good", "summary": "Previously checked", "url": "https://good.org"}]}])
    session.commit()

    def respond(request):
        if failure == "outage":
            raise httpx.ConnectError("test-key", request=request)
        return provider_response(request, truncate=failure == "truncated",
                                 supported=failure != "unsupported")

    mock_client(monkeypatch, respond)
    result = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert result["state"] == "failed_preserved_previous"
    assert "reason" in result and "test-key" not in json.dumps(result)
    assert repo.get_digest(report_date=TARGET).groups[0].title == "Good"


def test_insufficient_evidence_is_explicit_and_never_an_excerpt(session, tmp_path, monkeypatch):
    article(session, proof=True)
    row = article(session, 2)
    row.content = "Tiny text"
    session.commit()
    mock_client(monkeypatch, lambda _r: pytest.fail("Insufficient input went to a provider"))
    result = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert result["scope_count"] == 2 and result["published_count"] == 1
    assert result["state"] == "published_with_holds"
    assert result["held"] == [{"article_id": row.id,
                                "reason": "insufficient_source_or_date_evidence"}]


def test_changed_source_invalidates_cached_summary(session):
    row = article(session, proof=True)
    assert daily.reusable(row)
    row.content += "New material"
    assert not daily.reusable(row)


def test_oversized_source_holds_without_dispatch_and_preserves_other_publication(
    session, tmp_path, monkeypatch,
):
    held = article(session)
    held.content = "\u00e9" * 16000
    article(session, 2, proof=True)
    session.commit()
    mock_client(monkeypatch, lambda _r: pytest.fail("Oversized input must not be dispatched"))
    report = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert report["state"] == "published_with_holds"
    assert report["published_count"] == 1
    assert report["held"] == [{"article_id": held.id, "reason": "source_input_too_large"}]
    assert report["usage"]["total_committed_usd"] == 0


def test_ordinary_ingestion_uses_rubric_journal_and_reusable_admission(tmp_path, session):
    from logging import getLogger  # pylint: disable=import-outside-toplevel

    calls = []

    def respond(request):
        calls.append(request)
        return provider_response(request)

    item = CoreArticle(source_key="test", title="AI document extraction",
                       url="https://example.org/1", content=SOURCE)
    journal = PilotJournal(tmp_path / "admission.sqlite3", {"version": "test"}, daily.CAPS)
    with httpx.Client(transport=httpx.MockTransport(respond),
                      headers={"Authorization": "Bearer test-key"}) as client:
        scorer = JevRelevanceScorer(client, "jev-1.13.0", getLogger(__name__),
            semantic_admission_enabled=True, daily_enrichment_enabled=True,
            payment_journal=journal)
        assessment = scorer.classify(item)
        assert assessment.category == "AI Applications"
        second = JevRelevanceScorer(client, "jev-1.13.0", getLogger(__name__),
            semantic_admission_enabled=True, daily_enrichment_enabled=True,
            payment_journal=journal)
        assert second.classify(item) == assessment
    assert len(calls) == 1
    assert journal.report()["providers"]["jev"]["calls"] == 1
    journal.close()
    config = SourceConfig(id="test", name="Test", type="rss", url="https://example.org/feed")
    values = _build_article_row(item=item, config=config, db_source_id=1,
        canonical=item.url, canonical_hash="hash", assessment=assessment, admission_enabled=True)
    row = article(session)
    row.enrichment_provenance = values["enrichment_provenance"]
    data = daily.admission_from_proof(row, {"title": item.title, "content": SOURCE})
    assert data["answers"]["admission"]["choice"] == "accepted_ai_editorial"
    assert data["answers"]["comparison"]["choice"] == "NotComparison"


@pytest.mark.parametrize("schema", ["facts", "string_flags", "list"])
def test_review_schema_recovery_does_not_regenerate_summary(
    session, tmp_path, monkeypatch, schema,
):
    row = article(session)
    calls = []

    def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        response = provider_response(request)
        if "messages" not in body:
            return response
        prompt = body["messages"][0]["content"]
        if "entailment" in prompt and "Schema recovery task" not in prompt:
            value = {"facts": []} if schema == "facts" else (
                {"supported": "true", "english": True} if schema == "string_flags" else [])
            data = response.json()
            data["choices"][0]["message"]["content"] = json.dumps(value)
            return httpx.Response(200, json=data)
        return response

    mock_client(monkeypatch, respond)
    first = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert first["state"] == "published"
    assert len(calls) == 4
    summary_calls = [body for body in calls if "messages" in body and
                     "entailment" not in body["messages"][0]["content"]]
    assert len(summary_calls) == 1
    proof = json.loads(row.enrichment_provenance)
    assert proof["summary_review"]["schema_recovery"] == ["review_schema"]
    second = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert second["state"] == "published" and len(calls) == 4


def unresolved_proof(row, missing):
    assessment = {"relevance_score": 0.99, "admission_choice": "accepted_ai_editorial",
                  "admission_confidence": 0.99, "category": "AI Applications",
                  "category_confidence": 0.99, "comparison_choice": "NotComparison",
                  "comparison_confidence": 0.99}
    assessment["category" if missing == "category" else "comparison_choice"] = None
    assessment[missing + "_confidence"] = None
    row.enrichment_provenance = encoded({"rubric": daily.RUBRIC_VERSION,
        "admission_source_hash": fingerprint(daily.source_state(
            {"title": row.title, "content": SOURCE})), "admission_assessment": assessment})


def test_unresolved_ingestion_comparison_publishes_without_badge_or_jev_call(
    session, tmp_path, monkeypatch,
):
    row = article(session)
    unresolved_proof(row, "comparison")
    session.commit()
    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        assert "questions" not in calls[-1], "Saved admission proof must not be re-billed"
        return provider_response(request)

    mock_client(monkeypatch, respond)
    result = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert result["state"] == "published" and result["published_count"] == 1
    assert row.category == "AI Applications" and row.material_type is None
    assert not any(daily.TOPIC_FALLBACK_VERSION in c["messages"][0]["content"] for c in calls)


def test_unresolved_ingestion_topic_uses_deepseek_fallback_then_resumes_free(
    session, tmp_path, monkeypatch,
):
    row = article(session)
    article(session, 2, proof=True)
    unresolved_proof(row, "category")
    session.commit()
    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        assert "questions" not in calls[-1], "Saved admission proof must not be re-billed"
        return provider_response(request, topic="Infrastructure")

    mock_client(monkeypatch, respond)
    first = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert first["state"] == "published" and first["published_count"] == 2
    assert row.category == "Infrastructure" and row.category_confidence == 0.8
    proof = json.loads(row.enrichment_provenance)
    assert proof["topic_source"] == "deepseek_fallback"
    assert proof["topic_fallback"]["version"] == daily.TOPIC_FALLBACK_VERSION
    paid = len(calls)
    assert sum(daily.TOPIC_FALLBACK_VERSION in c["messages"][0]["content"] for c in calls) == 1
    second = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert second["state"] == "published" and len(calls) == paid


@pytest.mark.parametrize("answer", [None, "Not A Topic"])
def test_unresolved_fallback_topic_holds_only_that_article(
    session, tmp_path, monkeypatch, answer,
):
    held = article(session)
    article(session, 2, proof=True)
    unresolved_proof(held, "category")
    session.commit()
    mock_client(monkeypatch, lambda r: provider_response(r, topic=answer))
    result = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert result["state"] == "published_with_holds" and result["published_count"] == 1
    assert result["held"] == [{"article_id": held.id, "reason": "topic_or_type_unresolved"}]
    assert held.summary is None


def test_confident_topic_with_uncertain_comparison_is_published(session, tmp_path, monkeypatch):
    row = article(session)
    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        return provider_response(request, category=("Infrastructure", 0.9),
                                 comparison=("Comparison", 0.67))

    mock_client(monkeypatch, respond)
    result = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert result["state"] == "published" and result["published_count"] == 1
    assert row.category == "Infrastructure" and row.material_type is None
    assert json.loads(row.enrichment_provenance)["topic_source"] == "jev"
    assert not any("messages" in c and daily.TOPIC_FALLBACK_VERSION in
                   c["messages"][0]["content"] for c in calls)


def test_low_confidence_jev_topic_uses_fallback(session, tmp_path, monkeypatch):
    row = article(session)
    mock_client(monkeypatch, lambda r: provider_response(
        r, category=("AI Applications", 0.55), topic="Models & Research"))
    result = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert result["state"] == "published"
    assert row.category == "Models & Research"


@pytest.mark.parametrize(("raw", "clean"), [
    ("pplx-decider-v1.1-27b (Hugging Face Repo)", "pplx-decider-v1.1-27b"),
    ("Introducing Clef-omni for audio (7 minute read)", "Introducing Clef-omni for audio"),
    ("agent-kit (GitHub Repo) (3 min read)", "agent-kit"),
    ("Best QA Tools Compared (2026)", "Best QA Tools Compared (2026)"),
    ("Cheap GPUs for everyone (Sponsor)", "Cheap GPUs for everyone (Sponsor)"),
    ("(5 minute read)", "(5 minute read)"),
])
def test_digest_title_strips_only_aggregator_decorations(raw, clean):
    assert daily.digest_title(raw) == clean


def test_digest_uses_clean_title_without_changing_stored_title(session):
    row = article(session, proof=True)
    row.title = "AI document extraction (4 minute read)"
    session.commit()
    groups = daily.digest_groups([row])
    assert groups[0]["items"][0]["title"] == "AI document extraction"
    assert row.title == "AI document extraction (4 minute read)"


def test_explicit_unsupported_review_holds_one_article_and_reuses_billed_work(
    session, tmp_path, monkeypatch,
):
    article(session, proof=True)
    held = article(session, 2)
    calls = []

    def respond(request):
        calls.append(request)
        return provider_response(request, supported=False)

    mock_client(monkeypatch, respond)
    first = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert first["state"] == "published_with_holds"
    assert first["scope_count"] == 2 and first["published_count"] == 1
    assert first["held"] == [{"article_id": held.id, "reason": "summary_not_supported",
                              "details": ["summary_not_entailed_or_not_english"] * 2}]
    assert held.enrichment_provenance is None
    # Identical repaired facts reuse the already billed unsupported review.
    assert len(calls) == 4
    second = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert second["state"] == "published_with_holds"
    assert len(calls) == 4


def test_ungrounded_quote_holds_one_article_instead_of_failing_day(
    session, tmp_path, monkeypatch,
):
    article(session, proof=True)
    held = article(session, 2)

    def respond(request):
        body = json.loads(request.content)
        if "questions" in body or "entailment" in body["messages"][0]["content"]:
            return provider_response(request)
        value = {"facts": [{"sentence": SUMMARY, "quote": "A quote absent from the source."}],
                 "compared_products": []}
        return httpx.Response(200, json={"model": "deepseek-flash",
            "usage": {"prompt_tokens": 500, "completion_tokens": 90},
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]})

    mock_client(monkeypatch, respond)
    result = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert result["state"] == "published_with_holds"
    assert result["published_count"] == 1
    assert result["held"] == [{"article_id": held.id, "reason": "summary_not_supported",
                               "details": ["Unsupported summary quote"] * 2}]


def test_provider_overload_is_retried_then_resumable(session, tmp_path, monkeypatch):
    article(session)
    sleeps = []
    monkeypatch.setattr("app.storage.reenrich_pilot_journal.time.sleep", sleeps.append)
    busy = {"remaining": 4}

    def respond(request):
        if busy["remaining"]:
            busy["remaining"] -= 1
            return httpx.Response(503, json={"error": {"code": "service_unavailable_error"}})
        return provider_response(request)

    mock_client(monkeypatch, respond)
    first = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert first["state"] == "failed_preserved_previous"
    assert first["reason"] == "provider_response_failed"
    assert len(sleeps) == 3
    # The unbilled overload answer must not block an explicit resume.
    busy["remaining"] = 1
    second = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert second["state"] == "published"
    assert second["counts"] == {"enriched": 1}
