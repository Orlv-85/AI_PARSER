"""The writer's model call: journal of the real UTC day, client and `ask` (spec 018, item 3).

Behavior, decisions and tests: src/app/core/bulletin/writer.md. The pure part is writer.py.
"""
import json
import math
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from app.core.bulletin.writer import WRITER_VERSION
from app.core.daily.signals_brief import request_key
from app.core.provider_costs import PRICES, microdollars
from app.storage.provider_journal import PilotJournal, PilotStopped, TransportAttemptsExhausted

WRITER_MAX_USD_PER_DAY = "0.10"  # FR-012
WRITER_JOURNAL_VERSION = "bulletin-writer-1"
WRITER_ROOT = Path("data/bulletin/writer")
WRITER_TIMEOUT_SECONDS = 120.0
TRANSPORT_REVIEW_REASON = "bulletin-writer: transport failure, conservative reservation kept"
TRANSPORT_RETRY_DELAYS = (10,)
RUN_LIMIT_REASON = "run_limit"
OUTAGE_REASON = "provider_outage"
FAILED_REASON = "provider_failed"


def _key(_provider: str, body: dict[str, Any]) -> str:
    return str(request_key(body, WRITER_VERSION))


def _reservation(_provider: str, body: dict[str, Any]) -> int:
    """Microdollars: the request bytes as input tokens plus every allowed output token."""
    size = len(json.dumps(body, ensure_ascii=False).encode())
    price = PRICES["deepseek"]
    return int(math.ceil(size * price["input"] + body["max_tokens"] * price["output"]))


class Writer:
    """`ask` for `write_bulletin`: one capped, journaled request; failures return a reason."""

    def __init__(self, journal: PilotJournal, client: httpx.Client, secret: str,
                 limit_micro: int | None) -> None:
        self.journal = journal
        self.client = client
        self.secret = secret
        self.limit_micro = limit_micro

    def _check_limit(self, body: dict[str, Any]) -> None:
        committed = round(self.journal.committed_usd() * 1e6)
        if self.limit_micro is not None and committed + _reservation("deepseek", body) \
                > self.limit_micro:
            raise PilotStopped(RUN_LIMIT_REASON)

    def ask(self, body: dict[str, Any]) -> tuple[Any, str | None]:
        """(provider answer, None) or (None, reason); never raises for a provider fault."""
        try:
            data = self.journal.call("deepseek", body, self.client, self.secret,
                                     before_dispatch=lambda: self._check_limit(body))
            return data, None
        except PilotStopped as error:
            return None, str(error) or "stopped"
        except TransportAttemptsExhausted:
            return None, OUTAGE_REASON
        except (sqlite3.Error, httpx.HTTPError, ValueError, RuntimeError):
            return None, FAILED_REASON

    def report(self) -> dict[str, Any]:
        report: dict[str, Any] = self.journal.report()
        return report

    def cost_usd(self) -> float:
        return float(self.report()["providers"]["deepseek"]["usage_priced_usd"])


@contextmanager
def open_writer(settings: Any, today: date, *, max_usd: float | None = None,
                root: Path = WRITER_ROOT, transport: httpx.BaseTransport | None = None
                ) -> Iterator[Writer]:
    """Writer on the journal of the real UTC day `today` with the fixed daily cap.

    One file per real day, whatever `--date` a run builds. `max_usd` only lowers the cap of this
    run; above the daily cap it raises ValueError("max_usd_above_cap")."""
    key = getattr(settings, "ds_api_key", None)
    secret = key.get_secret_value().strip() if key is not None else ""
    if not secret:
        raise ValueError("missing_provider_key")
    cap = microdollars(WRITER_MAX_USD_PER_DAY)
    limit = None if max_usd is None else round(max_usd * 1e6)
    if limit is not None and limit > cap:
        raise ValueError("max_usd_above_cap")
    folder = root / today.isoformat()
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    # The journal needs three caps; Jev is never called here, so it gets the smallest.
    caps = {"total": str((cap + 1) / 1e6), "jev": "0.000001", "deepseek": str(cap / 1e6)}
    journal = PilotJournal(
        folder / f"journal-{WRITER_JOURNAL_VERSION}.sqlite3",
        {"version": WRITER_JOURNAL_VERSION, "day": today.isoformat()}, caps,
        key_function=_key, reservation_function=_reservation,
        transport_review_reason=TRANSPORT_REVIEW_REASON,
        transport_retry_delays=TRANSPORT_RETRY_DELAYS)
    try:
        with httpx.Client(timeout=WRITER_TIMEOUT_SECONDS, transport=transport) as client:
            yield Writer(journal, client, secret, limit)
    finally:
        journal.close()
