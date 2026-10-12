# pylint: disable=protected-access
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, date, datetime

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.core.weekly_analytics import DEFAULT_THRESHOLDS, Observation, _metrics, calculate, windows
from app.core.weekly_enrichment import WeeklyEnricher
from app.core.weekly_frozen import (
    FILES,
    compatible_assignments,
    file_hash,
    narrative_invariants,
    packet_from_manifest,
    prepare,
    prepare_narrative_revision,
    publish_prepared,
    run,
    verified_input,
)
from app.core.weekly_input import publication, source_fingerprint
from app.storage.models_sql import Article, Base, WeeklyInputObservation
from app.storage.weekly import WeeklyStore, encoded
from app.web.models import WeeklyAnalyticsResponse


def fixture_input():
    body = "Coding agents help software engineers build and test applications."
    evidence = {"quality": "extracted", "title": "Coding agents", "text_sha256":
                hashlib.sha256(body.encode()).hexdigest()}
    source_hash = source_fingerprint(f"Title: Coding agents\nContent: {body}")
    article = {"id": 1, "source_id": 1, "title": "Stored title before extraction",
               "summary": "Generated summary must not be source evidence", "content": "Old body",
               "url_canonical": "https://example.com/one", "url_canonical_hash": "one",
               "publication_status": "confirmed"}
    record = {"article_id": 1, "canonical_hash": "one", "window": "W0",
              "date_class": "confirmed_timestamp", "text_origin": "saved_page",
              "source_evidence_ref": source_fingerprint(evidence),
              "source_text_sha256": evidence["text_sha256"], "effective_precision": "second",
              "effective_published_at": "2026-10-08T12:00:00+00:00", "calendar_date": None,
              "possible_utc_interval": None, "publisher": "example.com", "observation_ids": [],
              "admission_refs": [{"kind": "cached_mass_admission", "source_hash": source_hash}],
              "possible_windows": ["W0"], "unresolved_reasons": []}
    runtime = {"report_date": "2026-10-11", "data_cutoff": "2026-10-12T07:00:00+00:00",
               "topics": [{"id": "coding-agents", "label": "Coding agents", "definition": "Coding",
                           "exclusions": "Other uses", "aliases": [],
                           "parent_category": "Applications"}], "taxonomy_version": "test-topics",
               "methodology_version": "attention-v2.1", "coverage": [],
               "thresholds": asdict(DEFAULT_THRESHOLDS), "provider_configuration": {},
               "window_complete": True}
    snapshot = {"tables": {"articles": [article], "admission_decisions": []},
                "runtime_freeze": runtime, "pilot_cache": {"decisions": [], "progress": []}}
    bundle = {"pages": {"1": {"text": body, "evidence": evidence, "integrity_ok": True}},
              "mass_results": [{"article_id": 1, "outcome": "kept", "source_hash": source_hash,
                                "assessment": {"admission_choice": "accepted_ai_editorial"}}]}
    manifest = {"revision": 4, "records": [record], "report_date": "2026-10-11",
                "deleted_article_tombstones": [], "observations": [],
                "counts": {k: {"total": 0} for k in ("unassigned", "outside_scope",
                                                        "boundary_ambiguous")}}
    return dict(zip(FILES[:3], (snapshot, manifest, bundle), strict=True))


def write_input(root, supplied=None):
    root.mkdir(mode=0o700)
    inputs = {**(supplied or fixture_input()), FILES[3]: {}}
    for name, value in inputs.items():
        (root / name).write_text(encoded(value))
    receipt = {key: {"sha256": file_hash(root / name)} for key, name in
               (("snapshot", FILES[0]), ("manifest", FILES[1]), ("source_evidence", FILES[2]),
                ("published_target", FILES[3]))}
    (root / FILES[4]).write_text(encoded(receipt))
    return {name: file_hash(root / name) for name in FILES}


