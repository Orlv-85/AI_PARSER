from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.sources import onboarding as source_onboarding
from app.storage.models_sql import Base, SourceCandidate
from app.storage.repos import SourceCandidateRepo


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_run_source_validation_persists_status_and_timestamp_end_to_end() -> None:
    assert hasattr(
        source_onboarding,
        "run_source_validation",
    ), (
        "Phase 2 validation orchestrator missing: "
        "app.core.sources.onboarding.run_source_validation"
    )
    assert hasattr(
        SourceCandidateRepo,
        "record_validation_result",
    ), (
        "Phase 2 validation persistence API missing: "
        "app.storage.repos.SourceCandidateRepo.record_validation_result"
    )

    session = _session()
    repo = SourceCandidateRepo(session)
    candidate, created = repo.create_draft_candidate(
        raw_input="https://example.com/feed.xml",
        normalized_url="https://example.com/feed.xml",
        candidate_type="rss",
    )
    assert created is True

    source_onboarding.run_source_validation(
        candidate_id=candidate.id,
        session=session,
        fetch_feed=lambda url: {
            "url": url,
            "title": "Example Feed",
            "entries": [{"title": "Post 1", "link": "https://example.com/posts/1"}],
        },
        fetch_html=lambda url: "<html></html>",
        extract_links=lambda html, base_url: [],
    )
    session.commit()

    stored = session.get(SourceCandidate, candidate.id)
    assert stored is not None
    assert stored.validation_status == "validated"
    assert stored.validation_error is None
    assert stored.validated_at is not None
