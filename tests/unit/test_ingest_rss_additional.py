import logging
from time import struct_time

import pytest

import app.ingest.rss as rss_module
from app.core.models import Article
from app.ingest.rss import (
    _extract_linked_article_text,
    _normalize_plain_text,
    _to_datetime,
    fetch_rss,
    parse_rss,
)


class _Fetcher:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def fetch_bytes(self, *, source_id: str, url: str) -> bytes:
        _ = (source_id, url)
        return self.content

    def fetch_text(self, *, source_id: str, url: str) -> str:
        _ = (source_id, url)
        return self.content.decode("utf-8")


class _Response:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


class _Client:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        _ = url
        return _Response(self.content)


def test_to_datetime_none_and_struct_time() -> None:
    assert _to_datetime(None) is None
    dt = _to_datetime(struct_time((2026, 2, 21, 12, 0, 0, 0, 0, 0)))
    assert dt is not None
    assert dt.year == 2026


def test_parse_rss_skips_invalid_and_separates_updated_parsed(monkeypatch) -> None:
    class _Entry:
        def __init__(self, link=None, title=None, updated_parsed=None):
            self.link = link
            self.title = title
            self.updated_parsed = updated_parsed

    class _Parsed:
        entries = [
            _Entry(link="https://example.com/1", title=" One "),
            _Entry(link=None, title="Missing link"),
            _Entry(link="https://example.com/2", title=None),
            _Entry(
                link="https://example.com/3",
                title="Three",
                updated_parsed=struct_time((2026, 2, 20, 10, 0, 0, 0, 0, 0)),
            ),
        ]

    monkeypatch.setattr("app.ingest.rss.feedparser.parse", lambda content: _Parsed())

    items = parse_rss("source", b"x")

    assert len(items) == 2
    assert items[0].title == "One"
    assert items[1].published_at is None
    assert items[1].publication_date_kind == "unknown"
    assert items[1].modified_at is not None


def test_fetch_rss_uses_fetcher_and_httpx_branches(monkeypatch) -> None:
    content = b"<rss></rss>"
    monkeypatch.setattr("app.ingest.rss.parse_rss", lambda source_key, content: ["ok"])

    via_fetcher = fetch_rss("s", "https://example.com/feed", fetcher=_Fetcher(content))
    monkeypatch.setattr("app.ingest.rss.httpx.Client", lambda **kwargs: _Client(content))
    via_httpx = fetch_rss("s", "https://example.com/feed", timeout_seconds=3.0, fetcher=None)

    assert via_fetcher == ["ok"]
    assert via_httpx == ["ok"]


def test_fetch_rss_httpx_branch_sends_conditional_headers_and_handles_304(monkeypatch) -> None:
    request_log: list[dict[str, object]] = []

    class _NotModifiedResponse:
        status_code = 304
        content = b""
        headers = {"ETag": '"etag-1"', "Last-Modified": "Mon, 01 Jan 2024 00:00:00 GMT"}

        @staticmethod
        def raise_for_status() -> None:
            return None

    class _ConditionalClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url: str, **kwargs):
            request_log.append({"url": url, "kwargs": kwargs})
            return _NotModifiedResponse()

    monkeypatch.setattr("app.ingest.rss.httpx.Client", lambda **kwargs: _ConditionalClient())

    result = rss_module.fetch_rss_with_metadata(
        "s",
        "https://example.com/feed",
        timeout_seconds=3.0,
        fetcher=None,
        if_none_match='"etag-1"',
        if_modified_since="Mon, 01 Jan 2024 00:00:00 GMT",
    )

    assert result.not_modified is True
    assert result.status_code == 304
    assert not result.items
    assert request_log == [
        {
            "url": "https://example.com/feed",
            "kwargs": {
                "headers": {
                    "If-None-Match": '"etag-1"',
                    "If-Modified-Since": "Mon, 01 Jan 2024 00:00:00 GMT",
                }
            },
        }
    ]


def test_fetch_rss_extract_full_text_enriches_only_first_n(monkeypatch) -> None:
    items = [
        Article(source_key="s", title="A", url="https://example.com/a"),
        Article(source_key="s", title="B", url="https://example.com/b"),
        Article(source_key="s", title="C", url="https://example.com/c"),
    ]
    monkeypatch.setattr("app.ingest.rss.parse_rss", lambda source_key, content: items)
    calls: list[str] = []

    def _fake_extract_linked_article_text(**kwargs):
        calls.append(kwargs["link"])
        return f"text for {kwargs['link']}"

    monkeypatch.setattr(
        "app.ingest.rss._extract_linked_article_text",
        _fake_extract_linked_article_text,
    )

    result = fetch_rss(
        "s",
        "https://example.com/feed",
        fetcher=_Fetcher(b"<rss></rss>"),
        extract_full_text=True,
        full_text_max_items=2,
    )

    assert len(result) == 3
    assert result[0].content == "text for https://example.com/a"
    assert result[1].content == "text for https://example.com/b"
    assert result[2].content is None
    assert calls == ["https://example.com/a", "https://example.com/b"]


