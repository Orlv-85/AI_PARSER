from __future__ import annotations

import importlib.util
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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


def test_normalize_title_batch_keeps_valid_items() -> None:
    bridge = _load_bridge_module()

    payload = {
        "report_date": "2026-03-01",
        "items": [
            {
                "url": "https://example.com/1",
                "title": "Short headline",
            },
            {
                "url": "not-a-url",
                "title": "Dropped",
            },
        ],
    }

    normalized = bridge.normalize_title_batch(payload, report_date="2026-03-01")

    assert normalized == {"https://example.com/1": "Short headline"}


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


def test_build_feed_digest_payload_preserves_known_brand_casing() -> None:
    bridge = _load_bridge_module()

    payload = bridge.build_feed_digest_payload(
        items=[
            {
                "title": "Building Telco Reasoning Models for Autonomous Networks with NVIDIA NeMo",
                "url": "https://example.com/nemo",
                "source_name": "NVIDIA",
                "published_at": "2026-03-01T10:00:00Z",
            },
            {
                "title": "AI code help with Amazon CodeWhisperer",
                "url": "https://example.com/codewhisperer",
                "source_name": "AWS",
                "published_at": "2026-03-01T11:00:00Z",
            },
            {
                "title": "Workflows Beta: Complex AI Apps with LlamaIndex",
                "url": "https://example.com/llamaindex",
                "source_name": "LlamaIndex",
                "published_at": "2026-03-01T12:00:00Z",
            },
        ],
        report_date="2026-03-01",
    )

    titles = [item["title"] for group in payload["groups"] for item in group["items"]]

    assert "Building Telco Reasoning Models for Autonomous Networks with NVIDIA NeMo" in titles
    assert "AI code help with Amazon CodeWhisperer" in titles
    assert "Workflows Beta: Complex AI Apps with LlamaIndex" in titles


def test_build_feed_digest_payload_rewrites_generic_update_titles_from_summary() -> None:
    bridge = _load_bridge_module()

    payload = bridge.build_categorized_digest_payload(
        items=[
            {
                "title": "August 2023 Pricing Update",
                "url": "https://example.com/pricing-update",
                "source_name": "Together AI Blog",
                "published_at": "2026-03-02T10:00:00Z",
            }
        ],
        report_date="2026-03-02",
        summaries_by_url={
            "https://example.com/pricing-update": (
                "Together AI revised inference and fine-tuning pricing to improve cost-efficiency "
                "for developers deploying models at scale."
            )
        },
    )

    item = payload["groups"][0]["items"][0]

    assert item["title"] == (
        "Together AI revised inference and fine-tuning pricing to improve cost-efficiency..."
    )


def test_build_feed_digest_payload_rewrites_sentence_like_titles_from_summary() -> None:
    bridge = _load_bridge_module()

    payload = bridge.build_categorized_digest_payload(
        items=[
            {
                "title": (
                    "Minions is an architecture designed to deploy specialized, smaller models "
                    "for sub-task execution"
                ),
                "url": "https://example.com/minions",
                "source_name": "Together AI Blog",
                "published_at": "2026-03-02T10:00:00Z",
            }
        ],
        report_date="2026-03-02",
        summaries_by_url={
            "https://example.com/minions": (
                "Modular architecture for specialized smaller models in larger autonomous "
                "agent workflows."
            )
        },
    )

    item = payload["groups"][0]["items"][0]

    assert item["title"] == (
        "Modular architecture for specialized smaller models in larger autonomous agent wo..."
    )


def test_build_feed_weekly_payload_computes_sections() -> None:
    bridge = _load_bridge_module()

    payload = bridge.build_feed_weekly_payload(
        recent_items=[
            {
                "title": "AI Browser Launches",
                "url": "https://example.com/new",
                "summary": "New browser story.",
                "published_at": "2026-03-08T10:00:00Z",
                "rank_score": 0.8,
            },
            {
                "title": "Coding Agents Expand",
                "url": "https://example.com/up-recent",
                "summary": "Coding agents accelerating.",
                "published_at": "2026-03-07T10:00:00Z",
                "rank_score": 0.9,
            },
        ],
        prior_items=[
            {
                "title": "Coding Agents Expand",
                "url": "https://example.com/up-prior",
                "summary": "Prior baseline lower score.",
                "published_at": "2026-02-28T10:00:00Z",
                "rank_score": 0.5,
            },
            {
                "title": "Standalone Vector DBs Cool Off",
                "url": "https://example.com/down-prior",
                "summary": "Prior topic disappeared.",
                "published_at": "2026-02-27T10:00:00Z",
                "rank_score": 0.7,
            },
        ],
        report_date="2026-03-08",
    )

    assert payload["report_date"] == "2026-03-08"
    assert payload["date_from"] == "2026-03-02"
    assert payload["date_to"] == "2026-03-08"
    assert [item["title"] for item in payload["new"]] == ["AI Browser Launches"]
    assert [item["title"] for item in payload["trending_up"]] == ["Coding Agents Expand"]
    assert [item["title"] for item in payload["trending_down"]] == [
        "Standalone Vector DBs Cool Off"
    ]
    assert "Signals: 1 new, 1 trending up, 1 trending down." in payload["summary"]
    assert "Top focus: AI Browser Launches, Coding Agents Expand." in payload["summary"]


