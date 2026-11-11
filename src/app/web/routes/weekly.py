"""Weekly analytics API: report read/publish, report list and data freshness."""

import re
from datetime import UTC, date, datetime, timedelta
from html import unescape

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from app.usecases.weekly_analytics import (
    WeeklyAnalyticsItem,
    WeeklyAnalyticsReport,
    WeeklyAnalyticsReportIndexEntry,
    read_weekly_report,
    save_weekly_report,
    stored_reports,
    weekly_freshness,
)
from app.web.models import (
    WeeklyAnalyticsFreshnessResponse,
    WeeklyAnalyticsItemPayload,
    WeeklyAnalyticsPayload,
    WeeklyAnalyticsReportListItem,
    WeeklyAnalyticsReportListResponse,
    WeeklyAnalyticsResponse,
)
from app.web.routes import WebDeps
from app.web.routes.common import _OPTIONAL_WEEKLY_ANALYTICS_DATE_QUERY

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _build_weekly_analytics_response(
    *,
    report_date: date,
    weekly_report: WeeklyAnalyticsReport | None,
) -> WeeklyAnalyticsResponse:
    if weekly_report is None:
        date_to = report_date
        date_from = report_date - timedelta(days=6)
        return WeeklyAnalyticsResponse(
            report_date=report_date,
            date_from=date_from,
            date_to=date_to,
            summary="No AI news signals for this week.",
            new=[],
            trending_up=[],
            trending_down=[],
        )

    def _serialize_items(items: list[WeeklyAnalyticsItem]) -> list[WeeklyAnalyticsItemPayload]:
        payload: list[WeeklyAnalyticsItemPayload] = []
        for item in items:
            if not item.url.startswith(("http://", "https://")):
                continue
            title = _plain_text(item.title, max_length=255)
            summary = _plain_text(item.summary, max_length=2000)
            if not title or not summary:
                continue
            payload.append(
                WeeklyAnalyticsItemPayload(
                    title=title,
                    summary=summary,
                    url=item.url,
                    **getattr(item, "details", {}),
                )
            )
        return payload

    return WeeklyAnalyticsResponse(
        report_date=weekly_report.report_date,
        date_from=weekly_report.date_from,
        date_to=weekly_report.date_to,
        summary=weekly_report.summary,
        new=_serialize_items(weekly_report.new),
        trending_up=_serialize_items(weekly_report.trending_up),
        trending_down=_serialize_items(weekly_report.trending_down),
        **{"status": "legacy", **getattr(weekly_report, "metadata", {})},
    )


def _plain_text(value: str, *, max_length: int) -> str:
    text = _HTML_TAG_RE.sub(" ", unescape(value))
    return " ".join(text.split())[:max_length]


def _build_weekly_report_list_response(
    *,
    items: list[WeeklyAnalyticsReportIndexEntry],
) -> WeeklyAnalyticsReportListResponse:
    return WeeklyAnalyticsReportListResponse(
        items=[
            WeeklyAnalyticsReportListItem(
                report_date=item.report_date,
                date_from=item.date_from,
                date_to=item.date_to,
                summary=item.summary,
                created_at=item.created_at,
            )
            for item in items
        ]
    )


def _items(items: list[WeeklyAnalyticsItemPayload]) -> list[dict[str, str]]:
    return [{"title": item.title, "summary": item.summary, "url": str(item.url)}
            for item in items]


def build_weekly_router(deps: WebDeps) -> APIRouter:
    router = APIRouter()

    @router.get("/api/news/weekly-analytics", response_model=WeeklyAnalyticsResponse,
                response_model_exclude_unset=True)
    def get_weekly_ai_analytics(
        *,
        target_date: date | None = _OPTIONAL_WEEKLY_ANALYTICS_DATE_QUERY,
    ) -> WeeklyAnalyticsResponse:
        try:
            deps.create_all()
            report_date, report = read_weekly_report(
                deps.SessionLocal, target_date, datetime.now(UTC).date())
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return _build_weekly_analytics_response(
            report_date=report_date,
            weekly_report=report,
        )

    @router.post("/api/news/weekly-analytics", response_model=WeeklyAnalyticsResponse,
                 response_model_exclude_unset=True)
    def save_weekly_ai_analytics(payload: WeeklyAnalyticsPayload) -> WeeklyAnalyticsResponse:
        try:
            deps.create_all()
            stored = save_weekly_report(
                deps.SessionLocal,
                report_date=payload.report_date,
                date_from=payload.date_from,
                date_to=payload.date_to,
                summary=payload.summary,
                new=_items(payload.new),
                trending_up=_items(payload.trending_up),
                trending_down=_items(payload.trending_down),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return _build_weekly_analytics_response(
            report_date=payload.report_date,
            weekly_report=stored,
        )

    @router.get(
        "/api/news/weekly-analytics/reports",
        response_model=WeeklyAnalyticsReportListResponse,
    )
    def list_weekly_ai_analytics_reports(
        *,
        limit: int = Query(52, ge=1, le=260),
    ) -> WeeklyAnalyticsReportListResponse:
        try:
            deps.create_all()
            items = stored_reports(deps.SessionLocal, limit)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc
        return _build_weekly_report_list_response(items=items)

    @router.get(
        "/api/news/weekly-analytics/freshness",
        response_model=WeeklyAnalyticsFreshnessResponse,
    )
    def get_weekly_ai_analytics_freshness(
        *,
        target_date: date | None = _OPTIONAL_WEEKLY_ANALYTICS_DATE_QUERY,
    ) -> WeeklyAnalyticsFreshnessResponse:
        try:
            deps.create_all()
            fresh = weekly_freshness(deps.SessionLocal, target_date, datetime.now(UTC).date())
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        run = fresh.latest_fetch_run
        dates = {"report_date": fresh.report_date, "date_from": fresh.date_from,
                 "date_to": fresh.date_to, "article_count": fresh.article_count}
        if run is None:
            return WeeklyAnalyticsFreshnessResponse(**dates)

        return WeeklyAnalyticsFreshnessResponse(
            **dates,
            latest_fetch_run_id=run.run_id,
            latest_fetch_status=run.status,
            latest_fetch_started_at=run.started_at,
            latest_fetch_finished_at=run.finished_at,
            latest_fetch_fetched=run.fetched_count,
            latest_fetch_new=run.new_count,
            latest_fetch_duplicates=run.duplicate_count,
            latest_fetch_errors=run.error_count,
        )

    return router
