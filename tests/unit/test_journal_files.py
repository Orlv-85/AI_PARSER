import os

import pytest

from app.storage.journal_files import private_bytes, private_write


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


@pytest.mark.parametrize("write", [_write_text, _write_bytes])
def test_private_writers_tighten_stale_staged_file_left_by_a_crash(tmp_path, write):
    path = tmp_path / "f.bin"
    stale = tmp_path / "f.bin.next"
    stale.write_text("partial")
    stale.chmod(0o644)
    write(path, "x")
    assert path.stat().st_mode & 0o777 == 0o600
    assert not stale.exists()
