"""Weekly hook of the fetch cycle (legacy Monday report only)."""
from datetime import UTC, date, datetime, timedelta
from logging import Logger
from typing import Any, cast

from app.storage.repos import WeeklyAnalyticsRepo


def _weekly_report_date_to_publish(today: date) -> date | None:
    if today.weekday() != 0:
        return None
    return today - timedelta(days=1)


def _publish_weekly_analytics_if_due(
    *,
    session: object,
    logger: Logger,
    run_id: str,
) -> None:
    report_date = _weekly_report_date_to_publish(datetime.now(UTC).date())
    if report_date is None:
        return

    try:
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

