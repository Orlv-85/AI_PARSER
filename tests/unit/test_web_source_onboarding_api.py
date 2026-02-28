from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings
from app.storage.models_sql import Base
from app.storage.repos import SourceCandidateRepo, SourceImportBatchRepo, SourceRepo
from app.web.app import create_app


def _build_client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    return TestClient(create_app())


def _build_session() -> tuple[Session, Any]:
    engine = create_engine(get_settings().database_url, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory(), engine


def _seed_candidate(
    *,
    status: str = "draft",
    validation_status: str = "validated",
    normalized_url: str = "https://example.com/feed.xml",
    candidate_type: str = "rss",
    raw_input: str | None = None,
) -> int:
    session, engine = _build_session()
    try:
        batch = SourceImportBatchRepo(session).create_batch(
            raw_text=normalized_url,
            parsed_count=1,
            accepted_count=1,
            rejected_count=0,
        )
        candidate, _ = SourceCandidateRepo(session).create_draft_candidate(
            batch_id=batch.id,
            raw_input=raw_input or normalized_url,
            normalized_url=normalized_url,
            candidate_type=candidate_type,
        )
        candidate.status = status
        candidate.validation_status = validation_status
        session.commit()
        return int(candidate.id)
    finally:
        session.close()
        engine.dispose()


def _fetch_candidate(candidate_id: int) -> dict[str, Any]:
    session, engine = _build_session()
    try:
        candidate = SourceCandidateRepo(session).get_candidate(candidate_id)
        assert candidate is not None
        return {
            "status": candidate.status,
            "validation_status": candidate.validation_status,
            "review_note": candidate.review_note,
            "duplicate_of_candidate_id": candidate.duplicate_of_candidate_id,
            "approved_source_id": candidate.approved_source_id,
            "normalized_url": candidate.normalized_url,
            "candidate_type": candidate.candidate_type,
            "raw_input": candidate.raw_input,
        }
    finally:
        session.close()
        engine.dispose()


def test_source_onboarding_review_routes_are_registered(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    fastapi_app = cast(Any, client.app)
    routes = {
        (route.path, frozenset(route.methods))
        for route in fastapi_app.routes
        if hasattr(route, "path") and hasattr(route, "methods")
    }

    expected_routes = {
        ("/api/source-onboarding/candidates/{candidate_id}/approve", frozenset({"POST"})),
        ("/api/source-onboarding/candidates/{candidate_id}/disable", frozenset({"POST"})),
        ("/api/source-onboarding/candidates/{candidate_id}/reject", frozenset({"POST"})),
        (
            "/api/source-onboarding/candidates/{candidate_id}/mark-duplicate",
            frozenset({"POST"}),
        ),
        ("/api/source-onboarding/candidates/{candidate_id}", frozenset({"PATCH"})),
    }

    missing_routes = sorted(expected_routes - routes)
    assert not missing_routes, f"Phase 3 review routes missing: {missing_routes}"


def test_source_onboarding_approve_action_returns_persisted_review_payload(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)
    sources_path = tmp_path / "sources.yaml"
    candidate_id = _seed_candidate()

    response = client.post(f"/api/source-onboarding/candidates/{candidate_id}/approve")

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate_id"] == candidate_id
    assert payload["status"] == "approved"
    assert payload["validation_status"] == "validated"
    assert payload["managed_source_created"] is True
    assert isinstance(payload["approved_source_id"], int)

    stored = _fetch_candidate(candidate_id)
    assert stored["status"] == "approved"
    assert stored["approved_source_id"] == payload["approved_source_id"]
    assert sources_path.exists() is False


def test_source_onboarding_reject_and_mark_duplicate_actions_capture_review_decisions(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)
    kept_candidate_id = _seed_candidate(
        normalized_url="https://example.com/blog",
        candidate_type="html",
    )
    rejected_candidate_id = _seed_candidate(
        normalized_url="https://example.com/reject",
        candidate_type="html",
        validation_status="failed",
    )
    duplicate_candidate_id = _seed_candidate(
        normalized_url="https://example.com/tag/ai",
        candidate_type="html",
    )

    reject = client.post(
        f"/api/source-onboarding/candidates/{rejected_candidate_id}/reject",
        json={"reason": "validation failed"},
    )
    assert reject.status_code == 200
    assert reject.json() == {
        "candidate_id": rejected_candidate_id,
        "status": "rejected",
        "review_note": "validation failed",
    }

    duplicate = client.post(
        f"/api/source-onboarding/candidates/{duplicate_candidate_id}/mark-duplicate",
        json={
            "duplicate_of_candidate_id": kept_candidate_id,
            "reason": "same vendor topic page",
        },
    )
    assert duplicate.status_code == 200
    assert duplicate.json() == {
        "candidate_id": duplicate_candidate_id,
        "status": "duplicate",
        "duplicate_of_candidate_id": kept_candidate_id,
        "review_note": "same vendor topic page",
    }

    rejected = _fetch_candidate(rejected_candidate_id)
    assert rejected["status"] == "rejected"
    assert rejected["review_note"] == "validation failed"

    marked_duplicate = _fetch_candidate(duplicate_candidate_id)
    assert marked_duplicate["status"] == "duplicate"
    assert marked_duplicate["duplicate_of_candidate_id"] == kept_candidate_id
    assert marked_duplicate["review_note"] == "same vendor topic page"


def test_source_onboarding_edit_action_returns_updated_candidate_fields(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)
    candidate_id = _seed_candidate(
        normalized_url="https://example.com/blog?utm_source=test",
        candidate_type="html",
    )

    response = client.patch(
        f"/api/source-onboarding/candidates/{candidate_id}",
        json={
            "normalized_url": "https://example.com/blog?utm_source=test",
            "candidate_type": "html",
            "raw_input": "https://example.com/blog",
            "review_note": "trimmed tracking params",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "candidate_id": candidate_id,
        "status": "draft",
        "normalized_url": "https://example.com/blog",
        "candidate_type": "html",
        "raw_input": "https://example.com/blog",
        "review_note": "trimmed tracking params",
    }

    stored = _fetch_candidate(candidate_id)
    assert stored["normalized_url"] == "https://example.com/blog"
    assert stored["review_note"] == "trimmed tracking params"


def test_source_onboarding_approve_action_rejects_non_validated_candidates(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)
    candidate_id = _seed_candidate(validation_status="failed")

    response = client.post(f"/api/source-onboarding/candidates/{candidate_id}/approve")

    assert response.status_code == 400
    assert "validated" in response.json()["detail"].lower()


def test_source_onboarding_approve_action_creates_enabled_managed_source(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)
    candidate_id = _seed_candidate(
        normalized_url="https://example.com/news",
        candidate_type="html",
    )

    response = client.post(f"/api/source-onboarding/candidates/{candidate_id}/approve")

    assert response.status_code == 200
    source_id = response.json()["approved_source_id"]

    session, engine = _build_session()
    try:
        source = SourceRepo(session).list_enabled_sources()
        enabled_ids = {row.id for row in source}
        assert source_id in enabled_ids
    finally:
        session.close()
        engine.dispose()


def test_source_onboarding_disable_action_disables_previously_approved_managed_source(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)
    candidate_id = _seed_candidate(
        normalized_url="https://example.com/disable-me",
        candidate_type="html",
    )

    approve = client.post(f"/api/source-onboarding/candidates/{candidate_id}/approve")
    assert approve.status_code == 200
    source_id = approve.json()["approved_source_id"]

    disable = client.post(f"/api/source-onboarding/candidates/{candidate_id}/disable")

    assert disable.status_code == 200
    assert disable.json() == {
        "candidate_id": candidate_id,
        "status": "disabled",
        "approved_source_id": source_id,
    }

    session, engine = _build_session()
    try:
        enabled_ids = {row.id for row in SourceRepo(session).list_enabled_sources()}
        assert source_id not in enabled_ids
    finally:
        session.close()
        engine.dispose()


def test_source_onboarding_review_routes_reject_malformed_inputs_cleanly(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)
    kept_candidate_id = _seed_candidate(
        normalized_url="https://example.com/primary",
        candidate_type="html",
    )
    candidate_id = _seed_candidate(
        normalized_url="https://example.com/secondary",
        candidate_type="html",
    )

    negative_path = client.post("/api/source-onboarding/candidates/-1/approve")
    assert negative_path.status_code == 422

    invalid_duplicate_id = client.post(
        f"/api/source-onboarding/candidates/{candidate_id}/mark-duplicate",
        json={"duplicate_of_candidate_id": 0},
    )
    assert invalid_duplicate_id.status_code == 422

    duplicate_self = client.post(
        f"/api/source-onboarding/candidates/{candidate_id}/mark-duplicate",
        json={"duplicate_of_candidate_id": candidate_id},
    )
    assert duplicate_self.status_code == 400
    assert "duplicate of itself" in duplicate_self.json()["detail"].lower()

    duplicate_missing = client.post(
        f"/api/source-onboarding/candidates/{candidate_id}/mark-duplicate",
        json={"duplicate_of_candidate_id": kept_candidate_id + 999},
    )
    assert duplicate_missing.status_code == 400
    assert "source candidate not found" in duplicate_missing.json()["detail"].lower()

    invalid_url = client.patch(
        f"/api/source-onboarding/candidates/{candidate_id}",
        json={"normalized_url": "notaurl"},
    )
    assert invalid_url.status_code == 400
    assert "invalid source candidate url" in invalid_url.json()["detail"].lower()

    invalid_type = client.patch(
        f"/api/source-onboarding/candidates/{candidate_id}",
        json={"candidate_type": "podcast"},
    )
    assert invalid_type.status_code == 400
    assert "candidate_type must be one of" in invalid_type.json()["detail"].lower()
