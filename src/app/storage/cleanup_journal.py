"""Private durable response journal with total-run request and spend reservations."""
import json
import math
import os
import sqlite3
from collections import Counter
from dataclasses import asdict
from logging import getLogger
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx

from app.core.ingestion.legacy_cleanup import cleanup_verdict
from app.core.jev import JevRelevanceScorer
from app.storage.legacy_cleanup import encoded, fingerprint

INPUT_PRICE_PER_MILLION = 0.042
MAX_INPUT_TOKENS = 64000
RESERVE_MICRO_USD = math.ceil(MAX_INPUT_TOKENS * INPUT_PRICE_PER_MILLION)


class CleanupStopped(RuntimeError):
    pass


class CleanupJournal:
    def __init__(self, path: Path, identity: dict[str, Any]):
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS identity (value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS calls (
                key TEXT PRIMARY KEY, reserved INTEGER NOT NULL, actual INTEGER,
                status TEXT NOT NULL, response TEXT, usage TEXT, verdict TEXT);
        """)
        stored = self.db.execute("SELECT value FROM identity").fetchone()
        value = fingerprint(identity)
        if stored and stored[0] != value:
            self.db.close()
            raise ValueError("Journal belongs to a different snapshot/model/policy/prompt")
        if not stored:
            self.db.execute("INSERT INTO identity VALUES (?)", (value,))
            self.db.commit()

    def close(self) -> None:
        self.db.close()

    def reserve(self, key: str, budget_usd: float, max_requests: int) -> None:
        if not math.isfinite(budget_usd) or budget_usd < 0 or max_requests < 0:
            raise ValueError("Invalid cleanup budget")
        self.db.execute("BEGIN IMMEDIATE")
        count, spent = self.db.execute(
            "SELECT COUNT(*), COALESCE(SUM(reserved),0) FROM calls").fetchone()
        if count >= max_requests or spent + RESERVE_MICRO_USD > math.floor(budget_usd * 1e6):
            self.db.rollback()
            raise CleanupStopped("budget_or_request_limit")
        self.db.execute("INSERT INTO calls(key,reserved,status) VALUES (?,?,?)",
                        (key, RESERVE_MICRO_USD, "inflight"))
        self.db.commit()

    def capture(self, key: str, response: httpx.Response) -> None:
        response.read()
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        usage = payload.get("usage") if isinstance(payload, dict) else None
        tokens = usage.get("input_tokens") if isinstance(usage, dict) else None
        valid = isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0
        actual = (math.ceil(tokens * INPUT_PRICE_PER_MILLION)
                  if isinstance(tokens, int) and valid else None)
        recorded = {"status_code": response.status_code, "body": response.text}
        # Commit the raw response before parsing: resume cannot repay a successful response.
        self.db.execute("UPDATE calls SET response=?, usage=?, actual=?, reserved=?, status=? "
                        "WHERE key=?", (encoded(recorded), encoded(usage), actual,
                                        actual if actual is not None else RESERVE_MICRO_USD,
                                        "response", key))
        self.db.commit()

    def evaluate(  # pylint: disable=too-many-positional-arguments
                 self, row: dict[str, Any], key: str, model: str, client: httpx.Client,
                 budget_usd: float, max_requests: int) -> dict[str, Any]:
        stored = self.db.execute("SELECT status,response,verdict FROM calls WHERE key=?",
                                 (key,)).fetchone()
        if stored and stored[2]:
            result = json.loads(stored[2])
            if result["outcome"] == "failed":
                raise CleanupStopped("provider_failed_previous_attempt")
            return result  # type: ignore[no-any-return]
        if stored and stored[0] == "inflight":
            raise CleanupStopped("interrupted_request_unknown_billing_requires_review")
        scorer = JevRelevanceScorer(client, model, getLogger(__name__),
                                     semantic_admission_enabled=True)
        if stored:
            raw = json.loads(stored[1])
            with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
                raw["status_code"], content=raw["body"], request=request,
            ))) as replay:
                scorer.client = replay
                assessment = scorer.classify(SimpleNamespace(**row))
        else:
            self.reserve(key, budget_usd, max_requests)
            def hook(response: httpx.Response) -> None:
                self.capture(key, response)
            client.event_hooks["response"].append(hook)
            try:
                assessment = scorer.classify(SimpleNamespace(**row))
            finally:
                client.event_hooks["response"].remove(hook)
        raw_stored = self.db.execute("SELECT response FROM calls WHERE key=?", (key,)).fetchone()
        returned_model = None
        if raw_stored[0]:
            try:
                returned_model = json.loads(json.loads(raw_stored[0])["body"]).get("model")
            except (ValueError, AttributeError):
                pass
        if returned_model and returned_model != model:
            assessment = None
        result = (cleanup_verdict(row, assessment) if assessment else
                  {"outcome": "failed", "reason": "provider_or_invalid_response"})
        if assessment:
            result["assessment"] = asdict(assessment)
        self.db.execute("UPDATE calls SET verdict=?, status=? WHERE key=?",
                        (encoded(result), "complete" if assessment else "failed", key))
        self.db.commit()
        if assessment is None:
            raise CleanupStopped("provider_or_invalid_response")
        return result

    def verdicts(self) -> dict[str, Any]:
        return {key: json.loads(value) for key, value in self.db.execute(
            "SELECT key,verdict FROM calls WHERE verdict IS NOT NULL")}

    def usage(self) -> dict[str, Any]:
        rows = self.db.execute("SELECT reserved,actual,usage,status FROM calls").fetchall()
        tokens: Counter[str] = Counter()
        for _, _, raw, _ in rows:
            value = json.loads(raw) if raw else None
            if isinstance(value, dict):
                tokens.update({key: value for key, value in value.items()
                               if isinstance(value, int) and not isinstance(value, bool)})
        return {"requests": len(rows), "reserved_usd": sum(row[0] for row in rows) / 1e6,
                "usage_priced_usd": sum(row[1] or 0 for row in rows) / 1e6,
                "unknown_usage_requests": sum(row[1] is None for row in rows),
                "usage": dict(tokens), "provider_actual_cost": "Only if present in raw response",
                "price_usd_per_million_input_tokens": INPUT_PRICE_PER_MILLION}
