"""Period AI Signals API (017): stored weekly/monthly signals; never calls a provider."""

import json
import logging
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.config.settings import get_settings
from app.storage.models_sql import PeriodSignalReport
from app.storage.period_signals import PeriodSignalRepo
from app.web.models import (
    PeriodSignalsIndexItem,
    PeriodSignalsIndexResponse,
    PeriodSignalsResponse,
)
from app.web.routes import WebDeps

_LOGGER = logging.getLogger(__name__)
# A default read shows the newest period that carries comparable numbers, else any stored one.
_SHOWN = ("ready", "building_history")


def _unavailable(kind: str, start: date | None, note: str | None = None) -> PeriodSignalsResponse:
    return PeriodSignalsResponse(period_kind=kind, period_start=start, status="unavailable",
                                 notes=[note] if note else [])


def _response(kind: str, start: date | None, row: PeriodSignalReport | None
              ) -> PeriodSignalsResponse:
    """Stored row as the API model; missing or unreadable -> `unavailable` (never an error)."""
    if row is None:
        return _unavailable(kind, start)
    try:
        response = PeriodSignalsResponse.model_validate(json.loads(row.payload))
    except (ValueError, TypeError, ValidationError) as exc:
        _LOGGER.error("period_signals_payload_unreadable kind=%s start=%s error=%s", kind,
                      row.period_start.isoformat(), type(exc).__name__)
        return _unavailable(kind, row.period_start, "Period signals could not be read.")
    response.brief = None
    return response


def build_period_router(deps: WebDeps) -> APIRouter:
    router = APIRouter()

    @router.get("/api/news/period-signals", response_model=PeriodSignalsResponse)
    def get_period_signals(
        *,
        kind: Literal["week", "month"] = "week",
        start: date | None = None,
    ) -> PeriodSignalsResponse:
        try:
            deps.create_all()
            with deps.SessionLocal() as session:
                repo = PeriodSignalRepo(
                    session, comparable_from=get_settings().daily_signals_comparable_from)
                row = repo.get_report(kind, start) if start is not None else (
                    repo.latest(kind, _SHOWN) or repo.latest(kind))
                return _response(kind, start, row)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

    @router.get("/api/news/period-signals/index", response_model=PeriodSignalsIndexResponse)
    def get_period_signals_index(
        *, kind: Literal["week", "month"] | None = Query(default=None),
    ) -> PeriodSignalsIndexResponse:
        try:
            deps.create_all()
            with deps.SessionLocal() as session:
                repo = PeriodSignalRepo(
                    session, comparable_from=get_settings().daily_signals_comparable_from)
                rows = repo.index(kind)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc
        return PeriodSignalsIndexResponse(periods=[PeriodSignalsIndexItem(
            period_kind=r.period_kind, period_start=r.period_start, period_end=r.period_end,
            status=r.status, computed_at=r.updated_at) for r in rows])

    return router
