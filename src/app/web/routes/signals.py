"""Daily API: digest publish/read, daily signals and daily article stats."""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from app.storage.models_sql import NewsDigestReport
from app.usecases.digest import save_digest, stored_digest
from app.usecases.news_reads import ArticleDailyStats, daily_stats
from app.web.models import (
    DailySignalsResponse,
    NewsDailyStatsItem,
    NewsDailyStatsResponse,
    NewsDigestGroupPayload,
    NewsDigestItemPayload,
    NewsDigestPayload,
    NewsDigestResponse,
)
from app.web.routes import WebDeps
from app.web.routes.common import _read_daily_signals

_NEWS_DIGEST_DATE_QUERY = Query(alias="date")


def _build_digest_response(
    *,
    report_date: date,
    digest: NewsDigestReport | None,
) -> NewsDigestResponse:
    if digest is None:
        return NewsDigestResponse(report_date=report_date, groups=[])

    return NewsDigestResponse(
        report_date=report_date,
        groups=[
            NewsDigestGroupPayload(
                title=group.title,
                items=[
                    NewsDigestItemPayload(
                        title=item.title,
                        summary=item.summary,
                        url=item.url,
                    )
                    for item in group.items
                ],
            )
            for group in digest.groups
        ],
    )


def _build_news_daily_stats_response(
    *,
    date_from: date,
    date_to: date,
    stats: list[ArticleDailyStats],
) -> NewsDailyStatsResponse:
    return NewsDailyStatsResponse(
        date_from=date_from,
        date_to=date_to,
        items=[
            NewsDailyStatsItem(
                stat_date=item.stat_date,
                published_count=item.published_count,
                discovered_count=item.discovered_count,
                fetch_run_count=item.fetch_run_count,
                fetched_count=item.fetched_count,
                new_count=item.new_count,
                duplicate_count=item.duplicate_count,
                error_count=item.error_count,
            )
            for item in stats
        ],
    )


def build_signals_router(deps: WebDeps) -> APIRouter:
    router = APIRouter()

    @router.post("/api/news/digests", response_model=NewsDigestResponse)
    def save_news_digest(payload: NewsDigestPayload) -> NewsDigestResponse:
        try:
            deps.create_all()
            stored = save_digest(
                deps.SessionLocal,
                payload.report_date,
                [
                    {
                        "title": group.title,
                        "items": [
                            {
                                "title": item.title,
                                "summary": item.summary,
                                "url": item.url,
                            }
                            for item in group.items
                        ],
                    }
                    for group in payload.groups
                ],
            )
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return _build_digest_response(report_date=payload.report_date, digest=stored)

    @router.get("/api/news/digests", response_model=NewsDigestResponse)
    def get_news_digest(*, target_date: date = _NEWS_DIGEST_DATE_QUERY) -> NewsDigestResponse:
        try:
            deps.create_all()
            digest = stored_digest(deps.SessionLocal, target_date)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return _build_digest_response(report_date=target_date, digest=digest)

    @router.get("/api/news/daily-signals", response_model=DailySignalsResponse)
    def get_daily_signals(*, target_date: date = _NEWS_DIGEST_DATE_QUERY) -> DailySignalsResponse:
        try:
            deps.create_all()
            return _read_daily_signals(target_date, session_local=deps.SessionLocal)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

    @router.get("/api/news/stats/daily", response_model=NewsDailyStatsResponse)
    def get_news_daily_stats(
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        days: int = Query(60, ge=1, le=365),
    ) -> NewsDailyStatsResponse:
        resolved_date_to = date_to or (datetime.now(UTC).date() - timedelta(days=1))
        resolved_date_from = date_from or (resolved_date_to - timedelta(days=days - 1))
        if resolved_date_from > resolved_date_to:
            raise HTTPException(status_code=422, detail="date_from must be <= date_to")
        try:
            deps.create_all()
            response = _build_news_daily_stats_response(
                date_from=resolved_date_from,
                date_to=resolved_date_to,
                stats=daily_stats(deps.SessionLocal, resolved_date_from, resolved_date_to),
            )
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc
        return response

    return router
