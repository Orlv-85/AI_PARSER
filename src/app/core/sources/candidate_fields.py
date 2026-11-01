"""Read one field of a source candidate given as a dict or as an object.

Shared by core/sources and the storage repos; see onboarding.md.
"""

from __future__ import annotations

from typing import Any


def _raw(candidate: object, field_name: str, default: object = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(field_name, default)
    return getattr(candidate, field_name, default)


def read_str(candidate: object, field_name: str, default: str | None = None) -> str:
    value = _raw(candidate, field_name, default)
    if value is None:
        raise ValueError(f"candidate field is required: {field_name}")
    return str(value)


def read_optional_str(candidate: object, field_name: str) -> str | None:
    value = _raw(candidate, field_name)
    return None if value is None else str(value)


def read_optional_int(candidate: object, field_name: str) -> int | None:
    value = _raw(candidate, field_name)
    return None if value is None else int(value)
