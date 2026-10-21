"""Web service for source onboarding candidate lists and review actions."""

from typing import Any, cast

from sqlalchemy.orm import Session

from app.core.sources.onboarding import review_source_candidate
from app.storage.source_candidate_repo import SourceCandidateRepo, SourceImportBatchRepo
from app.storage.source_repo import SourceRepo
from app.web.models import (
    SourceOnboardingApproveResponse,
    SourceOnboardingBatchSummary,
    SourceOnboardingCandidateFilters,
    SourceOnboardingCandidateListResponse,
    SourceOnboardingCandidateView,
    SourceOnboardingDisableResponse,
    SourceOnboardingDuplicateResponse,
    SourceOnboardingEditResponse,
    SourceOnboardingRejectResponse,
)

class SourceOnboardingService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._candidate_repo = SourceCandidateRepo(session)
        self._batch_repo = SourceImportBatchRepo(session)
        self._source_repo = SourceRepo(session)

    def list_candidates(
        self,
        *,
        batch_id: int | None = None,
        status: str | None = None,
        validation_status: str | None = None,
    ) -> SourceOnboardingCandidateListResponse:
        candidates = self._candidate_repo.list_candidates(
            batch_id=batch_id,
            status=status,
            validation_status=validation_status,
        )
        summary_batch_id = batch_id if batch_id is not None else self._first_batch_id(candidates)
        return SourceOnboardingCandidateListResponse(
            items=[self._build_candidate_view(candidate) for candidate in candidates],
            summary=self._build_batch_summary(summary_batch_id),
            filters=SourceOnboardingCandidateFilters(
                batch_id=batch_id,
                status=status,
                validation_status=validation_status,
            ),
        )

    def get_batch_summary(self, batch_id: int) -> SourceOnboardingBatchSummary:
        batch = self._batch_repo.get_batch(batch_id)
        if batch is None:
            raise ValueError(f"source import batch not found: {batch_id}")
        return self._build_batch_summary(batch_id)

    def approve_candidate(self, candidate_id: int) -> SourceOnboardingApproveResponse:
        updated = review_source_candidate(
            candidate_id=candidate_id,
            action="approve",
            candidate_repo=self._candidate_repo,
            managed_source_repo=self._source_repo,
        )
        return SourceOnboardingApproveResponse(
            candidate_id=updated.id,
            status=updated.status,
            validation_status=updated.validation_status,
            managed_source_created=bool(getattr(updated, "approved_source_id", None)),
            approved_source_id=getattr(updated, "approved_source_id", None),
            review_note=getattr(updated, "review_note", None),
        )

    def reject_candidate(
        self,
        candidate_id: int,
        *,
        reason: str | None = None,
    ) -> SourceOnboardingRejectResponse:
        updated = review_source_candidate(
            candidate_id=candidate_id,
            action="reject",
            candidate_repo=self._candidate_repo,
            managed_source_repo=self._source_repo,
            review_note=reason,
        )
        return SourceOnboardingRejectResponse(
            candidate_id=updated.id,
            status=updated.status,
            review_note=getattr(updated, "review_note", None),
        )

    def disable_candidate(self, candidate_id: int) -> SourceOnboardingDisableResponse:
        updated = review_source_candidate(
            candidate_id=candidate_id,
            action="disable",
            candidate_repo=self._candidate_repo,
            managed_source_repo=self._source_repo,
        )
        approved_source_id = getattr(updated, "approved_source_id", None)
        if approved_source_id is None:
            raise ValueError("disabled candidate is missing approved_source_id")
        return SourceOnboardingDisableResponse(
            candidate_id=updated.id,
            status=updated.status,
            approved_source_id=int(approved_source_id),
        )

    def mark_duplicate(
        self,
        candidate_id: int,
        *,
        duplicate_of_candidate_id: int,
        reason: str | None = None,
    ) -> SourceOnboardingDuplicateResponse:
        updated = review_source_candidate(
            candidate_id=candidate_id,
            action="mark_duplicate",
            candidate_repo=self._candidate_repo,
            managed_source_repo=self._source_repo,
            duplicate_of_candidate_id=duplicate_of_candidate_id,
            review_note=reason,
        )
        return SourceOnboardingDuplicateResponse(
            candidate_id=updated.id,
            status=updated.status,
            duplicate_of_candidate_id=updated.duplicate_of_candidate_id,
            review_note=getattr(updated, "review_note", None),
        )

    def edit_candidate(
        self,
        candidate_id: int,
        *,
        raw_input: str | None = None,
        normalized_url: str | None = None,
        candidate_type: str | None = None,
        review_note: str | None = None,
    ) -> SourceOnboardingEditResponse:
        updated = review_source_candidate(
            candidate_id=candidate_id,
            action="edit",
            candidate_repo=self._candidate_repo,
            managed_source_repo=self._source_repo,
            review_note=review_note,
            updates={
                key: value
                for key, value in {
                    "raw_input": raw_input,
                    "normalized_url": normalized_url,
                    "candidate_type": candidate_type,
                }.items()
                if value is not None
            },
        )
        return SourceOnboardingEditResponse(
            candidate_id=updated.id,
            status=updated.status,
            normalized_url=updated.normalized_url,
            candidate_type=updated.candidate_type,
            raw_input=updated.raw_input,
            review_note=getattr(updated, "review_note", None),
        )

    @staticmethod
    def _build_candidate_view(candidate: object) -> SourceOnboardingCandidateView:
        candidate_model: Any = candidate
        return SourceOnboardingCandidateView(
            candidate_id=int(candidate_model.id),
            batch_id=candidate_model.batch_id,
            status=str(candidate_model.status),
            validation_status=str(candidate_model.validation_status),
            candidate_type=str(candidate_model.candidate_type),
            normalized_url=str(candidate_model.normalized_url),
            raw_input=candidate_model.raw_input,
            review_note=candidate_model.review_note,
            duplicate_of_candidate_id=candidate_model.duplicate_of_candidate_id,
            approved_source_id=candidate_model.approved_source_id,
            validation_detected_type=candidate_model.validation_detected_type,
            validation_error=candidate_model.validation_error,
            validation_details=candidate_model.validation_details,
            validated_at=candidate_model.validated_at,
        )

    def _build_batch_summary(self, batch_id: int | None) -> SourceOnboardingBatchSummary:
        summary_counts = self._candidate_repo.summarize_batch(batch_id=batch_id)
        batch = self._batch_repo.get_batch(batch_id) if batch_id is not None else None
        return SourceOnboardingBatchSummary(
            batch_id=batch_id,
            parsed_count=batch.parsed_count if batch is not None else None,
            accepted_count=batch.accepted_count if batch is not None else None,
            rejected_count=(
                batch.rejected_count
                if batch is not None
                else summary_counts["rejected_count"]
            ),
            pending_review_count=summary_counts["pending_review_count"],
            validated_count=summary_counts["validated_count"],
            approved_count=summary_counts["approved_count"],
            rejected_review_count=summary_counts["rejected_review_count"],
            duplicate_count=summary_counts["duplicate_count"],
            total_candidates=summary_counts["total_candidates"],
            draft_count=summary_counts["draft_count"],
        )

    @staticmethod
    def _first_batch_id(candidates: list[object]) -> int | None:
        if not candidates:
            return None
        first_candidate: Any = candidates[0]
        return cast(int | None, first_candidate.batch_id)
