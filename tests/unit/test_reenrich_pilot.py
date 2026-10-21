"""Payment safety and source grounding using synthetic HTTP responses only."""
import importlib.util
import json
from logging import getLogger
from pathlib import Path

import httpx
import pytest

from app.core.daily.reenrich_pilot import (
    SUMMARY_RECOVERY_VERSION,
    TOPIC_CRITERIA,
    TOPIC_FALLBACK_VERSION,
    jev_request,
    parse_jev,
    parse_summary,
    request_key,
    reservation,
    summary_request,
    topic_request,
)
from app.core.jev import JevRelevanceScorer
from app.storage.legacy_cleanup import fingerprint
from app.storage.reenrich_pilot_journal import PilotJournal, PilotStopped

ROW = {"url": "https://example.com/article/ai", "title": "Synthetic AI release",
       "content": "The AI system handles document extraction for hospitals.",
       "summary": "An old model summary must never reach the providers."}
CAPS = {"total": "1.50", "jev": "0.25", "deepseek": "1.25"}


def jev_response(**overrides):
    return {"model": "jev-1.13.0", "usage": {"input_tokens": 1000}, "answers": {
        "ai_relevant": {"noul": 0.99},
        "admission": {"choice": "accepted_ai_editorial", "confidence": 0.99},
        "category": {"choice": "AI Applications", "confidence": 0.9},
        "comparison": {"choice": "NotComparison", "confidence": 0.9},
    }, **overrides}


def test_pilot_reuses_ordinary_admission_but_hashes_actual_topic_and_source():
    with httpx.Client() as client:
        ordinary = JevRelevanceScorer(client, "jev-1.13.0", getLogger(__name__),
                                      semantic_admission_enabled=True).questions()
    body = jev_request(ROW)
    assert body["questions"]["admission"] == ordinary["admission"]
    assert len(TOPIC_CRITERIA) == 10
    assert ROW["summary"] not in json.dumps(body)
    assert ROW["summary"] not in json.dumps(summary_request(ROW, False))
    key = request_key("jev", body)
    assert request_key("jev", jev_request({**ROW, "summary": "new generated summary"})) == key
    assert request_key("jev", jev_request({**ROW, "content": "Different evidence"})) != key
    changed = jev_request(ROW)
    changed["questions"]["category"]["criteria"]["AI Applications"] = "Changed criteria"
    assert request_key("jev", changed) != key


def test_unclassified_and_ambiguous_rejects_preserve_articles():
    data = jev_response()
    data["answers"]["category"]["confidence"] = 0.69
    result = parse_jev(ROW, data)
    assert result["topic"] is None and result["outcome"] == "kept"
    assert result["boundary_review"]
    assert not result["destructive_authority"]
    data["answers"]["admission"] = {"choice": "non_ai", "confidence": 0.99}
    assert parse_jev(ROW, data)["outcome"] == "unresolved"
    data["answers"]["category"]["confidence"] = float("nan")
    with pytest.raises(ValueError):
        parse_jev(ROW, data)


def test_paid_response_replays_after_process_restart_without_second_call(tmp_path):
    path = tmp_path / "journal.sqlite3"
    dispatched = []

    def handler(request):
        dispatched.append(request)
        return httpx.Response(200, json=jev_response())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        journal = PilotJournal(path, {"plan": "frozen"}, CAPS)
        body = jev_request(ROW)
        original = journal.call("jev", body, client, "synthetic-key")
        journal.close()
        journal = PilotJournal(path, {"plan": "frozen"}, CAPS)
        assert journal.call("jev", body, client, "synthetic-key") == original
        assert len(dispatched) == 1
        report = journal.report()
        assert report["providers"]["jev"]["usage_priced_usd"] == 0.000042
        journal.close()
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="budget changed"):
        PilotJournal(path, {"plan": "frozen"}, {**CAPS, "total": "2"})


@pytest.mark.parametrize("caps,provider", [
    ({"total": ".003", "jev": ".001", "deepseek": ".002"}, "jev"),
    ({"total": ".003", "jev": ".002", "deepseek": ".001"}, "deepseek"),
])
def test_provider_cap_refuses_dispatch(tmp_path, caps, provider):
    body = jev_request(ROW) if provider == "jev" else summary_request(ROW, False)
    journal = PilotJournal(tmp_path / "journal.sqlite3", {}, caps)
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: pytest.fail("No dispatch allowed"))) as client:
        with pytest.raises(PilotStopped, match="budget_limit"):
            journal.call(provider, body, client, "synthetic-key")
    assert journal.report()["total_committed_usd"] == 0
    journal.close()


