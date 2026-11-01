from types import SimpleNamespace

import pytest

from app.core.sources.candidate_fields import read_optional_int, read_optional_str, read_str


def _both(**fields):
    return [fields, SimpleNamespace(**fields)]


@pytest.mark.parametrize("candidate", _both(name="x", count="7", empty=None))
def test_read_str_returns_text_of_present_field(candidate) -> None:
    assert read_str(candidate, "name") == "x"
    assert read_str(candidate, "count") == "7"


@pytest.mark.parametrize("candidate", _both(empty=None))
def test_read_str_default_covers_absent_field_only_else_raises(candidate) -> None:
    assert read_str(candidate, "absent", default="draft") == "draft"
    for name in ("absent", "empty"):
        with pytest.raises(ValueError, match=f"candidate field is required: {name}"):
            read_str(candidate, name)
    with pytest.raises(ValueError, match="candidate field is required: empty"):
        read_str(candidate, "empty", default="draft")


def test_read_str_casts_non_text_values() -> None:
    assert read_str({"id": 5}, "id") == "5"


@pytest.mark.parametrize("candidate", _both(a=3, b=None))
def test_read_optional_str_and_int(candidate) -> None:
    assert read_optional_str(candidate, "a") == "3"
    assert read_optional_str(candidate, "b") is None
    assert read_optional_str(candidate, "absent") is None
    assert read_optional_int(candidate, "a") == 3
    assert read_optional_int(candidate, "b") is None
    assert read_optional_int(candidate, "absent") is None


def test_read_optional_int_casts_text_and_rejects_garbage() -> None:
    assert read_optional_int({"n": "9"}, "n") == 9
    with pytest.raises(ValueError):
        read_optional_int({"n": "x"}, "n")