def test_fetch_rss_extract_full_text_fail_soft_logs_and_continues(monkeypatch, caplog) -> None:
    items = [
        Article(source_key="s", title="A", url="https://example.com/a"),
        Article(source_key="s", title="B", url="https://example.com/b"),
    ]
    monkeypatch.setattr("app.ingest.rss.parse_rss", lambda source_key, content: items)

    calls: list[str] = []

    def _fake_extract_linked_article_text(**kwargs):
        calls.append(kwargs["link"])
        if kwargs["link"].endswith("/a"):
            raise RuntimeError("extract failed")
        return "ok text"

    monkeypatch.setattr(
        "app.ingest.rss._extract_linked_article_text",
        _fake_extract_linked_article_text,
    )
    caplog.set_level(logging.WARNING, logger="app.ingest.rss")

    result = fetch_rss(
        "s",
        "https://example.com/feed",
        fetcher=_Fetcher(b"<rss></rss>"),
        extract_full_text=True,
    )

    assert result[0].content is None
    assert result[1].content == "ok text"
    assert calls == ["https://example.com/a", "https://example.com/b"]
    assert "extract" in caplog.text.lower()
    assert "https://example.com/a" in caplog.text


def test_fetch_rss_extract_full_text_disabled(monkeypatch) -> None:
    items = [Article(source_key="s", title="A", url="https://example.com/a")]
    monkeypatch.setattr("app.ingest.rss.parse_rss", lambda source_key, content: items)
    called = {"value": False}

    def _fake_extract_linked_article_text(**kwargs):
        _ = kwargs
        called["value"] = True
        return "text"

    monkeypatch.setattr(
        "app.ingest.rss._extract_linked_article_text",
        _fake_extract_linked_article_text,
    )

    result = fetch_rss(
        "s",
        "https://example.com/feed",
        fetcher=_Fetcher(b"<rss></rss>"),
        extract_full_text=False,
    )

    assert result[0].content is None
    assert called["value"] is False


def test_normalize_plain_text_handles_none_and_blank() -> None:
    assert _normalize_plain_text(None) is None
    assert _normalize_plain_text(" \n\t ") is None
    assert _normalize_plain_text(" A \n  B\tC ") == "A B C"


def test_extract_linked_article_text_uses_fetcher(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.ingest.rss.extract_article_text",
        lambda **kwargs: " extracted \n value ",
    )
    fetcher = _Fetcher(b"<html>ignored</html>")

    text = _extract_linked_article_text(
        source_id="src",
        link="https://example.com/a",
        timeout_seconds=3.0,
        fetcher=fetcher,
    )

    assert text == "extracted value"


def test_extract_linked_article_text_uses_httpx_when_fetcher_missing(monkeypatch) -> None:
    class _HtmlResponse:
        text = "<html>ok</html>"

        @staticmethod
        def raise_for_status() -> None:
            return None

    class _HtmlClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @staticmethod
        def get(url: str):
            _ = url
            return _HtmlResponse()

    monkeypatch.setattr("app.ingest.rss.httpx.Client", lambda **kwargs: _HtmlClient())
    monkeypatch.setattr("app.ingest.rss.extract_article_text", lambda **kwargs: "httpx text")

    text = _extract_linked_article_text(
        source_id="src",
        link="https://example.com/a",
        timeout_seconds=1.0,
        fetcher=None,
    )

    assert text == "httpx text"


def test_fetch_rss_extract_full_text_ignores_empty_extracted_text(monkeypatch) -> None:
    items = [Article(source_key="s", title="A", url="https://example.com/a")]
    monkeypatch.setattr("app.ingest.rss.parse_rss", lambda source_key, content: items)
    monkeypatch.setattr("app.ingest.rss._extract_linked_article_text", lambda **kwargs: None)

    result = fetch_rss(
        "s",
        "https://example.com/feed",
        fetcher=_Fetcher(b"<rss></rss>"),
        extract_full_text=True,
    )

    assert result[0].content is None


