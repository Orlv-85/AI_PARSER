from types import SimpleNamespace

from app.core import source_onboarding


def _require_api(name: str):
    assert hasattr(
        source_onboarding,
        name,
    ), f"Phase 2 validation API missing: app.core.source_onboarding.{name}"
    return getattr(source_onboarding, name)


def _value(container, key: str):
    if isinstance(container, dict):
        return container[key]
    return getattr(container, key)


def test_validate_rss_candidate_marks_candidate_valid_when_feed_has_entries() -> None:
    validate_rss_candidate = _require_api("validate_rss_candidate")
    candidate = SimpleNamespace(
        id=1,
        normalized_url="https://example.com/feed.xml",
        candidate_type="rss",
    )

    result = validate_rss_candidate(
        candidate,
        fetch_feed=lambda url: {
            "url": url,
            "title": "Example Feed",
            "entries": [
                {"title": "Post 1", "link": "https://example.com/posts/1"},
                {"title": "Post 2", "link": "https://example.com/posts/2"},
            ],
        },
    )

    assert _value(result, "status") == "validated"
    assert _value(result, "detected_type") == "rss"
    assert _value(result, "entry_count") == 2
    assert _value(result, "validation_error") is None


def test_validate_rss_candidate_fails_when_feed_has_no_entries() -> None:
    validate_rss_candidate = _require_api("validate_rss_candidate")
    candidate = SimpleNamespace(
        id=2,
        normalized_url="https://example.com/empty.xml",
        candidate_type="rss",
    )

    result = validate_rss_candidate(
        candidate,
        fetch_feed=lambda url: {"url": url, "title": "Empty Feed", "entries": []},
    )

    assert _value(result, "status") == "failed"
    assert _value(result, "detected_type") == "rss"
    assert "entry" in _value(result, "validation_error").lower()


def test_validate_html_candidate_marks_candidate_valid_when_article_links_are_extractable(
) -> None:
    validate_html_candidate = _require_api("validate_html_candidate")
    candidate = SimpleNamespace(
        id=3,
        normalized_url="https://example.com/blog",
        candidate_type="html",
    )

    result = validate_html_candidate(
        candidate,
        fetch_html=lambda url: "<html><body>ok</body></html>",
        extract_links=lambda html, base_url: [
            f"{base_url}/posts/1",
            f"{base_url}/posts/2",
        ],
    )

    assert _value(result, "status") == "validated"
    assert _value(result, "detected_type") == "html"
    assert _value(result, "link_count") == 2
    assert _value(result, "sample_links") == [
        "https://example.com/blog/posts/1",
        "https://example.com/blog/posts/2",
    ]


def test_validate_html_candidate_warns_when_page_loads_but_has_no_article_links(
) -> None:
    validate_html_candidate = _require_api("validate_html_candidate")
    candidate = SimpleNamespace(
        id=4,
        normalized_url="https://example.com/category/testing",
        candidate_type="html",
    )

    result = validate_html_candidate(
        candidate,
        fetch_html=lambda url: "<html><body>empty</body></html>",
        extract_links=lambda html, base_url: [],
    )

    assert _value(result, "status") in {"warning", "failed"}
    assert _value(result, "detected_type") == "html"
    assert _value(result, "link_count") == 0
    assert "link" in _value(result, "validation_error").lower()
