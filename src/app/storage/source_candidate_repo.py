import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.storage.models_sql import SourceCandidate, SourceImportBatch

if TYPE_CHECKING:
    from app.core.sources.candidates import CandidateOverlapGroup


class SourceImportBatchRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_batch(
        self,
        *,
        raw_text: str,
        parsed_count: int = 0,
        accepted_count: int = 0,
        rejected_count: int = 0,
    ) -> SourceImportBatch:
        batch = SourceImportBatch(
            raw_text=raw_text,
            parsed_count=parsed_count,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
        )
        self.session.add(batch)
        self.session.flush()
        return batch

    def update_counts(
        self,
        *,
        batch: SourceImportBatch,
        parsed_count: int,
        accepted_count: int,
        rejected_count: int,
    ) -> SourceImportBatch:
        batch.parsed_count = parsed_count
        batch.accepted_count = accepted_count
        batch.rejected_count = rejected_count
        self.session.flush()
        return batch

    def get_batch(self, batch_id: int) -> SourceImportBatch | None:
        return self.session.get(SourceImportBatch, batch_id)


class SourceCandidateRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_draft_candidate(
        self,
        *,
        raw_input: str,
        normalized_url: str,
        batch_id: int | None = None,
        candidate_type: str = "unknown",
    ) -> tuple[SourceCandidate, bool]:
        stmt: Select[tuple[SourceCandidate]] = select(SourceCandidate).where(
            SourceCandidate.normalized_url == normalized_url
        )
        existing = self.session.execute(stmt).scalar_one_or_none()
        if existing is not None:
            return existing, False

        candidate = SourceCandidate(
            batch_id=batch_id,
            raw_input=raw_input,
            normalized_url=normalized_url,
            candidate_type=candidate_type,
        )
        self.session.add(candidate)
        self.session.flush()
        return candidate, True

    def create_draft_candidates(
        self,
        *,
        batch_id: int | None,
        candidates: list[object],
    ) -> tuple[list[SourceCandidate], int]:
        rows: list[SourceCandidate] = []
        accepted_count = 0
        for candidate_data in candidates:
            raw_input = self._read_candidate_value(candidate_data, "raw_input")
            normalized_url = self._read_candidate_value(candidate_data, "normalized_url")
            candidate_type = self._read_candidate_value(
                candidate_data,
                "candidate_type",
                default="unknown",
            )
            candidate, created = self.create_draft_candidate(
                raw_input=raw_input,
                normalized_url=normalized_url,
                batch_id=batch_id,
                candidate_type=candidate_type,
            )
            if created:
                rows.append(candidate)
                accepted_count += 1
        return rows, accepted_count

    @staticmethod
    def _read_candidate_value(
        candidate_data: object,
        field_name: str,
        *,
        default: str | None = None,
    ) -> str:
        if isinstance(candidate_data, dict):
            value = candidate_data.get(field_name, default)
        else:
            value = getattr(candidate_data, field_name, default)
        if value is None:
            raise ValueError(f"candidate field is required: {field_name}")
        return str(value)

    def get_candidate(self, candidate_id: int) -> SourceCandidate | None:
        return self.session.get(SourceCandidate, candidate_id)

    def list_candidates(
        self,
        *,
        batch_id: int | None = None,
        candidate_ids: list[int] | None = None,
        status: str | None = None,
        validation_status: str | None = None,
    ) -> list[SourceCandidate]:
        stmt: Select[tuple[SourceCandidate]] = select(SourceCandidate)
        if batch_id is not None:
            stmt = stmt.where(SourceCandidate.batch_id == batch_id)
        if candidate_ids:
            stmt = stmt.where(SourceCandidate.id.in_(candidate_ids))
        if status is not None:
            stmt = stmt.where(SourceCandidate.status == status)
        if validation_status is not None:
            stmt = stmt.where(SourceCandidate.validation_status == validation_status)
        stmt = stmt.order_by(SourceCandidate.id.asc())
        return list(self.session.scalars(stmt).all())

    def find_by_normalized_url(self, normalized_url: str) -> SourceCandidate | None:
        stmt: Select[tuple[SourceCandidate]] = (
            select(SourceCandidate).where(SourceCandidate.normalized_url == normalized_url).limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def record_validation_result(
        self,
        *,
        candidate_id: int,
        result: object,
    ) -> SourceCandidate:
        candidate = self.get_candidate(candidate_id)
        if candidate is None:
            raise ValueError(f"source candidate not found: {candidate_id}")

        status = self._read_candidate_value(result, "status")
        detected_type = self._read_optional_value(result, "detected_type")
        validation_error = self._read_optional_value(result, "validation_error")
        candidate.validation_status = status
        candidate.validation_detected_type = detected_type
        candidate.validation_error = validation_error
        if detected_type:
            candidate.candidate_type = detected_type
        candidate.validation_details = self._build_validation_details(result)
        candidate.validated_at = datetime.now(UTC)
        self.session.flush()
        return candidate

    def save_review_update(self, candidate: object) -> SourceCandidate:
        candidate_id = int(self._read_candidate_value(candidate, "id"))
        stored = self.get_candidate(candidate_id)
        if stored is None:
            raise ValueError(f"source candidate not found: {candidate_id}")
        for field_name in (
            "status",
            "review_note",
            "duplicate_of_candidate_id",
            "approved_source_id",
            "raw_input",
            "normalized_url",
            "candidate_type",
            "validation_status",
        ):
            if isinstance(candidate, dict):
                if field_name not in candidate:
                    continue
                value = candidate.get(field_name)
            else:
                if not hasattr(candidate, field_name):
                    continue
                value = getattr(candidate, field_name)
            setattr(stored, field_name, value)
        self.session.flush()
        return stored

    def find_overlap_groups(
        self,
        *,
        batch_id: int | None = None,
        candidate_ids: list[int] | None = None,
    ) -> list[CandidateOverlapGroup]:
        from app.core.sources.candidates import (  # pylint: disable=import-outside-toplevel
            group_candidate_overlaps,
        )

        candidates = self.list_candidates(batch_id=batch_id, candidate_ids=candidate_ids)
        return cast("list[CandidateOverlapGroup]", group_candidate_overlaps(candidates))

    def summarize_batch(self, *, batch_id: int | None) -> dict[str, int]:
        candidates = self.list_candidates(batch_id=batch_id)
        summary = {
            "batch_id": 0 if batch_id is None else batch_id,
            "total_candidates": len(candidates),
            "draft_count": 0,
            "validated_count": 0,
            "approved_count": 0,
            "rejected_count": 0,
            "duplicate_count": 0,
            "pending_review_count": 0,
            "rejected_review_count": 0,
        }
        for candidate in candidates:
            if candidate.status == "draft":
                summary["draft_count"] += 1
            if candidate.validation_status == "validated":
                summary["validated_count"] += 1
            if candidate.status == "approved":
                summary["approved_count"] += 1
            if candidate.status == "rejected":
                summary["rejected_count"] += 1
                summary["rejected_review_count"] += 1
            if candidate.status == "duplicate":
                summary["duplicate_count"] += 1
            if candidate.status == "draft":
                summary["pending_review_count"] += 1
        return summary

    @staticmethod
    def _build_validation_details(result: object) -> str | None:
        details: dict[str, object] = {}
        for field_name in ("entry_count", "link_count", "sample_links"):
            if isinstance(result, dict):
                value = result.get(field_name)
            else:
                value = getattr(result, field_name, None)
            if value is None:
                continue
            details[field_name] = value
        if not details:
            return None
        return json.dumps(details, ensure_ascii=True, sort_keys=True)

    @staticmethod
    def _read_optional_value(candidate_data: object, field_name: str) -> str | None:
        if isinstance(candidate_data, dict):
            value = candidate_data.get(field_name)
        else:
            value = getattr(candidate_data, field_name, None)
        if value is None:
            return None
        return str(value)
