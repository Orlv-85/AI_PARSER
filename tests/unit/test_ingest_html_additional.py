from typing import Any, cast

import httpx

from app.config.sources import SourceConfig
from app.ingest.html import (
    _build_html_article,
    _extract_links_with_selectolax,
    extract_article_text,
    extract_links_from_html,
    fetch_html,
    fetch_html_article,
    fetch_html_links,
    fetch_html_links_with_metadata,
)


class _StaticFetcher:
    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = mapping

    def fetch_text(self, *, source_id: str, url: str) -> str:
        _ = source_id
        value = self.mapping[url]
        if value == "__error__":
            raise RuntimeError("fetch failed")
        return value


class _Response:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.com")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("bad", request=request, response=response)


class _HttpClient:
    def __init__(self, mapping: dict[str, _Response]) -> None:
        self.mapping = mapping

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str) -> _Response:
        return self.mapping[url]


def _html_source() -> SourceConfig:
    return SourceConfig(
        id="html_source",
        name="HTML Source",
        type="html",
        url="https://example.com/news",
        html={
            "list_selector": "main",
            "link_selector": "a",
            "article_selector": "article",
            "extraction_strategy": "readability",
        },
    )


def test_html_title_excludes_embedded_styles_scripts_and_templates(monkeypatch) -> None:
    monkeypatch.setattr("app.ingest.html.extract_article_text", lambda **_kwargs: "content")
    article = _build_html_article(
        source=_html_source(),
        url="https://keploy.io/blog/ai-code-testing",
        article_html=(
            "<h1><style>" + ".khl-ai{color:red}" * 100 + "</style>"
            "AI writes code <script>alert('bad')</script>"
            "Keploy catches what breaks <template>Hidden text</template></h1>"
        ),
    )

    assert article is not None
    assert article.title == "AI writes code Keploy catches what breaks"


def test_html_empty_heading_uses_url(monkeypatch) -> None:
    monkeypatch.setattr("app.ingest.html.extract_article_text", lambda **_kwargs: "content")
    article = _build_html_article(
        source=_html_source(),
        url="https://example.com/story",
        article_html="<h1><style>.headline{color:red}</style></h1>",
    )

    assert article is not None
    assert article.title == "https://example.com/story"


def test_extract_article_text_handles_trafilatura_and_unknown_strategy(monkeypatch) -> None:
    monkeypatch.setattr("app.ingest.html.trafilatura.extract", lambda html, url: "  body  ")

    text = extract_article_text("<html></html>", "https://example.com", strategy="trafilatura")
    fallback = extract_article_text("<html></html>", "https://example.com", strategy="unknown")

    assert text == "body"
    assert fallback == "body"


def test_extract_article_text_uses_readability_when_trafilatura_empty(monkeypatch) -> None:
    class _Doc:
        def __init__(self, html: str) -> None:
            self.html = html

        def summary(self, html_partial: bool = True) -> str:
            _ = html_partial
            return "<div>Readable</div>"

    monkeypatch.setattr("app.ingest.html.trafilatura.extract", lambda html, url: "")
    monkeypatch.setattr("app.ingest.html.Document", _Doc)

    text = extract_article_text("<html></html>", "https://example.com", strategy=None)
    assert text == "Readable"


def test_extract_article_text_returns_none_when_extractors_fail(monkeypatch) -> None:
    class _Doc:
        def __init__(self, html: str) -> None:
            self.html = html

        def summary(self, html_partial: bool = True) -> str:
            _ = html_partial
            return "<div>   </div>"

    monkeypatch.setattr("app.ingest.html.trafilatura.extract", lambda html, url: None)
    monkeypatch.setattr("app.ingest.html.Document", _Doc)

    assert (
        extract_article_text("<html></html>", "https://example.com", strategy="readability")
        is None
    )


