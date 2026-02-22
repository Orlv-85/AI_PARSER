import json
import logging

from app.observability.logging import JsonFormatter, log_mcp_auth_event


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


def test_log_mcp_auth_event_without_subject() -> None:
    logger = logging.getLogger("test.observability.logging")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)

    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger.addHandler(_Collect())
    log_mcp_auth_event(logger, event="mcp_auth_failed", outcome="denied", tool="news.list")

    assert len(records) == 1
    event_fields = records[0].__dict__["event_fields"]
    assert event_fields["tool"] == "news.list"
    assert event_fields["outcome"] == "denied"
    assert "subject" not in event_fields
