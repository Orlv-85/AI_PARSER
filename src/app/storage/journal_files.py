"""Atomic private file writes for journals and manifests."""
import os
from pathlib import Path
from typing import Any

from app.core.canonical_json import encoded


def private_bytes(path: Path, value: bytes) -> None:
    staged = path.with_suffix(path.suffix + ".next")
    # The directory must also be private; open creates a protected file immediately.
    fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staged, path)


def private_write(path: Path, value: Any) -> None:
    private_bytes(path, (encoded(value) + "\n").encode())
