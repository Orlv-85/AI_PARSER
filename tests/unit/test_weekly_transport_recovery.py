"""Operator-reviewed failures retain reservations and never replay successful calls."""
import json

import httpx
import pytest

from app.core.weekly.enrichment import BudgetExhausted
from app.storage.reenrich_pilot_journal import PilotJournal, PilotStopped


def journal_at(path, review=True):
    return PilotJournal(path, "frozen", {"total": "0.002", "jev": "0.001", "deepseek": "0.001"},
        reservation_function=lambda *args: 100,
        transport_review_reason="Operator accepts conservative unknown expense" if review else None)


def test_reviewed_failure_retries_once_and_preserves_original_unknown_expense(tmp_path):
    journal = journal_at(tmp_path / "journal", review=True)
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ReadError("network disconnected", request=request)
        return httpx.Response(200, json={"answers": {}, "usage": {"input_tokens": 10}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = journal.call("jev", {"task": "one"}, client, "test")
        assert journal.call("jev", {"task": "one"}, client, "test") == response
    assert len(requests) == 2
    rows = journal.db.execute("SELECT state,committed,actual,error_type FROM calls "
                              "ORDER BY reserved_at,rowid").fetchall()
    assert rows == [("reviewed_transport", 100, None, "ReadError"), ("response", 1, 1, None)]
    assert journal.db.execute("SELECT count(*) FROM reviews").fetchone()[0] == 1
    assert journal.db.execute("SELECT count(*) FROM request_attempts").fetchone()[0] == 1
    assert journal.report()["total_committed_usd"] == 0.000101
    journal.close()


def test_two_transport_failures_become_unresolved_but_do_not_block_other_requests(tmp_path):
    journal = journal_at(tmp_path / "journal")
    requests = []

    def handler(request):
        requests.append(request)
        if json.loads(request.content)["task"] == "failed":
            raise httpx.ReadTimeout("network timeout", request=request)
        return httpx.Response(200, json={"usage": {"input_tokens": 10}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        for _ in range(2):
            with pytest.raises(ValueError, match="attempts exhausted"):
                journal.call("jev", {"task": "failed"}, client, "test")
        journal.call("jev", {"task": "other"}, client, "test")
    assert len(requests) == 3
    assert journal.report()["providers"]["jev"]["unknown_usage_calls"] == 2
    assert journal.report()["total_committed_usd"] == 0.000201
    journal.close()


@pytest.mark.parametrize("state", ["inflight", "failed", "response"])
def test_unreviewed_or_ambiguous_dispatch_remains_blocked(tmp_path, state):
    journal = journal_at(tmp_path / "journal", review=state != "failed")
    journal.reserve("old", "jev", 100)
    journal.db.execute("UPDATE calls SET state=?,error_type=? WHERE key='old'",
                       (state, "ReadError" if state == "failed" else None))
    journal.db.commit()
    if state != "failed":
        assert not journal.review_transport_failure("old", "review")
    requests = []
    with httpx.Client(transport=httpx.MockTransport(requests.append)) as client:
        with pytest.raises(PilotStopped, match="requires_review"):
            journal.call("jev", {"task": "other"}, client, "test")
    assert not requests and journal.report()["total_committed_usd"] == 0.0001
    journal.close()


def test_retry_dispatch_budget_and_total_expense_survive_restart(tmp_path):
    path = tmp_path / "journal"
    journal = journal_at(path)
    dispatched = []
    budget = []

    def before_dispatch():
        if budget:
            raise BudgetExhausted("jev")
        budget.append(True)

    def handler(request):
        dispatched.append(request)
        if len(dispatched) == 1:
            raise httpx.ReadError("network error", request=request)
        return httpx.Response(200, json={"usage": {"input_tokens": 10}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BudgetExhausted):
            journal.call("jev", {"task": "one"}, client, "test", before_dispatch=before_dispatch)
        journal.close()
        journal = journal_at(path)
        journal.call("jev", {"task": "one"}, client, "test")
    assert len(dispatched) == 2 and journal.report()["total_committed_usd"] == 0.000101
    with pytest.raises(PilotStopped, match="concurrent_dispatch"):
        key = journal.db.execute("SELECT key FROM calls LIMIT 1").fetchone()[0]
        journal.reserve(key, "jev", 100)
    journal.close()


def test_reviewed_reservations_still_count_against_cumulative_cap(tmp_path):
    journal = journal_at(tmp_path / "journal")
    journal.caps["total"] = journal.caps["jev"] = 150
    requests = []

    def handler(request):
        requests.append(request)
        raise httpx.ReadError("network disconnected", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PilotStopped, match="cumulative_budget_limit"):
            journal.call("jev", {"task": "one"}, client, "test")
    assert len(requests) == 1 and journal.report()["total_committed_usd"] == 0.0001
    journal.close()


def test_configured_delays_extend_the_attempt_chain_and_survive_restart(tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr("app.storage.reenrich_pilot_journal.time.sleep", sleeps.append)
    path = tmp_path / "journal"

    def open_journal():
        return PilotJournal(path, "daily", {"total": "0.002", "jev": "0.001",
                                            "deepseek": "0.001"},
                            reservation_function=lambda *args: 100,
                            transport_review_reason="accepted", transport_retry_delays=(60, 300))

    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) < 3:
            raise httpx.ReadError("network disconnected", request=request)
        return httpx.Response(200, json={"usage": {"input_tokens": 10}})

    journal = open_journal()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        journal.call("jev", {"task": "one"}, client, "test")
        journal.close()
        journal = open_journal()
        journal.call("jev", {"task": "one"}, client, "test")
    assert len(requests) == 3 and sleeps == [60, 300]
    assert journal.db.execute("SELECT count(*) FROM request_attempts").fetchone()[0] == 2
    assert journal.report()["total_committed_usd"] == 0.000201
    journal.close()