def test_hashes_checked_before_parsing_and_old_manifest_refused(tmp_path):
    root = tmp_path / "input"
    expected = write_input(root)
    assert verified_input(root, expected)[FILES[1]]["revision"] == 4
    (root / FILES[0]).write_text("invalid JSON and modified bytes")
    with pytest.raises(ValueError, match="hash differs"):
        verified_input(root, expected)


def test_selected_source_and_admission_are_checked_independently():
    inputs = fixture_input()
    packet = packet_from_manifest(inputs)
    row = packet["observations"][0]
    assert row["summary"] is None
    assert row["title"] == "Coding agents"
    assert row["admission_state"] == "accepted_compatible"
    inputs[FILES[2]]["mass_results"][0]["source_hash"] = "stale"
    assert packet_from_manifest(inputs)["observations"][0]["admission_state"] == "unresolved"
    inputs[FILES[2]]["pages"]["1"]["text"] = "modified body"
    with pytest.raises(ValueError, match="source body differs"):
        packet_from_manifest(inputs)


@pytest.mark.parametrize("changed", ["text", "task", "model", "prompt", "taxonomy", "cap",
                                      "admission"])
def test_reuse_requires_full_key_and_admission(changed):
    inputs = fixture_input()
    packet = packet_from_manifest(inputs)
    config = Settings(_env_file=None)
    service = WeeklyEnricher(config, None, None, packet["topics"],  # type: ignore[arg-type]
                            packet["taxonomy_version"])
    row = packet["observations"][0]
    key = service._key("assignment", {"text": service.assignment_text(row)})
    decision = {"key": key, "task": "assignment", "payload": encoded({
        "eligible": True, "topic_id": "coding-agents", "possible_topics": ["coding-agents"],
        "classification_complete": True})}
    inputs[FILES[0]]["pilot_cache"]["decisions"] = [decision]
    inputs[FILES[0]]["pilot_cache"]["progress"] = [{"key": "classified:1",
        "payload": {"published_at": "invented", "event_id": "old", "eligible": True}}]
    assert len(compatible_assignments(inputs[FILES[0]], packet, service)) == 1
    if changed == "text":
        row["content"] += " Changed source"
    elif changed == "task":
        decision["task"] = "narrative"
    elif changed == "model":
        service.settings = config.model_copy(update={"weekly_jev_model": "other"})
    elif changed == "prompt":
        service.settings = config.model_copy(update={"weekly_prompt_version": "other"})
    elif changed == "taxonomy":
        service.taxonomy_version = "different-topics"
    elif changed == "cap":
        service.settings = config.model_copy(update={"weekly_input_token_cap": 15000})
    else:
        row["admission_state"] = "unresolved"
    assert not compatible_assignments(inputs[FILES[0]], packet, service)


def test_calendar_boundaries_normalized_and_unknown_dates():
    periods = windows(date(2026, 10, 11))
    article = {"publication_status": "confirmed", "publication_precision": "day",
               "publication_day": "2026-10-08"}
    result = publication(article, periods)
    assert result["window_index"] == 0 and result["published_at"] is None
    assert result["calendar_date"] == "2026-10-08"
    boundary = publication({**article, "publication_day": "2026-10-05"}, periods)
    assert boundary["window_index"] is None and boundary["possible_windows"] == [0, 1]
    normalized = publication({"publication_status": "confirmed",
        "publication_precision": "normalized_timestamp", "published_at": "2026-10-08T00:00:00Z"},
        periods)
    assert normalized["window_index"] is None
    assert normalized["date_reason"] == "normalized_precision_unverified"
    assert publication({"publication_status": "unknown", "discovered_at":
                        "2026-10-08T12:00:00Z"}, periods)["window_index"] is None
    for provenance in ("null", "[]", "invalid JSON", '{"published":null}'):
        assert publication({"publication_status": "unknown", "date_provenance": provenance},
                           periods)["window_index"] is None


