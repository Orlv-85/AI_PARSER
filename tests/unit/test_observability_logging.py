import json
import logging

from app.observability.logging import JsonFormatter


def test_json_formatter_merges_tuple_dict_args_and_event_fields() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="event=%s",
        args=({"outcome": "ok"},),
        exc_info=None,
    )
    # Force tuple payload branch explicitly; LogRecord normalizes single-dict args to dict.
    record.args = ({"outcome": "ok"},)
    record.event_fields = {"tool": "news.list"}

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "event={'outcome': 'ok'}"
    assert payload["outcome"] == "ok"
    assert payload["tool"] == "news.list"



def test_json_formatter_keeps_the_traceback_of_a_logged_exception() -> None:
    formatter = JsonFormatter()
    error = ValueError("bad payload")
    record = logging.LogRecord("test.logger", logging.ERROR, __file__, 10, "event_failed", (),
                               (ValueError, error, None))
    payload = json.loads(formatter.format(record))
    assert payload["traceback"] == "ValueError: bad payload"
    plain = logging.LogRecord("test.logger", logging.INFO, __file__, 10, "ok", None, None)
    assert "traceback" not in json.loads(formatter.format(plain))
