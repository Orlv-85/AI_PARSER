import httpx

from app.config.sources import SourceConfig
from app.ingest.html import extract_article_text, extract_links_from_html, fetch_html


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
