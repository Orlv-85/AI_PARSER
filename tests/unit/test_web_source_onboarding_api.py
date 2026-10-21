from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import Any, cast

from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings
from app.storage.models_sql import Base, Source
from app.storage.source_candidate_repo import SourceCandidateRepo, SourceImportBatchRepo
from app.storage.source_repo import SourceRepo
from app.web.app import create_app
from app.web.routes import sources as sources_routes


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
        for route in iter_route_contexts(fastapi_app.routes)
        if route.path is not None and route.methods is not None
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


def test_source_onboarding_approve_action_rejects_duplicate_without_mutating_target_source(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)
    primary_id = _seed_candidate(
        normalized_url="https://example.com/original-feed.xml",
        candidate_type="rss",
    )
    primary_approve = client.post(f"/api/source-onboarding/candidates/{primary_id}/approve")
    assert primary_approve.status_code == 200
    source_id = primary_approve.json()["approved_source_id"]

    session, engine = _build_session()
    try:
        source = session.get(Source, source_id)
        assert source is not None
        original_source = (source.url, source.type, source.name, source.enabled)
    finally:
        session.close()
        engine.dispose()

    duplicate_id = _seed_candidate(
        normalized_url="https://example.com/duplicate-topic",
        candidate_type="html",
    )
    marked = client.post(
        f"/api/source-onboarding/candidates/{duplicate_id}/mark-duplicate",
        json={"duplicate_of_candidate_id": primary_id},
    )
    assert marked.status_code == 200

    response = client.post(f"/api/source-onboarding/candidates/{duplicate_id}/approve")

    assert response.status_code == 400
    assert response.json() == {"detail": "Duplicate candidates cannot be approved"}
    session, engine = _build_session()
    try:
        source = session.get(Source, source_id)
        assert source is not None
        assert (source.url, source.type, source.name, source.enabled) == original_source
    finally:
        session.close()
        engine.dispose()


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


def test_source_onboarding_import_route_rejects_non_mapping_and_blank_text(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)

    non_mapping = client.post("/api/source-onboarding/import", json=["not", "a", "dict"])
    assert non_mapping.status_code == 422
    assert non_mapping.json()["detail"] == "raw_text is required"

    blank = client.post("/api/source-onboarding/import", json={"raw_text": "   "})
    assert blank.status_code == 422
    assert blank.json()["detail"] == "raw_text is required"


