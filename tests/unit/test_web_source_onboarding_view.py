from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings
from app.storage.models_sql import Base
from app.storage.source_candidate_repo import SourceCandidateRepo, SourceImportBatchRepo
from app.web import models as web_models
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


def _seed_batch() -> int:
    session, engine = _build_session()
    try:
        batch = SourceImportBatchRepo(session).create_batch(
            raw_text="\n".join(
                [
                    "https://example.com/feed.xml",
                    "https://example.com/tag/ai",
                    "https://example.com/rejected",
                ]
            ),
            parsed_count=3,
            accepted_count=3,
            rejected_count=0,
        )
        candidate_repo = SourceCandidateRepo(session)
        validated_candidate, _ = candidate_repo.create_draft_candidate(
            batch_id=batch.id,
            raw_input="https://example.com/feed.xml",
            normalized_url="https://example.com/feed.xml",
            candidate_type="rss",
        )
        validated_candidate.validation_status = "validated"
        validated_candidate.validation_detected_type = "rss"

        duplicate_candidate, _ = candidate_repo.create_draft_candidate(
            batch_id=batch.id,
            raw_input="https://example.com/tag/ai",
            normalized_url="https://example.com/tag/ai",
            candidate_type="html",
        )
        duplicate_candidate.status = "duplicate"
        duplicate_candidate.validation_status = "warning"
        duplicate_candidate.review_note = "same host topic variant"
        duplicate_candidate.duplicate_of_candidate_id = validated_candidate.id

        rejected_candidate, _ = candidate_repo.create_draft_candidate(
            batch_id=batch.id,
            raw_input="https://example.com/rejected",
            normalized_url="https://example.com/rejected",
            candidate_type="html",
        )
        rejected_candidate.status = "rejected"
        rejected_candidate.validation_status = "failed"
        rejected_candidate.review_note = "anti-bot page"
        session.commit()
        return int(batch.id)
    finally:
        session.close()
        engine.dispose()


def test_source_onboarding_view_models_exist_for_candidate_list_and_batch_summary() -> None:
    missing_models = [
        model_name
        for model_name in (
            "SourceOnboardingCandidateView",
            "SourceOnboardingCandidateListResponse",
            "SourceOnboardingBatchSummary",
        )
        if not hasattr(web_models, model_name)
    ]

    assert not missing_models, f"Phase 3 onboarding view models missing: {missing_models}"


def test_source_onboarding_candidate_list_filters_return_summary_payload(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)
    batch_id = _seed_batch()

    response = client.get(
        "/api/source-onboarding/candidates",
        params={
            "batch_id": batch_id,
            "status": "draft",
            "validation_status": "validated",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "candidate_id": 1,
                "batch_id": batch_id,
                "status": "draft",
                "validation_status": "validated",
                "candidate_type": "rss",
                "normalized_url": "https://example.com/feed.xml",
                "raw_input": "https://example.com/feed.xml",
                "review_note": None,
                "duplicate_of_candidate_id": None,
                "approved_source_id": None,
                "validation_detected_type": "rss",
                "validation_error": None,
                "validation_details": None,
                "validated_at": None,
            }
        ],
        "summary": {
            "batch_id": batch_id,
            "parsed_count": 3,
            "accepted_count": 3,
            "rejected_count": 0,
            "pending_review_count": 1,
            "validated_count": 1,
            "approved_count": 0,
            "rejected_review_count": 1,
            "duplicate_count": 1,
            "total_candidates": 3,
            "draft_count": 1,
        },
        "filters": {
            "batch_id": batch_id,
            "status": "draft",
            "validation_status": "validated",
        },
    }


def test_source_onboarding_batch_summary_route_returns_aggregate_counts(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)
    batch_id = _seed_batch()

    response = client.get(f"/api/source-onboarding/batches/{batch_id}/summary")

    assert response.status_code == 200
    assert response.json() == {
        "batch_id": batch_id,
        "parsed_count": 3,
        "accepted_count": 3,
        "rejected_count": 0,
        "pending_review_count": 1,
        "validated_count": 1,
        "approved_count": 0,
        "rejected_review_count": 1,
        "duplicate_count": 1,
        "total_candidates": 3,
        "draft_count": 1,
    }


def test_source_onboarding_batch_summary_route_returns_not_found_for_missing_batch(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)

    response = client.get("/api/source-onboarding/batches/999/summary")

    assert response.status_code == 404
    assert "source import batch not found" in response.json()["detail"].lower()


def test_source_onboarding_review_request_models_reject_invalid_payload_shapes(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)
    batch_id = _seed_batch()

    negative_path = client.patch(
        "/api/source-onboarding/candidates/-1",
        json={"review_note": "should fail before service"},
    )
    assert negative_path.status_code == 422

    invalid_duplicate_payload = client.post(
        "/api/source-onboarding/candidates/1/mark-duplicate",
        json={"duplicate_of_candidate_id": "abc"},
    )
    assert invalid_duplicate_payload.status_code == 422

    invalid_edit_payload = client.patch(
        "/api/source-onboarding/candidates/1",
        json={"candidate_type": ["html"]},
    )
    assert invalid_edit_payload.status_code == 422

    summary = client.get(f"/api/source-onboarding/batches/{batch_id}/summary")
    assert summary.status_code == 200