def test_extract_article_text_fallback_readability_for_unknown_strategy(monkeypatch) -> None:
    class _Doc:
        def __init__(self, html: str) -> None:
            self.html = html

        def summary(self, html_partial: bool = True) -> str:
            _ = html_partial
            return "<div>Fallback Readability</div>"

    monkeypatch.setattr("app.ingest.html.trafilatura.extract", lambda html, url: None)
    monkeypatch.setattr("app.ingest.html.Document", _Doc)

    text = extract_article_text("<html></html>", "https://example.com", strategy="something-else")
    assert text == "Fallback Readability"


def test_extract_article_text_unknown_strategy_returns_none_when_fallback_empty(
    monkeypatch,
) -> None:
    class _Doc:
        def __init__(self, html: str) -> None:
            self.html = html

        def summary(self, html_partial: bool = True) -> str:
            _ = html_partial
            return "<div>   </div>"

    monkeypatch.setattr("app.ingest.html.trafilatura.extract", lambda html, url: None)
    monkeypatch.setattr("app.ingest.html.Document", _Doc)

    text = extract_article_text("<html></html>", "https://example.com", strategy="unsupported")
    assert text is None


def test_fetch_html_returns_empty_for_non_html_source() -> None:
    source = SourceConfig(id="rss_source", name="RSS", type="rss", url="https://example.com/feed")
    assert not fetch_html(source)


