import json
from dataclasses import asdict
from datetime import UTC, datetime

import httpx
import pytest

from app.core.jev import JevAssessment
from app.core.legacy_cleanup import cleanup_verdict
from app.storage.cleanup_journal import CleanupJournal, CleanupStopped
from app.storage.legacy_cleanup import (
    build_manifest,
    cache_key,
    fingerprint,
    known_article_fk,
    verify_manifest,
)
from app.storage.non_news_cleanup import EXPORT_TABLES


def article(**overrides):
    return {"id": 1, "url": "https://example.com/about", "url_canonical":
            "https://example.com/about", "url_canonical_hash": "hash", "source_id": None,
            "title": "About us", "summary": None, "content": "Company history " * 30,
            "published_at": None, "rank_score": 0, **overrides}


def response(choice="non_editorial", confidence=0.99, score=0.01):
    return {"model": "jev-1.13.0", "answers": {
        "ai_relevant": {"noul": score}, "category": {"choice": "Other", "confidence": 1},
        "admission": {"choice": choice, "confidence": confidence}},
        "usage": {"input_tokens": 1000, "output_tokens": 10}}


@pytest.mark.parametrize("choice,confidence,score,url,body,outcome", [
    ("accepted_ai_editorial", 0.7, 0.99, "/news", "AI news", "kept"),
    ("accepted_ai_editorial", None, 0.9, "/research", "AI research", "kept"),
    ("accepted_ai_editorial", 0.99, 1, "/tutorial", "AI evergreen guide", "kept"),
    ("non_editorial", 0.99, 0.5, "/about", "Company", "rejected"),
    ("non_editorial", 0.99, 0.4, "/products/tool",
     "Features and pricing. Request a demo", "rejected"),
    ("non_ai", 0.99, 0.01, "/football", "Football results " * 30, "rejected"),
    ("non_ai", 0.99, 0.5, "/topic", "AI mentioned " * 30, "unresolved"),
    ("non_ai", 0.94, 0.01, "/topic", "Football results " * 30, "unresolved"),
    ("non_ai", None, 0.01, "/topic", "Football results " * 30, "unresolved"),
    ("non_ai", 0.99, 0.01, "/topic", "Short snippet", "unresolved"),
    ("non_editorial", 0.99, 0.1, "/blog/article", "Article " * 30, "unresolved"),
    ("insufficient_evidence", 0.99, 0.01, "/about", "Unknown", "unresolved"),
])
def test_conservative_policy(  # pylint: disable=too-many-positional-arguments
    choice, confidence, score, url, body, outcome,
):
    row = article(url="https://example.com" + url, title="Topic", content=body)
    verdict = cleanup_verdict(row, JevAssessment(score, admission_choice=choice,
                                                admission_confidence=confidence))
    assert verdict["outcome"] == outcome


def snapshot():
    tables = {name: [] for name in EXPORT_TABLES}
    tables["articles"] = [article()]
    return {"tables": tables, "screening": {"model": "jev-1.13.0", "policy_version": "p1",
                                           "prompt_version": "q1"}}


def test_current_accepted_cache_excluded_and_changed_evidence_rechecked():
    saved = snapshot()
    key = cache_key(saved["tables"]["articles"][0], saved["screening"])
    saved["tables"]["admission_decisions"] = [{
        "id": 1, "key": key, "provider_status": "ok", "decision": "accept",
        "url_canonical_hash": "hash", "payload": json.dumps({"assessment": asdict(
            JevAssessment(0.99, admission_choice="accepted_ai_editorial"))})}]
    manifest = build_manifest(saved, {})
    assert manifest["counts"] == {"kept": 1}
    verify_manifest(saved, manifest)
    saved["tables"]["articles"][0]["content"] += "New evidence"
    assert build_manifest(saved, {})["counts"] == {"unchecked": 1}


def test_manifest_retained_references_and_tamper_rejection():
    saved = snapshot()
    tables = saved["tables"]
    tables["weekly_decisions"] = [{"key": "decision", "payload": '{"article_id":1}'}]
    tables["weekly_snapshots"] = [{"id": "snap", "payload": '{"id":"article-1"}'}]
    tables["weekly_publications"] = [{"report_date": "2026-10-04", "snapshot_id": "snap"}]
    tables["news_digest_items"] = [{"id": 3, "group_id": 2, "url": article()["url"]}]
    tables["news_digest_groups"] = [{"id": 2, "report_id": 1}]
    tables["news_digest_reports"] = [{"id": 1}]
    manifest = build_manifest(saved, {})
    names = {ref["table"] for ref in manifest["entries"][0]["dependencies"]}
    assert {"weekly_decisions", "weekly_snapshots", "weekly_publications", "news_digest_items",
            "news_digest_groups", "news_digest_reports"} <= names
    manifest["entries"][0]["outcome"] = "rejected"
    with pytest.raises(ValueError, match="integrity"):
        verify_manifest(saved, manifest)


