"""Period AI Signals brief step: the only paid step of 017 (signals_period.md, "Brief").

For each target period it builds the packet from the stored payload, reuses a stored brief with
the same input hash, and otherwise dispatches at most two attempts (one recovery) through the
signals ledger. The ledger, and with it the provider client, is created only when a call is due.
"""
import json
import logging
import time
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from app.core.daily.signals_brief import (
    BRIEF_PRICES,
    BriefInvalid,
    PacketTooLarge,
    brief_payload,
)
from app.core.periodic.period_brief import (
    PERIOD_BRIEF_MAX_USD,
    PERIOD_BRIEF_VERSION,
    PERIOD_MAX_OUTPUT,
    parse_period_brief,
    period_body,
    period_input_hash,
    period_packet,
    period_request_key,
)
from app.core.provider_costs import microdollars
from app.storage.daily_signals_ledger import LedgerStop, SignalsLedger
from app.storage.period_signals import PeriodSignalRepo

LOGGER = logging.getLogger(__name__)
BRIEF_STATUSES = ("ready", "building_history")
ATTEMPTS = 2


def _label(kind: str, start: date) -> str:
    return f"{kind}:{start.isoformat()}"


def _attempts(session: Any, repo: PeriodSignalRepo, ledger: SignalsLedger, *, kind: str,
              start: date, model: str, packet: dict[str, Any], id_map: dict[str, Any],
              digest: str) -> str:
    """Up to two attempts for one period (one recovery); returns its report state."""
    reasons: list[str] = []
    for _ in range(ATTEMPTS):
        body = period_body(packet, model, recovery=reasons[-1] if reasons else None)
        result = ledger.dispatch(
            body, request_key=period_request_key(body),
            reserved_micro=ledger.bound_micro(body, PERIOD_MAX_OUTPUT[kind]),
            version=PERIOD_BRIEF_VERSION, scope_day=start.isoformat())
        if result.state != "response":
            return f"skipped:attempt_{result.state}"
        try:
            sentences = parse_period_brief(result.data, packet, model)
        except BriefInvalid as error:
            reasons.append(str(error))
            continue
        repo.save_brief(kind, start, brief_version=PERIOD_BRIEF_VERSION, model=model,
                        input_hash=digest, status="ok", payload=brief_payload(sentences, id_map))
        session.commit()
        return "ok"
    repo.save_brief(kind, start, brief_version=PERIOD_BRIEF_VERSION, model=model,
                    input_hash=digest, status="invalid", payload={},
                    reason=",".join(reasons)[:1000])
    session.commit()
    return "invalid"


def _prepare(repo: PeriodSignalRepo, kind: str, start: date,  # pylint: disable=too-many-return-statements
             model: str) -> tuple[str, tuple[dict[str, Any], dict[str, Any], str] | None]:
    """(state, work): a final state without work, or "due" with (packet, id map, input hash)."""
    row = repo.get_report(kind, start)
    if row is None:
        return "skipped:no_period", None
    if row.status not in BRIEF_STATUSES:
        return f"skipped:status_{row.status}", None
    try:
        payload = json.loads(row.payload)
        if payload.get("quiet"):
            return "skipped:quiet", None
        packet, id_map = period_packet(payload, repo.digest_items(kind, start))
    except PacketTooLarge:
        return "skipped:packet_too_large", None
    except (ValueError, TypeError, KeyError, AttributeError):
        return "skipped:payload_unreadable", None
    digest = period_input_hash(packet, model)
    stored = repo.get_brief(kind, start)
    if stored is not None and stored.input_hash == digest:
        return "cached", None
    return "due", (packet, id_map, digest)


def run_briefs(session: Any, repo: PeriodSignalRepo, settings: Any,  # pylint: disable=too-many-locals
               targets: Sequence[tuple[str, date]], *, max_usd: str, cache_dir: Path,
               max_seconds: int, transport: httpx.BaseTransport | None = None,
               clock: Callable[[], float] = time.monotonic,
               now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> dict[str, Any]:
    """The brief step for `targets` (kind, start), oldest first. `max_usd` is the run total;
    each brief is also held to `PERIOD_BRIEF_MAX_USD` of its kind. Never raises a provider
    error: a stop is a terminal reason in the report."""
    model = settings.daily_signals_brief_model
    out: dict[str, Any] = {"state": "ok", "model": model, "periods": {},
                           "run": {"calls": 0, "usd": 0.0}, "terminal_reason": None}
    if not settings.period_signals_brief_enabled:
        out["state"] = "disabled"
        return out
    key = settings.ds_api_key.get_secret_value().strip() if settings.ds_api_key else ""
    if not key:
        out["state"] = "missing_provider_key"
        return out
    prices = BRIEF_PRICES.get(model)
    if prices is None:
        out["terminal_reason"] = "brief_model_unpriced"
        out["periods"] = {_label(k, s): "skipped:brief_model_unpriced" for k, s in targets}
        return out
    started = clock()
    run_id = now().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    total = microdollars(max_usd)
    spent = 0
    calls = 0
    for index, (kind, start) in enumerate(targets):
        label = _label(kind, start)
        state, work = _prepare(repo, kind, start, model)
        if work is None:
            out["periods"][label] = state
            continue
        cap = min(microdollars(PERIOD_BRIEF_MAX_USD[kind]), total - spent)
        if cap <= 0:
            out["terminal_reason"] = "brief_budget_exhausted"
            out["periods"][label] = "skipped:brief_budget_exhausted"
            continue
        cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        ledger = SignalsLedger(
            cache_dir / "ledger.sqlite3", run_id=f"{run_id}-brief-{label}", api_key=key,
            max_calls=ATTEMPTS, max_usd_micro=cap, deadline=started + max_seconds, clock=clock,
            transport=transport, prices=prices)
        try:
            packet, id_map, digest = work
            out["periods"][label] = _attempts(session, repo, ledger, kind=kind, start=start,
                                              model=model, packet=packet, id_map=id_map,
                                              digest=digest)
        except LedgerStop as stop:
            session.rollback()
            out["terminal_reason"] = str(stop)
            for rest_kind, rest in targets[index:]:
                out["periods"][_label(rest_kind, rest)] = f"skipped:{stop}"
            break
        finally:
            spent += int(ledger.run_spend_micro())
            calls += ledger.run_calls()
            ledger.close()
    out["run"] = {"calls": calls, "usd": round(spent / 1_000_000, 6)}
    return out
