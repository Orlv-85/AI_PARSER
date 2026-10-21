from datetime import date, datetime, timedelta, timezone

from app.storage.journal_files import encoded, fingerprint, private_write

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
