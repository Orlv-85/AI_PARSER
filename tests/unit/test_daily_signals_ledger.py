import json
import stat

import httpx
import pytest

from app.storage.daily_signals_ledger import Dispatch, LedgerStop, SignalsLedger

BODY = {"model": "deepseek-flash", "messages": []}
RESERVED = 6000


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def ok_body(prompt=1000, completion=200):
    return {"model": "deepseek-flash", "choices": [{"finish_reason": "stop",
                                                    "message": {"content": "{}"}}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion}}


def ledger(tmp_path, handler, *, run_id="run-1", max_calls=10, max_usd_micro=100000,
           deadline=10000.0, clock=None):
    calls = []

    def counted(request):
        calls.append(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer secret-key"
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        return handler(request)

    value = SignalsLedger(tmp_path / "cache" / "ledger.sqlite3", run_id=run_id,
                          api_key="secret-key", max_calls=max_calls,
                          max_usd_micro=max_usd_micro, deadline=deadline,
                          clock=clock or Clock(), transport=httpx.MockTransport(counted))
    return value, calls


def send(value, key="k1", reserved=RESERVED):
    return value.dispatch(BODY, request_key=key, reserved_micro=reserved, article_id=1,
                          version="v", scope_day="2026-10-16")


def test_one_post_per_dispatch_and_replay(tmp_path):
    value, calls = ledger(tmp_path, lambda r: httpx.Response(200, json=ok_body()))
    first = send(value)
    assert (first.state, first.status_code, first.cost_micro, first.replayed) == \
        ("response", 200, 540, False)
    assert send(value) == Dispatch("response", 200, first.data, 0, replayed=True)
    assert len(calls) == 1 and value.run_calls() == 1
    assert value.run_spend_micro() == 540
    mode = stat.S_IMODE((tmp_path / "cache" / "ledger.sqlite3").stat().st_mode)
    assert mode == 0o600
    value.close()
    again, calls = ledger(tmp_path, lambda r: httpx.Response(500), run_id="run-2")
    assert send(again).replayed and not calls
    again.close()


def test_pre_post_caps(tmp_path):
    value, calls = ledger(tmp_path, lambda r: httpx.Response(200, json=ok_body()), max_calls=2)
    send(value, "a")
    send(value, "b")
    with pytest.raises(LedgerStop, match="cap_reached"):
        send(value, "c")
    assert len(calls) == 2
    value.close()
    cheap, calls = ledger(tmp_path, lambda r: httpx.Response(200, json=ok_body()), run_id="r2",
                          max_usd_micro=RESERVED + 100)
    send(cheap, "d")
    with pytest.raises(LedgerStop, match="cap_reached"):
        send(cheap, "e")  # 540 spent + 6000 reserved > 6100
    assert len(calls) == 1
    cheap.close()


def test_deadline_reserve(tmp_path):
    clock = Clock()
    value, calls = ledger(tmp_path, lambda r: httpx.Response(200, json=ok_body()),
                          deadline=200.0, clock=clock)
    clock.now = 104.0
    send(value, "a")
    clock.now = 106.0
    with pytest.raises(LedgerStop, match="deadline_reached"):
        send(value, "b")
    assert len(calls) == 1 and value.run_calls() == 1
    value.close()


def test_slow_stream_aborted_at_body_deadline(tmp_path):
    clock = Clock()

    def chunks():
        for _ in range(100):
            clock.now += 1.0
            yield b" "

    value, _ = ledger(tmp_path, lambda r: httpx.Response(200, content=chunks()), clock=clock)
    result = send(value)
    assert (result.state, result.cost_micro, result.data) == ("unknown", RESERVED, None)
    assert 60 <= clock.now < 70
    value.close()


@pytest.mark.parametrize(("handler", "state", "cost"), [
    (lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow")), "unknown", RESERVED),
    (lambda r: (_ for _ in ()).throw(httpx.ConnectError("down")), "unknown", RESERVED),
    (lambda r: httpx.Response(500, json={"error": "boom", **{"usage": ok_body()["usage"]}}),
     "error_billed", 540),
    (lambda r: httpx.Response(503, json={"error": {"message": "overloaded"}}), "transient", 0),
    (lambda r: httpx.Response(200, text="not json"), "unknown", RESERVED),
    (lambda r: httpx.Response(200, json={"choices": []}), "unknown", RESERVED),
])
def test_outcomes(tmp_path, handler, state, cost):
    value, _ = ledger(tmp_path, handler)
    result = send(value)
    assert (result.state, result.cost_micro) == (state, cost)
    assert value.run_spend_micro() == cost
    assert value.replay("k1") is None
    value.close()


def test_actual_above_reservation_stops_run(tmp_path):
    value, calls = ledger(tmp_path, lambda r: httpx.Response(200, json=ok_body(10000, 5000)))
    result = send(value, reserved=1000)
    assert result.state == "response" and result.cost_micro == 9000
    with pytest.raises(LedgerStop, match="usage_exceeded_bound"):
        send(value, "k2")
    assert len(calls) == 1
    value.close()


def test_three_consecutive_failures_stop(tmp_path):
    value, calls = ledger(tmp_path, lambda r: httpx.Response(503, json={"error": "busy"}))
    for key in ("a", "b", "c"):
        assert send(value, key).state == "transient"
    with pytest.raises(LedgerStop, match="provider_unavailable"):
        send(value, "d")
    assert len(calls) == 3
    value.close()


def test_success_resets_failure_streak(tmp_path):
    answers = iter([503, 503, 200, 503, 503, 200])

    def handler(_request):
        code = next(answers)
        return httpx.Response(200, json=ok_body()) if code == 200 else \
            httpx.Response(503, json={"error": "busy"})

    value, calls = ledger(tmp_path, handler)
    for key in "abcdef":
        send(value, key)
    assert len(calls) == 6
    value.close()


def test_crash_left_reserved_row_counts_as_unknown(tmp_path):
    value, _ = ledger(tmp_path, lambda r: httpx.Response(200, json=ok_body()))
    value.db.execute("INSERT INTO calls (request_key, run_id, state, reserved_micro, created_at) "
                     "VALUES ('x', 'old-run', 'reserved', 6000, 'now')")
    value.close()
    later, _ = ledger(tmp_path, lambda r: httpx.Response(200, json=ok_body()), run_id="old-run-2")
    state, reserved = later.db.execute(
        "SELECT state, reserved_micro FROM calls WHERE request_key = 'x'").fetchone()
    assert (state, reserved) == ("unknown", 6000)
    later.close()


def test_ledger_never_stores_the_key(tmp_path):
    value, _ = ledger(tmp_path, lambda r: httpx.Response(200, json=ok_body()))
    send(value)
    value.close()
    assert b"secret-key" not in (tmp_path / "cache" / "ledger.sqlite3").read_bytes()
