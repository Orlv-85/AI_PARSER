"""publish_day guards and outputs; see enrichment.md."""
import json
import sqlite3
from contextlib import closing
from datetime import timedelta

import httpx
import pytest
from daily_fixtures import (  # pylint: disable=import-error,unused-import
    SOURCE,
    SUMMARY,
    TARGET,
    article,
    daily,
    daily_session,  # noqa: F401
    mock_client,
    provider_response,
    settings,
)
from pydantic import SecretStr

from app.storage.digest_repo import NewsDigestRepo
from app.storage.journal_files import encoded
from app.storage.provider_journal import PilotJournal


@pytest.mark.parametrize("change", [
    {"rubric": "old"}, {"summary_review": {"supported": 1}},
    {"summary_review": {}}, {"summary": {}}, {"summary": None},
])
def test_reusable_rejects_invalid_proof(session, change):
    row = article(session, proof=True)
    row.enrichment_provenance = encoded({**json.loads(row.enrichment_provenance), **change})
    assert daily.reusable(row) is False


@pytest.mark.parametrize("proof", ["not json", "null", "[]"])
def test_reusable_rejects_malformed_provenance(session, proof):
    row = article(session, proof=True)
    row.enrichment_provenance = proof
    assert daily.reusable(row) is False


@pytest.mark.parametrize(("text", "count", "expected"), [
    (SUMMARY, 0, False), (SUMMARY, 3, True), (SUMMARY, 4, False),
    ("", 1, False), ("x " * 79 + "x", 1, True), ("x " * 80 + "x", 1, False),
    ("x" * 400, 1, True), ("x" * 401, 1, False),
])
def test_reusable_summary_boundaries(session, text, count, expected):
    row = article(session, proof=True)
    proof = json.loads(row.enrichment_provenance)
    proof["summary"]["generated_summary"] = row.summary = text
    proof["summary"]["support"] *= count
    row.enrichment_provenance = encoded(proof)
    assert daily.reusable(row) is expected


@pytest.mark.parametrize("change", ["category", "summary", "quote", "hash"])
def test_reusable_rejects_mismatched_applied_summary(session, change):
    row = article(session, proof=True)
    proof = json.loads(row.enrichment_provenance)
    if change == "category":
        row.category = "Other"
    elif change == "summary":
        row.summary = "Different summary"
    elif change == "quote":
        proof["summary"]["support"][0]["quote"] = "An absent supporting quotation."
    else:
        proof["source_content_hash"] = "old hash"
    row.enrichment_provenance = encoded(proof)
    assert daily.reusable(row) is False


@pytest.mark.parametrize(("change", "reason"), [
    ({"semantic_admission_enabled": False}, "mandatory_admission_disabled"),
    ({"jev_api_key": None}, "missing_provider_key"),
    ({"ds_api_key": SecretStr("  ")}, "missing_provider_key"),
    ({"semantic_admission_enabled": False, "jev_api_key": None}, "mandatory_admission_disabled"),
])
def test_publish_day_guard_raises_before_any_journal_file(session, tmp_path, change, reason):
    article(session)
    config = settings()
    for name, value in change.items():
        setattr(config, name, value)
    with pytest.raises(ValueError, match=reason):
        daily.publish_day(session, config, TARGET, tmp_path / "cache")
    assert not list((tmp_path / "cache").rglob("journal.sqlite3*"))
    assert not (tmp_path / "cache" / TARGET.isoformat() / "report.json").exists()


def test_publish_day_writes_progress_json_after_each_non_reused_article(
        session, tmp_path, monkeypatch):
    for index in (1, 2):
        article(session, index).content = "short"
    session.commit()
    snapshots = []
    real_write = daily.private_write

    def spy(path, value):
        if path.name == "progress.json":
            snapshots.append(json.loads(json.dumps(value)))
        real_write(path, value)

    monkeypatch.setattr(daily, "private_write", spy)
    mock_client(monkeypatch, lambda _r: pytest.fail("Paid request without source"))
    daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    reason = "insufficient_source_or_date_evidence"
    assert snapshots == [
        {"counts": {reason: 1}, "held": [{"article_id": 1, "reason": reason}]},
        {"counts": {reason: 2}, "held": [{"article_id": 1, "reason": reason},
                                         {"article_id": 2, "reason": reason}]}]
    progress = tmp_path / "cache" / TARGET.isoformat() / "progress.json"
    assert json.loads(progress.read_text()) == snapshots[-1]


