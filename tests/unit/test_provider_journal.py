"""Characterize durable journal guards and ordering with isolated SQLite and fake HTTP."""
import json
import sqlite3

import httpx
import pytest

from app.core.canonical_json import encoded, fingerprint
from app.core.daily.provider_requests import (
    SUMMARY_RECOVERY_VERSION,
    request_key,
    summary_request,
)
from app.storage import provider_journal as pj

CAPS = {"total": "2", "jev": "1", "deepseek": "1"}
BODY = {"state": "synthetic"}
ROW = {"title": "AI release", "content": "The AI system extracts hospital documents."}
GOOD = {"usage": {"input_tokens": 1000}}


@pytest.fixture(name="journal")
def journal_fixture(tmp_path):
    instance = pj.PilotJournal(tmp_path / "journal.sqlite3", {}, CAPS)
    yield instance
    instance.close()


def saved_call(journal, key="saved", *, provider="jev", state="failed", error="ReadError",
               actual=None, received=None, committed=100):
    journal.db.execute(
        "INSERT INTO calls(key,provider,committed,actual,state,response,error_type) "
        "VALUES (?,?,?,?,?,?,?)", (key, provider, committed, actual, state,
                                   None if received is None else encoded(received), error))
    journal.db.commit()
    return key


def snapshot(journal):
    return journal.db.execute(
        "SELECT key,committed,actual,state,response,error_type FROM calls ORDER BY key").fetchall()


@pytest.mark.parametrize("options,message", [
    ({"caps": {"total": "2"}}, "All three caps required"),
    ({"caps": {**CAPS, "total": "1"}}, "Provider caps exceed total cap"),
    ({"transport_retry_delays": ()}, "At least one transport retry delay required"),
])
def test_journal_configuration_guards(tmp_path, options, message):
    args = {"caps": CAPS, **options}
    with pytest.raises(ValueError, match=f"^{message}$"):
        pj.PilotJournal(tmp_path / "j.sqlite3", {}, **args)


@pytest.mark.parametrize("reason", [None, 1, "", " \t"])
def test_transport_review_requires_reason(journal, reason):
    with pytest.raises(ValueError, match="^A transport review reason is required$"):
        journal.review_transport_failure("absent", reason)
    assert not journal.db.in_transaction


@pytest.mark.parametrize("error", [
    "ReadError", "ReadTimeout", "ConnectError", "ConnectTimeout", "WriteError", "WriteTimeout",
    "RemoteProtocolError", "PoolTimeout",
])
def test_transport_review_eligibility(journal, error):
    key = saved_call(journal, error=error)
    before = snapshot(journal)[0]
    assert journal.review_transport_failure(key, "  accepted risk  ") is True
    after = snapshot(journal)[0]
    assert after == (*before[:3], "reviewed_transport", *before[4:])
    assert journal.db.execute("SELECT key,reason FROM reviews").fetchall() == [
        (key, "  accepted risk  ")]
    assert not journal.review_transport_failure(key, "again")
    journal.reserve("next", "jev", 1)


@pytest.mark.parametrize("changes", [
    {"state": "inflight"}, {"error": "HTTPError"}, {"error": "InvalidSummary"},
    {"actual": 0}, {"received": {"status_code": 200, "body": GOOD}},
])
def test_transport_review_refuses_nontransport_or_received_rows(journal, changes):
    assert journal.review_transport_failure("absent", "reason") is False
    key = saved_call(journal, **changes)
    before = snapshot(journal)
    assert journal.review_transport_failure(key, "reason") is False
    assert snapshot(journal) == before
    assert not journal.db.execute("SELECT * FROM reviews").fetchall()
    assert not journal.db.in_transaction


