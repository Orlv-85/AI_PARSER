"""Helpers shared by several web routers: stored daily signals and the weekly default date."""

import json
import logging
from collections.abc import Callable
from datetime import date
from typing import Any

from fastapi import Query
from sqlalchemy.orm import Session

from app.usecases.daily.signals_reads import stored_signals
from app.web.models import DailySignalBrief, DailySignalsResponse

_LOGGER = logging.getLogger(__name__)
_OPTIONAL_WEEKLY_ANALYTICS_DATE_QUERY = Query(default=None, alias="date")


def _daily_signals_response(*, report_date: date, payload: str | None) -> DailySignalsResponse:
    """Stored snapshot as the API model; missing or unreadable -> `unavailable`."""
    if payload is None:
        return DailySignalsResponse(report_date=report_date, status="unavailable")
    try:
        return DailySignalsResponse.model_validate(json.loads(payload))
    except (ValueError, TypeError) as exc:
        _LOGGER.error("daily_signals_payload_unreadable report_date=%s error=%s",
                      report_date.isoformat(), type(exc).__name__)
        return DailySignalsResponse(report_date=report_date, status="unavailable",
                                    notes=["Daily signals could not be read."])


def _daily_signal_brief(*, report_date: date, row: Any) -> DailySignalBrief | None:
    """The stored `ok` brief as the API model; missing, invalid or unreadable -> None."""
    if row is None or row.status != "ok":
        return None
    try:
        data = json.loads(row.payload)
        return DailySignalBrief(sentences=data["sentences"], model=row.model,
                                brief_version=row.brief_version, generated_at=row.updated_at)
    except (ValueError, TypeError, KeyError) as exc:
        _LOGGER.error("daily_signals_brief_unreadable report_date=%s error=%s",
                      report_date.isoformat(), type(exc).__name__)
        return None


def _read_daily_signals(
    report_date: date, *, session_local: Callable[[], Session]
) -> DailySignalsResponse:
    """Indexed reads of the stored snapshot and brief; never calls a provider."""
    row, brief_row = stored_signals(session_local, report_date)
    payload = row.payload if row is not None else None
    brief = _daily_signal_brief(report_date=report_date, row=brief_row) \
        if row is not None else None
    response = _daily_signals_response(report_date=report_date, payload=payload)
    if response.status != "unavailable":
        response.brief = brief
    return response

