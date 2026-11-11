"""Stored weekly analytics of the web API: read, save, list and data freshness."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.storage.models_sql import Article, FetchRun
from app.storage.repos import (
    WeeklyAnalyticsItem,
    WeeklyAnalyticsRepo,
    WeeklyAnalyticsReport,
    WeeklyAnalyticsReportIndexEntry,
)

__all__ = ["WeeklyAnalyticsItem", "WeeklyAnalyticsReport", "WeeklyAnalyticsReportIndexEntry"]


@dataclass(frozen=True, slots=True)
class WeeklyFreshness:
    report_date: date
    date_from: date
    date_to: date
    article_count: int
    latest_fetch_run: FetchRun | None


def default_report_date(*, repo: object, today: date) -> date:
    """The latest stored report date; yesterday when none is stored or the read fails."""
    get_latest = getattr(repo, "get_latest_report_date", None)
    if callable(get_latest):
        try:
            latest_published = get_latest()
        except SQLAlchemyError:
            latest_published = None
        if latest_published is not None:
            return cast(date, latest_published)
    return today - timedelta(days=1)


def read_weekly_report(session_factory: Callable[[], Session], target_date: date | None,
                  today: date) -> tuple[date, WeeklyAnalyticsReport]:
    """(report date, report) of `target_date` or of the default date."""
    with session_factory() as session:
        repo = WeeklyAnalyticsRepo(session)
        report_date = target_date or default_report_date(repo=repo, today=today)
        return report_date, repo.get_weekly_report(report_date=report_date)


def save_weekly_report(session_factory: Callable[[], Session], **report: Any
                       ) -> WeeklyAnalyticsReport:
    """Stores a report, commits, and returns it as stored."""
    with session_factory() as session:
        repo = WeeklyAnalyticsRepo(session)
        repo.save_weekly_report(**report)
        session.commit()
        return repo.get_weekly_report(report_date=report["report_date"])


def stored_reports(session_factory: Callable[[], Session], limit: int
                   ) -> list[WeeklyAnalyticsReportIndexEntry]:
    """Stored reports, newest first."""
    with session_factory() as session:
        reports: list[WeeklyAnalyticsReportIndexEntry] = WeeklyAnalyticsRepo(
            session).list_stored_reports(limit=limit)
        return reports


def weekly_freshness(session_factory: Callable[[], Session], target_date: date | None,
                     today: date) -> WeeklyFreshness:
    """Article count of the report week and the latest fetch run."""
    with session_factory() as session:
        repo = WeeklyAnalyticsRepo(session)
        report_date = target_date or default_report_date(repo=repo, today=today)
        date_from = report_date - timedelta(days=6)
        start_at = datetime.combine(date_from, time.min, tzinfo=UTC)
        end_at = datetime.combine(report_date + timedelta(days=1), time.min, tzinfo=UTC)
        article_count = (
            session.query(Article.id)
            .where(Article.published_at >= start_at)
            .where(Article.published_at < end_at)
            .count()
        )
        latest_fetch_run = session.execute(
            select(FetchRun).order_by(FetchRun.started_at.desc()).limit(1)
        ).scalar_one_or_none()
        return WeeklyFreshness(report_date=report_date, date_from=date_from,
                               date_to=report_date, article_count=cast(int, article_count),
                               latest_fetch_run=latest_fetch_run)
