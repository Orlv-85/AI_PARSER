"""Period AI Signals API (017): stored weekly/monthly signals; never calls a provider."""

import json
import logging
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.config.settings import get_settings
from app.storage.models_sql import PeriodSignalBrief, PeriodSignalReport
from app.storage.period_signals import PeriodSignalRepo
from app.web.models import (
    DailySignalBrief,
    PeriodSignalsIndexItem,
    PeriodSignalsIndexResponse,
    PeriodSignalsResponse,
)
from app.web.period_view import (
    NOT_FOR_WEEK,
    NOT_YET,
    render_content,
    render_page,
    render_picker,
)
from app.web.routes import WebDeps

_LOGGER = logging.getLogger(__name__)
# A default read shows the newest period that carries comparable numbers, else any stored one.
_SHOWN = ("ready", "building_history")


def _unavailable(kind: str, start: date | None, note: str | None = None) -> PeriodSignalsResponse:
    return PeriodSignalsResponse(period_kind=kind, period_start=start, status="unavailable",
                                 notes=[note] if note else [])


def _brief(row: PeriodSignalBrief | None) -> DailySignalBrief | None:
    """The stored `ok` brief as the API model; missing, invalid or unreadable -> None."""
    if row is None or row.status != "ok":
        return None
    try:
        data = json.loads(row.payload)
        return DailySignalBrief(sentences=data["sentences"], model=row.model,
                                brief_version=row.brief_version, generated_at=row.updated_at)
    except (ValueError, TypeError, KeyError) as exc:
        _LOGGER.error("period_brief_unreadable kind=%s start=%s error=%s",
                      row.period_kind, row.period_start.isoformat(), type(exc).__name__)
        return None


def _response(kind: str, start: date | None, row: PeriodSignalReport | None,
              brief: PeriodSignalBrief | None = None) -> PeriodSignalsResponse:
    """Stored row as the API model; missing or unreadable -> `unavailable` (never an error)."""
    if row is None:
        return _unavailable(kind, start)
    try:
        response = PeriodSignalsResponse.model_validate(json.loads(row.payload))
    except (ValueError, TypeError, ValidationError) as exc:
        _LOGGER.error("period_signals_payload_unreadable kind=%s start=%s error=%s", kind,
                      row.period_start.isoformat(), type(exc).__name__)
        return _unavailable(kind, row.period_start, "Period signals could not be read.")
    response.brief = _brief(brief)
    return response


def latest_week(deps: WebDeps) -> tuple[date, date] | None:
    """Start and end of the week `/weekly` shows by default; None when no week is stored or the
    read fails (the nav link and the line on `/` then stay hidden)."""
    try:
        deps.create_all()
        with deps.SessionLocal() as session:
            rows = PeriodSignalRepo(
                session, comparable_from=get_settings().daily_signals_comparable_from
            ).index("week")
    except Exception as exc:  # any failure: the caller's page stays up
        _LOGGER.error("period_signals_latest_failed error=%s", type(exc).__name__)
        return None
    shown = next((r for r in rows if r.status in _SHOWN), rows[0] if rows else None)
    return (shown.period_start, shown.period_end) if shown is not None else None


def build_period_router(deps: WebDeps) -> APIRouter:
    router = APIRouter()

    @router.get("/weekly", response_class=HTMLResponse)
    def weekly_page(week: str | None = None) -> Response:
        """Stored week as HTML (no provider, no compute). `?week=` is a Monday; another day
        redirects to its Monday; text that is not a date gives the unavailable page."""
        start: date | None = None
        if week is not None:
            try:
                start = date.fromisoformat(week)
            except ValueError:
                start = None
            if start is not None and start.weekday() != 0:
                monday = start - timedelta(days=start.weekday())
                return RedirectResponse(url=f"/weekly?week={monday.isoformat()}", status_code=303)
        weeks: list[tuple[date, date, str]] = []
        signals = None
        note = NOT_FOR_WEEK if week is not None else NOT_YET
        try:
            deps.create_all()
            with deps.SessionLocal() as session:
                repo = PeriodSignalRepo(
                    session, comparable_from=get_settings().daily_signals_comparable_from)
                weeks = [(r.period_start, r.period_end, r.status) for r in repo.index("week")]
                if week is None:
                    row = repo.latest("week", _SHOWN) or repo.latest("week")
                elif start is not None:
                    row = repo.get_report("week", start)
                else:
                    row = None
                signals = _response("week", start, row, repo.get_brief("week", row.period_start)
                                    ) if row is not None else None
        except Exception as exc:  # unavailable page, never a 500 (plan: Web)
            _LOGGER.error("period_signals_page_failed error=%s", type(exc).__name__)
            weeks, signals, note = [], None, "Weekly signals are temporarily unavailable."
        current = signals.period_start if signals is not None else None
        return HTMLResponse(render_page(render_content(signals, note=note),
                                        render_picker(weeks, current)))

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
                return _response(kind, start, row, repo.get_brief(kind, row.period_start)
                                 if row is not None else None)
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
