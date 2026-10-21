"""Weekly analytics API: report read/publish, report list and data freshness."""

import re
from datetime import UTC, date, datetime, time, timedelta
from html import unescape
from typing import cast

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.storage.models_sql import Article, FetchRun
from app.storage.repos import (
    WeeklyAnalyticsItem,
    WeeklyAnalyticsRepo,
    WeeklyAnalyticsReport,
    WeeklyAnalyticsReportIndexEntry,
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
from app.web.routes.common import (
    _OPTIONAL_WEEKLY_ANALYTICS_DATE_QUERY,
    _resolve_weekly_default_report_date,
)

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
            with deps.SessionLocal() as session:
                repo = WeeklyAnalyticsRepo(session)
                report_date = target_date or _resolve_weekly_default_report_date(
                    repo=repo,
                    today=datetime.now(UTC).date(),
                )
                weekly_report = repo.get_weekly_report(
                    report_date=report_date
                )
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return _build_weekly_analytics_response(
            report_date=report_date,
            weekly_report=weekly_report,
        )

    @router.post("/api/news/weekly-analytics", response_model=WeeklyAnalyticsResponse,
                 response_model_exclude_unset=True)
    def save_weekly_ai_analytics(payload: WeeklyAnalyticsPayload) -> WeeklyAnalyticsResponse:
        try:
            deps.create_all()
            with deps.SessionLocal() as session:
                repo = WeeklyAnalyticsRepo(session)
                repo.save_weekly_report(
                    report_date=payload.report_date,
                    date_from=payload.date_from,
                    date_to=payload.date_to,
                    summary=payload.summary,
                    new=[
                        {
                            "title": item.title,
                            "summary": item.summary,
                            "url": str(item.url),
                        }
                        for item in payload.new
                    ],
                    trending_up=[
                        {
                            "title": item.title,
                            "summary": item.summary,
                            "url": str(item.url),
                        }
                        for item in payload.trending_up
                    ],
                    trending_down=[
                        {
                            "title": item.title,
                            "summary": item.summary,
                            "url": str(item.url),
                        }
                        for item in payload.trending_down
                    ],
                )
                session.commit()
                stored = repo.get_weekly_report(report_date=payload.report_date)
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
            with deps.SessionLocal() as session:
                items = WeeklyAnalyticsRepo(session).list_stored_reports(limit=limit)
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
            with deps.SessionLocal() as session:
                repo = WeeklyAnalyticsRepo(session)
                report_date = target_date or _resolve_weekly_default_report_date(
                    repo=repo,
                    today=datetime.now(UTC).date(),
                )
                date_from = report_date - timedelta(days=6)
                date_to = report_date
                start_at = datetime.combine(date_from, time.min, tzinfo=UTC)
                end_at = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
                article_count = (
                    session.query(Article.id)
                    .where(Article.published_at >= start_at)
                    .where(Article.published_at < end_at)
                    .count()
                )
                latest_fetch_run = session.execute(
                    select(FetchRun).order_by(FetchRun.started_at.desc()).limit(1)
                ).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        if latest_fetch_run is None:
            return WeeklyAnalyticsFreshnessResponse(
                report_date=report_date,
                date_from=date_from,
                date_to=date_to,
                article_count=cast(int, article_count),
            )

        return WeeklyAnalyticsFreshnessResponse(
            report_date=report_date,
            date_from=date_from,
            date_to=date_to,
            article_count=cast(int, article_count),
            latest_fetch_run_id=latest_fetch_run.run_id,
            latest_fetch_status=latest_fetch_run.status,
            latest_fetch_started_at=latest_fetch_run.started_at,
            latest_fetch_finished_at=latest_fetch_run.finished_at,
            latest_fetch_fetched=latest_fetch_run.fetched_count,
            latest_fetch_new=latest_fetch_run.new_count,
            latest_fetch_duplicates=latest_fetch_run.duplicate_count,
            latest_fetch_errors=latest_fetch_run.error_count,
        )

    return router