def test_calendar_facts_have_no_invented_day_support_or_timestamp_matching():
    interval = {"start": "2026-10-07T10:00:00+00:00", "end": "2026-10-09T12:00:00+00:00"}
    row = Observation("1", "1", "example.com", None, "coding-agents", title="Coding agents",
                      url="https://example.com/one", calendar_date="2026-10-08",
                      publication_precision="day", publication_interval=interval)
    result = calculate(date(2026, 10, 11), [row], [], [{"id": "coding-agents", "label": "Coding"}],
                       now=datetime(2026, 10, 12, tzinfo=UTC))
    item = result["other_signals"][0]
    assert item["event_count_current"] == 1 and item["share_current"] is None
    assert item["state"] == "insufficient_evidence" and item["evidence"][0]["published_at"] is None
    assert _metrics([row], "coding-agents", {"example.com"})["days"] == 0
    precise = Observation("2", "2", "another.com", datetime(2026, 10, 10, tzinfo=UTC),
                          "coding-agents")
    mixed = calculate(date(2026, 10, 11), [row, precise], [],
                      [{"id": "coding-agents", "label": "Coding"}],
                      now=datetime(2026, 10, 12, tzinfo=UTC))
    assert mixed["other_signals"][0]["first_observed_at"] is None
    requests = []
    with httpx.Client(transport=httpx.MockTransport(requests.append)) as client:
        service = WeeklyEnricher(Settings(_env_file=None), None, client, [], "test")  # type: ignore[arg-type]
        rows = [{"id": str(i), "published_at": None, "publication_interval": interval,
                 "canonical_hash": str(i), "title": "Coding agents launch", "topic_id": "coding"}
                for i in range(2)]
        clustered, complete = service.cluster(rows)
    assert not requests and not complete
    assert clustered[0]["event_id"] != clustered[1]["event_id"]


