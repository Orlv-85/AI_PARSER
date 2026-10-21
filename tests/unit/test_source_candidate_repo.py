from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.storage.models_sql import Base, Source, SourceCandidate
from app.storage.source_candidate_repo import SourceCandidateRepo, SourceImportBatchRepo
from app.storage.source_repo import SourceRepo


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_create_draft_candidate_persists_normalized_canonical_url() -> None:
    session = _session()
    repo = SourceCandidateRepo(session)

    candidate, created = repo.create_draft_candidate(
        raw_input="https://Example.com/blog/?utm_source=feed",
        normalized_url="https://example.com/blog",
    )
    session.commit()

    assert created is True
    assert candidate.normalized_url == "https://example.com/blog"

    rows = session.query(SourceCandidate).all()
    assert len(rows) == 1
    assert rows[0].normalized_url == "https://example.com/blog"


def test_create_draft_candidate_deduplicates_exact_normalized_canonical_url() -> None:
    session = _session()
    repo = SourceCandidateRepo(session)

    first, first_created = repo.create_draft_candidate(
        raw_input="https://example.com/blog/?utm_source=feed",
        normalized_url="https://example.com/blog",
    )
    second, second_created = repo.create_draft_candidate(
        raw_input="https://EXAMPLE.com/blog#top",
        normalized_url="https://example.com/blog",
    )
    session.commit()

    assert first_created is True
    assert second_created is False
    assert second.id == first.id

    rows = session.query(SourceCandidate).all()
    assert len(rows) == 1
    assert rows[0].normalized_url == "https://example.com/blog"


def test_create_draft_candidates_returns_only_rows_created_for_current_batch() -> None:
    session = _session()
    candidate_repo = SourceCandidateRepo(session)
    batch_repo = SourceImportBatchRepo(session)

    first_batch = batch_repo.create_batch(raw_text="https://example.com/blog")
    second_batch = batch_repo.create_batch(raw_text="https://example.com/blog")

    first_rows, first_accepted = candidate_repo.create_draft_candidates(
        batch_id=first_batch.id,
        candidates=[
            {
                "raw_input": "https://example.com/blog",
                "normalized_url": "https://example.com/blog",
                "candidate_type": "html",
            }
        ],
    )
    second_rows, second_accepted = candidate_repo.create_draft_candidates(
        batch_id=second_batch.id,
        candidates=[
            {
                "raw_input": "https://example.com/blog",
                "normalized_url": "https://example.com/blog",
                "candidate_type": "html",
            }
        ],
    )
    session.commit()

    assert first_accepted == 1
    assert [candidate.id for candidate in first_rows] == [1]
    assert second_accepted == 0
    assert not second_rows

    stored_rows = session.query(SourceCandidate).all()
    assert len(stored_rows) == 1
    assert stored_rows[0].id == 1
    assert stored_rows[0].batch_id == first_batch.id


def test_insert_normalized_draft_candidates_alias_and_required_field_validation() -> None:
    session = _session()
    repo = SourceCandidateRepo(session)

    rows, accepted = repo.insert_normalized_draft_candidates(
        batch_id=None,
        candidates=[
            {
                "raw_input": "https://example.com/feed.xml",
                "normalized_url": "https://example.com/feed.xml",
            }
        ],
    )

    assert accepted == 1
    assert [row.normalized_url for row in rows] == ["https://example.com/feed.xml"]

    try:
        repo.create_draft_candidates(batch_id=None, candidates=[{"raw_input": "https://example.com"}])
    except ValueError as exc:
        assert "candidate field is required: normalized_url" in str(exc)
    else:  # pragma: no cover - exercised when guard is implemented incorrectly
        raise AssertionError("create_draft_candidates should require normalized_url")


