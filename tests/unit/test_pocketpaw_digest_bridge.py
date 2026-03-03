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


def test_normalize_summary_batch_keeps_valid_items() -> None:
    bridge = _load_bridge_module()

    payload = {
        "report_date": "2026-03-01",
        "items": [
            {
                "url": "https://example.com/1",
                "summary": "Short technical summary.",
            },
            {
                "url": "not-a-url",
                "summary": "Dropped.",
            },
        ],
    }

    normalized = bridge.normalize_summary_batch(payload, report_date="2026-03-01")

    assert normalized == {"https://example.com/1": "Short technical summary."}


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
    categories = [group["title"] for group in payload["groups"]]

    assert payload["report_date"] == "2026-03-01"
    assert urls == ["https://example.com/1", "https://example.com/2"]
    assert categories == ["Business & Product"]
    assert payload["groups"][0]["items"][0]["summary"].startswith("Source: Tech Source.")


def test_build_feed_digest_payload_rejects_invalid_feed_row() -> None:
    bridge = _load_bridge_module()

    with pytest.raises(ValueError, match="valid title/url"):
        bridge.build_feed_digest_payload(
            items=[{"title": "Missing URL"}],
            report_date="2026-03-01",
        )


def test_build_feed_digest_payload_humanizes_url_titles() -> None:
    bridge = _load_bridge_module()

    payload = bridge.build_feed_digest_payload(
        items=[
            {
                "title": "https://www.together.ai/blog/together-python-sdk-2-0",
                "url": "https://www.together.ai/blog/together-python-sdk-2-0",
                "source_name": "Together",
                "published_at": "2026-03-02T10:00:00Z",
            }
        ],
        report_date="2026-03-02",
    )

    item = payload["groups"][0]["items"][0]

    assert item["title"] == "Together Python SDK 2 0"


def test_build_feed_digest_payload_enriches_short_titles_from_summary() -> None:
    bridge = _load_bridge_module()

    payload = bridge.build_categorized_digest_payload(
        items=[
            {
                "title": "Medusa",
                "url": "https://www.together.ai/blog/medusa",
                "source_name": "Together",
                "published_at": "2026-03-02T10:00:00Z",
            }
        ],
        report_date="2026-03-02",
        summaries_by_url={
            "https://www.together.ai/blog/medusa": (
                "Speculative decoding technique for faster long-context inference in production."
            )
        },
    )

    item = payload["groups"][0]["items"][0]

    assert item["title"] == (
        "Medusa: Speculative decoding technique for faster long-context inference in production"
    )


def test_build_feed_digest_payload_prefixes_source_for_short_titles_without_ai_summary() -> None:
    bridge = _load_bridge_module()

    payload = bridge.build_feed_digest_payload(
        items=[
            {
                "title": "Medusa",
                "url": "https://www.together.ai/blog/medusa",
                "source_name": "Together",
                "published_at": "2026-03-02T10:00:00Z",
            }
        ],
        report_date="2026-03-02",
    )

    item = payload["groups"][0]["items"][0]

    assert item["title"] == "Together: Medusa"


def test_build_feed_digest_payload_cleans_noisy_long_titles() -> None:
    bridge = _load_bridge_module()

    payload = bridge.build_feed_digest_payload(
        items=[
            {
                "title": (
                    "Beyond LGTM in the age of AI.\n"
                    "Code Reviewwith your rules & standards.for complex codebases."
                    "that continuously learns.with #1 precision & recall."
                ),
                "url": "https://example.com/review",
                "source_name": "Graphite",
                "published_at": "2026-03-01T10:00:00Z",
            }
        ],
        report_date="2026-03-01",
    )

    item = payload["groups"][0]["items"][0]

    assert item["title"] == "Beyond LGTM in the age of AI. Code Review with your rules & standards"


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
    assert repaired["groups"][0]["title"] == "Business & Product"


def test_chunk_feed_items_splits_large_batches() -> None:
    bridge = _load_bridge_module()

    chunks = bridge.chunk_feed_items(
        [{"url": f"https://example.com/{index}"} for index in range(5)],
        chunk_size=2,
    )

    assert [len(chunk) for chunk in chunks] == [2, 2, 1]


def test_run_antigravity_chunk_retries_after_non_json_response() -> None:
    bridge = _load_bridge_module()
    responses = iter(
        [
            {"content": [{"type": "text", "text": "not json"}]},
            {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"report_date":"2026-03-01","items":'
                            '[{"url":"https://example.com/1","summary":"Short summary."}]}'
                        ),
                    }
                ]
            },
        ]
    )

    original = bridge.read_json_response
    bridge.read_json_response = lambda *args, **kwargs: next(responses)
    try:
        normalized = bridge.run_antigravity_chunk(
            admin_url="http://example.test",
            api_key="key",
            model="gemini-3-flash",
            prompt="Prompt",
            report_date="2026-03-01",
            articles=[{"title": "Item", "url": "https://example.com/1"}],
        )
    finally:
        bridge.read_json_response = original

    assert normalized == {"https://example.com/1": "Short summary."}


def test_run_antigravity_chunk_retries_after_network_timeout() -> None:
    bridge = _load_bridge_module()
    responses = iter(
        [
            RuntimeError("Network timeout for http://example.test/v1/messages"),
            {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"report_date":"2026-03-01","items":'
                            '[{"url":"https://example.com/1","summary":"Short summary."}]}'
                        ),
                    }
                ]
            },
        ]
    )

    def fake_read_json_response(*_args, **_kwargs):
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    original = bridge.read_json_response
    bridge.read_json_response = fake_read_json_response
    try:
        normalized = bridge.run_antigravity_chunk(
            admin_url="http://example.test",
            api_key="key",
            model="gemini-3-flash",
            prompt="Prompt",
            report_date="2026-03-01",
            articles=[{"title": "Item", "url": "https://example.com/1"}],
        )
    finally:
        bridge.read_json_response = original

    assert normalized == {"https://example.com/1": "Short summary."}
