from dataclasses import dataclass
from typing import Literal, cast
from urllib.parse import urljoin

import httpx
import trafilatura
from lxml import html as lxml_html
from readability import Document

try:
    from selectolax.parser import HTMLParser as _SelectolaxHTMLParser
except ImportError:  # pragma: no cover - optional dependency
    _SelectolaxHTMLParser = None

from app.config.sources import SourceConfig
from app.core.models import Article
from app.ingest.fetcher import Fetcher


@dataclass(frozen=True)
class HtmlListPageResult:
    links: list[str]
    not_modified: bool = False
    status_code: int | None = None
    etag: str | None = None
    last_modified: str | None = None


def extract_links_from_html(
    *,
    html_content: str,
    base_url: str,
    list_selector: str | None,
    link_selector: str | None,
    parser: str | None = None,
) -> list[str]:
    selected_parser = _resolve_link_parser(parser)
    if selected_parser == "selectolax":
        return _extract_links_with_selectolax(
            html_content=html_content,
            base_url=base_url,
            list_selector=list_selector,
            link_selector=link_selector,
        )
    return _extract_links_with_lxml(
        html_content=html_content,
        base_url=base_url,
        list_selector=list_selector,
        link_selector=link_selector,
    )


def _resolve_link_parser(parser: str | None) -> Literal["lxml", "selectolax"]:
    parser_name = (parser or "auto").strip().lower()
    if parser_name not in {"auto", "lxml", "selectolax"}:
        parser_name = "auto"
    if parser_name in {"auto", "selectolax"} and _SelectolaxHTMLParser is not None:
        return "selectolax"
    return "lxml"


def _extract_links_with_lxml(
    *,
    html_content: str,
    base_url: str,
    list_selector: str | None,
    link_selector: str | None,
) -> list[str]:
    tree = lxml_html.fromstring(html_content)
    roots = tree.cssselect(list_selector) if list_selector else [tree]
    selector = link_selector or "a"

    found: list[str] = []
    seen: set[str] = set()
    for root in roots:
        for node in root.cssselect(selector):
            href = node.attrib.get("href")
            if not href:
                continue
            absolute = urljoin(base_url, href).strip()
            if absolute in seen:
                continue
            seen.add(absolute)
            found.append(absolute)
    return found


def _extract_links_with_selectolax(
    *,
    html_content: str,
    base_url: str,
    list_selector: str | None,
    link_selector: str | None,
) -> list[str]:
    if _SelectolaxHTMLParser is None:
        return _extract_links_with_lxml(
            html_content=html_content,
            base_url=base_url,
            list_selector=list_selector,
            link_selector=link_selector,
        )

    tree = _SelectolaxHTMLParser(html_content)
    roots = tree.css(list_selector) if list_selector else [tree]
    selector = link_selector or "a"

    found: list[str] = []
    seen: set[str] = set()
    for root in roots:
        for node in root.css(selector):
            href = node.attributes.get("href")
            if not href:
                continue
            absolute = urljoin(base_url, href).strip()
            if absolute in seen:
                continue
            seen.add(absolute)
            found.append(absolute)
    return found


def extract_article_text(html_content: str, url: str, strategy: str | None = None) -> str | None:
    # Keep extraction order deterministic and fail-soft.
    modes = [strategy] if strategy else ["trafilatura", "readability"]

    for mode in modes:
        if mode == "trafilatura":
            text = trafilatura.extract(html_content, url=url)
            if text:
                return text.strip()

        if mode == "readability":
            summary = Document(html_content).summary(html_partial=True)
            cleaned = lxml_html.fromstring(summary).text_content().strip()
            if cleaned:
                return cast(str, cleaned)

    if strategy not in {"trafilatura", "readability"}:
        fallback = trafilatura.extract(html_content, url=url)
        if fallback:
            return fallback.strip()
        summary = Document(html_content).summary(html_partial=True)
        cleaned = lxml_html.fromstring(summary).text_content().strip()
        if cleaned:
            return cast(str, cleaned)
    return None