def test_publish_day_progress_json_records_held_article(session, tmp_path, monkeypatch):
    held = article(session)
    held.content = "short"
    session.commit()
    mock_client(monkeypatch, lambda _r: pytest.fail("Paid request without source"))
    daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    progress = tmp_path / "cache" / TARGET.isoformat() / "progress.json"
    assert json.loads(progress.read_text()) == {
        "counts": {"insufficient_source_or_date_evidence": 1},
        "held": [{"article_id": held.id, "reason": "insufficient_source_or_date_evidence"}]}


def test_publish_day_backup_file_holds_previous_digest(session, tmp_path, monkeypatch):
    article(session, proof=True)
    repo = NewsDigestRepo(session)
    repo.save_digest(report_date=TARGET, groups=[{"title": "Old group", "items": [
        {"title": "Old title", "summary": "Old summary", "url": "https://old.org/a"}]}])
    session.commit()
    created = repo.get_digest(report_date=TARGET).created_at
    mock_client(monkeypatch, lambda _r: pytest.fail("Paid request for cached data"))
    result = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    backup = tmp_path / "cache" / TARGET.isoformat() / result["backup_path"].split("/")[-1]
    assert backup.name.startswith("digest-before-") and backup.suffix == ".json"
    assert json.loads(backup.read_text()) == {
        "report_date": TARGET.isoformat(), "created_at": created.isoformat(),
        "groups": [{"title": "Old group", "items": [
            {"title": "Old title", "summary": "Old summary", "url": "https://old.org/a"}]}]}


def test_publish_day_commits_each_enrichment_before_a_later_failure(
        session, tmp_path, monkeypatch):
    first = article(session, 1)
    second = article(session, 2)
    second.content = SOURCE + " A second, different article body."
    session.commit()
    monkeypatch.setattr("app.storage.provider_journal.time.sleep", lambda _seconds: None)
    calls = []

    def respond(request):
        calls.append(request)
        if len(calls) > 3:
            raise httpx.ConnectError("down", request=request)
        return provider_response(request)

    mock_client(monkeypatch, respond)
    result = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert result["state"] == "failed_preserved_previous"
    assert daily.reusable(first) and not daily.reusable(second)


def test_publish_day_all_reused_writes_no_progress_json(session, tmp_path, monkeypatch):
    article(session, 1, proof=True)
    article(session, 2, proof=True)
    mock_client(monkeypatch, lambda _r: pytest.fail("Paid request for cached data"))
    result = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert result["counts"] == {"reused": 2}
    assert not (tmp_path / "cache" / TARGET.isoformat() / "progress.json").exists()


def test_publish_day_scope_change_preserves_previous_digest(session, tmp_path, monkeypatch):
    article(session, proof=True)
    repo = NewsDigestRepo(session)
    repo.save_digest(report_date=TARGET, groups=[{"title": "Previous", "items": [
        {"title": "Old", "summary": "Saved summary", "url": "https://old.org"}]}])
    session.commit()
    selected = []
    real_scope = daily.day_articles

    def scope(db, target):
        if selected:
            article(db, 2, proof=True)
        rows = real_scope(db, target)
        selected.append([row.id for row in rows])
        return rows

    monkeypatch.setattr(daily, "day_articles", scope)
    mock_client(monkeypatch, lambda _r: pytest.fail("Reusable article was billed"))
    result = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert selected == [[1], [1, 2]]
    assert result["reason"] == "daily_scope_changed_resume_required"
    assert result["state"] == "failed_preserved_previous"
    assert result["scope_complete"] is False
    assert result["counts"] == {"reused": 1}
    assert repo.get_digest(report_date=TARGET).groups[0].title == "Previous"
    assert not list((tmp_path / "cache").rglob("digest-before-*.json"))


def test_publish_day_dispatch_sees_committed_reservation(session, tmp_path, monkeypatch):
    article(session)
    root = tmp_path / "cache"
    seen = []

    def respond(request):
        body = json.loads(request.content)
        provider = "jev" if "questions" in body else "deepseek"
        key = daily.request_key(provider, body)
        with closing(sqlite3.connect(root / TARGET.isoformat() / "journal.sqlite3")) as db:
            state, reserved, actual = db.execute(
                "SELECT state,committed,actual FROM calls WHERE key=?", (key,)).fetchone()
        seen.append(provider)
        assert state == "inflight" and reserved > 0 and actual is None
        return provider_response(request)

    mock_client(monkeypatch, respond)
    result = daily.publish_day(session, settings(), TARGET, root)
    assert result["state"] == "published"
    assert seen == ["jev", "deepseek", "deepseek"]