def test_list_candidates_filters_by_ids_status_and_validation_status() -> None:
    session = _session()
    repo = SourceCandidateRepo(session)
    batch = SourceImportBatchRepo(session).create_batch(raw_text="seed")

    first, _ = repo.create_draft_candidate(
        batch_id=batch.id,
        raw_input="https://example.com/a",
        normalized_url="https://example.com/a",
        candidate_type="rss",
    )
    second, _ = repo.create_draft_candidate(
        batch_id=batch.id,
        raw_input="https://example.com/b",
        normalized_url="https://example.com/b",
        candidate_type="html",
    )
    third, _ = repo.create_draft_candidate(
        batch_id=batch.id,
        raw_input="https://example.com/c",
        normalized_url="https://example.com/c",
        candidate_type="html",
    )
    first.status = "approved"
    first.validation_status = "validated"
    second.status = "duplicate"
    second.validation_status = "failed"
    third.status = "draft"
    third.validation_status = "validated"
    session.flush()

    filtered = repo.list_candidates(
        batch_id=batch.id,
        candidate_ids=[first.id, third.id],
        status="draft",
        validation_status="validated",
    )

    assert [candidate.id for candidate in filtered] == [third.id]


def test_record_validation_result_updates_candidate_and_guards_missing_candidate() -> None:
    session = _session()
    repo = SourceCandidateRepo(session)
    batch = SourceImportBatchRepo(session).create_batch(raw_text="seed")
    candidate, _ = repo.create_draft_candidate(
        batch_id=batch.id,
        raw_input="https://example.com/a",
        normalized_url="https://example.com/a",
        candidate_type="unknown",
    )

    updated = repo.record_validation_result(
        candidate_id=candidate.id,
        result={
            "status": "validated",
            "detected_type": "rss",
            "validation_error": None,
            "entry_count": 2,
            "sample_links": ["https://example.com/a/1"],
        },
    )

    assert updated.validation_status == "validated"
    assert updated.candidate_type == "rss"
    assert updated.validation_details == (
        '{"entry_count": 2, "sample_links": ["https://example.com/a/1"]}'
    )
    assert updated.validated_at is not None

    try:
        repo.record_validation_result(candidate_id=999, result={"status": "failed"})
    except ValueError as exc:
        assert "source candidate not found: 999" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("record_validation_result should reject unknown candidates")


def test_update_candidate_rejects_missing_candidate_and_duplicate_normalized_url() -> None:
    session = _session()
    repo = SourceCandidateRepo(session)
    batch = SourceImportBatchRepo(session).create_batch(raw_text="seed")
    first, _ = repo.create_draft_candidate(
        batch_id=batch.id,
        raw_input="https://example.com/a",
        normalized_url="https://example.com/a",
    )
    second, _ = repo.create_draft_candidate(
        batch_id=batch.id,
        raw_input="https://example.com/b",
        normalized_url="https://example.com/b",
    )

    try:
        repo.update_candidate(candidate_id=999, normalized_url="https://example.com/missing")
    except ValueError as exc:
        assert "source candidate not found: 999" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("update_candidate should reject unknown candidates")

    try:
        repo.update_candidate(candidate_id=second.id, normalized_url=first.normalized_url)
    except ValueError as exc:
        assert "normalized URL already exists" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("update_candidate should reject duplicate normalized_url")

    updated = repo.update_candidate(
        candidate_id=second.id,
        raw_input="https://example.com/b-updated",
        normalized_url="https://example.com/b-updated",
        candidate_type="html",
    )
    assert updated.raw_input == "https://example.com/b-updated"
    assert updated.normalized_url == "https://example.com/b-updated"
    assert updated.candidate_type == "html"