def test_fetch_rss_extract_full_text_uses_semaphore_acquire_and_release(monkeypatch) -> None:
    items = [Article(source_key="s", title="A", url="https://example.com/a")]
    monkeypatch.setattr("app.ingest.rss.parse_rss", lambda source_key, content: items)
    monkeypatch.setattr("app.ingest.rss._extract_linked_article_text", lambda **kwargs: "ok text")

    class _Semaphore:
        def __init__(self) -> None:
            self.acquire_calls = 0
            self.release_calls = 0

        def acquire(self) -> None:
            self.acquire_calls += 1

        def release(self) -> None:
            self.release_calls += 1

    semaphore = _Semaphore()

    result = fetch_rss(
        "s",
        "https://example.com/feed",
        fetcher=_Fetcher(b"<rss></rss>"),
        extract_full_text=True,
        full_text_semaphore=semaphore,
    )

    assert result[0].content == "ok text"
    assert semaphore.acquire_calls == 1
    assert semaphore.release_calls == 1


class _RequestResponse:
    def __init__(
        self,
        *,
        status_code: int,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        return None


class _RequestFetcher:
    def __init__(self, response: _RequestResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _fetch_rss_with_metadata_api():
    api = getattr(rss_module, "fetch_rss_with_metadata", None)
    assert callable(api), "Expected app.ingest.rss.fetch_rss_with_metadata() to be added"
    return api


def test_fetch_rss_with_metadata_304_skips_parse_and_reports_not_modified(monkeypatch) -> None:
    api = _fetch_rss_with_metadata_api()
    fetcher = _RequestFetcher(_RequestResponse(status_code=304))

    def _parse_should_not_run(*args, **kwargs):
        raise AssertionError("parse_rss should not be called for HTTP 304")

    monkeypatch.setattr("app.ingest.rss.parse_rss", _parse_should_not_run)

    result = api(
        "s",
        "https://example.com/feed.xml",
        fetcher=fetcher,
        if_none_match='"etag-old"',
        if_modified_since="Mon, 01 Jan 2024 00:00:00 GMT",
    )

    assert result.not_modified is True
    assert result.status_code == 304
    assert not result.items
    assert hasattr(result, "etag")
    assert hasattr(result, "last_modified")


def test_fetch_rss_with_metadata_passes_conditional_validators_to_fetcher_request() -> None:
    api = _fetch_rss_with_metadata_api()
    fetcher = _RequestFetcher(_RequestResponse(status_code=304))

    _ = api(
        "s",
        "https://example.com/feed.xml",
        fetcher=fetcher,
        if_none_match='"etag-123"',
        if_modified_since="Tue, 02 Jan 2024 00:00:00 GMT",
    )

    assert fetcher.calls == [
        {
            "source_id": "s",
            "url": "https://example.com/feed.xml",
            "if_none_match": '"etag-123"',
            "if_modified_since": "Tue, 02 Jan 2024 00:00:00 GMT",
        }
    ]


def test_fetch_rss_with_metadata_200_captures_headers_and_parses(monkeypatch) -> None:
    api = _fetch_rss_with_metadata_api()
    response = _RequestResponse(
        status_code=200,
        content=b"<rss></rss>",
        headers={
            "ETag": '"etag-new"',
            "Last-Modified": "Wed, 03 Jan 2024 00:00:00 GMT",
        },
    )
    fetcher = _RequestFetcher(response)
    monkeypatch.setattr("app.ingest.rss.parse_rss", lambda source_key, content: ["parsed-item"])

    result = api("s", "https://example.com/feed.xml", fetcher=fetcher)

    assert result.not_modified is False
    assert result.status_code == 200
    assert result.etag == '"etag-new"'
    assert result.last_modified == "Wed, 03 Jan 2024 00:00:00 GMT"
    assert result.items == ["parsed-item"]


def test_fetch_rss_compatibility_wrapper_still_returns_item_list(monkeypatch) -> None:
    if not hasattr(rss_module, "fetch_rss_with_metadata"):
        pytest.fail("Expected fetch_rss_with_metadata() for compatibility wrapper coverage")

    class _Result:
        def __init__(self) -> None:
            self.items = ["a", "b"]
            self.not_modified = False
            self.status_code = 200
            self.etag = None
            self.last_modified = None

    monkeypatch.setattr("app.ingest.rss.fetch_rss_with_metadata", lambda *args, **kwargs: _Result())

    result = fetch_rss("s", "https://example.com/feed.xml", fetcher=None)

    assert result == ["a", "b"]
    assert isinstance(result, list)
