# pylint: disable=protected-access

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.sources.onboarding import review_source_candidate
from app.storage.models_sql import Base, Source
from app.storage.source_candidate_repo import SourceCandidateRepo, SourceImportBatchRepo
from app.storage.source_repo import SourceRepo
from app.web.service import SourceOnboardingService


def _build_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory(), engine


def _create_candidate(
    session,
    *,
    normalized_url: str,
    candidate_type: str,
    validation_status: str,
):
    batch = SourceImportBatchRepo(session).create_batch(raw_text=normalized_url, parsed_count=1)
    candidate, created = SourceCandidateRepo(session).create_draft_candidate(
        batch_id=batch.id,
        raw_input=normalized_url,
        normalized_url=normalized_url,
        candidate_type=candidate_type,
    )
    assert created is True
    candidate.validation_status = validation_status
    session.flush()
    return candidate


def test_review_source_candidate_approve_promotes_validated_draft() -> None:
    session, engine = _build_session()
    try:
        candidate_repo = SourceCandidateRepo(session)
        source_repo = SourceRepo(session)
        candidate = _create_candidate(
            session,
            normalized_url="https://example.com/feed.xml",
            candidate_type="rss",
            validation_status="validated",
        )

        updated = review_source_candidate(
            candidate_id=candidate.id,
            action="approve",
            candidate_repo=candidate_repo,
            managed_source_repo=source_repo,
        )

        assert updated.status == "approved"
        assert updated.validation_status == "validated"
        assert isinstance(updated.approved_source_id, int)

        stored_source = session.get(Source, updated.approved_source_id)
        assert stored_source is not None
        assert stored_source.enabled is True
        assert stored_source.url == "https://example.com/feed.xml"
    finally:
        session.close()
        engine.dispose()


def test_review_source_candidate_rejects_approval_when_validation_failed() -> None:
    session, engine = _build_session()
    try:
        candidate = _create_candidate(
            session,
            normalized_url="https://example.com/blog",
            candidate_type="html",
            validation_status="failed",
        )

        try:
            review_source_candidate(
                candidate_id=candidate.id,
                action="approve",
                candidate_repo=SourceCandidateRepo(session),
                managed_source_repo=SourceRepo(session),
            )
        except ValueError as exc:
            assert "validated" in str(exc).lower()
        else:  # pragma: no cover - exercised when the contract is implemented incorrectly
            raise AssertionError("Approving a failed candidate should raise ValueError")
    finally:
        session.close()
        engine.dispose()


def test_review_source_candidate_mark_duplicate_sets_duplicate_relationship() -> None:
    session, engine = _build_session()
    try:
        candidate_repo = SourceCandidateRepo(session)
        primary = _create_candidate(
            session,
            normalized_url="https://example.com/blog",
            candidate_type="html",
            validation_status="validated",
        )
        duplicate = _create_candidate(
            session,
            normalized_url="https://example.com/tag/ai",
            candidate_type="html",
            validation_status="validated",
        )

        updated = review_source_candidate(
            candidate_id=duplicate.id,
            action="mark_duplicate",
            duplicate_of_candidate_id=primary.id,
            candidate_repo=candidate_repo,
            managed_source_repo=SourceRepo(session),
        )

        assert updated.status == "duplicate"
        assert updated.duplicate_of_candidate_id == primary.id
        stored = candidate_repo.get_candidate(duplicate.id)
        assert stored is not None
        assert stored.duplicate_of_candidate_id == primary.id
    finally:
        session.close()
        engine.dispose()


def test_review_source_candidate_reuses_existing_source_for_reapproval() -> None:
    session, engine = _build_session()
    try:
        source_repo = SourceRepo(session)
        candidate_repo = SourceCandidateRepo(session)
        candidate = _create_candidate(
            session,
            normalized_url="https://example.com/news",
            candidate_type="html",
            validation_status="validated",
        )

        first = review_source_candidate(
            candidate_id=candidate.id,
            action="approve",
            candidate_repo=candidate_repo,
            managed_source_repo=source_repo,
        )
        source_id = first.approved_source_id
        assert source_id is not None

        first.status = "rejected"
        session.flush()

        second = review_source_candidate(
            candidate_id=candidate.id,
            action="approve",
            candidate_repo=candidate_repo,
            managed_source_repo=source_repo,
        )

        assert second.approved_source_id == source_id
        source_ids = session.execute(select(Source.id)).scalars().all()
        assert source_ids == [source_id]
    finally:
        session.close()
        engine.dispose()


def test_review_source_candidate_disable_turns_off_previously_approved_managed_source() -> None:
    session, engine = _build_session()
    try:
        source_repo = SourceRepo(session)
        candidate_repo = SourceCandidateRepo(session)
        candidate = _create_candidate(
            session,
            normalized_url="https://example.com/managed-feed.xml",
            candidate_type="rss",
            validation_status="validated",
        )

        approved = review_source_candidate(
            candidate_id=candidate.id,
            action="approve",
            candidate_repo=candidate_repo,
            managed_source_repo=source_repo,
        )
        approved_source_id = approved.approved_source_id
        assert approved_source_id is not None

        disabled = review_source_candidate(
            candidate_id=candidate.id,
            action="disable",
            candidate_repo=candidate_repo,
            managed_source_repo=source_repo,
        )

        assert disabled.status == "disabled"
        stored_source = session.get(Source, approved_source_id)
        assert stored_source is not None
        assert stored_source.enabled is False
    finally:
        session.close()
        engine.dispose()


