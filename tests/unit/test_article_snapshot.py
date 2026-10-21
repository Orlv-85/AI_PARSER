from datetime import UTC, datetime

from app.storage.article_snapshot import EXPORT_TABLES, dependencies, normalize_snapshot
from app.storage.journal_files import fingerprint


def article(**overrides):
    return {"id": 1, "url": "https://example.com/about", "url_canonical":
            "https://example.com/about", "url_canonical_hash": "hash", "source_id": None,
            "title": "About us", "summary": None, "content": "Company history " * 30,
            "published_at": None, "rank_score": 0, **overrides}


def snapshot():
    tables = {name: [] for name in EXPORT_TABLES}
    tables["articles"] = [article()]
    return {"tables": tables, "screening": {"model": "jev-1.13.0", "policy_version": "p1",
                                           "prompt_version": "q1"}}


def test_retained_references_follow_parent_rows():
    saved = snapshot()
    tables = saved["tables"]
    tables["weekly_decisions"] = [{"key": "decision", "payload": '{"article_id":1}'}]
    tables["weekly_snapshots"] = [{"id": "snap", "payload": '{"id":"article-1"}'}]
    tables["weekly_publications"] = [{"report_date": "2026-10-04", "snapshot_id": "snap"}]
    tables["news_digest_items"] = [{"id": 3, "group_id": 2, "url": article()["url"]}]
    tables["news_digest_groups"] = [{"id": 2, "report_id": 1}]
    tables["news_digest_reports"] = [{"id": 1}]
    names = {ref["table"] for ref in dependencies(tables)[1]}
    assert {"weekly_decisions", "weekly_snapshots", "weekly_publications", "news_digest_items",
            "news_digest_groups", "news_digest_reports"} <= names


def test_invalid_embedded_urls_do_not_break_dependency_inventory():
    saved = snapshot()
    saved["tables"]["weekly_jobs"] = [{"id": "job", "input_payload":
                                      'Text: http://localhost:4723\\ and unrelated content'}]
    assert dependencies(saved["tables"]) == {1: []}


def test_timestamp_normalization():
    saved = snapshot()
    saved["tables"]["articles"][0]["published_at"] = "2026-10-10 20:00:00+00:00"
    normalized = normalize_snapshot(saved)
    row = dict(normalized["tables"]["articles"][0])
    row["published_at"] = datetime(2026, 10, 10, 20, tzinfo=UTC)
    assert fingerprint(row) == fingerprint(normalized["tables"]["articles"][0])