def test_invalid_embedded_urls_do_not_break_dependency_inventory():
    saved = snapshot()
    saved["tables"]["weekly_jobs"] = [{"id": "job", "input_payload":
                                      'Text: http://localhost:4723\\ and unrelated content'}]
    assert build_manifest(saved, {})["counts"] == {"unchecked": 1}


def test_journal_resume_and_response_before_verdict(tmp_path):
    path = tmp_path / "journal.sqlite"
    identity = {"snapshot": "s1", "model": "jev-1.13.0"}
    calls = []

    def transport(request):
        calls.append(request)
        return httpx.Response(200, json=response())

    store = CleanupJournal(path, identity)
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        first = store.evaluate(article(), "a", "jev-1.13.0", client, 2, 10)
        assert first["outcome"] == "rejected"
        assert store.usage()["usage_priced_usd"] == 0.000042
    store.reserve("b", 2, 10)
    raw = httpx.Response(200, json=response(), request=httpx.Request("POST", "https://test"))
    store.capture("b", raw)
    store.close()
    store = CleanupJournal(path, identity)
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        assert store.evaluate(article(), "a", "jev-1.13.0", client, 2, 10) == first
        assert store.evaluate(article(), "b", "jev-1.13.0", client, 2, 10) == first
    assert len(calls) == 1
    assert store.usage()["requests"] == 2
    store.close()
    with pytest.raises(ValueError, match="different snapshot"):
        CleanupJournal(path, {"model": "changed"})


@pytest.mark.parametrize("failure", ["outage", "bad_admission", "wrong_model"])
def test_failure_stops_and_does_not_repay(tmp_path, failure):
    calls = []

    def transport(request):
        calls.append(request)
        raw = response()
        if failure == "bad_admission":
            raw["answers"]["admission"]["confidence"] = "invalid"
        if failure == "wrong_model":
            raw["model"] = "another-model"
        return httpx.Response(503 if failure == "outage" else 200, json=raw)

    store = CleanupJournal(tmp_path / "journal.sqlite", {})
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        for _ in range(2):
            with pytest.raises(CleanupStopped, match="provider"):
                store.evaluate(article(), "key", "jev-1.13.0", client, 2, 10)
    assert len(calls) == 1
    assert store.verdicts()["key"]["outcome"] == "failed"
    store.close()


@pytest.mark.parametrize("budget,maximum", [(0.001, 10), (2, 0), (float("nan"), 1)])
def test_limits_stop_before_network(tmp_path, budget, maximum):
    store = CleanupJournal(tmp_path / "journal.sqlite", {})
    transport = httpx.MockTransport(lambda request: pytest.fail("paid call"))
    with httpx.Client(transport=transport) as client:
        with pytest.raises((CleanupStopped, ValueError)):
            store.evaluate(article(), "key", "jev-1.13.0", client, budget, maximum)
    assert store.usage()["requests"] == 0
    store.close()


def test_interrupted_inflight_is_not_paid_again(tmp_path):
    store = CleanupJournal(tmp_path / "journal.sqlite", {})
    store.reserve("key", 2, 10)
    with httpx.Client() as client:
        with pytest.raises(CleanupStopped, match="unknown_billing"):
            store.evaluate(article(), "key", "jev-1.13.0", client, 2, 10)
    assert store.usage()["unknown_usage_requests"] == 1
    store.close()


def test_timestamp_normalization():
    from app.storage.legacy_cleanup import normalize_snapshot  # pylint: disable=import-outside-toplevel
    saved = snapshot()
    saved["tables"]["articles"][0]["published_at"] = "2026-10-10 20:00:00+00:00"
    normalized = normalize_snapshot(saved)
    row = dict(normalized["tables"]["articles"][0])
    row["published_at"] = datetime(2026, 10, 10, 20, tzinfo=UTC)
    assert fingerprint(row) == fingerprint(normalized["tables"]["articles"][0])


def test_cleanup_guard_accepts_only_known_article_foreign_keys():
    cascade = {"constrained_columns": ["article_id"], "options": {"ondelete": "CASCADE"}}
    plain = {"constrained_columns": ["article_id"], "options": {}}
    assert known_article_fk("article_aliases", plain)
    assert known_article_fk("article_signals", cascade)
    assert known_article_fk("daily_signal_scope", cascade)
    assert not known_article_fk("article_signals", plain)
    assert not known_article_fk("other_table", cascade)
    assert not known_article_fk("daily_signal_scope",
                                 {**cascade, "constrained_columns": ["source_id"]})