def test_transport_review_rolls_back(journal):
    key = saved_call(journal)
    journal.db.execute("CREATE TRIGGER refuse_review BEFORE UPDATE ON calls "
                       "BEGIN SELECT RAISE(ABORT, 'synthetic review failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="synthetic review failure"):
        journal.review_transport_failure(key, "reason")
    assert snapshot(journal)[0][3] == "failed"
    assert not journal.db.execute("SELECT * FROM reviews").fetchall()
    assert not journal.db.in_transaction


def test_review_failed_transports_counts_only_eligible_rows(journal):
    saved_call(journal, "transport")
    saved_call(journal, "semantic", error="InvalidSummary")
    assert journal.review_failed_transports() == 0
    journal.transport_review_reason = "review"
    assert journal.review_failed_transports() == 1
    assert journal.review_failed_transports() == 0
    assert dict(journal.db.execute("SELECT key,state FROM calls")) == {
        "transport": "reviewed_transport", "semantic": "failed"}


@pytest.mark.parametrize("state,reason,error,message", [
    ("reviewed_transport", None, None, "unknown_or_failed_previous_call_requires_review"),
    ("reviewed_transport", "review", None, "transport_review_provenance_missing"),
    ("failed", "review", "InvalidSummary", "unknown_or_failed_previous_call_requires_review"),
    ("inflight", "review", None, "unknown_or_failed_previous_call_requires_review"),
])
def test_attempt_chain_requires_review_provenance(journal, state, reason, error, message):
    saved_call(journal, request_key("jev", BODY), state=state, error=error)
    journal.transport_review_reason = reason
    with pytest.raises(pj.PilotStopped, match=f"^{message}$"):
        journal.call("jev", BODY, None, "fake")


def test_attempt_reviews_old_transport_before_retry(journal):
    key = saved_call(journal, request_key("jev", BODY))
    journal.transport_review_reason = "old failure accepted"
    with httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(
        200, json=GOOD))) as client:
        assert journal.call("jev", BODY, client, "fake") == GOOD
    assert journal.db.execute("SELECT state FROM calls WHERE key=?", (key,)).fetchone() == (
        "reviewed_transport",)
    assert journal.db.execute("SELECT reason FROM reviews WHERE key=?", (key,)).fetchone() == (
        "old failure accepted",)


def test_unreviewable_http_error_stops_with_reservation(journal):
    journal.transport_review_reason = "review"

    def broken(_request):
        raise httpx.HTTPError("synthetic")

    with httpx.Client(transport=httpx.MockTransport(broken)) as client:
        with pytest.raises(pj.PilotStopped, match="^provider_outage_unknown_billing$") as caught:
            journal.call("jev", BODY, client, "fake")
    assert caught.value.__suppress_context__
    assert snapshot(journal)[0][1:] == (2688, None, "failed", None, "HTTPError")
    assert not journal.db.execute("SELECT * FROM reviews").fetchall()


def test_callback_stop_does_not_reserve_or_dispatch(journal):
    def stop():
        raise pj.PilotStopped("run_limit")

    with pytest.raises(pj.PilotStopped, match="^run_limit$"):
        journal.call("jev", BODY, None, "fake", before_dispatch=stop)
    assert snapshot(journal) == []


@pytest.mark.parametrize("exhaust", [False, True])
def test_transport_attempt_chain_replays_and_exhausts(journal, monkeypatch, exhaust):
    journal.transport_review_reason = "accepted"
    journal.transport_retry_delays = (7, 11)
    events = []
    monkeypatch.setattr(pj.time, "sleep", lambda delay: events.append(("sleep", delay)))

    def respond(request):
        events.append(("post", snapshot(journal)))
        if exhaust or len([e for e in events if e[0] == "post"]) < 3:
            raise httpx.ReadTimeout("synthetic", request=request)
        return httpx.Response(200, json=GOOD)

    def before():
        events.append(("before", None))

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        if exhaust:
            with pytest.raises(pj.TransportAttemptsExhausted) as caught:
                journal.call("jev", BODY, client, "fake", before_dispatch=before)
            assert str(caught.value) == "Reviewed transport attempts exhausted; result unresolved"
            assert caught.value.dispatched is True
        else:
            assert journal.call("jev", BODY, client, "fake", before_dispatch=before) == GOOD
        count = len(events)
        if exhaust:
            with pytest.raises(pj.TransportAttemptsExhausted) as caught:
                journal.call("jev", BODY, client, "fake", before_dispatch=before)
            assert caught.value.dispatched is False
        else:
            assert journal.call("jev", BODY, client, "fake", before_dispatch=before) == GOOD
        assert len(events) == count
    assert [event[0] for event in events] == [
        "before", "post", "before", "sleep", "post", "before", "sleep", "post"]
    assert [e[1] for e in events if e[0] == "sleep"] == [7, 11]
    root = request_key("jev", BODY)
    second = fingerprint({"request_key": root, "attempt": 2})
    third = fingerprint({"request_key": root, "attempt": 3})
    assert set(journal.db.execute("SELECT * FROM request_attempts")) == {
        (root, second), (second, third)}
    for _, rows in [e for e in events if e[0] == "post"]:
        assert sum(r[3] == "inflight" for r in rows) == 1
    assert journal.committed_usd() == (8064 if exhaust else 5418) / 1e6


