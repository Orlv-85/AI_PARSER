from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.storage.models_sql import Base, SourceCandidate
from app.storage.repos import SourceCandidateRepo, SourceImportBatchRepo


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