def test_cumulative_limit_counts_both_providers_and_restart(tmp_path):
    # First JEV usage consumes .00210 of a total .003; a summary cannot fit.
    caps = {"total": ".003", "jev": ".0028", "deepseek": ".0002"}
    path = tmp_path / "journal.sqlite3"
    body = jev_request(ROW)
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json=jev_response(usage={"input_tokens": 50000})))) as client:
        journal = PilotJournal(path, {}, caps)
        journal.call("jev", body, client, "synthetic-key")
        journal.close()
        journal = PilotJournal(path, {}, caps)
        with pytest.raises(PilotStopped, match="budget_limit"):
            journal.reserve("new-call", "jev", 1000)
        journal.close()


@pytest.mark.parametrize("failure", ["network", "missing_usage", "inflight", "http"])
def test_unknown_or_failed_call_stops_resume_and_keeps_reservation(tmp_path, failure):
    path = tmp_path / "journal.sqlite3"
    body = jev_request(ROW)
    journal = PilotJournal(path, {}, CAPS)

    def handler(request):
        if failure == "network":
            raise httpx.ReadTimeout("synthetic", request=request)
        return httpx.Response(503 if failure == "http" else 200, json=jev_response(usage=None))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        if failure == "inflight":
            journal.reserve(request_key("jev", body), "jev", reservation("jev", body))
        else:
            with pytest.raises(PilotStopped):
                journal.call("jev", body, client, "synthetic-key")
    journal.close()
    journal = PilotJournal(path, {}, CAPS)
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: pytest.fail("Unknown outcomes must not retry"))) as client:
        with pytest.raises(PilotStopped):
            journal.call("jev", body, client, "synthetic-key")
        with pytest.raises(PilotStopped):
            journal.call("deepseek", summary_request(ROW, False), client, "synthetic-key")
    assert journal.report()["total_committed_usd"] == 0.002688
    journal.close()


def test_summary_requires_exact_quotes_and_products_only_for_comparison():
    value = {"facts": [{"sentence": "The system extracts documents in hospitals.",
                        "quote": ROW["content"]}], "compared_products": []}

    def response():
        return {"model": "deepseek-flash", "choices": [{"finish_reason": "stop",
                "message": {"content": json.dumps(value)}}]}

    result = parse_summary(ROW, response(), False)
    assert result["semantic_support_review_required"]
    value["facts"][0]["quote"] = "A fabricated exact source quotation."
    with pytest.raises(ValueError, match="quote"):
        parse_summary(ROW, response(), False)
    value["facts"][0]["quote"] = ROW["content"]
    value["compared_products"] = [{"name": "AI system", "quote": ROW["content"]}]
    with pytest.raises(ValueError, match="products"):
        parse_summary(ROW, response(), False)


@pytest.mark.parametrize("status,actual", [(503, 42), (200, 999999)])
def test_crash_after_receipt_before_validation_never_replays_invalid_response(
    tmp_path, status, actual,
):
    journal = PilotJournal(tmp_path / "journal.sqlite3", {}, CAPS)
    body = jev_request(ROW)
    key = request_key("jev", body)
    journal.reserve(key, "jev", reservation("jev", body))
    received = {"status_code": status, "body": jev_response()}
    journal.db.execute("UPDATE calls SET state='response',actual=?,response=? WHERE key=?",
                       (actual, json.dumps(received), key))
    journal.db.commit()
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: pytest.fail("Received response must not be repaid"))) as client:
        with pytest.raises(PilotStopped, match="saved_response"):
            journal.call("jev", body, client, "synthetic-key")
    journal.close()


