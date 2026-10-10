import json

import pytest

from app.core.source_onboarding import (
    extract_candidate_urls,
    normalize_candidate_url,
    parse_source_candidates,
)


def test_extract_candidate_urls_finds_plain_text_urls_in_prose() -> None:
    raw_text = """
    Candidate set:
    https://example.com/blog/post-1?utm_source=newsletter
    Keep this note, and also review https://sub.example.com/feed.xml#latest soon.
    """

    assert extract_candidate_urls(raw_text) == [
        "https://example.com/blog/post-1?utm_source=newsletter",
        "https://sub.example.com/feed.xml#latest",
    ]


def test_extract_candidate_urls_finds_markdown_link_targets() -> None:
    raw_text = """
    Useful reads:
    - [Vendor Blog](https://example.com/blog/)
    - [QA Feed](https://example.com/feed.xml?ref=nav)
    """

    assert extract_candidate_urls(raw_text) == [
        "https://example.com/blog/",
        "https://example.com/feed.xml?ref=nav",
    ]


def test_normalize_candidate_url_applies_canonical_cleanup() -> None:
    normalized = normalize_candidate_url(
        "HTTPS://Example.com/blog/?utm_source=feed&gclid=123&id=9#latest"
    )

    assert normalized == "https://example.com/blog?id=9"


def test_normalize_candidate_url_rejects_search_wrapper_urls() -> None:
    with pytest.raises(ValueError, match="wrapper|search"):
        normalize_candidate_url(
            "https://www.google.com/url?q=https%3A%2F%2Fexample.com%2Fblog&sa=D&source=editors"
        )


def test_normalize_candidate_url_keeps_non_default_port_and_normalizes_root_path() -> None:
    assert normalize_candidate_url("https://Example.com:8443/") == "https://example.com:8443"


def test_parse_source_candidates_rejects_invalid_and_duplicate_urls() -> None:
    candidates, parsed_count, rejected_count = parse_source_candidates(
        "\n".join(
            [
                "https://www.google.com/url?q=https%3A%2F%2Fexample.com%2Fblog&sa=D",
                "https://example.com/feed.xml",
                "https://example.com/feed.xml#dup",
            ]
        )
    )

    assert parsed_count == 3
    assert rejected_count == 2
    assert [candidate.normalized_url for candidate in candidates] == ["https://example.com/feed.xml"]


def test_json_intake_imports_only_source_urls_and_preserves_declared_type() -> None:
    report = {"sources": [{"name": "AI Publisher", "type": "rss",
                           "url": "https://example.com/stream",
                           "website_url": "https://example.com/blog",
                           "verification": {"evidence_url": "https://example.com/story"}}],
              "replacement_suggestions": [{"url": "https://other.example.com/feed"}],
              "unverified": [{"url": "https://unknown.example.com/feed"}]}
    text = json.dumps(report)
    assert extract_candidate_urls(text) == ["https://example.com/stream"]
    candidates, parsed, rejected = parse_source_candidates(text)
    assert (parsed, rejected) == (1, 0)
    assert candidates[0].candidate_type == "rss"
    assert json.loads(candidates[0].raw_input)["name"] == "AI Publisher"
    assert "evidence_url" not in candidates[0].raw_input


def test_json_arrays_and_fences_are_supported() -> None:
    candidates, parsed, rejected = parse_source_candidates(
        '```json\n[{"url":"https://example.com/atom","type":"atom"},'
        '"https://other.example.com/blog"]\n```'
    )
    assert (parsed, rejected) == (2, 0)
    assert candidates[0].candidate_type == "rss"


@pytest.mark.parametrize("text", [
    '{"sources":', '{"url":"https://example.com"}', '{"sources":{}}',
    '{"sources":[{"name":"No URL"}]}', '[42]',
    json.dumps(["https://example.com"] * 201),
    json.dumps({"sources": [], "notes": "x" * 1_000_000}),
])
def test_malformed_or_oversized_json_does_not_fall_back_to_url_scraping(text) -> None:
    with pytest.raises(ValueError):
        parse_source_candidates(text)
