"""Durable pilot payment reservations shared by both providers and restarts."""
import json
import math
import os
import sqlite3
import time
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

# Overload/rate-limit answers without usage are not billed; retry them in place.
TRANSIENT_STATUS = {429, 500, 502, 503, 504}
TRANSIENT_RETRY_DELAYS = (15, 60, 180)


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


def _json_or_none(response):
    try:
        return response.json()
    except ValueError:
        return None


def is_overload(status_code, data):
    """An explicit error-only overload answer; anything else keeps unknown billing."""
    return status_code in TRANSIENT_STATUS and isinstance(data, dict) and set(data) == {"error"}


class PilotJournal:
    def __init__(self, path, identity, caps, *, key_function=request_key,
                 reservation_function=reservation, transport_review_reason=None,
                 transport_retry_delays=(0,)):
        if set(caps) != {"total", "jev", "deepseek"}:
            raise ValueError("All three caps required")
        if not transport_retry_delays:
            raise ValueError("At least one transport retry delay required")
        self.caps = {k: microdollars(v) for k, v in caps.items()}
        self.key_function = key_function
        self.reservation_function = reservation_function
        self.transport_review_reason = transport_review_reason
        # One reviewed retry per delay; each attempt keeps its own conservative reservation.
        self.transport_retry_delays = tuple(transport_retry_delays)
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
            CREATE TABLE IF NOT EXISTS request_attempts (
                request_key TEXT PRIMARY KEY, attempt_key TEXT UNIQUE NOT NULL);
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

    def reserve(self, key, provider, amount, parent_key=None):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            unsafe = self.db.execute(
                "SELECT COUNT(*) FROM calls WHERE state IN ('inflight','failed') "
                "OR (actual IS NULL AND NOT (state='reviewed_transport' AND EXISTS "
                "(SELECT 1 FROM reviews WHERE reviews.key=calls.key)))").fetchone()[0]
            if unsafe:
                raise PilotStopped("unknown_or_failed_previous_call_requires_review")
            total = self.db.execute("SELECT COALESCE(SUM(committed),0) FROM calls").fetchone()[0]
            spent = self.db.execute("SELECT COALESCE(SUM(committed),0) FROM calls "
                                    "WHERE provider=?", (provider,)).fetchone()[0]
            if total + amount > self.caps["total"] or spent + amount > self.caps[provider]:
                raise PilotStopped("cumulative_budget_limit")
            if self.db.execute("SELECT 1 FROM calls WHERE key=?", (key,)).fetchone():
                raise PilotStopped("concurrent_dispatch_requires_review")
            self.db.execute("INSERT INTO calls(key,provider,committed,state) VALUES (?,?,?,?)",
                            (key, provider, amount, "inflight"))
            if parent_key:
                self.db.execute("INSERT INTO request_attempts VALUES (?,?)", (parent_key, key))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def fail(self, key, error_type):
        self.db.execute("UPDATE calls SET state='failed',error_type=? WHERE key=?",
                        (error_type, key))
        self.db.commit()

    def review_transport_failure(self, key, reason):
        """Accept the reserved expense without inventing usage or a semantic answer."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("A transport review reason is required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT state,error_type,response,actual FROM calls WHERE key=?",
                                  (key,)).fetchone()
            allowed = {"ReadError", "ReadTimeout", "ConnectError", "ConnectTimeout",
                       "WriteError", "WriteTimeout", "RemoteProtocolError", "PoolTimeout"}
            if not row or row[0] != "failed" or row[1] not in allowed or row[2:] != (None, None):
                self.db.rollback()
                return False
            self.db.execute("INSERT INTO reviews(key,reason) VALUES (?,?)", (key, reason))
            self.db.execute("UPDATE calls SET state='reviewed_transport' WHERE key=?", (key,))
            self.db.commit()
            return True
        except BaseException:
            self.db.rollback()
            raise

    def _attempt(self, request):
        """Return (key, saved, attempt, parent) of the first unresolved attempt in the chain."""
        key, attempt, parent = request, 1, None
        while True:
            saved = self.db.execute("SELECT state,response,actual FROM calls WHERE key=?",
                                    (key,)).fetchone()
            if not saved or saved[0] == "response":
                return key, saved, attempt, parent
            if saved[0] == "failed" and self._release_unbilled_transient(key):
                return key, None, attempt, parent
            if self.transport_review_reason and saved[0] == "failed":
                if self.review_transport_failure(key, self.transport_review_reason):
                    saved = ("reviewed_transport", saved[1], saved[2])
            if saved[0] != "reviewed_transport" or not self.transport_review_reason:
                raise PilotStopped("unknown_or_failed_previous_call_requires_review")
            if not self.db.execute("SELECT 1 FROM reviews WHERE key=?", (key,)).fetchone():
                raise PilotStopped("transport_review_provenance_missing")
            if attempt > len(self.transport_retry_delays):
                raise ValueError("Reviewed transport attempts exhausted; result unresolved")
            # request_attempts links each attempt to the next one (request -> 2 -> 3).
            following = self.db.execute("SELECT attempt_key FROM request_attempts "
                                        "WHERE request_key=?", (key,)).fetchone()
            attempt, parent = attempt + 1, key
            key = following[0] if following else fingerprint(
                {"request_key": request, "attempt": attempt})

    def _release_unbilled_transient(self, key):
        """Drop a recorded overload answer without usage so a resume may redispatch."""
        row = self.db.execute("SELECT error_type,actual,response FROM calls WHERE key=?",
                              (key,)).fetchone()
        if not row or row[0] != "HTTPOrJSONError" or row[1] is not None or row[2] is None:
            return False
        received = json.loads(row[2])
        if not is_overload(received.get("status_code"), received.get("body")):
            return False
        with self.db:
            self.db.execute("DELETE FROM calls WHERE key=?", (key,))
            self.db.execute("DELETE FROM request_attempts WHERE attempt_key=?", (key,))
        return True

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

    def call(self, provider, body, client, secret, *, before_dispatch=None):
        request = self.key_function(provider, body)
        key, saved, attempt, parent = self._attempt(request)
        amount = self.reservation_function(provider, body)
        if saved:
            if saved[0] != "response" or saved[2] is None:
                raise PilotStopped("unknown_or_failed_previous_call_requires_review")
            received = json.loads(saved[1])
            if (received["status_code"] != 200 or not isinstance(received["body"], dict)
                    or saved[2] > amount):
                self.fail(key, "InvalidSavedResponse")
                raise PilotStopped("saved_response_requires_review")
            return received["body"]
        if before_dispatch:
            before_dispatch()
        if attempt > 1 and self.transport_retry_delays[attempt - 2]:
            time.sleep(self.transport_retry_delays[attempt - 2])
        self.reserve(key, provider, amount, parent_key=parent)
        try:
            for delay in (*TRANSIENT_RETRY_DELAYS, None):
                response = client.post(ENDPOINTS[provider], json=body,
                                       headers={"Authorization": "Bearer " + secret})
                if delay is None or not is_overload(response.status_code,
                                                    _json_or_none(response)):
                    break
                time.sleep(delay)
        except httpx.HTTPError as exc:
            self.fail(key, type(exc).__name__)
            if self.transport_review_reason and self.review_transport_failure(
                    key, self.transport_review_reason):
                return self.call(provider, body, client, secret, before_dispatch=before_dispatch)
            raise PilotStopped("provider_outage_unknown_billing") from None
        data = _json_or_none(response)
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
