"""Source onboarding admin API: import, check, validate, overlaps and candidate review."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi import Path as FastAPIPath
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from app.usecases.sources.candidate_review import (
    SourceOnboardingApproveResponse,
    SourceOnboardingBatchSummary,
    SourceOnboardingCandidateListResponse,
    SourceOnboardingDisableResponse,
    SourceOnboardingDuplicateResponse,
    SourceOnboardingEditResponse,
    SourceOnboardingRejectResponse,
    SourceOnboardingService,
    review_in_session,
)
from app.usecases.sources.onboarding import candidate_overlaps, import_batch
from app.usecases.sources.validation import validate_batch
from app.web.models import (
    WEB_BODY_ERROR,
    SourceOnboardingDuplicateRequest,
    SourceOnboardingEditRequest,
    SourceOnboardingImportRequest,
    SourceOnboardingRejectRequest,
    SourceOnboardingValidateRequest,
    json_body,
)
from app.web.routes import WebDeps
from app.web.routes.common import _http_errors

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


@contextmanager
def _onboarding(deps: WebDeps, value_error_status: int | None = None) -> Iterator[None]:
    """Onboarding tables created, errors mapped as in `_http_errors`."""
    with _http_errors(value_error_status):
        deps.create_onboarding_tables()
        yield


def _review[R](deps: WebDeps, action: Callable[[SourceOnboardingService], R], *,
               commit: bool, value_error_status: int | None = None) -> R:
    """One candidate review action in its own session (`review_in_session`)."""
    with _onboarding(deps, value_error_status):
        result: R = review_in_session(deps.onboarding_session_local, action, commit=commit)
        return result


def _import_response(deps: WebDeps, body: bytes) -> JSONResponse:
    raw_text = _read_body(SourceOnboardingImportRequest, body, "raw_text is required").raw_text
    with _onboarding(deps, 422):
        result = import_batch(deps.onboarding_session_local, raw_text)
    return JSONResponse(
        status_code=201,
        content={
            "batch_id": result.batch_id,
            "parsed_count": result.parsed_count,
            "accepted_count": result.accepted_count,
            "rejected_count": result.rejected_count,
            "candidate_ids": result.candidate_ids,
        },
    )


def _latest_batch_response(deps: WebDeps) -> dict[str, Any]:
    with _onboarding(deps):
        return {"batch_id": deps.source_intake.latest_batch(),
                "job": deps.source_intake.status()}


def _check_batch_response(deps: WebDeps, batch_id: int) -> dict[str, Any]:
    with _onboarding(deps, 409):
        return dict(deps.source_intake.start(batch_id))


def _approve_ready_response(deps: WebDeps, batch_id: int) -> dict[str, Any]:
    with _onboarding(deps, 409):
        approved = deps.source_intake.approve_ready(batch_id)
        return {"batch_id": batch_id, "approved_count": len(approved),
                "candidate_ids": approved}


async def _validate_response(deps: WebDeps, body: bytes) -> JSONResponse:
    """Validation fetches every candidate, so it runs in the thread pool."""
    request_body = _read_body(
        SourceOnboardingValidateRequest, body, "batch_id or candidate_ids is required"
    )
    return await run_in_threadpool(_validated, deps, request_body)


def _validated(deps: WebDeps, body: SourceOnboardingValidateRequest) -> JSONResponse:
    with _onboarding(deps):
        results = validate_batch(
            deps.onboarding_session_local,
            batch_id=body.batch_id,
            candidate_ids=body.candidate_ids,
        )
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


def _overlaps_response(deps: WebDeps, batch_id: int | None,
                       candidate_ids: list[int]) -> JSONResponse:
    with _onboarding(deps):
        groups = candidate_overlaps(
            deps.onboarding_session_local, batch_id=batch_id,
            candidate_ids=candidate_ids or None,
        )
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


def build_sources_router(deps: WebDeps) -> APIRouter:
    router = APIRouter()

    @router.post("/api/source-onboarding/import")
    async def import_source_onboarding_batch(request: Request) -> JSONResponse:
        return _import_response(deps, await request.body())

    @router.get("/api/source-onboarding/latest")
    def latest_source_batch() -> dict[str, Any]:
        return _latest_batch_response(deps)

    @router.get("/api/source-onboarding/check-status")
    def source_check_status() -> dict[str, Any]:
        return dict(deps.source_intake.status())

    @router.post("/api/source-onboarding/batches/{batch_id}/check", status_code=202)
    def check_source_batch(batch_id: int = FastAPIPath(..., ge=1)) -> dict[str, Any]:
        return _check_batch_response(deps, batch_id)

    @router.post("/api/source-onboarding/batches/{batch_id}/approve-ready")
    def approve_ready_sources(batch_id: int = FastAPIPath(..., ge=1)) -> dict[str, Any]:
        return _approve_ready_response(deps, batch_id)

    @router.post("/api/source-onboarding/validate")
    async def validate_source_onboarding_batch(request: Request) -> JSONResponse:
        return await _validate_response(deps, await request.body())

    @router.get("/api/source-onboarding/overlaps")
    def get_source_onboarding_overlaps(
        *,
        batch_id: int | None = _SOURCE_ONBOARDING_OVERLAP_BATCH_QUERY,
        candidate_id: list[int] = _SOURCE_ONBOARDING_OVERLAP_CANDIDATE_QUERY,
    ) -> JSONResponse:
        return _overlaps_response(deps, batch_id, list(candidate_id))

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
        return _review(deps, lambda service: service.list_candidates(
            batch_id=batch_id, status=status, validation_status=validation_status,
        ), commit=False)

    @router.get(
        "/api/source-onboarding/batches/{batch_id}/summary",
        response_model=SourceOnboardingBatchSummary,
    )
    def get_source_onboarding_batch_summary(batch_id: int) -> SourceOnboardingBatchSummary:
        return _review(deps, lambda service: service.get_batch_summary(batch_id),
                       commit=False, value_error_status=404)

    @router.post(
        "/api/source-onboarding/candidates/{candidate_id}/approve",
        response_model=SourceOnboardingApproveResponse,
    )
    def approve_source_onboarding_candidate(
        candidate_id: int = FastAPIPath(..., ge=1),
    ) -> SourceOnboardingApproveResponse:
        return _review(deps, lambda service: service.approve_candidate(candidate_id),
                       commit=True, value_error_status=400)

    @router.post(
        "/api/source-onboarding/candidates/{candidate_id}/disable",
        response_model=SourceOnboardingDisableResponse,
    )
    def disable_source_onboarding_candidate(
        candidate_id: int = FastAPIPath(..., ge=1),
    ) -> SourceOnboardingDisableResponse:
        return _review(deps, lambda service: service.disable_candidate(candidate_id),
                       commit=True, value_error_status=400)

    @router.post(
        "/api/source-onboarding/candidates/{candidate_id}/reject",
        response_model=SourceOnboardingRejectResponse,
    )
    def reject_source_onboarding_candidate(
        payload: SourceOnboardingRejectRequest,
        candidate_id: int = FastAPIPath(..., ge=1),
    ) -> SourceOnboardingRejectResponse:
        return _review(deps, lambda service: service.reject_candidate(
            candidate_id, reason=payload.reason,
        ), commit=True, value_error_status=400)

    @router.post(
        "/api/source-onboarding/candidates/{candidate_id}/mark-duplicate",
        response_model=SourceOnboardingDuplicateResponse,
    )
    def mark_source_onboarding_candidate_duplicate(
        payload: SourceOnboardingDuplicateRequest,
        candidate_id: int = FastAPIPath(..., ge=1),
    ) -> SourceOnboardingDuplicateResponse:
        return _review(deps, lambda service: service.mark_duplicate(
            candidate_id,
            duplicate_of_candidate_id=payload.duplicate_of_candidate_id,
            reason=payload.reason,
        ), commit=True, value_error_status=400)

    @router.patch(
        "/api/source-onboarding/candidates/{candidate_id}",
        response_model=SourceOnboardingEditResponse,
    )
    def edit_source_onboarding_candidate(
        payload: SourceOnboardingEditRequest,
        candidate_id: int = FastAPIPath(..., ge=1),
    ) -> SourceOnboardingEditResponse:
        return _review(deps, lambda service: service.edit_candidate(
            candidate_id,
            raw_input=payload.raw_input,
            normalized_url=payload.normalized_url,
            candidate_type=payload.candidate_type,
            review_note=payload.review_note,
        ), commit=True, value_error_status=400)

    return router