def test_reviewed_truncation_preserves_spend_and_old_successes(tmp_path):
    journal = PilotJournal(tmp_path / "journal.sqlite3", {}, CAPS)
    old_body = summary_request(ROW, True)
    new_body = summary_request(ROW, True, output_cap=4096)
    assert request_key("deepseek", old_body) != request_key("deepseek", new_body)
    assert reservation("deepseek", new_body) > reservation("deepseek", old_body)
    dispatched = []

    def respond(request):
        dispatched.append(request)
        body = json.loads(request.content)
        return httpx.Response(200, json={"model": "deepseek-flash",
            "usage": {"prompt_tokens": 100, "completion_tokens": 300},
            "choices": [{"finish_reason": "length" if body["max_tokens"] == 300 else "stop",
                         "message": {"content": "synthetic stored response"}}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        journal.call("deepseek", old_body, client, "synthetic-key")
        key = request_key("deepseek", old_body)
        journal.fail(key, "InvalidSummary")
        spent = journal.report()["total_committed_usd"]
        assert journal.review_truncated_summaries("User authorised continuation") == [key]
        assert journal.report()["total_committed_usd"] == spent
        assert not journal.review_truncated_summaries("User authorised continuation")
        assert not journal.has_response("deepseek", old_body)
        journal.call("deepseek", new_body, client, "synthetic-key")
        assert journal.has_response("deepseek", new_body)
        journal.call("deepseek", new_body, client, "synthetic-key")
        assert len(dispatched) == 2
        assert journal.report()["total_committed_usd"] == 2 * spent
        assert journal.db.execute("SELECT state,response FROM calls WHERE key=?",
                                  (key,)).fetchone()[0] == "reviewed"
    journal.close()


def test_review_does_not_clear_unknown_billing(tmp_path):
    journal = PilotJournal(tmp_path / "journal.sqlite3", {}, CAPS)
    body = summary_request(ROW, True)
    key = request_key("deepseek", body)
    journal.reserve(key, "deepseek", reservation("deepseek", body))
    journal.fail(key, "InvalidSummary")
    assert not journal.review_truncated_summaries("User authorised continuation")
    with pytest.raises(PilotStopped):
        journal.reserve("replacement", "deepseek", 1000)
    journal.close()


@pytest.mark.parametrize("valid_quote", [True, False])
def test_length_review_reuses_complete_response_but_preserves_grounding(tmp_path, valid_quote):
    journal = PilotJournal(tmp_path / "journal.sqlite3", {}, CAPS)
    body = summary_request(ROW, False, output_cap=4096)
    value = {"facts": [{"sentence": " ".join(["synthetic"] * 82),
                        "quote": ROW["content"] if valid_quote else "Fabricated source quote"}],
             "compared_products": []}
    data = {"model": "deepseek-flash", "usage": {"prompt_tokens": 100, "completion_tokens": 300},
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]}
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=data))) as client:
        journal.call("deepseek", body, client, "synthetic-key")
    journal.fail(request_key("deepseek", body), "InvalidSummary")
    cost = journal.report()["total_committed_usd"]
    assert journal.restore_valid_summary(ROW, False, body, SUMMARY_RECOVERY_VERSION) == valid_quote
    assert journal.report()["total_committed_usd"] == cost
    if valid_quote:
        with httpx.Client(transport=httpx.MockTransport(
            lambda request: pytest.fail("Complete response must be reused"))) as client:
            saved = journal.call("deepseek", body, client, "synthetic-key")
        assert parse_summary(ROW, saved, False)["summary_length_review_required"]
    journal.close()


def test_quote_mapping_preserves_source_whitespace_and_rejects_omitted_words():
    row = {**ROW, "content": "The AI system\nhandles document extraction for hospitals."}
    value = {"facts": [{"sentence": "The system extracts documents.", "quote": ROW["content"]}],
             "compared_products": []}

    def response():
        return {"model": "deepseek-flash", "choices": [{"finish_reason": "stop",
                "message": {"content": json.dumps(value)}}]}

    result = parse_summary(row, response(), False)
    assert result["support"][0]["quote"] == row["content"]
    assert result["support"][0]["provider_quote"] == ROW["content"]
    value["facts"][0]["quote"] = "The AI system handles extraction for hospitals."
    with pytest.raises(ValueError, match="quote"):
        parse_summary(row, response(), False)


def test_driver_repairs_known_quote_failure_once_and_replays_success(tmp_path, monkeypatch):
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("pilot_driver", scripts / "reenrich_pilot.py")
    assert spec and spec.loader
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    journal = PilotJournal(tmp_path / "journal.sqlite3", {}, CAPS)
    dispatched = []

    def respond(request):
        dispatched.append(request)
        quote = "Fabricated source quotation" if len(dispatched) == 1 else ROW["content"]
        value = {"facts": [{"sentence": "The system extracts documents.", "quote": quote}],
                 "compared_products": []}
        return httpx.Response(200, json={"model": "deepseek-flash",
            "usage": {"prompt_tokens": 100, "completion_tokens": 100},
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        first = driver.obtain_summary(ROW, False, journal, client, "synthetic-key", 4096)
        second = driver.obtain_summary(ROW, False, journal, client, "synthetic-key", 4096)
    assert first == second
    assert len(dispatched) == 2
    assert journal.report()["providers"]["deepseek"]["states"] == {"reviewed": 1, "response": 1}
    journal.close()


def test_unclear_product_stays_unknown_without_discarding_grounded_summary():
    value = {"facts": [{"sentence": "The system extracts documents.", "quote": ROW["content"]}],
             "compared_products": [{"name": "Unverified product", "quote": ROW["content"]}]}
    data = {"model": "deepseek-flash", "choices": [{"finish_reason": "stop",
            "message": {"content": json.dumps(value)}}]}
    result = parse_summary(ROW, data, True)
    assert result["generated_summary"]
    assert not result["compared_products"]
    assert result["unresolved_compared_products"] == 1
    assert result["compared_products_status"] == "partial_unresolved"


def test_topic_fallback_request_is_bounded_versioned_and_summary_free():
    body = topic_request(ROW)
    assert body["max_tokens"] == 300 and reservation("deepseek", body) > 0
    assert "old model summary" not in json.dumps(body)
    assert set(json.loads(body["messages"][1]["content"])["topics"]) == set(TOPIC_CRITERIA)
    assert request_key("deepseek", body) == fingerprint(
        {"provider": "deepseek", "body": body, "version": TOPIC_FALLBACK_VERSION})
    assert request_key("deepseek", body) != request_key("deepseek", summary_request(ROW, False))
