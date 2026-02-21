import calendar
from datetime import UTC, datetime
from time import struct_time

import feedparser
import httpx

from app.core.models import Article
from app.ingest.fetcher import Fetcher


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


def fetch_rss(
    source_key: str,
    url: str,
    timeout_seconds: float = 15.0,
    fetcher: Fetcher | None = None,
) -> list[Article]:
    if fetcher is not None:
        content = fetcher.fetch_bytes(source_id=source_key, url=url)
        return parse_rss(source_key=source_key, content=content)

    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        content = response.content
    return parse_rss(source_key=source_key, content=content)
