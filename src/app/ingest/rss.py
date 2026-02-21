import calendar
import logging
import re
from datetime import UTC, datetime
from time import struct_time

import feedparser
import httpx

from app.core.models import Article
from app.ingest.fetcher import Fetcher
from app.ingest.html import extract_article_text

_LOGGER = logging.getLogger(__name__)


def _to_datetime(value: struct_time | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(calendar.timegm(value), tz=UTC)


def parse_rss(source_key: str, content: bytes) -> list[Article]:
    parsed = feedparser.parse(content)
    items: list[Article] = []

    for entry in parsed.entries:
        link = getattr(entry, "link", None)
        title = getattr(entry, "title", None)
        if not link or not title:
            continue

        published = _to_datetime(getattr(entry, "published_parsed", None))
        if published is None:
            published = _to_datetime(getattr(entry, "updated_parsed", None))

        items.append(
            Article(
                source_key=source_key,
                title=str(title).strip(),
                url=str(link).strip(),
                published_at=published,
                summary=getattr(entry, "summary", None),
                content=None,
            )
        )

    return items


def _normalize_plain_text(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned or None


def _extract_linked_article_text(
    *,
    source_id: str,
    link: str,
    timeout_seconds: float,
    fetcher: Fetcher | None,
) -> str | None:
    if fetcher is not None:
        html_content = fetcher.fetch_text(source_id=source_id, url=link)
    else:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            response = client.get(link)
            response.raise_for_status()
            html_content = response.text
    extracted = extract_article_text(html_content=html_content, url=link, strategy="trafilatura")
    return _normalize_plain_text(extracted)

# pylint: disable=too-many-positional-arguments
def fetch_rss(
    source_key: str,
    url: str,
    timeout_seconds: float = 15.0,
    fetcher: Fetcher | None = None,
    extract_full_text: bool = False,
    full_text_max_items: int = 20,
) -> list[Article]:
    if fetcher is not None:
        content = fetcher.fetch_bytes(source_id=source_key, url=url)
    else:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            content = response.content

    items = parse_rss(source_key=source_key, content=content)
    if not extract_full_text:
        return items

    for item in items[: max(0, full_text_max_items)]:
        try:
            text = _extract_linked_article_text(
                source_id=source_key,
                link=str(item.url),
                timeout_seconds=timeout_seconds,
                fetcher=fetcher,
            )
        except Exception as exc:
            _LOGGER.warning(
                "event=rss.full_text_extract outcome=failed source_key=%s url=%s error=%s",
                source_key,
                item.url,
                type(exc).__name__,
            )
            continue
        if text:
            item.content = text
    return items
