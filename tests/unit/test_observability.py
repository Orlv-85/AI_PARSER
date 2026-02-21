import logging

from app import observability
from app.observability.logging import JsonFormatter, setup_json_logging


def test_json_formatter_merges_dict_args() -> None:
    formatter = JsonFormatter()
    logger = logging.getLogger("ai_news_test")
    record = logger.makeRecord(
        name="ai_news_test",
        level=logging.INFO,
        fn=__file__,
        lno=1,
        msg="event",
        args=({"run_id": "abc"},),
        exc_info=None,
    )

    payload = formatter.format(record)

    assert '"message": "event"' in payload
    assert '"run_id": "abc"' in payload


def test_json_formatter_ignores_non_dict_args() -> None:
    formatter = JsonFormatter()
    logger = logging.getLogger("ai_news_test_plain")
    record = logger.makeRecord(
        name="ai_news_test_plain",
        level=logging.INFO,
        fn=__file__,
        lno=1,
        msg="event %s",
        args=("x",),
        exc_info=None,
    )

    payload = formatter.format(record)
    assert '"message": "event x"' in payload
    assert "run_id" not in payload


def test_setup_json_logging_configures_logger() -> None:
    logger = setup_json_logging(level=logging.DEBUG)

    assert logger.name == "ai_news"
    assert logger.level == logging.DEBUG
    assert logger.propagate is False
    assert len(logger.handlers) == 1


def test_observability_init_exports_setup_function() -> None:
    assert "setup_json_logging" in observability.__all__
