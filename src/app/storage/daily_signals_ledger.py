"""Physical-call ledger for Daily AI Signals (plan Decision 1, "Signals ledger").

One row per physical POST in a private SQLite file. Saved 200 responses are replayed without a
call. Per-run caps (calls, USD with reservations, app-side deadline) are checked atomically
before every POST. Budget ids, per-day caps, attempt limits and a watchdog are deferred.
"""
import json
import math
import os
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx

from app.core.daily.reenrich_pilot import ENDPOINTS, PRICES
from app.storage.legacy_cleanup import encoded
from app.storage.reenrich_pilot_journal import is_overload

CONNECT_TIMEOUT = httpx.Timeout(connect=10, read=20, write=10, pool=5)
BODY_DEADLINE_SECONDS = 60
PRE_POST_RESERVE_SECONDS = 95
MAX_CONSECUTIVE_FAILURES = 3
FAILURE_STATES = ("unknown", "transient", "error_billed")
# USD per 1M tokens (input, output) = microdollars per token; the extraction model's prices.
DEFAULT_PRICES = (PRICES["deepseek"]["input"], PRICES["deepseek"]["output"])


class LedgerStop(RuntimeError):
    """No further paid requests in this run; `str(error)` is the terminal reason."""


@dataclass(frozen=True)
class Dispatch:
    state: str  # response | error_billed | transient | unknown
    status_code: int | None
    data: Any
    cost_micro: int
    replayed: bool = False