def test_save_review_update_supports_dict_and_object_inputs() -> None:
    session = _session()
    repo = SourceCandidateRepo(session)
    batch = SourceImportBatchRepo(session).create_batch(raw_text="seed")
    candidate, _ = repo.create_draft_candidate(
        batch_id=batch.id,
        raw_input="https://example.com/a",
        normalized_url="https://example.com/a",
    )

    updated_from_dict = repo.save_review_update(
        {
            "id": candidate.id,
            "status": "approved",
            "review_note": "ok",
            "approved_source_id": 5,
        }
    )
    assert updated_from_dict.status == "approved"
    assert updated_from_dict.review_note == "ok"
    assert updated_from_dict.approved_source_id == 5

    updated_from_object = repo.save_review_update(
        SimpleNamespace(
            id=candidate.id,
            status="duplicate",
            duplicate_of_candidate_id=12,
            validation_status="validated",
        )
    )
    assert updated_from_object.status == "duplicate"
    assert updated_from_object.duplicate_of_candidate_id == 12
    assert updated_from_object.validation_status == "validated"

    try:
        repo.save_review_update({"id": 999, "status": "draft"})
    except ValueError as exc:
        assert "source candidate not found: 999" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("save_review_update should reject unknown candidates")


def test_find_overlap_groups_and_summarize_batch_cover_review_helpers(monkeypatch) -> None:
    session = _session()
    repo = SourceCandidateRepo(session)
    batch = SourceImportBatchRepo(session).create_batch(raw_text="seed")
    first, _ = repo.create_draft_candidate(
        batch_id=batch.id,
        raw_input="https://example.com/a",
        normalized_url="https://example.com/a",
    )
    second, _ = repo.create_draft_candidate(
        batch_id=batch.id,
        raw_input="https://example.com/b",
        normalized_url="https://example.com/b",
    )
    third, _ = repo.create_draft_candidate(
        batch_id=batch.id,
        raw_input="https://example.com/c",
        normalized_url="https://example.com/c",
    )
    first.status = "approved"
    first.validation_status = "validated"
    second.status = "rejected"
    second.validation_status = "failed"
    third.status = "duplicate"
    third.validation_status = "warning"
    session.flush()

    expected_group = SimpleNamespace(candidate_ids=[first.id, second.id], reason="same_host")
    monkeypatch.setattr(
        "app.core.sources.onboarding.group_candidate_overlaps",
        lambda candidates: [expected_group] if len(candidates) == 2 else [],
    )

    groups = repo.find_overlap_groups(batch_id=batch.id, candidate_ids=[first.id, second.id])
    assert groups == [expected_group]

    summary = repo.summarize_batch(batch_id=batch.id)
    assert summary == {
        "batch_id": batch.id,
        "total_candidates": 3,
        "draft_count": 0,
        "validated_count": 1,
        "approved_count": 1,
        "rejected_count": 1,
        "duplicate_count": 1,
        "pending_review_count": 0,
        "rejected_review_count": 1,
    }


def test_source_repo_helpers_cover_disable_and_candidate_promotion_paths() -> None:
    session = _session()
    source_repo = SourceRepo(session)

    try:
        source_repo.disable_source(999)
    except ValueError as exc:
        assert "source not found: 999" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("disable_source should reject unknown source ids")

    existing = Source(
        source_key="existing-source",
        name="Existing",
        type="html",
        url="https://example.com/existing",
        enabled=False,
        fetch_interval_minutes=15,
        source_weight=1.0,
    )
    session.add(existing)
    session.flush()

    reused = source_repo.create_from_candidate(
        {
            "approved_source_id": existing.id,
            "normalized_url": "https://example.com/existing-updated",
            "candidate_type": "unknown",
            "validation_detected_type": "rss",
        }
    )
    assert reused.id == existing.id
    assert reused.enabled is True
    assert reused.type == "rss"
    assert reused.url == "https://example.com/existing-updated"

    by_url = source_repo.create_from_candidate(
        {
            "normalized_url": "https://example.com/existing-updated",
            "candidate_type": "html",
        }
    )
    assert by_url.id == existing.id
    assert by_url.type == "html"

    allocated = source_repo.create_from_candidate(
        {
            "normalized_url": "https://example.com/existing-updated",
            "candidate_type": "html",
            "approved_source_id": 999999,
        }
    )
    assert allocated.id == existing.id