def test_current_articles_override_stale_conflicts_and_deleted_rejects(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'scope.sqlite'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for i, status, stamp in ((1, "confirmed", "2026-10-08T12:00:00+00:00"),
                                 (2, "conflict", "2026-10-08T12:00:00+00:00"),
                                 (3, "confirmed", "2026-07-01T12:00:00+00:00"),
                                 (4, "confirmed", "2026-06-29T12:00:00+00:00")):
            session.add(Article(id=i, source_id=1, title=f"Current {i}",
                url=f"https://example.com/{i}", url_canonical=f"https://example.com/{i}",
                url_canonical_hash=str(i), publication_status=status,
                publication_precision="second", published_at=datetime.fromisoformat(stamp),
                discovered_at=datetime(2026, 10, 9, tzinfo=UTC)))
        for i in range(2, 6):
            session.add(WeeklyInputObservation(id=str(i), source_id=1, canonical_hash=str(i),
                published_at=datetime(2026, 10, 8, tzinfo=UTC),
                discovered_at=datetime(2026, 10, 9, tzinfo=UTC),
                payload=encoded({"title": "Stale observation", "content": "Deleted reject"})))
        session.commit()
        packet = WeeklyStore(session).freeze_input(date(2026, 10, 11), Settings(_env_file=None))
    assert [r["article_id"] for r in packet["observations"]] == [1]
    assert packet["observations"][0]["publication_provenance"] == "current_article"
    assert packet["unassigned_articles"][0]["date_reason"] == "conflict"
    assert packet["quality_counters"]["orphan_observations"] == 1
    engine.dispose()


def test_frozen_runner_resumes_budget_and_publishes_without_models(tmp_path, monkeypatch):
    inputs = tmp_path / "input"
    supplied = fixture_input()
    snapshot, manifest, bundle = (supplied[name] for name in FILES[:3])
    snapshot["tables"]["articles"].append({**snapshot["tables"]["articles"][0], "id": 2,
        "url_canonical_hash": "two", "url_canonical": "https://example.com/two"})
    body = bundle["pages"]["1"]["text"] + " A separate release."
    evidence = {**bundle["pages"]["1"]["evidence"], "text_sha256": hashlib.sha256(
        body.encode()).hexdigest()}
    source_hash = source_fingerprint(f"Title: Coding agents\nContent: {body}")
    bundle["pages"]["2"] = {"text": body, "evidence": evidence, "integrity_ok": True}
    bundle["mass_results"].append({**bundle["mass_results"][0], "article_id": 2,
                                  "source_hash": source_hash})
    manifest["records"].append({**manifest["records"][0], "article_id": 2,
        "canonical_hash": "two", "source_evidence_ref": source_fingerprint(evidence),
        "source_text_sha256": evidence["text_sha256"], "admission_refs": [
            {"kind": "cached_mass_admission", "source_hash": source_hash}]})
    expected = write_input(inputs, supplied)
    root = tmp_path / "run"
    config = Settings(_env_file=None, jev_api_key="key", ds_api_key="key",
                      weekly_jev_decision_budget=1)
    prep = prepare(inputs, root, expected, {"total": "1", "jev": "0.5", "deepseek": "0.5"}, config)
    assert prep["scope"] == 2 and prep["paid_calls"] == 0
    requests = []

    def handler(request):
        requests.append(request)
        if "same_event" in json.loads(request.content)["questions"]:
            return httpx.Response(200, json={"answers": {"same_event": {"noul": 0.05}},
                                             "usage": {"input_tokens": 100}})
        return httpx.Response(200, json={"answers": {"relevant": {"noul": 0.95},
            "topic": {"choice": "coding-agents", "confidence": 0.95}},
            "usage": {"input_tokens": 100}})

    client_type = httpx.Client
    monkeypatch.setattr("app.core.weekly_frozen.httpx.Client", lambda **_: client_type(
        transport=httpx.MockTransport(handler)))
    monkeypatch.setattr("app.core.weekly_worker.explain", lambda *args: False)
    first = run(root, config)
    assert first["status"] == "retry" and len(requests) == 1
    assert run(root, config)["status"] == "retry" and len(requests) == 2
    assert run(root, config)["status"] == "complete" and len(requests) == 3
    assert run(root, config)["status"] == "complete" and len(requests) == 3
    payload = json.loads((root / "candidate.json").read_text())
    WeeklyAnalyticsResponse.model_validate(payload)
    assert payload["other_signals"][0]["event_count_current"] == 2
    engine = create_engine(f"sqlite:///{tmp_path / 'publication.sqlite'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        store = WeeklyStore(session)
        result = publish_prepared(root, store, file_hash(root / "candidate.json"))
        assert result["provider_calls"] == 0
        assert store.published(date(2026, 10, 11))["snapshot_id"] == first["snapshot_id"]
        assert publish_prepared(root, store, file_hash(root / "candidate.json"))["already_stored"]
        with pytest.raises(ValueError, match="Candidate hash"):
            publish_prepared(root, store, "changed")
    assert len(requests) == 3
    engine.dispose()


def test_narrative_revision_preserves_calculation_resumes_and_publishes_without_providers(
    tmp_path, monkeypatch
):
    inputs, parent, root = (tmp_path / name for name in ("inputs", "parent", "prose"))
    config = Settings(_env_file=None, jev_api_key="key", ds_api_key="key")
    prepare(inputs, parent, write_input(inputs),
            {"total": "1", "jev": "0.5", "deepseek": "0.5"}, config)
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if request.url.host == "api.deepseek.com":
            packet = json.loads(body["messages"][1]["content"])
            evidence = packet["evidence"][0]
            claim = {"text": "Coding agents help software engineers build and test applications.",
                     "evidence_ids": [evidence["id"]], "quotes": [{"evidence_id": evidence["id"],
                         "span": evidence["excerpt"]}]}
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
                "content": encoded({"topic_id": "coding-agents", "claims": [claim]})}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 100}})
        questions = body["questions"]
        answers = ({name: {"noul": 0.99} for name in questions} if "supported" in questions else {
            "relevant": {"noul": 0.95}, "topic": {"choice": "coding-agents", "confidence": 0.95}})
        return httpx.Response(200, json={"answers": answers, "usage": {"input_tokens": 100}})

    client_type = httpx.Client
    monkeypatch.setattr("app.core.weekly_frozen.httpx.Client", lambda **_: client_type(
        transport=httpx.MockTransport(handler)))
    monkeypatch.setattr("app.core.weekly_worker.explain", lambda *args: False)
    assert run(parent, config)["status"] == "complete"
    original = json.loads((parent / "candidate.json").read_text())
    parent_bytes = {p.name: p.read_bytes() for p in parent.iterdir() if p.is_file()}
    prepare_narrative_revision(parent, root, file_hash(parent / "candidate.json"),
                               ["coding-agents"], config)
    monkeypatch.setattr("app.core.weekly_frozen.build_snapshot", lambda *args: pytest.fail(
        "Must not recompute admission/classification/events/metrics"))
    count = len(requests)
    assert run(root, config)["status"] == "complete"
    assert len(requests) == count + 2
    revised = json.loads((root / "candidate.json").read_text())
    assert revised["other_signals"][0]["narrative_mode"] == "deepseek"
    assert revised["other_signals"][0]["narrative_support"][0]["score"] >= 0.85
    assert narrative_invariants(revised) == narrative_invariants(original)
    assert all((parent / name).read_bytes() == value for name, value in parent_bytes.items())
    count = len(requests)
    assert run(root, config)["status"] == "complete" and len(requests) == count
    engine = create_engine(f"sqlite:///{tmp_path / 'target.sqlite'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        with pytest.raises(ValueError, match="publication drifted"):
            publish_prepared(root, WeeklyStore(session), file_hash(root / "candidate.json"),
                             expected_previous_snapshot_id="unexpected")
        result = publish_prepared(root, WeeklyStore(session), file_hash(root / "candidate.json"))
        assert result["provider_calls"] == 0
        assert len(requests) == count
        revised["other_signals"][0]["event_count_current"] += 1
        (root / "candidate.json").write_text(encoded(revised))
        with pytest.raises(ValueError, match="changed calculated facts"):
            publish_prepared(root, WeeklyStore(session), file_hash(root / "candidate.json"))
    engine.dispose()


def test_unknown_billing_blocks_resume_and_is_not_semantic_rejection(tmp_path, monkeypatch):
    inputs = tmp_path / "input"
    expected = write_input(inputs)
    root = tmp_path / "run"
    config = Settings(_env_file=None, jev_api_key="key", ds_api_key="key")
    prepare(inputs, root, expected, {"total": "1", "jev": "0.5", "deepseek": "0.5"}, config)
    requests = []

    def handler(request):
        requests.append(request)
        raise httpx.ReadTimeout("unknown billing", request=request)

    client_type = httpx.Client
    monkeypatch.setattr("app.core.weekly_frozen.httpx.Client", lambda **_: client_type(
        transport=httpx.MockTransport(handler)))
    assert run(root, config)["status"] == "retry"
    resumed = run(root, config)
    assert resumed["status"] == "retry" and len(requests) == 1
    assert resumed["usage"]["providers"]["jev"]["unknown_usage_calls"] == 1
    assert not (root / "candidate.json").exists()


def test_cumulative_money_cap_stops_before_dispatch(tmp_path, monkeypatch):
    inputs = tmp_path / "input"
    expected = write_input(inputs)
    root = tmp_path / "run"
    config = Settings(_env_file=None, jev_api_key="key", ds_api_key="key")
    caps = {"total": "0.003", "jev": "0.002", "deepseek": "0.001"}
    prepare(inputs, root, expected, caps, config)
    requests = []
    client_type = httpx.Client
    monkeypatch.setattr("app.core.weekly_frozen.httpx.Client", lambda **_: client_type(
        transport=httpx.MockTransport(requests.append)))
    assert run(root, config)["status"] == "retry" and not requests
    assert run(root, config)["usage"]["total_committed_usd"] == 0
    with pytest.raises(ValueError, match="Frozen revision differs"):
        prepare(inputs, root, expected, {"total": "1", "jev": "0.5", "deepseek": "0.5"}, config)


def test_provider_failure_preserves_unresolved_admission_denominator(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'admission.sqlite'}")
    Base.metadata.create_all(engine)
    packet = packet_from_manifest(fixture_input())
    row = packet["observations"][0]
    row["admission_state"] = "unresolved"
    with Session(engine) as session, httpx.Client(transport=httpx.MockTransport(
            lambda _: httpx.Response(401))) as client:
        service = WeeklyEnricher(Settings(_env_file=None, jev_api_key="key"), WeeklyStore(session),
                                client, packet["topics"], packet["taxonomy_version"])
        result = service.classify(row)
    assert result["eligible"] is True and result["admission_state"] == "unresolved"
    assert result["topic_id"] is None and not result["classification_complete"]
    engine.dispose()


def test_source_admission_cache_survives_taxonomy_changes(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'admission.sqlite'}")
    Base.metadata.create_all(engine)
    packet = packet_from_manifest(fixture_input())
    row = {**packet["observations"][0], "admission_state": "unresolved"}
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"answers": {"admission": {
            "choice": "accepted_ai_editorial", "confidence": 0.75}}})

    with Session(engine) as session, httpx.Client(transport=httpx.MockTransport(handler)) as client:
        service = WeeklyEnricher(Settings(_env_file=None, jev_api_key="key"), WeeklyStore(session),
                                client, packet["topics"], packet["taxonomy_version"])
        assert service.admission(row) == "accepted_compatible"
        service.topics = [*service.topics, {"id": "emerging"}]
        service.taxonomy_version = "expanded"
        assert service.admission(row) == "accepted_compatible"
    assert len(requests) == 1
    engine.dispose()


