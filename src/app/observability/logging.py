import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if isinstance(record.args, dict):
            payload.update(record.args)
        if (
            isinstance(record.args, tuple)
            and len(record.args) == 1
            and isinstance(record.args[0], dict)
        ):
            payload.update(record.args[0])
        event_fields = getattr(record, "event_fields", None)
        if isinstance(event_fields, dict):
            payload.update(event_fields)
        return json.dumps(payload, ensure_ascii=True)


def setup_json_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("ai_news")
    logger.setLevel(level)
    logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def log_event(
    logger: logging.Logger,
    *,
    level: int = logging.INFO,
    event: str,
    **event_fields: object,
) -> None:
    logger.log(level, event, extra={"event_fields": event_fields})
