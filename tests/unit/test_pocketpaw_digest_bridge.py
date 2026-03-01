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
    assert normalized["title"] == "Daily AI News Digest"
    assert normalized["generated_by"] == "pocketpaw-antigravity"
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