def test_review_source_candidate_reject_disables_approved_managed_source() -> None:
    session, engine = _build_session()
    try:
        source_repo = SourceRepo(session)
        candidate_repo = SourceCandidateRepo(session)
        primary = _create_candidate(
            session,
            normalized_url="https://example.com/feed.xml",
            candidate_type="rss",
            validation_status="validated",
        )
        duplicate = _create_candidate(
            session,
            normalized_url="https://example.com/tag/ai",
            candidate_type="html",
            validation_status="validated",
        )
        approved = review_source_candidate(
            candidate_id=primary.id,
            action="approve",
            candidate_repo=candidate_repo,
            managed_source_repo=source_repo,
        )
        source_id = approved.approved_source_id
        review_source_candidate(
            candidate_id=duplicate.id,
            action="mark_duplicate",
            duplicate_of_candidate_id=primary.id,
            candidate_repo=candidate_repo,
            managed_source_repo=source_repo,
        )

        review_source_candidate(
            candidate_id=duplicate.id,
            action="reject",
            candidate_repo=candidate_repo,
            managed_source_repo=source_repo,
        )
        assert session.get(Source, source_id).enabled is True

        rejected = review_source_candidate(
            candidate_id=primary.id,
            action="reject",
            candidate_repo=candidate_repo,
            managed_source_repo=source_repo,
            review_note="off-topic",
        )
        assert rejected.status == "rejected"
        assert session.get(Source, source_id).enabled is False
        assert source_id not in {row.id for row in source_repo.list_enabled_sources()}
    finally:
        session.close()
        engine.dispose()


def test_review_source_candidate_rejects_invalid_duplicate_targets() -> None:
    session, engine = _build_session()
    try:
        candidate = _create_candidate(
            session,
            normalized_url="https://example.com/blog",
            candidate_type="html",
            validation_status="validated",
        )

        for duplicate_target, expected_fragment in (
            (candidate.id, "cannot be marked duplicate of itself"),
            (candidate.id + 999, "source candidate not found"),
        ):
            try:
                review_source_candidate(
                    candidate_id=candidate.id,
                    action="mark_duplicate",
                    duplicate_of_candidate_id=duplicate_target,
                    candidate_repo=SourceCandidateRepo(session),
                    managed_source_repo=SourceRepo(session),
                )
            except ValueError as exc:
                assert expected_fragment in str(exc).lower()
            else:  # pragma: no cover - exercised when the contract is implemented incorrectly
                raise AssertionError("Invalid duplicate targets should raise ValueError")
    finally:
        session.close()
        engine.dispose()


def test_review_source_candidate_rejects_invalid_edit_payloads() -> None:
    session, engine = _build_session()
    try:
        candidate = _create_candidate(
            session,
            normalized_url="https://example.com/edit-me",
            candidate_type="html",
            validation_status="validated",
        )

        invalid_cases = (
            (
                {"normalized_url": "notaurl"},
                "invalid source candidate url",
            ),
            (
                {"candidate_type": "podcast"},
                "candidate_type must be one of",
            ),
        )

        for updates, expected_fragment in invalid_cases:
            try:
                review_source_candidate(
                    candidate_id=candidate.id,
                    action="edit",
                    candidate_repo=SourceCandidateRepo(session),
                    managed_source_repo=SourceRepo(session),
                    updates=updates,
                )
            except ValueError as exc:
                assert expected_fragment in str(exc).lower()
            else:  # pragma: no cover - exercised when the contract is implemented incorrectly
                raise AssertionError("Invalid edit payloads should raise ValueError")
    finally:
        session.close()
        engine.dispose()


def test_source_onboarding_service_disable_requires_approved_source_id(monkeypatch) -> None:
    service = SourceOnboardingService(session=None)  # type: ignore[arg-type]

    def _review_source_candidate(**_kwargs):
        return type(
            "Candidate",
            (),
            {
                "id": 11,
                "status": "disabled",
                "approved_source_id": None,
            },
        )()

    monkeypatch.setattr("app.web.service.review_source_candidate", _review_source_candidate)

    try:
        service.disable_candidate(11)
    except ValueError as exc:
        assert "missing approved_source_id" in str(exc)
    else:  # pragma: no cover - exercised when the guard is implemented incorrectly
        raise AssertionError("disable_candidate should reject missing approved_source_id")


def test_source_onboarding_service_first_batch_id_returns_none_for_empty_candidates() -> None:
    assert SourceOnboardingService._first_batch_id([]) is None


def test_source_onboarding_service_first_batch_id_returns_first_candidate_batch_id() -> None:
    candidate = type("Candidate", (), {"batch_id": 42})()

    assert SourceOnboardingService._first_batch_id([candidate]) == 42
