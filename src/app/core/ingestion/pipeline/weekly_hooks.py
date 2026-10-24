"""Weekly coverage hooks of the fetch cycle (weekly v2, deferred; moved as is)."""
from datetime import UTC, date, datetime, timedelta
from logging import Logger
from typing import Any, cast

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.storage.article_repo import ArticleRepo
from app.storage.repos import WeeklyAnalyticsRepo
from app.storage.weekly import WeeklyStore, record_observation


def _weekly_report_date_to_publish(today: date) -> date | None:
    if today.weekday() != 0:
        return None
    return today - timedelta(days=1)


def _publish_weekly_analytics_if_due(
    *,
    session: object,
    logger: Logger,
    run_id: str,
    settings: Settings,
) -> None:
    report_date = _weekly_report_date_to_publish(datetime.now(UTC).date())
    if report_date is None:
        return

    try:
        if settings.weekly_v2_enabled:
            WeeklyStore(cast(Any, session)).enqueue(report_date, settings)
        else:
            WeeklyAnalyticsRepo(cast(Any, session)).save_weekly_report(report_date=report_date)
    except Exception as exc:  # pragma: no cover - defensive logging path
        logger.error(
            "weekly_analytics_publish_failed",
            {
                "run_id": run_id,
                "report_date": report_date.isoformat(),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )
        return

    logger.info(
        "weekly_analytics_published",
        {
            "run_id": run_id,
            "report_date": report_date.isoformat(),
        },
    )


def _record_weekly_observation(article_repo: ArticleRepo, source_id: int, item: Any) -> None:
    if isinstance(article_repo.session, Session):
        record_observation(article_repo.session, source_id, item)