@pytest.mark.parametrize("changes", [
    {"state": "failed"}, {"state": "reviewed_transport", "actual": None}, {"actual": None},
])
def test_reservation_guards_and_rollback(journal, changes):
    saved_call(journal, **{"state": "response", "actual": 1, **changes})
    before = snapshot(journal)
    with pytest.raises(pj.PilotStopped, match="unknown_or_failed_previous_call_requires_review"):
        journal.reserve("next", "jev", 1)
    assert snapshot(journal) == before
    assert not journal.db.in_transaction


def test_duplicate_reservation_and_link_failure_roll_back(journal):
    saved_call(journal, state="response", actual=1)
    with pytest.raises(pj.PilotStopped, match="^concurrent_dispatch_requires_review$"):
        journal.reserve("saved", "jev", 1)
    journal.db.execute("INSERT INTO request_attempts VALUES ('parent','previous')")
    journal.db.commit()
    before = snapshot(journal)
    with pytest.raises(sqlite3.IntegrityError):
        journal.reserve("new", "jev", 1, parent_key="parent")
    assert snapshot(journal) == before
    assert not journal.db.in_transaction


def test_caps_allow_exact_boundary(journal):
    assert journal.transport_retry_delays == (0,)
    saved_call(journal, "deepseek", provider="deepseek", state="response",
               actual=1000000, committed=1000000)
    journal.reserve("jev", "jev", 1000000)
    assert journal.committed_usd() == 2
    assert journal.db.execute("SELECT committed,state FROM calls WHERE key='jev'").fetchone() == (
        1000000, "inflight")


def test_total_cap_blocks_even_when_provider_has_room(journal):
    # A receipt committed before validation can exceed the other provider's cap.
    saved_call(journal, "receipt", provider="deepseek", state="response",
               actual=1500000, committed=1500000)
    before = snapshot(journal)
    with pytest.raises(pj.PilotStopped, match="^cumulative_budget_limit$"):
        journal.reserve("jev", "jev", 600000)
    assert snapshot(journal) == before
    assert not journal.db.in_transaction


def test_dispatch_and_receipt_order(journal, monkeypatch):
    events = []
    journal.key_function = lambda provider, body: events.append("key") or "custom"
    journal.reservation_function = lambda provider, body: events.append("amount") or 100

    def respond(request):
        events.append("post")
        assert request.url == pj.ENDPOINTS["jev"]
        assert request.headers["Authorization"] == "Bearer fake"
        assert json.loads(request.content) == BODY
        with sqlite3.connect(journal.db.execute("PRAGMA database_list").fetchone()[2]) as other:
            assert other.execute("SELECT committed,state FROM calls").fetchall() == [
                (100, "inflight")]
        return httpx.Response(200, json=GOOD)

    price = pj.priced_usage

    def pricing(provider, data):
        events.append("price")
        assert snapshot(journal)[0][3:] == ("inflight", None, None)
        return price(provider, data)

    monkeypatch.setattr(pj, "priced_usage", pricing)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert journal.call("jev", BODY, client, "fake",
                            before_dispatch=lambda: events.append("before")) == GOOD
    assert events == ["key", "amount", "before", "post", "price"]
    assert snapshot(journal)[0][1:4] == (42, 42, "response")
    raw = json.loads(snapshot(journal)[0][4])
    assert raw == {"status_code": 200, "raw": httpx.Response(200, json=GOOD).text, "body": GOOD}
    assert not journal.db.in_transaction


def test_custom_key_and_reservation_replay(journal):
    seen = []
    journal.key_function = lambda provider, body: "custom"
    journal.reservation_function = lambda provider, body: seen.append((provider, body)) or 42
    saved_call(journal, "custom", state="response", actual=42,
               received={"status_code": 200, "body": GOOD})
    assert journal.call("jev", BODY, None, "fake",
                        before_dispatch=lambda: pytest.fail("Replay callback")) == GOOD
    assert seen == [("jev", BODY)]
    assert not journal.has_response("jev", BODY)


@pytest.mark.parametrize("actual,received,message,error", [
    (None, {"status_code": 200, "body": GOOD},
     "unknown_or_failed_previous_call_requires_review", "ReadError"),
    (42, {"status_code": 200, "body": []},
     "saved_response_requires_review", "InvalidSavedResponse"),
])
def test_saved_response_guards(journal, actual, received, message, error):
    saved_call(journal, request_key("jev", BODY), state="response", actual=actual,
               received=received)
    with pytest.raises(pj.PilotStopped, match=f"^{message}$"):
        journal.call("jev", BODY, None, "fake")
    assert snapshot(journal)[0][-1] == error


