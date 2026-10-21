"""Helpers shared by several web routers: stored daily signals and the weekly default date."""

import json
import logging
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any, cast

from fastapi import Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.storage.daily_signals import DailySignalRepo
from app.storage.repos import WeeklyAnalyticsRepo
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
    with session_local() as session:
        repo = DailySignalRepo(session,
                               comparable_from=get_settings().daily_signals_comparable_from)
        row = repo.get_report(report_date)
        payload = row.payload if row is not None else None
        brief = _daily_signal_brief(report_date=report_date, row=repo.get_brief(report_date)) \
            if row is not None else None
    response = _daily_signals_response(report_date=report_date, payload=payload)
    if response.status != "unavailable":
        response.brief = brief
    return response


def _resolve_weekly_default_report_date(*, repo: WeeklyAnalyticsRepo, today: date) -> date:
    get_latest = getattr(repo, "get_latest_report_date", None)
    if callable(get_latest):
        try:
            latest_published = get_latest()
        except SQLAlchemyError:
            latest_published = None
        if latest_published is not None:
            return cast(date, latest_published)
    return today - timedelta(days=1)