def test_recovery_preserves_input_and_cumulative_unknown_expense(tmp_path, monkeypatch):
    from app.core.weekly_frozen import recover  # pylint: disable=import-outside-toplevel

    inputs = tmp_path / "input"
    expected = write_input(inputs)
    old_root, new_root = tmp_path / "old", tmp_path / "recovered"
    config = Settings(_env_file=None, jev_api_key="key", ds_api_key="key")
    prepare(inputs, old_root, expected, {"total": "1", "jev": "0.5", "deepseek": "0.5"}, config)
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) <= 2:
            raise httpx.ReadError("unknown billing", request=request)
        return httpx.Response(200, json={"answers": {"relevant": {"noul": 0.95},
            "topic": {"choice": "coding-agents", "confidence": 0.95}},
            "usage": {"input_tokens": 100}})

    client_type = httpx.Client
    monkeypatch.setattr("app.core.weekly_frozen.httpx.Client", lambda **_: client_type(
        transport=httpx.MockTransport(handler)))
    monkeypatch.setattr("app.core.weekly_worker.explain", lambda *args: False)
    first = run(old_root, config)
    hashes = {name: file_hash(old_root / name) for name in ("frozen.json", "journal.sqlite3",
                                                          "weekly.sqlite")}
    receipt = recover(inputs, old_root, new_root, hashes["frozen.json"], "Operator review")
    assert receipt["provider_dispatches"] == 0
    assert receipt["lineage"]["parent_identity"] == first["snapshot_id"]
    repeated = recover(inputs, old_root, new_root, hashes["frozen.json"], "Operator review")
    assert repeated["already_prepared"]
    completed = run(new_root, config)
    assert completed["status"] == "complete" and len(requests) == 2
    assert completed["usage"]["providers"]["jev"]["unknown_usage_calls"] == 2
    assert completed["usage"]["total_committed_usd"] == 0.005376
    payload = json.loads((new_root / "candidate.json").read_text())
    assert payload["quality"]["observed_weeks"][0]["unresolved"] == 1
    assert payload["assignments"][0]["eligible"] is True
    assert payload["assignments"][0]["classification_complete"] is False
    assert run(new_root, config)["status"] == "complete" and len(requests) == 2
    assert all(file_hash(old_root / name) == digest for name, digest in hashes.items())