@pytest.mark.parametrize("status,data,text,message,actual,state,error", [
    (200, GOOD, None, None, 42, "response", None),
    (200, {"usage": {"input_tokens": 64000}}, None, None, 2688, "response", None),
    (200, {"usage": None}, None, "missing_usage_reservation_retained", None, "response", None),
    (200, {"usage": {"input_tokens": 100000}}, None,
     "usage_exceeded_conservative_bound", 4200, "failed", "ReservationExceeded"),
    (401, GOOD, None, "provider_response_failed", 42, "failed", "HTTPOrJSONError"),
    (200, [], None, "provider_response_failed", None, "failed", "HTTPOrJSONError"),
    (200, None, "not JSON", "provider_response_failed", None, "failed", "HTTPOrJSONError"),
])
def test_received_response_guards(journal, *, status, data, text, message, actual, state, error):
    response = httpx.Response(status, text=text) if text else httpx.Response(status, json=data)
    with httpx.Client(transport=httpx.MockTransport(lambda _r: response)) as client:
        if message:
            with pytest.raises(pj.PilotStopped, match=f"^{message}$"):
                journal.call("jev", BODY, client, "fake")
        else:
            assert journal.call("jev", BODY, client, "fake") == data
    saved = snapshot(journal)[0]
    assert saved[1:4] == (2688 if actual is None else actual, actual, state)
    assert saved[-1] == error
    assert json.loads(saved[4]) == {"status_code": status, "raw": response.text, "body": data}
    assert not journal.db.in_transaction


def test_transient_retry_order_and_release(journal, monkeypatch):
    events = []
    monkeypatch.setattr(pj.time, "sleep", events.append)

    def busy(_request):
        events.append("post")
        return httpx.Response(503, json={"error": "overloaded"})

    with httpx.Client(transport=httpx.MockTransport(busy)) as client:
        with pytest.raises(pj.PilotStopped, match="^provider_response_failed$"):
            journal.call("jev", BODY, client, "fake")
    assert events == ["post", 15, "post", 60, "post", 180, "post"]
    key = request_key("jev", BODY)
    journal.db.execute("INSERT INTO request_attempts VALUES ('parent',?)", (key,))
    journal.db.commit()
    assert journal._attempt(key) == (key, None, 1, None)  # pylint: disable=protected-access
    assert snapshot(journal) == []
    assert journal.db.execute("SELECT * FROM request_attempts").fetchall() == []
    with httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(
        200, json=GOOD))) as client:
        assert journal.call("jev", BODY, client, "fake") == GOOD


@pytest.mark.parametrize("changes", [
    {"error": "ReadError"}, {"actual": 0}, {"received": None},
    {"received": {"status_code": 401, "body": {"error": "bad key"}}},
    {"received": {"status_code": 503, "body": {"error": "busy", "usage": None}}},
])
def test_transient_release_guards(journal, changes):
    assert not journal._release_unbilled_transient("absent")  # pylint: disable=protected-access
    options = {"error": "HTTPOrJSONError", "received": {
        "status_code": 503, "body": {"error": "busy"}}, **changes}
    key = saved_call(journal, **options)
    before = snapshot(journal)
    assert journal._release_unbilled_transient(key) is False  # pylint: disable=protected-access
    assert snapshot(journal) == before


@pytest.mark.parametrize("provider,data,expected", [
    ("jev", None, None), ("jev", [], None), ("jev", {}, None),
    ("jev", {"usage": []}, None), ("jev", {"usage": {}}, None),
    ("jev", {"usage": {"input_tokens": True}}, None),
    ("jev", {"usage": {"input_tokens": -1}}, None),
    ("jev", {"usage": {"input_tokens": 1.5}}, None),
    ("jev", {"usage": {"input_tokens": 0}}, 0),
    ("jev", {"usage": {"input_tokens": 1}}, 1),
    ("deepseek", {"usage": {"prompt_tokens": 1}}, None),
    ("deepseek", {"usage": {"prompt_tokens": 10, "completion_tokens": 2}}, 6),
    ("deepseek", {"usage": {"prompt_tokens": 10, "completion_tokens": False}}, None),
])
def test_priced_usage_validation(provider, data, expected):
    assert pj.priced_usage(provider, data) == expected