@dataclass(frozen=True)
class LedgerConfig:
    endpoint: str
    max_calls: int
    max_usd_micro: int
    deadline: float  # clock value after which no POST may start


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SignalsLedger:  # pylint: disable=too-many-instance-attributes
    def __init__(self, path: Path, *, run_id: str, api_key: str, max_calls: int,
                 max_usd_micro: int, deadline: float,
                 clock: Callable[[], float] = time.monotonic,
                 transport: httpx.BaseTransport | None = None,
                 endpoint: str = ENDPOINTS["deepseek"],
                 prices: tuple[float, float] = DEFAULT_PRICES) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        self.db = sqlite3.connect(path, isolation_level=None, timeout=30)
        self.db.execute("PRAGMA busy_timeout=30000")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS calls (
                id INTEGER PRIMARY KEY, request_key TEXT NOT NULL, article_id INTEGER,
                extraction_version TEXT, scope_day TEXT, run_id TEXT NOT NULL,
                state TEXT NOT NULL, reserved_micro INTEGER NOT NULL, actual_micro INTEGER,
                status_code INTEGER, response TEXT, created_at TEXT NOT NULL, received_at TEXT);
            CREATE INDEX IF NOT EXISTS ix_calls_request_key ON calls (request_key);
            CREATE INDEX IF NOT EXISTS ix_calls_run_id ON calls (run_id);
        """)
        # A row left `reserved` by a crashed run has unknown billing.
        self.db.execute("UPDATE calls SET state = 'unknown' "
                        "WHERE state = 'reserved' AND run_id != ?", (run_id,))
        self.run_id = run_id
        self.caps = LedgerConfig(endpoint, max_calls, max_usd_micro, deadline)
        self.clock = clock
        self.prices = prices
        # The key lives only in the client's headers; it is never stored in the ledger.
        self.client = httpx.Client(
            transport=transport, timeout=CONNECT_TIMEOUT,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        self.consecutive_failures = 0
        self.stop_reason: str | None = None

    def close(self) -> None:
        self.client.close()
        self.db.close()

    def priced(self, data: Any) -> int | None:
        """Actual cost in microdollars from the answer's usage, at this ledger's prices."""
        usage = data.get("usage") if isinstance(data, dict) else None
        if not isinstance(usage, dict):
            return None
        counts = (usage.get("prompt_tokens"), usage.get("completion_tokens"))
        if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in counts):
            return None
        prompt, completion = cast(tuple[int, int], counts)
        return math.ceil(prompt * self.prices[0] + completion * self.prices[1])

    def bound_micro(self, body: dict[str, Any], max_output: int) -> int:
        """Reservation: the encoded body bytes as input tokens plus `max_output` tokens."""
        return math.ceil(len(encoded(body).encode()) * self.prices[0]
                         + max_output * self.prices[1])

    def replay(self, request_key: str) -> Any | None:
        row = self.db.execute(
            "SELECT response FROM calls WHERE request_key = ? AND state = 'response' "
            "AND status_code = 200 ORDER BY id DESC LIMIT 1", (request_key,)).fetchone()
        return json.loads(row[0]) if row else None

    def run_calls(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM calls WHERE run_id = ?",
                                   (self.run_id,)).fetchone()[0])

    def run_spend_micro(self) -> int:
        return int(self.db.execute(
            "SELECT COALESCE(SUM(CASE WHEN actual_micro IS NOT NULL THEN actual_micro "
            "ELSE reserved_micro END), 0) FROM calls WHERE run_id = ?",
            (self.run_id,)).fetchone()[0])

    def run_states(self) -> dict[str, int]:
        return dict(self.db.execute("SELECT state, COUNT(*) FROM calls WHERE run_id = ? "
                                    "GROUP BY state", (self.run_id,)).fetchall())

    def _reserve(self, request_key: str, reserved_micro: int, article_id: int | None,
                 version: str | None, scope_day: str | None) -> int:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if self.clock() + PRE_POST_RESERVE_SECONDS > self.caps.deadline:
                raise LedgerStop("deadline_reached")
            if self.run_calls() >= self.caps.max_calls:
                raise LedgerStop("cap_reached")
            if self.run_spend_micro() + reserved_micro > self.caps.max_usd_micro:
                raise LedgerStop("cap_reached")
            cursor = self.db.execute(
                "INSERT INTO calls (request_key, article_id, extraction_version, scope_day, "
                "run_id, state, reserved_micro, created_at) "
                "VALUES (?, ?, ?, ?, ?, 'reserved', ?, ?)",
                (request_key, article_id, version, scope_day, self.run_id, reserved_micro, _now()))
            self.db.execute("COMMIT")
            return int(cursor.lastrowid or 0)
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _post(self, body: dict[str, Any]) -> tuple[int | None, bytes | None]:
        """One physical POST; (status, body) or (None, None) on transport error or abort."""
        started = self.clock()
        try:
            with self.client.stream("POST", self.caps.endpoint, json=body) as response:
                chunks = []
                for chunk in response.iter_bytes():
                    chunks.append(chunk)
                    if self.clock() - started > BODY_DEADLINE_SECONDS:
                        return None, None
                return response.status_code, b"".join(chunks)
        except httpx.HTTPError:
            return None, None

    def dispatch(self, body: dict[str, Any], *, request_key: str, reserved_micro: int,
                 article_id: int | None = None, version: str | None = None,
                 scope_day: str | None = None) -> Dispatch:
        """Replay a saved 200 answer or make exactly one POST; raises LedgerStop at a cap."""
        saved = self.replay(request_key)
        if saved is not None:
            return Dispatch("response", 200, saved, 0, replayed=True)
        if self.stop_reason is not None:
            raise LedgerStop(self.stop_reason)
        if self.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            self.stop_reason = "provider_unavailable"
            raise LedgerStop(self.stop_reason)
        row_id = self._reserve(request_key, reserved_micro, article_id, version, scope_day)
        status, raw = self._post(body)
        data = None
        if raw is not None:
            try:
                data = json.loads(raw)
            except ValueError:
                data = None
        actual = self.priced(data) if data is not None else None
        if status is None:
            state, cost = "unknown", None
        elif actual is not None:
            state, cost = ("response" if status == 200 else "error_billed"), actual
        elif is_overload(status, data):
            state, cost = "transient", 0
        else:
            state, cost = "unknown", None
        self.db.execute(
            "UPDATE calls SET state = ?, actual_micro = ?, status_code = ?, response = ?, "
            "received_at = ? WHERE id = ?",
            (state, cost, status, raw.decode("utf-8", "replace") if raw is not None else None,
             _now(), row_id))
        self.consecutive_failures = 0 if state == "response" else self.consecutive_failures + 1
        if cost is not None and cost > reserved_micro:
            self.stop_reason = "usage_exceeded_bound"
        return Dispatch(state, status, data, reserved_micro if cost is None else cost)
