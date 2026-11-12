"""Weekly analytics API: report read/publish, report list and data freshness."""

import re
from datetime import UTC, date, datetime, timedelta
from html import unescape

from fastapi import APIRouter, Query

from app.usecases.weekly_analytics import (
    WeeklyAnalyticsItem,
    WeeklyAnalyticsReport,
    WeeklyAnalyticsReportIndexEntry,
    WeeklyDraft,
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
from app.web.routes.common import _OPTIONAL_WEEKLY_ANALYTICS_DATE_QUERY, _http_errors

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

    return WeeklyAnalyticsResponse(
        report_date=weekly_report.report_date,
        date_from=weekly_report.date_from,
        date_to=weekly_report.date_to,
        summary=weekly_report.summary,
        new=_item_payloads(weekly_report.new),
        trending_up=_item_payloads(weekly_report.trending_up),
        trending_down=_item_payloads(weekly_report.trending_down),
        **{"status": "legacy", **getattr(weekly_report, "metadata", {})},
    )


def _item_payloads(items: list[WeeklyAnalyticsItem]) -> list[WeeklyAnalyticsItemPayload]:
    """Items with an http(s) URL and a non-empty plain-text title and summary."""
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


def _report_response(deps: WebDeps, target_date: date | None) -> WeeklyAnalyticsResponse:
    with _http_errors():
        deps.create_all()
        report_date, report = read_weekly_report(
            deps.SessionLocal, target_date, datetime.now(UTC).date())
    return _build_weekly_analytics_response(report_date=report_date, weekly_report=report)


def _save_response(deps: WebDeps, payload: WeeklyAnalyticsPayload) -> WeeklyAnalyticsResponse:
    with _http_errors(409):
        deps.create_all()
        stored = save_weekly_report(
            deps.SessionLocal,
            payload.report_date,
            WeeklyDraft(
                date_from=payload.date_from,
                date_to=payload.date_to,
                summary=payload.summary,
                new=_items(payload.new),
                trending_up=_items(payload.trending_up),
                trending_down=_items(payload.trending_down),
            ),
        )
    return _build_weekly_analytics_response(report_date=payload.report_date,
                                            weekly_report=stored)


def _report_list_response(deps: WebDeps, limit: int) -> WeeklyAnalyticsReportListResponse:
    with _http_errors():
        deps.create_all()
        items = stored_reports(deps.SessionLocal, limit)
    return _build_weekly_report_list_response(items=items)


def _freshness_response(deps: WebDeps,
                        target_date: date | None) -> WeeklyAnalyticsFreshnessResponse:
    with _http_errors():
        deps.create_all()
        fresh = weekly_freshness(deps.SessionLocal, target_date, datetime.now(UTC).date())

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


def build_weekly_router(deps: WebDeps) -> APIRouter:
    router = APIRouter()

    @router.get("/api/news/weekly-analytics", response_model=WeeklyAnalyticsResponse,
                response_model_exclude_unset=True)
    def get_weekly_ai_analytics(
        *,
        target_date: date | None = _OPTIONAL_WEEKLY_ANALYTICS_DATE_QUERY,
    ) -> WeeklyAnalyticsResponse:
        return _report_response(deps, target_date)

    @router.post("/api/news/weekly-analytics", response_model=WeeklyAnalyticsResponse,
                 response_model_exclude_unset=True)
    def save_weekly_ai_analytics(payload: WeeklyAnalyticsPayload) -> WeeklyAnalyticsResponse:
        return _save_response(deps, payload)

    @router.get(
        "/api/news/weekly-analytics/reports",
        response_model=WeeklyAnalyticsReportListResponse,
    )
    def list_weekly_ai_analytics_reports(
        *,
        limit: int = Query(52, ge=1, le=260),
    ) -> WeeklyAnalyticsReportListResponse:
        return _report_list_response(deps, limit)

    @router.get(
        "/api/news/weekly-analytics/freshness",
        response_model=WeeklyAnalyticsFreshnessResponse,
    )
    def get_weekly_ai_analytics_freshness(
        *,
        target_date: date | None = _OPTIONAL_WEEKLY_ANALYTICS_DATE_QUERY,
    ) -> WeeklyAnalyticsFreshnessResponse:
        return _freshness_response(deps, target_date)

    return router