def test_source_onboarding_import_route_returns_503_when_storage_is_unavailable(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)

    def _raise_db_error(**_kwargs):
        raise SQLAlchemyError("db unavailable")

    monkeypatch.setattr(sources_routes, "import_source_candidates", _raise_db_error)

    response = client.post(
        "/api/source-onboarding/import",
        json={"raw_text": "https://example.com/feed.xml"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "News storage is unavailable"


def test_source_onboarding_validate_route_rejects_invalid_payload_shapes(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)

    non_mapping = client.post("/api/source-onboarding/validate", json=["bad"])
    assert non_mapping.status_code == 422
    assert "batch_id or candidate_ids is required" in non_mapping.json()["detail"]

    missing_scope = client.post("/api/source-onboarding/validate", json={})
    assert missing_scope.status_code == 422
    assert "batch_id or candidate_ids is required" in missing_scope.json()["detail"]

    bool_batch = client.post("/api/source-onboarding/validate", json={"batch_id": True})
    assert bool_batch.status_code == 422
    assert "batch_id must be an integer" in bool_batch.json()["detail"]

    zero_batch = client.post("/api/source-onboarding/validate", json={"batch_id": 0})
    assert zero_batch.status_code == 422
    assert "batch_id must be >= 1" in zero_batch.json()["detail"]

    invalid_candidate_list = client.post(
        "/api/source-onboarding/validate",
        json={"candidate_ids": "abc"},
    )
    assert invalid_candidate_list.status_code == 422
    assert "candidate_ids must be a list of integers" in invalid_candidate_list.json()["detail"]

    none_candidate = client.post(
        "/api/source-onboarding/validate",
        json={"candidate_ids": [None]},
    )
    assert none_candidate.status_code == 422
    assert "candidate_ids must be a list of integers" in none_candidate.json()["detail"]


def test_source_onboarding_validate_route_accepts_candidate_ids_only(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)
    captured: dict[str, object] = {}

    def _run_source_validation_batch(**kwargs):
        captured["batch_id"] = kwargs["batch_id"]
        captured["candidate_ids"] = kwargs["candidate_ids"]
        return [
            cast(
                Any,
                type(
                    "ValidationResult",
                    (),
                    {
                        "candidate_id": 7,
                        "status": "validated",
                        "detected_type": "rss",
                        "validation_error": None,
                        "entry_count": 3,
                        "link_count": None,
                        "sample_links": None,
                    },
                )(),
            )
        ]

    monkeypatch.setattr(sources_routes, "run_source_validation_batch", _run_source_validation_batch)

    response = client.post(
        "/api/source-onboarding/validate",
        json={"candidate_ids": [7]},
    )

    assert response.status_code == 200
    assert captured == {"batch_id": None, "candidate_ids": [7]}
    assert response.json() == {
        "validated_count": 1,
        "results": [
            {
                "candidate_id": 7,
                "status": "validated",
                "detected_type": "rss",
                "validation_error": None,
                "entry_count": 3,
                "link_count": None,
                "sample_links": None,
            }
        ],
    }


def test_source_onboarding_validation_keeps_health_endpoint_responsive(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)
    validation_started = Event()
    release_validation = Event()

    def _blocking_validation(**_kwargs):
        validation_started.set()
        assert release_validation.wait(timeout=10)
        return []

    monkeypatch.setattr(sources_routes, "run_source_validation_batch", _blocking_validation)

    with client, ThreadPoolExecutor(max_workers=2) as executor:
        validation = executor.submit(
            client.post, "/api/source-onboarding/validate", json={"batch_id": 1}
        )
        try:
            assert validation_started.wait(timeout=5)
            health = executor.submit(client.get, "/health")
            assert health.result(timeout=2).status_code == 200
            assert not validation.done()
        finally:
            release_validation.set()
        assert validation.result(timeout=5).json() == {"validated_count": 0, "results": []}


def test_source_onboarding_validate_route_returns_503_when_storage_is_unavailable(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)

    def _raise_db_error(**_kwargs):
        raise SQLAlchemyError("db unavailable")

    monkeypatch.setattr(sources_routes, "run_source_validation_batch", _raise_db_error)

    response = client.post("/api/source-onboarding/validate", json={"batch_id": 1})

    assert response.status_code == 503
    assert response.json()["detail"] == "News storage is unavailable"


def test_source_onboarding_overlaps_and_listing_return_503_on_storage_errors(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)

    def _raise_db_error(**_kwargs):
        raise SQLAlchemyError("db unavailable")

    monkeypatch.setattr(sources_routes, "review_candidate_overlaps", _raise_db_error)
    overlaps = client.get("/api/source-onboarding/overlaps", params={"batch_id": 1})
    assert overlaps.status_code == 503
    assert overlaps.json()["detail"] == "News storage is unavailable"

    class _BrokenService:
        def __init__(self, _session) -> None:
            pass

        def list_candidates(self, **_kwargs):
            raise SQLAlchemyError("db unavailable")

        def get_batch_summary(self, _batch_id: int):
            raise SQLAlchemyError("db unavailable")

    monkeypatch.setattr(sources_routes, "SourceOnboardingService", _BrokenService)

    listed = client.get("/api/source-onboarding/candidates", params={"batch_id": 1})
    assert listed.status_code == 503
    assert listed.json()["detail"] == "News storage is unavailable"

    summary = client.get("/api/source-onboarding/batches/1/summary")
    assert summary.status_code == 503
    assert summary.json()["detail"] == "News storage is unavailable"


def test_source_onboarding_review_routes_return_503_on_storage_errors(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)

    class _BrokenService:
        def __init__(self, _session) -> None:
            pass

        def approve_candidate(self, _candidate_id: int):
            raise SQLAlchemyError("db unavailable")

        def disable_candidate(self, _candidate_id: int):
            raise SQLAlchemyError("db unavailable")

        def reject_candidate(self, _candidate_id: int, *, reason: str | None = None):
            _ = reason
            raise SQLAlchemyError("db unavailable")

        def mark_duplicate(
            self,
            _candidate_id: int,
            *,
            duplicate_of_candidate_id: int,
            reason: str | None = None,
        ):
            _ = (duplicate_of_candidate_id, reason)
            raise SQLAlchemyError("db unavailable")

        def edit_candidate(self, _candidate_id: int, **_kwargs):
            raise SQLAlchemyError("db unavailable")

    monkeypatch.setattr(sources_routes, "SourceOnboardingService", _BrokenService)

    approve = client.post("/api/source-onboarding/candidates/1/approve")
    assert approve.status_code == 503
    assert approve.json()["detail"] == "News storage is unavailable"

    disable = client.post("/api/source-onboarding/candidates/1/disable")
    assert disable.status_code == 503
    assert disable.json()["detail"] == "News storage is unavailable"

    reject = client.post("/api/source-onboarding/candidates/1/reject", json={"reason": "x"})
    assert reject.status_code == 503
    assert reject.json()["detail"] == "News storage is unavailable"

    duplicate = client.post(
        "/api/source-onboarding/candidates/1/mark-duplicate",
        json={"duplicate_of_candidate_id": 2},
    )
    assert duplicate.status_code == 503
    assert duplicate.json()["detail"] == "News storage is unavailable"

    edit = client.patch(
        "/api/source-onboarding/candidates/1",
        json={"review_note": "x"},
    )
    assert edit.status_code == 503
    assert edit.json()["detail"] == "News storage is unavailable"


def test_source_onboarding_disable_and_reject_routes_return_400_on_domain_errors(
    monkeypatch, tmp_path
) -> None:
    client = _build_client(monkeypatch, tmp_path)

    class _DomainErrorService:
        def __init__(self, _session) -> None:
            pass

        def disable_candidate(self, _candidate_id: int):
            raise ValueError("cannot disable draft candidate")

        def reject_candidate(self, _candidate_id: int, *, reason: str | None = None):
            _ = reason
            raise ValueError("candidate already rejected")

    monkeypatch.setattr(sources_routes, "SourceOnboardingService", _DomainErrorService)

    disable = client.post("/api/source-onboarding/candidates/1/disable")
    assert disable.status_code == 400
    assert disable.json()["detail"] == "cannot disable draft candidate"

    reject = client.post("/api/source-onboarding/candidates/1/reject", json={"reason": "x"})
    assert reject.status_code == 400
    assert reject.json()["detail"] == "candidate already rejected"
