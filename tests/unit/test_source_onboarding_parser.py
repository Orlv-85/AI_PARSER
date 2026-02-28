import pytest

from app.core.source_onboarding import extract_candidate_urls, normalize_candidate_url


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
