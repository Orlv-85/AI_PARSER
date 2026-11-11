"""Source onboarding admin API: import, check, validate, overlaps and candidate review."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi import Path as FastAPIPath
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.storage.source_candidate_repo import SourceCandidateRepo, SourceImportBatchRepo
from app.usecases.sources.onboarding import import_source_candidates, review_candidate_overlaps
from app.usecases.sources.validation import run_source_validation_batch
from app.web.models import (
    WEB_BODY_ERROR,
    SourceOnboardingApproveResponse,
    SourceOnboardingBatchSummary,
    SourceOnboardingCandidateListResponse,
    SourceOnboardingDisableResponse,
    SourceOnboardingDuplicateRequest,
    SourceOnboardingDuplicateResponse,
    SourceOnboardingEditRequest,
    SourceOnboardingEditResponse,
    SourceOnboardingImportRequest,
    SourceOnboardingRejectRequest,
    SourceOnboardingRejectResponse,
    SourceOnboardingValidateRequest,
    json_body,
)
from app.web.routes import WebDeps
from app.web.source_onboarding import SourceOnboardingService

_SOURCE_ONBOARDING_OVERLAP_BATCH_QUERY = Query(None, ge=1)
_SOURCE_ONBOARDING_OVERLAP_CANDIDATE_QUERY = Query(default=[])


def _read_body[M: BaseModel](model: type[M], body: bytes, required: str) -> M:
    """The body as `model`; any error is 422 with one string `detail` for the admin page."""
    try:
        return model.model_validate(json_body(body))
    except ValidationError as exc:
        # The validators raise every field error as WEB_BODY_ERROR; anything else is the body
        # itself not being an object.
        error = exc.errors()[0]
        detail = error["msg"] if error["type"] == WEB_BODY_ERROR else required
        raise HTTPException(status_code=422, detail=detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=required) from exc


def build_sources_router(deps: WebDeps) -> APIRouter:  # pylint: disable=too-many-statements
    onboarding_session_local = deps.onboarding_session_local
    source_intake = deps.source_intake
    router = APIRouter()

    @router.post("/api/source-onboarding/import")
    async def import_source_onboarding_batch(request: Request) -> JSONResponse:
        raw_text = _read_body(
            SourceOnboardingImportRequest, await request.body(), "raw_text is required"
        ).raw_text

        try:
            deps.create_onboarding_tables()
            with onboarding_session_local() as session:
                result = import_source_candidates(
                    raw_text=raw_text,
                    batch_repo=SourceImportBatchRepo(session),
                    candidate_repo=SourceCandidateRepo(session),
                )
                session.commit()
                batch_id = result.batch.id
                parsed_count = result.parsed_count
                accepted_count = result.accepted_count
                rejected_count = result.rejected_count
                candidate_ids = [candidate.id for candidate in result.candidates]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return JSONResponse(
            status_code=201,
            content={
                "batch_id": batch_id,
                "parsed_count": parsed_count,
                "accepted_count": accepted_count,
                "rejected_count": rejected_count,
                "candidate_ids": candidate_ids,
            },
        )

    @router.get("/api/source-onboarding/latest")
    def latest_source_batch() -> dict[str, Any]:
        try:
            deps.create_onboarding_tables()
            return {"batch_id": source_intake.latest_batch(), "job": source_intake.status()}
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

    @router.get("/api/source-onboarding/check-status")
    def source_check_status() -> dict[str, Any]:
        return dict(source_intake.status())

    @router.post("/api/source-onboarding/batches/{batch_id}/check", status_code=202)
    def check_source_batch(batch_id: int = FastAPIPath(..., ge=1)) -> dict[str, Any]:
        try:
            deps.create_onboarding_tables()
            return dict(source_intake.start(batch_id))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

    @router.post("/api/source-onboarding/batches/{batch_id}/approve-ready")
    def approve_ready_sources(batch_id: int = FastAPIPath(..., ge=1)) -> dict[str, Any]:
        try:
            deps.create_onboarding_tables()
            approved = source_intake.approve_ready(batch_id)
            return {"batch_id": batch_id, "approved_count": len(approved),
                    "candidate_ids": approved}
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

    @router.post("/api/source-onboarding/validate")
    async def validate_source_onboarding_batch(request: Request) -> JSONResponse:
        body = _read_body(
            SourceOnboardingValidateRequest,
            await request.body(),
            "batch_id or candidate_ids is required",
        )
        batch_id, candidate_ids = body.batch_id, body.candidate_ids

        def _validate_batch() -> JSONResponse:
            try:
                deps.create_onboarding_tables()
                with onboarding_session_local() as session:
                    results = run_source_validation_batch(
                        session=session,
                        batch_id=batch_id,
                        candidate_ids=candidate_ids,
                    )
                    session.commit()
            except SQLAlchemyError as exc:
                raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

            return JSONResponse(
                status_code=200,
                content={
                    "validated_count": len(results),
                    "results": [
                        {
                            "candidate_id": result.candidate_id,
                            "status": result.status,
                            "detected_type": result.detected_type,
                            "validation_error": result.validation_error,
                            "entry_count": result.entry_count,
                            "link_count": result.link_count,
                            "sample_links": result.sample_links,
                        }
                        for result in results
                    ],
                },
            )

        return await run_in_threadpool(_validate_batch)

    @router.get("/api/source-onboarding/overlaps")
    def get_source_onboarding_overlaps(
        *,
        batch_id: int | None = _SOURCE_ONBOARDING_OVERLAP_BATCH_QUERY,
        candidate_id: list[int] = _SOURCE_ONBOARDING_OVERLAP_CANDIDATE_QUERY,
    ) -> JSONResponse:
        candidate_ids = list(candidate_id)
        try:
            deps.create_onboarding_tables()
            with onboarding_session_local() as session:
                groups = review_candidate_overlaps(
                    session=session,
                    batch_id=batch_id,
                    candidate_ids=candidate_ids or None,
                )
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return JSONResponse(
            status_code=200,
            content={
                "groups": [
                    {
                        "candidate_ids": group.candidate_ids,
                        "reason": group.reason,
                        "preferred_candidate_id": group.preferred_candidate_id,
                    }
                    for group in groups
                ]
            },
        )

    @router.get(
        "/api/source-onboarding/candidates",
        response_model=SourceOnboardingCandidateListResponse,
    )
    def list_source_onboarding_candidates(
        *,
        batch_id: int | None = Query(None, ge=1),
        status: str | None = None,
        validation_status: str | None = None,
    ) -> SourceOnboardingCandidateListResponse:
        try:
            deps.create_onboarding_tables()
            with onboarding_session_local() as session:
                service = SourceOnboardingService(session)
                return service.list_candidates(
                    batch_id=batch_id,
                    status=status,
                    validation_status=validation_status,
                )
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

    @router.get(
        "/api/source-onboarding/batches/{batch_id}/summary",
        response_model=SourceOnboardingBatchSummary,
    )
    def get_source_onboarding_batch_summary(batch_id: int) -> SourceOnboardingBatchSummary:
        try:
            deps.create_onboarding_tables()
            with onboarding_session_local() as session:
                service = SourceOnboardingService(session)
                return service.get_batch_summary(batch_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

    @router.post(
        "/api/source-onboarding/candidates/{candidate_id}/approve",
        response_model=SourceOnboardingApproveResponse,
    )
    def approve_source_onboarding_candidate(
        candidate_id: int = FastAPIPath(..., ge=1),
    ) -> SourceOnboardingApproveResponse:
        try:
            deps.create_onboarding_tables()
            with onboarding_session_local() as session:
                service = SourceOnboardingService(session)
                response = service.approve_candidate(candidate_id)
                session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return response

    @router.post(
        "/api/source-onboarding/candidates/{candidate_id}/disable",
        response_model=SourceOnboardingDisableResponse,
    )
    def disable_source_onboarding_candidate(
        candidate_id: int = FastAPIPath(..., ge=1),
    ) -> SourceOnboardingDisableResponse:
        try:
            deps.create_onboarding_tables()
            with onboarding_session_local() as session:
                service = SourceOnboardingService(session)
                response = service.disable_candidate(candidate_id)
                session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return response

    @router.post(
        "/api/source-onboarding/candidates/{candidate_id}/reject",
        response_model=SourceOnboardingRejectResponse,
    )
    def reject_source_onboarding_candidate(
        payload: SourceOnboardingRejectRequest,
        candidate_id: int = FastAPIPath(..., ge=1),
    ) -> SourceOnboardingRejectResponse:
        try:
            deps.create_onboarding_tables()
            with onboarding_session_local() as session:
                service = SourceOnboardingService(session)
                response = service.reject_candidate(candidate_id, reason=payload.reason)
                session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return response

    @router.post(
        "/api/source-onboarding/candidates/{candidate_id}/mark-duplicate",
        response_model=SourceOnboardingDuplicateResponse,
    )
    def mark_source_onboarding_candidate_duplicate(
        payload: SourceOnboardingDuplicateRequest,
        candidate_id: int = FastAPIPath(..., ge=1),
    ) -> SourceOnboardingDuplicateResponse:
        try:
            deps.create_onboarding_tables()
            with onboarding_session_local() as session:
                service = SourceOnboardingService(session)
                response = service.mark_duplicate(
                    candidate_id,
                    duplicate_of_candidate_id=payload.duplicate_of_candidate_id,
                    reason=payload.reason,
                )
                session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return response

    @router.patch(
        "/api/source-onboarding/candidates/{candidate_id}",
        response_model=SourceOnboardingEditResponse,
    )
    def edit_source_onboarding_candidate(
        payload: SourceOnboardingEditRequest,
        candidate_id: int = FastAPIPath(..., ge=1),
    ) -> SourceOnboardingEditResponse:
        try:
            deps.create_onboarding_tables()
            with onboarding_session_local() as session:
                service = SourceOnboardingService(session)
                response = service.edit_candidate(
                    candidate_id,
                    raw_input=payload.raw_input,
                    normalized_url=payload.normalized_url,
                    candidate_type=payload.candidate_type,
                    review_note=payload.review_note,
                )
                session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return response

    return router
