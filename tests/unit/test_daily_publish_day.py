"""publish_day guards and outputs; see enrichment.md."""
import json

import httpx
import pytest
from daily_fixtures import (  # pylint: disable=import-error,unused-import
    SOURCE,
    TARGET,
    article,
    daily,
    daily_session,  # noqa: F401
    mock_client,
    provider_response,
    settings,
)
from pydantic import SecretStr

from app.storage.digest_repo import NewsDigestRepo


@pytest.mark.parametrize(("change", "reason"), [
    ({"semantic_admission_enabled": False}, "mandatory_admission_disabled"),
    ({"jev_api_key": None}, "missing_provider_key"),
    ({"ds_api_key": SecretStr("  ")}, "missing_provider_key"),
])
def test_publish_day_guard_raises_before_any_journal_file(session, tmp_path, change, reason):
    article(session)
    config = settings()
    for name, value in change.items():
        setattr(config, name, value)
    with pytest.raises(ValueError, match=reason):
        daily.publish_day(session, config, TARGET, tmp_path / "cache")
    assert not list((tmp_path / "cache").rglob("journal.sqlite3*"))
    assert not (tmp_path / "cache" / TARGET.isoformat() / "report.json").exists()


def test_publish_day_writes_progress_json_after_each_non_reused_article(
        session, tmp_path, monkeypatch):
    for index in (1, 2):
        article(session, index).content = "short"
    session.commit()
    snapshots = []
    real_write = daily.private_write

    def spy(path, value):
        if path.name == "progress.json":
            snapshots.append(json.loads(json.dumps(value)))
        real_write(path, value)

    monkeypatch.setattr(daily, "private_write", spy)
    mock_client(monkeypatch, lambda _r: pytest.fail("Paid request without source"))
    daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    reason = "insufficient_source_or_date_evidence"
    assert snapshots == [
        {"counts": {reason: 1}, "held": [{"article_id": 1, "reason": reason}]},
        {"counts": {reason: 2}, "held": [{"article_id": 1, "reason": reason},
                                         {"article_id": 2, "reason": reason}]}]
    progress = tmp_path / "cache" / TARGET.isoformat() / "progress.json"
    assert json.loads(progress.read_text()) == snapshots[-1]


def test_publish_day_progress_json_records_held_article(session, tmp_path, monkeypatch):
    held = article(session)
    held.content = "short"
    session.commit()
    mock_client(monkeypatch, lambda _r: pytest.fail("Paid request without source"))
    daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    progress = tmp_path / "cache" / TARGET.isoformat() / "progress.json"
    assert json.loads(progress.read_text()) == {
        "counts": {"insufficient_source_or_date_evidence": 1},
        "held": [{"article_id": held.id, "reason": "insufficient_source_or_date_evidence"}]}


def test_publish_day_backup_file_holds_previous_digest(session, tmp_path, monkeypatch):
    article(session, proof=True)
    repo = NewsDigestRepo(session)
    repo.save_digest(report_date=TARGET, groups=[{"title": "Old group", "items": [
        {"title": "Old title", "summary": "Old summary", "url": "https://old.org/a"}]}])
    session.commit()
    created = repo.get_digest(report_date=TARGET).created_at
    mock_client(monkeypatch, lambda _r: pytest.fail("Paid request for cached data"))
    result = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    backup = tmp_path / "cache" / TARGET.isoformat() / result["backup_path"].split("/")[-1]
    assert backup.name.startswith("digest-before-") and backup.suffix == ".json"
    assert json.loads(backup.read_text()) == {
        "report_date": TARGET.isoformat(), "created_at": created.isoformat(),
        "groups": [{"title": "Old group", "items": [
            {"title": "Old title", "summary": "Old summary", "url": "https://old.org/a"}]}]}


def test_publish_day_commits_each_enrichment_before_a_later_failure(
        session, tmp_path, monkeypatch):
    first = article(session, 1)
    second = article(session, 2)
    second.content = SOURCE + " A second, different article body."
    session.commit()
    monkeypatch.setattr("app.storage.provider_journal.time.sleep", lambda _seconds: None)
    calls = []

    def respond(request):
        calls.append(request)
        if len(calls) > 3:
            raise httpx.ConnectError("down", request=request)
        return provider_response(request)

    mock_client(monkeypatch, respond)
    result = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert result["state"] == "failed_preserved_previous"
    assert daily.reusable(first) and not daily.reusable(second)


def test_publish_day_all_reused_writes_no_progress_json(session, tmp_path, monkeypatch):
    article(session, 1, proof=True)
    article(session, 2, proof=True)
    mock_client(monkeypatch, lambda _r: pytest.fail("Paid request for cached data"))
    result = daily.publish_day(session, settings(), TARGET, tmp_path / "cache")
    assert result["counts"] == {"reused": 2}
    assert not (tmp_path / "cache" / TARGET.isoformat() / "progress.json").exists()
