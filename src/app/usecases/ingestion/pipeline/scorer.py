"""Opens the Jev relevance scorer of one fetch cycle, with the daily admission journal.

Flow and code map: src/app/usecases/ingestion/pipeline.md.
"""
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from logging import Logger
from pathlib import Path

import httpx

from app.config.settings import Settings
from app.core.jev import (
    ADMISSION_TRANSPORT_RETRY_DELAYS,
    ADMISSION_TRANSPORT_REVIEW_REASON,
    JevRelevanceScorer,
    ScorerConfig,
)
from app.storage.provider_journal import JournalPolicy, PilotJournal


@contextmanager
def jev_relevance_scorer(
    settings: Settings, logger: Logger,
) -> Iterator[JevRelevanceScorer | None]:
    if not getattr(settings, "jev_enabled", False):
        yield None
        return
    api_key = getattr(settings, "jev_api_key", None)
    if api_key is None or not api_key.get_secret_value().strip():
        logger.error("jev_relevance_fallback", {"error_type": "MissingApiKey"})
        yield None
        return
    with httpx.Client(
        timeout=settings.jev_timeout_seconds,
        headers={"Authorization": "Bearer " + api_key.get_secret_value().strip()},
    ) as client:
        daily = bool(getattr(settings, "daily_enrichment_enabled", False))
        journal = None
        if daily:
            root = Path("data/daily-admission") / datetime.now(UTC).date().isoformat()
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            journal = PilotJournal(root / "journal.sqlite3", {"version": "daily-admission-1"},
                                   {"total": "2", "jev": "1", "deepseek": "1"},
                                   JournalPolicy(
                                       transport_review_reason=ADMISSION_TRANSPORT_REVIEW_REASON,
                                       transport_retry_delays=ADMISSION_TRANSPORT_RETRY_DELAYS))
        try:
            yield JevRelevanceScorer(
                client,
                logger,
                ScorerConfig(
                    settings.jev_model,
                    category_min_confidence=settings.jev_category_min_confidence,
                    semantic_admission_enabled=bool(
                        getattr(settings, "semantic_admission_enabled", False)),
                    daily_enrichment_enabled=daily,
                ),
                payment_journal=journal,
            )
        finally:
            if journal is not None:
                logger.info("daily_admission_usage", journal.report())
                journal.close()