def test_extract_links_from_html_prefers_selectolax_in_auto_mode_when_available(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.ingest.html._SelectolaxHTMLParser", object(), raising=False)
    monkeypatch.setattr(
        "app.ingest.html._extract_links_with_selectolax",
        lambda **_kwargs: ["selectolax"],
    )
    monkeypatch.setattr(
        "app.ingest.html._extract_links_with_lxml",
        lambda **_kwargs: ["lxml"],
    )

    links = extract_links_from_html(
        html_content="<main><a href='/x'>x</a></main>",
        base_url="https://example.com",
        list_selector="main",
        link_selector="a",
        parser="auto",
    )

    assert links == ["selectolax"]


def test_extract_links_from_html_falls_back_to_lxml_when_selectolax_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.ingest.html._SelectolaxHTMLParser", None, raising=False)
    monkeypatch.setattr(
        "app.ingest.html._extract_links_with_selectolax",
        lambda **_kwargs: ["selectolax"],
    )
    monkeypatch.setattr(
        "app.ingest.html._extract_links_with_lxml",
        lambda **_kwargs: ["lxml"],
    )

    links = extract_links_from_html(
        html_content="<main><a href='/x'>x</a></main>",
        base_url="https://example.com",
        list_selector="main",
        link_selector="a",
        parser="selectolax",
    )

    assert links == ["lxml"]


def test_fetch_html_uses_fetcher_and_fail_soft(monkeypatch) -> None:
    list_html = (
        '<main><a href="/news/1">one</a><a href="/news/2">two</a><a href="/news/3">three</a></main>'
    )
    article_html = "<html><body><h1>Headline</h1><p>content</p></body></html>"

    monkeypatch.setattr("app.ingest.html.extract_article_text", lambda **kwargs: "parsed")
    fetcher = _StaticFetcher(
        {
            "https://example.com/news": list_html,
            "https://example.com/news/1": article_html,
            "https://example.com/news/2": "__error__",
            "https://example.com/news/3": "<html><body><p>no h1</p></body></html>",
        }
    )

    items = fetch_html(_html_source(), fetcher=fetcher)

    assert len(items) == 2
    assert items[0].title == "Headline"
    assert str(items[1].url) == "https://example.com/news/3"


def test_fetch_html_uses_httpx_client_branch(monkeypatch) -> None:
    source = _html_source()
    list_html = '<main><a href="/news/1">one</a></main>'
    article_html = "<html><body><h1>Server Title</h1><p>body</p></body></html>"
    responses = {
        "https://example.com/news": _Response(list_html),
        "https://example.com/news/1": _Response(article_html),
    }

    monkeypatch.setattr("app.ingest.html.httpx.Client", lambda **kwargs: _HttpClient(responses))
    monkeypatch.setattr("app.ingest.html.extract_article_text", lambda **kwargs: "body")

    items = fetch_html(source, timeout_seconds=2.0, fetcher=None)

    assert len(items) == 1
    assert items[0].title == "Server Title"


def test_fetch_html_httpx_branch_fail_soft_and_skip_missing_href(monkeypatch) -> None:
    source = _html_source()
    list_html = '<main><a href=\"/news/1\">one</a><a>missing</a><a href=\"/news/2\">two</a></main>'
    responses = {
        "https://example.com/news": _Response(list_html),
        "https://example.com/news/1": _Response("<html><body><h1>One</h1></body></html>"),
        "https://example.com/news/2": _Response("bad", status_code=500),
    }

    monkeypatch.setattr("app.ingest.html.httpx.Client", lambda **kwargs: _HttpClient(responses))
    monkeypatch.setattr("app.ingest.html.extract_article_text", lambda **kwargs: "body")

    items = fetch_html(source, fetcher=None)
    assert len(items) == 1
    assert items[0].title == "One"


def test_extract_links_from_html_forces_lxml_on_invalid_parser(monkeypatch) -> None:
    monkeypatch.setattr("app.ingest.html._SelectolaxHTMLParser", None, raising=False)
    html_content = '<div><a href="/a">A</a><a>B</a><a href="/a">dup</a><a href="/b">B</a></div>'

    links = extract_links_from_html(
        html_content=html_content,
        base_url="https://example.com",
        list_selector=None,
        link_selector="a",
        parser="invalid-parser",
    )

    assert links == ["https://example.com/a", "https://example.com/b"]


def test_extract_links_with_selectolax_falls_back_to_lxml_helper(monkeypatch) -> None:
    monkeypatch.setattr("app.ingest.html._SelectolaxHTMLParser", None, raising=False)
    calls: list[dict[str, object]] = []

    def _fake_lxml(**kwargs):
        calls.append(kwargs)
        return ["https://example.com/fallback"]

    monkeypatch.setattr("app.ingest.html._extract_links_with_lxml", _fake_lxml)

    links = _extract_links_with_selectolax(
        html_content="<div></div>",
        base_url="https://example.com",
        list_selector="div",
        link_selector="a",
    )

    assert links == ["https://example.com/fallback"]
    assert calls


def test_extract_links_with_selectolax_uses_fake_parser(monkeypatch) -> None:
    class _FakeNode:
        def __init__(self, href: str | None) -> None:
            self.attributes = {} if href is None else {"href": href}

    class _FakeRoot:
        def __init__(self, hrefs: list[str | None]) -> None:
            self._hrefs = hrefs

        def css(self, selector: str):
            assert selector == "a"
            return [_FakeNode(href) for href in self._hrefs]

    class _FakeSelectolaxParser:
        def __init__(self, html_content: str) -> None:
            self.html_content = html_content

        def css(self, selector: str):
            if selector == "main":
                return [_FakeRoot(["/a", None, "/a", "/b"])]
            if selector == "a":
                return [_FakeNode("/top")]
            return []

    monkeypatch.setattr(
        "app.ingest.html._SelectolaxHTMLParser",
        _FakeSelectolaxParser,
        raising=False,
    )

    links = extract_links_from_html(
        html_content="<main></main>",
        base_url="https://example.com",
        list_selector="main",
        link_selector="a",
        parser="selectolax",
    )

    assert links == ["https://example.com/a", "https://example.com/b"]


def test_build_html_article_and_fetch_helpers_cover_non_html_and_httpx_paths(monkeypatch) -> None:
    non_html = SourceConfig(
        id="rss_source",
        name="RSS",
        type="rss",
        url="https://example.com/feed",
    )
    assert (
        _build_html_article(
            source=non_html,
            url="https://example.com/a",
            article_html="<h1>x</h1>",
        )
        is None
    )
    assert not fetch_html_links(non_html)
    assert fetch_html_article(source=non_html, url="https://example.com/a") is None
    assert not fetch_html_links_with_metadata(non_html).links

    source = _html_source()
    list_html = '<main><a href="/news/1">one</a></main>'
    article_html = "<html><body><h1>Helper Title</h1><p>body</p></body></html>"
    responses = {
        "https://example.com/news": _Response(list_html),
        "https://example.com/news/1": _Response(article_html),
    }
    monkeypatch.setattr("app.ingest.html.httpx.Client", lambda **kwargs: _HttpClient(responses))
    monkeypatch.setattr("app.ingest.html.extract_article_text", lambda **kwargs: "body")

    links = fetch_html_links(source, fetcher=None)
    article = fetch_html_article(source=source, url="https://example.com/news/1", fetcher=None)

    assert links == ["https://example.com/news/1"]
    assert article is not None
    assert article.title == "Helper Title"


def test_fetch_html_links_with_metadata_httpx_not_modified_and_success(monkeypatch) -> None:
    source = _html_source()
    request_log: list[dict[str, object]] = []
    responses = {
        "https://example.com/news": _Response("", status_code=304),
    }
    responses["https://example.com/news"].headers = {
        "ETag": '"etag-1"',
        "Last-Modified": "Mon, 01 Jan 2024 00:00:00 GMT",
    }

    class _ConditionalClient(_HttpClient):
        def get(self, url: str, **kwargs) -> _Response:
            request_log.append({"url": url, "kwargs": kwargs})
            return self.mapping[url]

    monkeypatch.setattr(
        "app.ingest.html.httpx.Client",
        lambda **kwargs: _ConditionalClient(responses),
    )

    not_modified = fetch_html_links_with_metadata(
        source,
        fetcher=None,
        if_none_match='"etag-1"',
        if_modified_since="Mon, 01 Jan 2024 00:00:00 GMT",
    )

    assert not_modified.not_modified is True
    assert not_modified.status_code == 304
    assert not_modified.etag == '"etag-1"'
    first_call = cast(dict[str, Any], request_log[0])
    assert first_call["kwargs"]["headers"]["If-None-Match"] == '"etag-1"'

    responses["https://example.com/news"] = _Response('<main><a href="/news/2">two</a></main>')
    responses["https://example.com/news"].headers = {
        "ETag": '"etag-2"',
        "Last-Modified": "Tue, 02 Jan 2024 00:00:00 GMT",
    }

    success = fetch_html_links_with_metadata(source, fetcher=None)

    assert success.not_modified is False
    assert success.links == ["https://example.com/news/2"]
    assert success.etag == '"etag-2"'


def test_fetch_html_links_with_metadata_uses_fetcher_request_branch() -> None:
    source = _html_source()

    class _FetcherWithRequest:
        @staticmethod
        def request(**kwargs):
            _ = kwargs
            response = _Response('<main><a href="/news/3">three</a></main>')
            response.headers = {
                "ETag": '"etag-3"',
                "Last-Modified": "Wed, 03 Jan 2024 00:00:00 GMT",
            }
            return response

    result = fetch_html_links_with_metadata(
        source,
        fetcher=_FetcherWithRequest(),
        if_none_match='"etag-old"',
        if_modified_since="Tue, 02 Jan 2024 00:00:00 GMT",
    )

    assert result.not_modified is False
    assert result.links == ["https://example.com/news/3"]
    assert result.etag == '"etag-3"'


def test_fetch_html_skips_none_articles_in_both_paths(monkeypatch) -> None:
    source = _html_source()

    monkeypatch.setattr(
        "app.ingest.html.fetch_html_links",
        lambda *_args, **_kwargs: ["https://example.com/news/1"],
    )
    monkeypatch.setattr(
        "app.ingest.html.fetch_html_article",
        lambda *_args, **_kwargs: None,
    )

    assert not fetch_html(source, fetcher=_StaticFetcher({}))

    list_html = '<main><a href="/news/1">one</a></main>'
    responses = {
        "https://example.com/news": _Response(list_html),
        "https://example.com/news/1": _Response("<html><body><h1>Ignored</h1></body></html>"),
    }
    monkeypatch.setattr("app.ingest.html.httpx.Client", lambda **kwargs: _HttpClient(responses))
    monkeypatch.setattr("app.ingest.html._build_html_article", lambda **_kwargs: None)

    assert not fetch_html(source, fetcher=None)
