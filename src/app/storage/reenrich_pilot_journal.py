"""Durable pilot payment reservations shared by both providers and restarts."""
import json
import math
import os
import sqlite3
from collections import Counter
from decimal import Decimal

import httpx

from app.core.reenrich_pilot import (
    DEEPSEEK_MODEL,
    ENDPOINTS,
    PRICES,
    parse_summary,
    request_key,
    reservation,
)
from app.storage.legacy_cleanup import encoded, fingerprint


class PilotStopped(RuntimeError):
    """No further paid requests may be dispatched."""


def microdollars(value):
    amount = Decimal(str(value))
    if not amount.is_finite() or amount <= 0 or amount * 1000000 != int(amount * 1000000):
        raise ValueError("Invalid dollar cap")
    return int(amount * 1000000)


def priced_usage(provider, data):
    usage = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(usage, dict):
        return None
    names = ("input_tokens",) if provider == "jev" else ("prompt_tokens", "completion_tokens")
    tokens = [usage.get(name) for name in names]
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in tokens):
        return None
    return math.ceil(tokens[0] * PRICES[provider]["input"] +
                     (0 if provider == "jev" else tokens[1] * PRICES[provider]["output"]))


class PilotJournal:
    def __init__(self, path, identity, caps, *, key_function=request_key,
                 reservation_function=reservation):
        if set(caps) != {"total", "jev", "deepseek"}:
            raise ValueError("All three caps required")
        self.caps = {k: microdollars(v) for k, v in caps.items()}
        self.key_function = key_function
        self.reservation_function = reservation_function
        if self.caps["jev"] + self.caps["deepseek"] > self.caps["total"]:
            raise ValueError("Provider caps exceed total cap")
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS identity (value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS calls (
                key TEXT PRIMARY KEY, provider TEXT NOT NULL, committed INTEGER NOT NULL,
                actual INTEGER, state TEXT NOT NULL, response TEXT, error_type TEXT,
                reserved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                received_at TEXT);
            CREATE TABLE IF NOT EXISTS reviews (
                key TEXT PRIMARY KEY, reason TEXT NOT NULL,
                reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        """)
        value = fingerprint({"identity": identity, "caps_micro_usd": self.caps})
        stored = self.db.execute("SELECT value FROM identity").fetchone()
        if stored and stored[0] != value:
            self.db.close()
            raise ValueError("Pilot identity or approved budget changed")
        if not stored:
            self.db.execute("INSERT INTO identity VALUES (?)", (value,))
            self.db.commit()

    def close(self):
        self.db.close()

    def reserve(self, key, provider, amount):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            unsafe = self.db.execute(
                "SELECT COUNT(*) FROM calls WHERE state IN ('inflight','failed') "
                "OR actual IS NULL").fetchone()[0]
            if unsafe:
                raise PilotStopped("unknown_or_failed_previous_call_requires_review")
            total = self.db.execute("SELECT COALESCE(SUM(committed),0) FROM calls").fetchone()[0]
            spent = self.db.execute("SELECT COALESCE(SUM(committed),0) FROM calls "
                                    "WHERE provider=?", (provider,)).fetchone()[0]
            if total + amount > self.caps["total"] or spent + amount > self.caps[provider]:
                raise PilotStopped("cumulative_budget_limit")
            self.db.execute("INSERT INTO calls(key,provider,committed,state) VALUES (?,?,?,?)",
                            (key, provider, amount, "inflight"))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def fail(self, key, error_type):
        self.db.execute("UPDATE calls SET state='failed',error_type=? WHERE key=?",
                        (error_type, key))
        self.db.commit()

    def has_response(self, provider, body):
        saved = self.db.execute("SELECT 1 FROM calls WHERE key=? AND state='response' "
                                "AND actual IS NOT NULL", (request_key(provider, body),)).fetchone()
        return saved is not None

    def has_reviewed_response(self, provider, body):
        return self.db.execute("SELECT 1 FROM calls WHERE key=? AND provider=? "
                               "AND state='reviewed'", (request_key(provider, body), provider)
                               ).fetchone() is not None

    def review_quote_failure(self, row, comparison, body, prompt_version):
        key = request_key("deepseek", body)
        saved = self.db.execute("SELECT actual,response FROM calls WHERE key=? "
                                "AND provider='deepseek' AND state='failed' "
                                "AND error_type='InvalidSummary'", (key,)).fetchone()
        if not saved or saved[0] is None or saved[1] is None:
            return False
        received = json.loads(saved[1])
        data = received["body"]
        if (received["status_code"] != 200 or not isinstance(data, dict)
                or data.get("model") not in {DEEPSEEK_MODEL, "deepseek-v4.1-flash"}
                or priced_usage("deepseek", data) != saved[0]):
            return False
        try:
            parse_summary(row, data, comparison, prompt_version=prompt_version)
        except ValueError as exc:
            if str(exc) not in {"Unsupported summary quote", "Unsupported comparison product"}:
                return False
        except (KeyError, TypeError, IndexError):
            return False
        else:
            return False
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO reviews(key,reason) VALUES (?,?)",
                            (key, "Known billed quote failure; user authorised grounded repair"))
            self.db.execute("UPDATE calls SET state='reviewed' WHERE key=?", (key,))
        return True

    def review_truncated_summaries(self, reason):
        """A known billed truncation may be superseded, retaining its response and cost."""
        reviewed = []
        for key, actual, raw in self.db.execute(
            "SELECT key,actual,response FROM calls WHERE provider='deepseek' "
            "AND state='failed' AND error_type='InvalidSummary'"
        ).fetchall():
            if actual is None or raw is None:
                continue
            received = json.loads(raw)
            data = received.get("body")
            if (received.get("status_code") != 200 or not isinstance(data, dict)
                    or not data.get("choices")
                    or data["choices"][0].get("finish_reason") != "length"):
                continue
            if (data.get("model") not in {DEEPSEEK_MODEL, "deepseek-v4.1-flash"}
                    or priced_usage("deepseek", data) != actual):
                continue
            with self.db:
                self.db.execute("INSERT INTO reviews(key,reason) VALUES (?,?)", (key, reason))
                self.db.execute("UPDATE calls SET state='reviewed' WHERE key=?", (key,))
            reviewed.append(key)
        return reviewed

    def restore_valid_summary(self, row, comparison, body, prompt_version):
        key = request_key("deepseek", body)
        saved = self.db.execute("SELECT actual,response FROM calls WHERE key=? "
                                "AND provider='deepseek' AND state='failed' "
                                "AND error_type='InvalidSummary'", (key,)).fetchone()
        if not saved or saved[0] is None or saved[1] is None:
            return False
        received = json.loads(saved[1])
        if received["status_code"] != 200 or priced_usage("deepseek", received["body"]) != saved[0]:
            return False
        try:
            parse_summary(row, received["body"], comparison, prompt_version=prompt_version)
        except (ValueError, KeyError, TypeError, IndexError):
            return False
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO reviews(key,reason) VALUES (?,?)",
                            (key, "Complete grounded summary revalidated; length is advisory"))
            self.db.execute("UPDATE calls SET state='response' WHERE key=?", (key,))
        return True

    def call(self, provider, body, client, secret):
        key = self.key_function(provider, body)
        amount = self.reservation_function(provider, body)
        saved = self.db.execute("SELECT state,response,actual FROM calls WHERE key=?",
                                (key,)).fetchone()
        if saved:
            if saved[0] != "response" or saved[2] is None:
                raise PilotStopped("unknown_or_failed_previous_call_requires_review")
            received = json.loads(saved[1])
            if (received["status_code"] != 200 or not isinstance(received["body"], dict)
                    or saved[2] > amount):
                self.fail(key, "InvalidSavedResponse")
                raise PilotStopped("saved_response_requires_review")
            return received["body"]
        self.reserve(key, provider, amount)
        try:
            response = client.post(ENDPOINTS[provider], json=body,
                                   headers={"Authorization": "Bearer " + secret})
        except httpx.HTTPError as exc:
            self.fail(key, type(exc).__name__)
            raise PilotStopped("provider_outage_unknown_billing") from None
        try:
            data = response.json()
        except ValueError:
            data = None
        actual = priced_usage(provider, data)
        # Save received bytes before inspecting model answers. Resume only replays them.
        self.db.execute("UPDATE calls SET response=?,actual=?,committed=?,state='response', "
                        "received_at=CURRENT_TIMESTAMP WHERE key=?",
                        (encoded({"status_code": response.status_code,
                                  "raw": response.text, "body": data}), actual,
                         amount if actual is None else actual, key))
        self.db.commit()
        if response.status_code != 200 or not isinstance(data, dict):
            self.fail(key, "HTTPOrJSONError")
            raise PilotStopped("provider_response_failed")
        if actual is None:
            raise PilotStopped("missing_usage_reservation_retained")
        if actual > amount:
            self.fail(key, "ReservationExceeded")
            raise PilotStopped("usage_exceeded_conservative_bound")
        return data

    def report(self):
        rows = self.db.execute(
            "SELECT provider,committed,actual,state,response FROM calls").fetchall()
        providers = {}
        for provider in PRICES:
            selected = [row for row in rows if row[0] == provider]
            tokens = Counter()
            for row in selected:
                if row[4]:
                    data = json.loads(row[4])["body"]
                    usage = data.get("usage", {}) if isinstance(data, dict) else {}
                    if isinstance(usage, dict):
                        tokens.update({k: v for k, v in usage.items()
                                       if isinstance(v, int) and not isinstance(v, bool)
                                       and v >= 0})
            providers[provider] = {
                "calls": len(selected), "committed_usd": sum(r[1] for r in selected) / 1e6,
                "usage_priced_usd": sum(r[2] or 0 for r in selected) / 1e6,
                "unknown_usage_calls": sum(r[2] is None for r in selected),
                "states": dict(Counter(r[3] for r in selected)), "tokens": dict(tokens)}
        return {"providers": providers, "total_committed_usd": sum(r[1] for r in rows) / 1e6,
                "approved_caps_usd": {k: v / 1e6 for k, v in self.caps.items()},
                "rates_usd_per_million": PRICES, "cost_kind": "usage_priced_peak_not_invoice"}