def _build_html_article(*, source: SourceConfig, url: str, article_html: str) -> Article | None:
    if source.type != "html" or source.html is None:
        return None
    title_nodes = lxml_html.fromstring(article_html).cssselect("h1")
    title = title_nodes[0].text_content().strip() if title_nodes else url
    content = extract_article_text(
        html_content=article_html,
        url=url,
        strategy=source.html.extraction_strategy,
    )
    return Article(
        source_key=source.id,
        title=title,
        url=url,
        published_at=None,
        summary=None,
        content=content,
    )


def fetch_html_links(
    source: SourceConfig,
    timeout_seconds: float = 15.0,
    fetcher: Fetcher | None = None,
    link_parser: str | None = None,
) -> list[str]:
    if source.type != "html" or source.html is None:
        return []

    if fetcher is not None:
        list_html = fetcher.fetch_text(source_id=source.id, url=str(source.url))
    else:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            response = client.get(str(source.url))
            response.raise_for_status()
            list_html = response.text

    return extract_links_from_html(
        html_content=list_html,
        base_url=str(source.url),
        list_selector=source.html.list_selector,
        link_selector=source.html.link_selector,
        parser=link_parser,
    )


def fetch_html_links_with_metadata(
    source: SourceConfig,
    timeout_seconds: float = 15.0,
    fetcher: Fetcher | None = None,
    link_parser: str | None = None,
    *,
    if_none_match: str | None = None,
    if_modified_since: str | None = None,
) -> HtmlListPageResult:
    if source.type != "html" or source.html is None:
        return HtmlListPageResult(links=[])

    request_headers: dict[str, str] = {}
    if if_none_match is not None:
        request_headers["If-None-Match"] = if_none_match
    if if_modified_since is not None:
        request_headers["If-Modified-Since"] = if_modified_since

    if fetcher is not None:
        response = fetcher.request(
            source_id=source.id,
            url=str(source.url),
            if_none_match=if_none_match,
            if_modified_since=if_modified_since,
        )
    else:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            if request_headers:
                response = client.get(str(source.url), headers=request_headers)
            else:
                response = client.get(str(source.url))
            if response.status_code != 304:
                response.raise_for_status()

    if response.status_code == 304:
        return HtmlListPageResult(
            links=[],
            not_modified=True,
            status_code=304,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )

    return HtmlListPageResult(
        links=extract_links_from_html(
            html_content=response.text,
            base_url=str(source.url),
            list_selector=source.html.list_selector,
            link_selector=source.html.link_selector,
            parser=link_parser,
        ),
        not_modified=False,
        status_code=response.status_code,
        etag=response.headers.get("ETag"),
        last_modified=response.headers.get("Last-Modified"),
    )


def fetch_html_article(
    *,
    source: SourceConfig,
    url: str,
    timeout_seconds: float = 15.0,
    fetcher: Fetcher | None = None,
) -> Article | None:
    if source.type != "html" or source.html is None:
        return None

    if fetcher is not None:
        article_html = fetcher.fetch_text(source_id=source.id, url=url)
    else:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            article_html = response.text
    return _build_html_article(source=source, url=url, article_html=article_html)


def fetch_html(
    source: SourceConfig,
    timeout_seconds: float = 15.0,
    fetcher: Fetcher | None = None,
) -> list[Article]:
    if source.type != "html" or source.html is None:
        return []

    if fetcher is None:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            list_response = client.get(str(source.url))
            list_response.raise_for_status()
            links = extract_links_from_html(
                html_content=list_response.text,
                base_url=str(source.url),
                list_selector=source.html.list_selector,
                link_selector=source.html.link_selector,
            )
            fetched_items: list[Article] = []
            for link in links:
                try:
                    response = client.get(link)
                    response.raise_for_status()
                    article = _build_html_article(
                        source=source,
                        url=link,
                        article_html=response.text,
                    )
                except Exception:
                    continue
                if article is not None:
                    fetched_items.append(article)
            return fetched_items

    links = fetch_html_links(source, timeout_seconds=timeout_seconds, fetcher=fetcher)
    items: list[Article] = []
    for link in links:
        try:
            article = fetch_html_article(
                source=source,
                url=link,
                timeout_seconds=timeout_seconds,
                fetcher=fetcher,
            )
        except Exception:
            # Fail-soft: keep processing remaining links.
            continue
        if article is not None:
            items.append(article)
    return items
