"""Canonical JSON and its fingerprint for journals, manifests and provider requests."""
import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any


def serialize(value: Any) -> str:
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or UTC).astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def encoded(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, default=serialize)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(encoded(value).encode()).hexdigest()
