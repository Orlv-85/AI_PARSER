# pylint: disable=protected-access

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.storage.models_sql import Base
from app.storage.source_candidate_repo import SourceCandidateRepo, SourceImportBatchRepo


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_record_validation_result_keeps_candidate_type_when_detected_type_missing() -> None:
    session = _session()
    repo = SourceCandidateRepo(session)
    batch = SourceImportBatchRepo(session).create_batch(raw_text="seed")
    candidate, _ = repo.create_draft_candidate(
        batch_id=batch.id,
        raw_input="https://example.com/a",
        normalized_url="https://example.com/a",
        candidate_type="html",
    )

    updated = repo.record_validation_result(
        candidate_id=candidate.id,
        result=SimpleNamespace(
            status="warning",
            detected_type=None,
            validation_error="soft fail",
            entry_count=None,
            link_count=None,
            sample_links=None,
        ),
    )

    assert updated.validation_status == "warning"
    assert updated.candidate_type == "html"
    assert updated.validation_details is None


def test_save_review_update_skips_missing_object_fields_and_preserves_existing_values() -> None:
    session = _session()
    repo = SourceCandidateRepo(session)
    batch = SourceImportBatchRepo(session).create_batch(raw_text="seed")
    candidate, _ = repo.create_draft_candidate(
        batch_id=batch.id,
        raw_input="https://example.com/a",
        normalized_url="https://example.com/a",
    )
    candidate.review_note = "keep me"
    session.flush()

    updated = repo.save_review_update(
        SimpleNamespace(
            id=candidate.id,
            status="approved",
        )
    )

    assert updated.status == "approved"
    assert updated.review_note == "keep me"
    assert updated.normalized_url == "https://example.com/a"


def test_candidate_repo_helpers_cover_missing_values_and_optional_serialization() -> None:
    with pytest.raises(ValueError, match="candidate field is required: raw_input"):
        SourceCandidateRepo._read_candidate_value({}, "raw_input")

    assert SourceCandidateRepo._build_validation_details({}) is None
    assert SourceCandidateRepo._read_optional_value({}, "validation_error") is None

    details = SourceCandidateRepo._build_validation_details(
        {"link_count": 2, "sample_links": ["https://example.com/a", "https://example.com/b"]}
    )
    assert details == (
        '{"link_count": 2, "sample_links": ["https://example.com/a", "https://example.com/b"]}'
    )


def test_list_candidates_empty_candidate_ids_include_all_candidates() -> None:
    session = _session()
    repo = SourceCandidateRepo(session)
    candidate, _ = repo.create_draft_candidate(
        raw_input="https://example.com/a",
        normalized_url="https://example.com/a",
    )

    listed = repo.list_candidates(batch_id=None, candidate_ids=[])

    assert [row.id for row in listed] == [candidate.id]