@pytest.mark.parametrize(("failure", "reason"), [
    ("assessment", "invalid_daily_assessment"),
    ("model", "invalid_summary:Unexpected DeepSeek model,Unexpected DeepSeek model"),
    ("review", "invalid_semantic_review:review_truncated,review_truncated"),
])
def test_invalid_provider_answers_preserve_digest_and_billed_journal(
        session, tmp_path, monkeypatch, failure, reason):
    row = article(session)
    repo = NewsDigestRepo(session)
    repo.save_digest(report_date=TARGET, groups=[{"title": "Previous", "items": [
        {"title": "Old", "summary": "Saved", "url": "https://old.org"}]}])
    session.commit()
    calls = []

    def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        data = provider_response(request).json()
        if failure == "assessment" and "questions" in body:
            data["model"] = "other"
        if failure == "model" and "messages" in body:
            data["model"] = "other"
        if failure == "review" and "messages" in body and "entailment" in (
                body["messages"][0]["content"]):
            data["choices"][0]["finish_reason"] = "length"
        return httpx.Response(200, json=data)

    mock_client(monkeypatch, respond)
    root = tmp_path / "cache"
    report = daily.publish_day(session, settings(), TARGET, root)
    assert report["state"] == "failed_preserved_previous"
    assert report["reason"] == reason
    assert row.summary is None
    assert repo.get_digest(report_date=TARGET).groups[0].title == "Previous"
    journal = PilotJournal(root / TARGET.isoformat() / "journal.sqlite3",
                           {"version": daily.DAILY_VERSION, "day": TARGET.isoformat()}, daily.CAPS)
    saved = journal.db.execute("SELECT state, actual FROM calls ORDER BY rowid").fetchall()
    assert len(saved) == len(calls)
    assert all(state == "response" and actual > 0 for state, actual in saved)
    journal.close()


def test_non_kept_assessment_holds_without_summary_calls(session, tmp_path, monkeypatch):
    held = article(session)
    article(session, 2, proof=True)
    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        data = provider_response(request).json()
        data["answers"]["admission"] = {"choice": "non_ai", "confidence": 0.99}
        return httpx.Response(200, json=data)

    mock_client(monkeypatch, respond)
    result = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert result["held"] == [{"article_id": held.id, "reason": "unresolved"}]
    assert held.summary is None
    assert len(calls) == 1 and "questions" in calls[0]


@pytest.mark.parametrize("sentence", ["x " * 79 + "x", "x" * 400])
def test_grounded_summary_accepts_exact_length_limits(session, tmp_path, monkeypatch, sentence):
    row = article(session)

    def respond(request):
        response = provider_response(request)
        body = json.loads(request.content)
        if "messages" in body and "entailment" not in body["messages"][0]["content"]:
            data = response.json()
            data["choices"][0]["message"]["content"] = json.dumps({
                "facts": [{"sentence": sentence, "quote": SUMMARY}], "compared_products": []})
            return httpx.Response(200, json=data)
        return response

    mock_client(monkeypatch, respond)
    result = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert result["state"] == "published"
    assert row.summary == sentence and daily.reusable(row)


@pytest.mark.parametrize(("value", "error"), [
    ({}, "KeyError"), (None, "TypeError"),
])
def test_malformed_summary_records_exception_class(session, tmp_path, monkeypatch, value, error):
    article(session, proof=True)
    held = article(session, 2)

    def respond(request):
        data = provider_response(request).json()
        if "messages" in json.loads(request.content):
            data["choices"][0]["message"]["content"] = json.dumps(value)
        return httpx.Response(200, json=data)

    mock_client(monkeypatch, respond)
    result = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert result["held"] == [{"article_id": held.id, "reason": "summary_not_supported",
                               "details": [error, error]}]
    assert held.summary is None


