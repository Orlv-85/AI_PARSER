# pylint: disable=protected-access
import json
import time
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config.settings import Settings, get_settings
from app.core.canonicalize import canonicalize_url
from app.core.sources.onboarding import import_source_candidates
from app.core.sources.review import SourceProbe
from app.storage.models_sql import Base, Source, SourceCandidate
from app.storage.source_candidate_repo import SourceCandidateRepo, SourceImportBatchRepo
from app.web import source_intake
from app.web.app import create_app
from app.web.source_intake import SourceIntakeService, review_details


@pytest.fixture(name="intake")
def intake_service(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'intake.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    service = SourceIntakeService(factory, Settings(_env_file=None))
    monkeypatch.setattr(source_intake, "probe_source", lambda _client, url: SourceProbe(
        url, "rss", "AI News", "AI models", [{"title": "New AI", "url": "/post", "date": ""}], 1
    ))
    yield service
    engine.dispose()


def _batch(service, urls):
    with service.session_factory() as session:
        result = import_source_candidates(
            raw_text=json.dumps({"sources": [
                {"name": "AI Publisher", "url": url} for url in urls
            ]}),
            batch_repo=SourceImportBatchRepo(session), candidate_repo=SourceCandidateRepo(session),
        )
        session.commit()
        return result.batch.id


def _reviews(service, batch_id):
    with service.session_factory() as session:
        return [(c.id, c.status, c.validation_status, review_details(c))
                for c in SourceCandidateRepo(session).list_candidates(batch_id=batch_id)]


def test_background_reviews_commit_results_cache_repeats_and_bulk_connect(
    intake, monkeypatch
) -> None:
    assert intake.latest_batch() is None
    batch = _batch(intake, ["https://one.example/feed", "https://two.example/feed"])
    calls = []

    def review(_self, brief):
        calls.append(brief)
        if len(calls) == 2:
            assert _reviews(intake, batch)[0][3]["decision"] == "ready"
        return {"decision": "ready", "provider": "jev", "reason": "AI feed"}

    monkeypatch.setattr(source_intake.SourceReviewer, "review", review)
    intake._run(batch)
    assert intake.latest_batch() == batch
    assert intake.status()["status"] == "finished"
    assert intake.status()["completed"] == 2
    assert all(row[3]["decision"] == "ready" for row in _reviews(intake, batch))
    intake._run(batch)
    assert len(calls) == 2
    assert all(row[3]["cached"] for row in _reviews(intake, batch))
    approved = intake.approve_ready(batch)
    assert len(approved) == 2
    assert intake.approve_ready(batch) == []
    with intake.session_factory() as session:
        sources = session.scalars(select(Source)).all()
        assert len(sources) == 2
        assert all(s.enabled and s.name == "AI Publisher" for s in sources)


def test_stale_cache_rechecks_and_missing_provider_is_not_cached(intake, monkeypatch) -> None:
    batch = _batch(intake, ["https://one.example/feed"])
    calls = []
    def review(_self, brief):
        calls.append(brief)
        return {"decision": "review", "provider": "jev", "reason": "Uncertain"}

    monkeypatch.setattr(source_intake.SourceReviewer, "review", review)
    intake._run(batch)
    with intake.session_factory() as session:
        candidate = session.scalar(select(SourceCandidate))
        candidate.validated_at = datetime.now(UTC) - timedelta(days=8)
        session.commit()
    intake._run(batch)
    assert len(calls) == 2
    assert intake.approve_ready(batch) == []


def test_failed_second_opinion_is_asked_again_and_deepseek_answer_is_reused(
    intake, monkeypatch
) -> None:
    batch = _batch(intake, ["https://one.example/feed"])
    answers = iter([
        {"decision": "review", "provider": "jev", "reason": "Manual review: DeepSeek check failed"},
        {"decision": "ready", "provider": "deepseek", "reason": "AI publication samples"},
    ])
    calls = []

    def review(_self, brief):
        calls.append(brief)
        return next(answers)

    monkeypatch.setattr(source_intake.SourceReviewer, "review", review)
    intake._run(batch)
    intake._run(batch)
    assert len(calls) == 2
    intake._run(batch)
    assert len(calls) == 2
    assert _reviews(intake, batch)[0][3]["cached"] is True
    assert _reviews(intake, batch)[0][3]["provider"] == "deepseek"


def test_cache_hit_keeps_the_age_of_the_model_call(intake, monkeypatch) -> None:
    batch = _batch(intake, ["https://one.example/feed"])
    calls = []

    def review(_self, brief):
        calls.append(brief)
        return {"decision": "ready", "provider": "jev", "reason": "AI feed"}

    monkeypatch.setattr(source_intake.SourceReviewer, "review", review)
    intake._run(batch)
    old = (datetime.now(UTC) - timedelta(days=6)).isoformat()
    with intake.session_factory() as session:
        candidate = session.scalar(select(SourceCandidate))
        details = json.loads(candidate.validation_details)
        details["source_review"]["reviewed_at"] = old
        candidate.validation_details = json.dumps(details)
        session.commit()
    intake._run(batch)
    assert len(calls) == 1
    assert _reviews(intake, batch)[0][3]["reviewed_at"] == old
    with intake.session_factory() as session:
        candidate = session.scalar(select(SourceCandidate))
        details = json.loads(candidate.validation_details)
        details["source_review"]["reviewed_at"] = (
            datetime.now(UTC) - timedelta(days=8)
        ).isoformat()
        candidate.validation_details = json.dumps(details)
        session.commit()
    intake._run(batch)
    assert len(calls) == 2


def test_existing_urls_and_same_host_families_never_use_models(intake, monkeypatch) -> None:
    with intake.session_factory() as session:
        session.add(Source(source_key="known", name="Known", type="rss",
                           url="https://known.example/feed", enabled=False,
                           fetch_interval_minutes=30, source_weight=1))
        session.commit()
    batch = _batch(intake, ["http://www.known.example/feed/", "https://known.example/blog",
                           "https://new.example/blog", "https://new.example/feed"])
    monkeypatch.setattr(source_intake.SourceReviewer, "review",
                        lambda *_a: pytest.fail("No AI calls"))
    intake._run(batch)
    reviews = _reviews(intake, batch)
    assert reviews[0][1] == "duplicate"
    assert all(row[3]["decision"] == "review" for row in reviews[1:])
    assert intake.approve_ready(batch) == []


def test_failures_and_redirect_duplicates_stay_out_of_approval(intake, monkeypatch) -> None:
    with intake.session_factory() as session:
        session.add(Source(source_key="known", name="Known", type="rss",
                           url="https://known.example/feed", enabled=True,
                           fetch_interval_minutes=30, source_weight=1))
        session.commit()
    batch = _batch(intake, ["https://redirect.example/feed", "https://broken.example/feed"])

    def probe(_client, url):
        if "broken" in url:
            raise ValueError("No publication links")
        return SourceProbe("https://known.example/feed", "rss", "AI", "", [], 0)

    monkeypatch.setattr(source_intake, "probe_source", probe)
    intake._run(batch)
    reviews = _reviews(intake, batch)
    assert reviews[0][3]["decision"] == "duplicate"
    assert reviews[1][2] == "failed"
    assert "No publication links" in reviews[1][3]["reason"]
    assert intake.approve_ready(batch) == []


def test_worker_failure_does_not_report_success_and_bad_details_are_safe(
    intake, monkeypatch
) -> None:
    batch = _batch(intake, ["https://one.example/feed"])

    def broken_client():
        raise RuntimeError("provider secret")

    monkeypatch.setattr(source_intake, "source_http_client", broken_client)
    intake._run(batch)
    assert intake.status()["status"] == "failed"
    assert "provider secret" not in intake.status()["error"]
    assert review_details(SourceCandidate(validation_details="invalid")) == {}
    assert review_details(SourceCandidate(validation_details='{"source_review":42}')) == {}
    assert review_details(SourceCandidate(validation_details="[]")) == {}
    with pytest.raises(ValueError, match="not found"):
        intake.start(999)
    with pytest.raises(ValueError, match="not found"):
        intake.approve_ready(999)


def test_bulk_approval_rechecks_registry_and_skips_manual_failed_and_known(intake) -> None:
    batch = _batch(intake, [f"https://source-{i}.example/feed" for i in range(5)])
    with intake.session_factory() as session:
        candidates = SourceCandidateRepo(session).list_candidates(batch_id=batch)
        for c in candidates:
            c.validation_status = "validated"
            c.validation_details = json.dumps({"source_review": {"decision": "ready"}})
        candidates[1].validation_details = '{"source_review":{"decision":"review"}}'
        candidates[2].validation_status = "failed"
        candidates[3].status = "rejected"
        session.add(Source(source_key="known", name="Known", type="rss",
                           url=candidates[4].normalized_url, enabled=True,
                           fetch_interval_minutes=30, source_weight=1))
        session.commit()
    assert len(intake.approve_ready(batch)) == 1


def test_editing_a_candidate_invalidates_its_model_review(intake, monkeypatch) -> None:
    batch = _batch(intake, ["https://one.example/feed"])
    monkeypatch.setattr(source_intake.SourceReviewer, "review", lambda *_a: {
        "decision": "ready", "provider": "jev", "reason": "AI feed",
    })
    intake._run(batch)
    candidate_id = _reviews(intake, batch)[0][0]
    with intake.session_factory() as session:
        source_intake.SourceOnboardingService(session).edit_candidate(
            candidate_id, normalized_url="https://changed.example/feed"
        )
        session.commit()
    assert intake.approve_ready(batch) == []
    assert _reviews(intake, batch)[0][2] == "pending"


def test_candidate_changed_during_probe_does_not_receive_old_evidence(intake, monkeypatch) -> None:
    batch = _batch(intake, ["https://one.example/feed"])

    def probe(_client, url):
        with intake.session_factory() as session:
            candidate = session.scalar(select(SourceCandidate))
            candidate.normalized_url = "https://changed.example/feed"
            session.commit()
        return SourceProbe(url, "rss", "AI", "AI", [], 1)

    monkeypatch.setattr(source_intake, "probe_source", probe)
    monkeypatch.setattr(source_intake.SourceReviewer, "review", lambda *_a: {
        "decision": "ready", "provider": "jev", "reason": "AI feed",
    })
    intake._run(batch)
    assert _reviews(intake, batch)[0][2] == "pending"
    assert intake.approve_ready(batch) == []


def test_upload_api_returns_immediately_health_and_progress_remain_available(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    started = Event()
    release = Event()

    def slow_probe(_client, url):
        started.set()
        assert release.wait(10)
        return SourceProbe(url, "rss", "AI", "AI models", [], 1)

    monkeypatch.setattr(source_intake, "probe_source", slow_probe)
    monkeypatch.setattr(source_intake.SourceReviewer, "review", lambda *_a: {
        "decision": "ready", "provider": "jev", "reason": "AI source",
    })
    with TestClient(create_app()) as client:
        assert client.get("/api/source-onboarding/latest").json()["batch_id"] is None
        malformed = client.post("/api/source-onboarding/import", json={"raw_text": '{"sources":'})
        assert malformed.status_code == 422
        response = client.post("/api/source-onboarding/import", json={"raw_text": json.dumps({
            "sources": [{"name": "AI Publisher", "url": "https://one.example/feed"}],
            "evidence_url": "https://one.example/article",
        })})
        batch_id = response.json()["batch_id"]
        assert response.json()["accepted_count"] == 1
        assert client.get("/api/source-onboarding/latest").json()["batch_id"] == batch_id
        try:
            checking = client.post(f"/api/source-onboarding/batches/{batch_id}/check")
            assert checking.status_code == 202
            assert started.wait(5)
            assert client.get("/health").status_code == 200
            assert client.get("/api/source-onboarding/check-status").json()["status"] == "running"
            assert client.post(
                f"/api/source-onboarding/batches/{batch_id}/check"
            ).status_code == 202
            assert client.post(
                f"/api/source-onboarding/batches/{batch_id}/approve-ready"
            ).status_code == 409
            other = client.post("/api/source-onboarding/import", json={
                "raw_text": "https://two.example/feed"
            }).json()["batch_id"]
            assert client.post(f"/api/source-onboarding/batches/{other}/check").status_code == 409
        finally:
            release.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status = client.get("/api/source-onboarding/check-status").json()
            if status["status"] != "running":
                break
            time.sleep(0.01)
        assert status["status"] == "finished"
        assert status["completed"] == status["total"] == 1
        approved = client.post(f"/api/source-onboarding/batches/{batch_id}/approve-ready")
        assert approved.json()["approved_count"] == 1
        assert client.post("/api/source-onboarding/batches/999/check").status_code == 409
        assert client.post("/api/source-onboarding/batches/999/approve-ready").status_code == 409


def test_admin_shows_upload_latest_batch_and_bulk_connection(
    monkeypatch, tmp_path, page_with_assets
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    client = TestClient(create_app())
    text = page_with_assets(client, client.get("/admin"))
    assert 'id="onboarding-json-file"' in text
    assert 'id="approve-ready-sources"' in text
    assert "loadLatestSourceBatch();" in text
    assert 'id="onboarding-batch-id" type="number" min="1"' in text
    assert "source_review" in text


def test_url_key_agrees_with_the_pipeline_canonical_url() -> None:
    # The same page, spelled the way the pipeline canonicalizes it, must give one key.
    spellings = [
        "https://example.com/blog?a=1&b=2",
        "http://www.Example.com/blog/?b=2&a=1&spm=nav&yclid=7",
        "https://example.com:443//blog/?utm_source=x&ref_src=y&a=1&b=2#top",
    ]
    assert len({source_intake._url_key(url) for url in spellings}) == 1
    assert source_intake._url_key(spellings[1]) == canonicalize_url(spellings[0])


def test_registry_duplicate_uses_the_pipeline_canonical_key(intake, monkeypatch) -> None:
    with intake.session_factory() as session:
        session.add(Source(source_key="known", name="Known", type="html",
                           url="https://known.example/blog?b=2&a=1&spm=x", enabled=True,
                           fetch_interval_minutes=30, source_weight=1))
        session.commit()
    batch = _batch(intake, ["http://www.known.example/blog/?a=1&b=2"])
    monkeypatch.setattr(source_intake.SourceReviewer, "review",
                        lambda *_a: pytest.fail("No AI calls"))
    intake._run(batch)
    assert _reviews(intake, batch)[0][1] == "duplicate"
