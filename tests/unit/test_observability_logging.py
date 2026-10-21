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