def test_day_articles_end_is_exclusive_and_undated_rows_use_publication_day(session):
    article(session, 1, target=TARGET - timedelta(days=1))
    start = article(session, 2)
    article(session, 3, target=TARGET + timedelta(days=1))
    undated = article(session, 4)
    undated.published_at = None
    undated.publication_day = TARGET
    other = article(session, 5)
    other.published_at = None
    other.publication_day = TARGET + timedelta(days=1)
    dated = article(session, 6, target=TARGET + timedelta(days=1))
    dated.publication_day = TARGET
    session.commit()
    assert [row.id for row in daily.day_articles(session, TARGET)] == [start.id, undated.id]


@pytest.mark.parametrize("comparison", [False, True])
def test_publish_day_preserves_request_fields_and_comparison_provenance(
        session, tmp_path, monkeypatch, comparison):
    row = article(session)
    bodies, retries = [], []
    real_transport = daily.httpx.HTTPTransport

    def transport(**kwargs):
        retries.append(kwargs)
        return real_transport(**kwargs)

    def respond(request):
        body = json.loads(request.content)
        bodies.append(body)
        data = provider_response(request, comparison=(
            "Comparison" if comparison else "NotComparison", 0.99)).json()
        if comparison and "messages" in body and "entailment" not in (
                body["messages"][0]["content"]):
            value = json.loads(data["choices"][0]["message"]["content"])
            value["compared_products"] = [{"name": "AI system", "quote": SUMMARY}]
            data["choices"][0]["message"]["content"] = json.dumps(value)
        return httpx.Response(200, json=data)

    mock_client(monkeypatch, respond)
    monkeypatch.setattr(daily.httpx, "HTTPTransport", transport)
    root = tmp_path / "missing" / "parent" / "cache"
    report = daily.publish_day(session, settings(), TARGET, root)
    assert report["state"] == "published"
    assert report["scope_complete"] is True and report["enrichment_complete"] is True
    assert root.stat().st_mode & 0o777 == 0o700
    assert (root / TARGET.isoformat()).stat().st_mode & 0o777 == 0o700
    assert retries == [{"retries": 0}]
    assert row.material_type == ("Comparison" if comparison else None)
    assert json.loads(row.compared_products) == (["AI system"] if comparison else [])
    proof = json.loads(row.enrichment_provenance)
    assert proof["summary_review"]["model_review_not_ground_truth"] is True
    assert len(bodies) == 3
    for body in bodies[1:]:
        assert body["model"] == "deepseek-flash" and body["temperature"] == 0
        assert body["max_tokens"] == 4096 and body["thinking"] == {"type": "disabled"}
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][1]["role"] == "user"
    assert json.loads(bodies[1]["messages"][1]["content"]) == {
        "source": f"Title: {row.title}\nContent: {SOURCE}", "comparison": comparison}
    assert json.loads(bodies[2]["messages"][1]["content"]) == {
        "facts": proof["summary"]["support"]}


@pytest.mark.parametrize("sentence", ["x " * 79 + "x", "x" * 400])
def test_salvage_accepts_exact_length_limits(session, tmp_path, monkeypatch, sentence):
    row = article(session)

    def respond(request):
        body = json.loads(request.content)
        if "questions" in body:
            return provider_response(request)
        if "entailment" in body["messages"][0]["content"]:
            facts = json.loads(body["messages"][1]["content"])["facts"]
            supported = len(facts) == 1 and facts[0]["sentence"] == sentence
            return provider_response(request, supported=supported)
        data = provider_response(request).json()
        data["choices"][0]["message"]["content"] = json.dumps({"facts": [
            {"sentence": sentence, "quote": SUMMARY},
            {"sentence": "Unsupported detail.", "quote": SUMMARY}], "compared_products": []})
        return httpx.Response(200, json=data)

    mock_client(monkeypatch, respond)
    report = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert report["state"] == "published" and row.summary == sentence
    proof = json.loads(row.enrichment_provenance)
    assert proof["summary"]["partial"] == {"kept": 1, "dropped": 1}
    assert proof["summary_review"]["model_review_not_ground_truth"] is True


@pytest.mark.parametrize("message", [None, "custom collection pause"])
def test_publish_day_preserves_pause_reason(session, tmp_path, monkeypatch, message):
    monkeypatch.setattr(daily, "read_collection_status", lambda _session: (True, message))
    result = daily.publish_day(session, object(), TARGET, tmp_path / "cache")
    assert result["reason"] == (message or "collection_paused")
    assert result["state"] == "held_collection_paused"
    assert not list((tmp_path / "cache").rglob("journal.sqlite3*"))
