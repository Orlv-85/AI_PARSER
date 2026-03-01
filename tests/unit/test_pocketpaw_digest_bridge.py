from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_bridge_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "pocketpaw_digest_bridge.py"
    spec = importlib.util.spec_from_file_location("pocketpaw_digest_bridge", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_digest_keeps_valid_groups_and_items() -> None:
    bridge = _load_bridge_module()

    payload = {
        "report_date": "2026-03-01",
        "title": "anything",
        "generated_by": "antigravity",
        "groups": [
            {
                "title": "AI Coding",
                "items": [
                    {
                        "article_id": 5,
                        "title": "Inside Replit's Snapshot Engine",
                        "summary": "Technical breakdown of snapshot rollback behavior.",
                        "url": "https://example.com/replit",
                    },
                    {
                        "title": "",
                        "summary": "This invalid item should be dropped.",
                        "url": "https://example.com/drop-me",
                    },
                ],
            }
        ],
    }

    normalized = bridge.normalize_digest(payload, report_date="2026-03-01")

    assert normalized["report_date"] == "2026-03-01"
    assert normalized["groups"] == [
        {
            "title": "AI Coding",
            "items": [
                {
                    "article_id": 5,
                    "title": "Inside Replit's Snapshot Engine",
                    "summary": "Technical breakdown of snapshot rollback behavior.",
                    "url": "https://example.com/replit",
                }
            ],
        }
    ]


def test_normalize_digest_rejects_wrong_report_date() -> None:
    bridge = _load_bridge_module()

    payload = {
        "report_date": "2026-03-02",
        "groups": [{"title": "AI Coding", "items": []}],
    }

    with pytest.raises(ValueError, match="report_date"):
        bridge.normalize_digest(payload, report_date="2026-03-01")


def test_normalize_digest_rejects_when_no_valid_groups_remain() -> None:
    bridge = _load_bridge_module()

    payload = {
        "report_date": "2026-03-01",
        "groups": [
            {
                "title": "AI Coding",
                "items": [
                    {
                        "title": "Bad URL",
                        "summary": "This item should be rejected.",
                        "url": "not-a-url",
                    }
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match="no valid groups"):
        bridge.normalize_digest(payload, report_date="2026-03-01")


def test_build_feed_digest_payload_includes_every_link_once() -> None:
    bridge = _load_bridge_module()

    payload = bridge.build_feed_digest_payload(
        items=[
            {
                "article_id": 10,
                "title": "First item",
                "url": "https://example.com/1",
                "source_name": "Tech Source",
                "published_at": "2026-03-01T10:00:00Z",
            },
            {
                "article_id": 11,
                "title": "Second item",
                "url": "https://example.com/2",
                "source_name": "Infra Source",
                "published_at": "2026-03-01T11:00:00Z",
            },
        ],
        report_date="2026-03-01",
    )

    urls = [item["url"] for group in payload["groups"] for item in group["items"]]

    assert payload["report_date"] == "2026-03-01"
    assert urls == ["https://example.com/1", "https://example.com/2"]
    assert payload["groups"][0]["items"][0]["summary"].startswith("Source: Tech Source.")


def test_build_feed_digest_payload_rejects_invalid_feed_row() -> None:
    bridge = _load_bridge_module()

    with pytest.raises(ValueError, match="valid title/url"):
        bridge.build_feed_digest_payload(
            items=[{"title": "Missing URL"}],
            report_date="2026-03-01",
        )


def test_repair_digest_coverage_adds_missing_links_without_duplicates() -> None:
    bridge = _load_bridge_module()

    repaired = bridge.repair_digest_coverage(
        digest={
            "report_date": "2026-03-01",
            "groups": [
                {
                    "title": "AI Coding",
                    "items": [
                        {
                            "title": "First item",
                            "summary": "AI summary",
                            "url": "https://example.com/1",
                        },
                        {
                            "title": "Duplicate item",
                            "summary": "Duplicate should be dropped",
                            "url": "https://example.com/1",
                        },
                    ],
                }
            ],
        },
        feed_items=[
            {
                "title": "First item",
                "url": "https://example.com/1",
                "source_name": "One",
                "published_at": "2026-03-01T10:00:00Z",
            },
            {
                "title": "Second item",
                "url": "https://example.com/2",
                "source_name": "Two",
                "published_at": "2026-03-01T11:00:00Z",
            },
        ],
        report_date="2026-03-01",
    )

    urls = [item["url"] for group in repaired["groups"] for item in group["items"]]

    assert urls == ["https://example.com/1", "https://example.com/2"]
    assert repaired["groups"][-1]["title"].startswith("Additional Coverage")
