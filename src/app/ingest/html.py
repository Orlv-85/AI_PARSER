from typing import cast
from urllib.parse import urljoin

import httpx
import trafilatura
from lxml import html as lxml_html
from readability import Document

from app.config.sources import SourceConfig
from app.core.models import Article
from app.ingest.fetcher import Fetcher


def extract_links_from_html(
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


def fetch_html(
    source: SourceConfig,
    timeout_seconds: float = 15.0,
    fetcher: Fetcher | None = None,
) -> list[Article]:
    if source.type != "html" or source.html is None:
        return []

    if fetcher is not None:
        list_html = fetcher.fetch_text(source_id=source.id, url=str(source.url))
        links = extract_links_from_html(
            html_content=list_html,
            base_url=str(source.url),
            list_selector=source.html.list_selector,
            link_selector=source.html.link_selector,
        )

        html_items: list[Article] = []
        for link in links:
            try:
                article_html = fetcher.fetch_text(source_id=source.id, url=link)
                title_nodes = lxml_html.fromstring(article_html).cssselect("h1")
                title = title_nodes[0].text_content().strip() if title_nodes else link
                content = extract_article_text(
                    html_content=article_html,
                    url=link,
                    strategy=source.html.extraction_strategy,
                )
                html_items.append(
                    Article(
                        source_key=source.id,
                        title=title,
                        url=link,
                        published_at=None,
                        summary=None,
                        content=content,
                    )
                )
            except Exception:
                # Fail-soft: keep processing remaining links.
                continue
        return html_items

    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        list_response = client.get(str(source.url))
        list_response.raise_for_status()
        links = extract_links_from_html(
            html_content=list_response.text,
            base_url=str(source.url),
            list_selector=source.html.list_selector,
            link_selector=source.html.link_selector,
        )

        items: list[Article] = []
        for link in links:
            try:
                response = client.get(link)
                response.raise_for_status()
                title_nodes = lxml_html.fromstring(response.text).cssselect("h1")
                title = title_nodes[0].text_content().strip() if title_nodes else link
                content = extract_article_text(
                    html_content=response.text,
                    url=link,
                    strategy=source.html.extraction_strategy,
                )
                items.append(
                    Article(
                        source_key=source.id,
                        title=title,
                        url=link,
                        published_at=None,
                        summary=None,
                        content=content,
                    )
                )
            except Exception:
                # Fail-soft: keep processing remaining links.
                continue
        return items