def summary_data():
    value = {"facts": [{"sentence": "AI extracts documents.", "quote": ROW["content"]}],
             "compared_products": []}
    return {"model": "deepseek-flash", "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            "choices": [{"finish_reason": "stop", "message": {"content": encoded(value)}}]}


@pytest.mark.parametrize("case", [
    "absent", "no_actual", "no_response", "http", "wrong_price", "value_error", "key_error",
    "type_error", "index_error", "no_actual_incomplete_receipt", "valid",
])
def test_summary_restore_guards(journal, case):
    body = summary_request(ROW, False)
    data = summary_data()
    status, actual = 200, 6
    if case == "http":
        status = 503
    if case == "wrong_price":
        actual = 7
    if case == "value_error":
        data["model"] = "unknown"
    if case == "key_error":
        del data["choices"][0]["message"]
    if case == "type_error":
        data["choices"] = None
    if case == "index_error":
        data["choices"] = []
    key = request_key("deepseek", body)
    if case != "absent":
        received = {"status_code": status, "body": data}
        if case == "no_actual_incomplete_receipt":
            received = {"status_code": 200}
        saved_call(journal, key, provider="deepseek", error="InvalidSummary",
                   actual=None if case in {"no_actual", "no_actual_incomplete_receipt"} else actual,
                   received=None if case == "no_response" else received)
    before = snapshot(journal)
    assert journal.restore_valid_summary(ROW, False, body, SUMMARY_RECOVERY_VERSION) == (
        case == "valid")
    if case == "valid":
        assert snapshot(journal)[0] == (*before[0][:3], "response", *before[0][4:])
        assert journal.db.execute("SELECT key,reason FROM reviews").fetchall() == [
            (key, "Complete grounded summary revalidated; length is advisory")]
        assert journal.has_response("deepseek", body)
    else:
        assert snapshot(journal) == before
        assert not journal.db.execute("SELECT * FROM reviews").fetchall()


@pytest.mark.parametrize("case", [
    "no_actual", "no_response", "http", "not_dict", "no_choices", "stop", "model", "price",
    "valid_alias",
])
def test_truncated_summary_review_guards(journal, case):
    data = summary_data()
    data["choices"][0]["finish_reason"] = "length"
    status, actual = 200, 6
    if case == "http":
        status = 503
    if case == "not_dict":
        data = []
    if case == "no_choices":
        data["choices"] = []
    if case == "stop":
        data["choices"][0]["finish_reason"] = "stop"
    if case == "model":
        data["model"] = "unknown"
    if case == "price":
        actual = 7
    if case == "valid_alias":
        data["model"] = "deepseek-v4.1-flash"
    key = saved_call(journal, provider="deepseek", error="InvalidSummary",
                     actual=None if case == "no_actual" else actual,
                     received=None if case == "no_response" else {
                         "status_code": status, "body": data})
    before = snapshot(journal)
    assert journal.review_truncated_summaries("review") == ([key] if case == "valid_alias" else [])
    if case == "valid_alias":
        assert snapshot(journal)[0] == (*before[0][:3], "reviewed", *before[0][4:])
        assert journal.db.execute("SELECT key,reason FROM reviews").fetchall() == [(key, "review")]
    else:
        assert snapshot(journal) == before


def test_report_filters_tokens_and_keeps_unknown_cost(journal):
    saved_call(journal, "unknown", committed=100)
    saved_call(journal, "priced", state="response", actual=42, committed=42,
               received={"body": {"usage": {"good": 7, "zero": 0, "negative": -1,
                                           "boolean": True, "float": 1.5, "str": "8"}}})
    saved_call(journal, "list", provider="deepseek", actual=0, committed=0,
               received={"body": []})
    saved_call(journal, "bad_usage", provider="deepseek", actual=0, committed=0,
               received={"body": {"usage": []}})
    report = journal.report()
    assert report == {
        "providers": {
            "jev": {"calls": 2, "committed_usd": .000142, "usage_priced_usd": .000042,
                    "unknown_usage_calls": 1, "states": {"failed": 1, "response": 1},
                    "tokens": {"good": 7, "zero": 0}},
            "deepseek": {"calls": 2, "committed_usd": 0, "usage_priced_usd": 0,
                         "unknown_usage_calls": 0, "states": {"failed": 2}, "tokens": {}}},
        "total_committed_usd": .000142, "approved_caps_usd": {"total": 2, "jev": 1, "deepseek": 1},
        "rates_usd_per_million": {"jev": {"input": .042, "output": 0},
                                 "deepseek": {"input": .30, "output": 1.20}},
        "cost_kind": "usage_priced_peak_not_invoice"}
    assert journal.committed_usd() == .000142
