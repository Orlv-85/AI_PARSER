"""Opens the world change assessor with its own capped payment journal.

Behavior: src/app/core/bulletin/world_change.md.
"""
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from logging import Logger
from pathlib import Path

import httpx

from app.core.bulletin.world_change import (
    ASSESS_TIMEOUT_SECONDS,
    TRANSPORT_RETRY_DELAYS,
    TRANSPORT_REVIEW_REASON,
    WORLD_CHANGE_VERSION,
    WorldChangeAssessor,
)
from app.core.provider_costs import microdollars
from app.storage.provider_journal import PilotJournal


@contextmanager
def open_assessor(settings, logger: Logger, target: date, max_usd: str, *,
                  root: Path | None = None, version: str = WORLD_CHANGE_VERSION,
                  usage_event: str = "bulletin_assess_usage",
                  file_name: str | None = None) -> Iterator[WorldChangeAssessor]:
    """Assessor with its own capped journal in data/bulletin/<day>/ (one file per cap).

    The world stream passes its own `root`, journal `version`, `usage_event` and `file_name`.
    """
    api_key = getattr(settings, "jev_api_key", None)
    secret = api_key.get_secret_value().strip() if api_key is not None else ""
    if not secret:
        raise ValueError("missing_provider_key")
    cap = microdollars(max_usd)
    root = root or Path("data/bulletin") / target.isoformat()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    # The journal needs three caps; DeepSeek is never called here, so it gets the smallest.
    caps = {"total": str((cap + 1) / 1e6), "jev": str(cap / 1e6), "deepseek": "0.000001"}
    journal = PilotJournal(root / (file_name or f"journal-{version}-{cap}.sqlite3"),
                         {"version": version, "day": target.isoformat()}, caps,
                         transport_review_reason=TRANSPORT_REVIEW_REASON,
                         transport_retry_delays=TRANSPORT_RETRY_DELAYS)
    try:
        with httpx.Client(timeout=ASSESS_TIMEOUT_SECONDS) as client:
            yield WorldChangeAssessor(client, settings.jev_model, logger,
                                      payment_journal=journal, secret=secret)
    finally:
        logger.info(usage_event, journal.report())
        journal.close()
