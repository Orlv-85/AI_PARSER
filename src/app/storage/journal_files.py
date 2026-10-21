"""Canonical JSON, its fingerprint and atomic private file writes for journals and manifests."""
import hashlib
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
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


def private_write(path: Path, value: Any) -> None:
    staged = path.with_suffix(path.suffix + ".next")
    # The directory must also be private; open creates a protected file immediately.
    fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(encoded(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staged, path)
