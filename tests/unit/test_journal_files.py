import os
from datetime import date, datetime, timedelta, timezone

import pytest

from app.storage.journal_files import encoded, fingerprint, private_bytes, private_write

# Fingerprints are stored in journals and manifests; this value must never change.
FIXED = {"b": [1, "é", None, True], "f": 0.1, "d": date(2026, 10, 21),
         "a": datetime(2026, 10, 21, 12, 30, tzinfo=timezone(timedelta(hours=2))),
         "n": datetime(2026, 1, 2, 3, 4, 5)}


def test_fingerprint_of_fixed_input_is_pinned():
    assert encoded(FIXED) == ('{"a": "2026-10-21T10:30:00+00:00", "b": [1, "\\u00e9", null, true], '
                              '"d": "2026-10-21", "f": 0.1, "n": "2026-01-02T03:04:05+00:00"}')
    assert fingerprint(FIXED) == "3088d140b50ebc2dd11ca13c1f9faff5319c2bb69956972a9b4f1d6a563282fe"


def test_private_write_replaces_file_with_owner_only_mode(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_text("old")
    private_write(path, {"k": 1})
    assert path.read_text() == '{"k": 1}\n'
    assert path.stat().st_mode & 0o777 == 0o600
    assert not path.with_suffix(".json.next").exists()


def _write_text(path, text):
    private_write(path, text)


def _write_bytes(path, text):
    private_bytes(path, text.encode())


@pytest.mark.parametrize("write", [_write_text, _write_bytes])
def test_private_writers_create_0600_and_leave_no_staged_file(tmp_path, write):
    path = tmp_path / "new.bin"
    write(path, "x")
    assert path.stat().st_mode & 0o777 == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["new.bin"]


@pytest.mark.parametrize("write", [_write_text, _write_bytes])
def test_private_writers_fsync_before_replace(tmp_path, monkeypatch, write):
    calls = []
    real_replace = os.replace
    monkeypatch.setattr(os, "fsync", lambda fd: calls.append("fsync"))
    monkeypatch.setattr(os, "replace", lambda a, b: (calls.append("replace"), real_replace(a, b)))
    write(tmp_path / "f.bin", "x")
    assert calls == ["fsync", "replace"]


@pytest.mark.parametrize("write", [_write_text, _write_bytes])
def test_private_writers_fail_when_directory_is_missing(tmp_path, write):
    with pytest.raises(FileNotFoundError):
        write(tmp_path / "missing" / "f.bin", "x")
    assert not (tmp_path / "missing").exists()


def test_private_bytes_replaces_existing_content(tmp_path):
    path = tmp_path / "body.bin"
    path.write_bytes(b"old")
    path.chmod(0o644)
    private_bytes(path, b"\x00new")
    assert path.read_bytes() == b"\x00new"
    assert path.stat().st_mode & 0o777 == 0o600