def test_build_feed_weekly_payload_handles_empty_recent_window() -> None:
    bridge = _load_bridge_module()

    payload = bridge.build_feed_weekly_payload(
        recent_items=[],
        prior_items=[],
        report_date="2026-03-08",
    )

    assert payload["new"] == []
    assert payload["trending_up"] == []
    assert payload["trending_down"] == []
    assert payload["summary"] == "No AI news signals between 2026-03-02 and 2026-03-08."


def test_build_feed_weekly_payload_matches_same_topic_with_title_variants() -> None:
    bridge = _load_bridge_module()

    payload = bridge.build_feed_weekly_payload(
        recent_items=[
            {
                "title": "NVIDIA TensorRT automatically optimizes inference for RTX",
                "url": "https://example.com/recent-topic",
                "summary": "Recent week variant with stronger momentum.",
                "published_at": "2026-03-08T10:00:00Z",
                "rank_score": 0.92,
            }
        ],
        prior_items=[
            {
                "title": "Adaptive Inference in NVIDIA TensorRT for RTX optimization",
                "url": "https://example.com/prior-topic",
                "summary": "Prior week wording of the same topic.",
                "published_at": "2026-03-01T10:00:00Z",
                "rank_score": 0.31,
            }
        ],
        report_date="2026-03-08",
    )

    assert payload["new"] == []
    assert [item["title"] for item in payload["trending_up"]] == [
        "NVIDIA TensorRT automatically optimizes inference for RTX"
    ]


def test_build_feed_weekly_payload_uses_source_fallback_for_missing_item_summary() -> None:
    bridge = _load_bridge_module()

    payload = bridge.build_feed_weekly_payload(
        recent_items=[
            {
                "title": "DeepSeek Can Buy Nvidia H200 AI Chips",
                "url": "https://example.com/h200",
                "summary": "",
                "published_at": "2026-03-08T10:00:00Z",
                "source_name": "AI Wire",
                "rank_score": 0.9,
            }
        ],
        prior_items=[],
        report_date="2026-03-08",
    )

    assert payload["new"][0]["summary"] == "Reported by AI Wire on 2026-03-08."


def test_fetch_news_links_range_paginates_daily_results() -> None:
    bridge = _load_bridge_module()
    captured_queries: list[dict[str, str]] = []

    def fake_read_json_response(url: str, **_kwargs):
        parsed = urlparse(url)
        query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        captured_queries.append(query)
        if query.get("date") != "2026-03-08":
            return []
        if query.get("offset") == "0":
            return [
                {
                    "title": "A",
                    "url": "https://example.com/a",
                    "published_at": "2026-03-08T10:00:00Z",
                }
            ]
        return []

    original = bridge.read_json_response
    bridge.read_json_response = fake_read_json_response
    try:
        fetch_range = bridge.__dict__["_fetch_news_links_range"]
        rows = fetch_range(
            base_url="http://example.test",
            date_from="2026-03-08",
            date_to="2026-03-08",
            limit=1,
        )
    finally:
        bridge.read_json_response = original

    assert len(rows) == 1
    assert captured_queries == [
        {"date": "2026-03-08", "limit": "1", "offset": "0"},
        {"date": "2026-03-08", "limit": "1", "offset": "1"},
    ]


def test_categorize_digest_item_prefers_rag_for_true_rag_signals() -> None:
    bridge = _load_bridge_module()

    category = bridge.categorize_digest_item(
        row={
            "title": "Hybrid search with reranking for enterprise RAG",
            "source_name": "Docs",
            "url": "https://example.com/rag",
        },
        summary="Combines vector retrieval with reranking for knowledge base grounding.",
    )

    assert category == "RAG & Data Systems"


def test_categorize_digest_item_keeps_infra_out_of_rag_bucket() -> None:
    bridge = _load_bridge_module()

    category = bridge.categorize_digest_item(
        row={
            "title": "High-throughput GPU kernel design for H100 inference",
            "source_name": "Infra Blog",
            "url": "https://example.com/gpu",
        },
        summary="Optimizes CUDA kernels and throughput on H100 hardware.",
    )

    assert category == "Infrastructure"


def test_categorize_digest_item_keeps_eval_out_of_rag_bucket() -> None:
    bridge = _load_bridge_module()

    category = bridge.categorize_digest_item(
        row={
            "title": "Benchmarking semantic retrieval quality",
            "source_name": "Eval Lab",
            "url": "https://example.com/eval",
        },
        summary="Evaluation harness for retrieval quality and regression tracking.",
    )

    assert category == "QA & Observability"


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


def test_run_antigravity_title_chunk_retries_after_non_json_response() -> None:
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
                            '[{"url":"https://example.com/1","title":"Better headline"}]}'
                        ),
                    }
                ]
            },
        ]
    )

    original = bridge.read_json_response
    bridge.read_json_response = lambda *args, **kwargs: next(responses)
    try:
        normalized = bridge.run_antigravity_title_chunk(
            admin_url="http://example.test",
            api_key="key",
            model="gemini-3-flash",
            report_date="2026-03-01",
            articles=[
                {
                    "title": "Weak title",
                    "url": "https://example.com/1",
                    "summary": "Technical summary",
                }
            ],
        )
    finally:
        bridge.read_json_response = original

    assert normalized == {"https://example.com/1": "Better headline"}
