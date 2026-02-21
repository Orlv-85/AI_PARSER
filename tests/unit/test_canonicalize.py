from app.core.canonicalize import canonical_url_hash, canonicalize_url


def test_canonicalize_removes_tracking_params_and_fragment() -> None:
    url = "HTTPS://Example.com/path/?utm_source=x&gclid=123&id=9#section"
    assert canonicalize_url(url) == "https://example.com/path?id=9"


def test_canonicalize_normalizes_trailing_slash_and_query_order() -> None:
    url = "https://example.com/news/?b=2&a=1"
    assert canonicalize_url(url) == "https://example.com/news?a=1&b=2"


def test_canonicalize_normalizes_default_ports() -> None:
    assert canonicalize_url("https://example.com:443/test/") == "https://example.com/test"
    assert canonicalize_url("http://example.com:80/test/") == "http://example.com/test"


def test_canonical_hash_is_stable_for_equivalent_urls() -> None:
    left = canonical_url_hash("https://example.com/a/?utm_campaign=abc&id=42")
    right = canonical_url_hash("https://EXAMPLE.com/a?id=42")
    assert left == right

