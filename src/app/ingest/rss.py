import calendar
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Semaphore
from time import struct_time
from typing import Literal

import feedparser
import httpx

from app.core.models import Article
from app.ingest.fetcher import Fetcher
from app.ingest.html import extract_article_text
from app.ingest.page_filter import (
    NonNewsPageError,
    html_exclusion_reason,
    log_exclusion,
    text_exclusion_reason,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class RssFetchResult:
    items: list[Article]
    not_modified: bool
    status_code: int
    etag: str | None
    last_modified: str | None
    coverage_complete: bool = True


class RssItemList(list[Article]):
    """List-compatible RSS result that preserves response metadata."""

    not_modified: bool
    status_code: int
    etag: str | None
    last_modified: str | None
    coverage_complete: bool = True


def _with_rss_metadata(items: list[Article], result: RssFetchResult) -> list[Article]:
    wrapped = RssItemList(items)
    wrapped.not_modified = result.not_modified
    wrapped.status_code = result.status_code
    wrapped.etag = result.etag
    wrapped.last_modified = result.last_modified
    wrapped.coverage_complete = getattr(result, "coverage_complete", True)
    return wrapped


def _to_datetime(value: struct_time | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(calendar.timegm(value), tz=UTC)


def parse_rss(source_key: str, content: bytes) -> list[Article]:
    parsed = feedparser.parse(content)
    items = RssItemList()
    items.coverage_complete = bool(getattr(parsed, "version", None)) and not getattr(
        parsed, "bozo", False)

    for entry in parsed.entries:
        link = getattr(entry, "link", None)
        title = getattr(entry, "title", None)
        if not link or not title:
            items.coverage_complete = False
            continue
        reason = text_exclusion_reason(str(link), str(title), str(getattr(entry, "summary", "")))
        if reason:
            log_exclusion(str(link), reason)
            continue

        published = _to_datetime(getattr(entry, "published_parsed", None))
        date_kind: Literal["published", "updated", "unknown"] = (
            "published" if published is not None else "unknown")
        if published is None:
            published = _to_datetime(getattr(entry, "updated_parsed", None))
            if published is not None:
                date_kind = "updated"

        items.append(
            Article(
                source_key=source_key,
                title=str(title).strip(),
                url=str(link).strip(),
                published_at=published,
                summary=getattr(entry, "summary", None),
                content=None,
                publication_date_kind=date_kind,
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
    reason = html_exclusion_reason(link, html_content)
    if reason:
        log_exclusion(link, reason)
        raise NonNewsPageError(reason)
    extracted = extract_article_text(html_content=html_content, url=link, strategy="trafilatura")
    return _normalize_plain_text(extracted)


def fetch_rss_with_metadata(
    source_key: str,
    url: str,
    timeout_seconds: float = 15.0,
    fetcher: Fetcher | None = None,
    *,
    if_none_match: str | None = None,
    if_modified_since: str | None = None,
) -> RssFetchResult:
    if fetcher is not None:
        request_method = getattr(fetcher, "request", None)
        if callable(request_method):
            response = request_method(
                source_id=source_key,
                url=url,
                if_none_match=if_none_match,
                if_modified_since=if_modified_since,
            )
        else:
            content = fetcher.fetch_bytes(source_id=source_key, url=url)
            items = parse_rss(source_key=source_key, content=content)
            return RssFetchResult(
                items=items,
                not_modified=False,
                status_code=200,
                etag=None,
                last_modified=None,
                coverage_complete=getattr(items, "coverage_complete", False),
            )
    else:
        headers: dict[str, str] = {}
        if if_none_match is not None:
            headers["If-None-Match"] = if_none_match
        if if_modified_since is not None:
            headers["If-Modified-Since"] = if_modified_since
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            if headers:
                response = client.get(url, headers=headers)
            else:
                response = client.get(url)
            if getattr(response, "status_code", None) != 304:
                response.raise_for_status()

    status_code = int(getattr(response, "status_code", 200))
    if status_code == 304:
        return RssFetchResult(
            items=[],
            not_modified=True,
            status_code=status_code,
            etag=getattr(response, "headers", {}).get("ETag"),
            last_modified=getattr(response, "headers", {}).get("Last-Modified"),
        )

    content = response.content
    items = parse_rss(source_key=source_key, content=content)
    headers = getattr(response, "headers", {})
    return RssFetchResult(
        items=items,
        not_modified=False,
        status_code=status_code,
        etag=headers.get("ETag"),
        last_modified=headers.get("Last-Modified"),
        coverage_complete=getattr(items, "coverage_complete", False),
    )

# pylint: disable=too-many-positional-arguments
def fetch_rss(
    source_key: str,
    url: str,
    timeout_seconds: float = 15.0,
    fetcher: Fetcher | None = None,
    extract_full_text: bool = False,
    full_text_max_items: int = 20,
    full_text_semaphore: Semaphore | None = None,
    *,
    if_none_match: str | None = None,
    if_modified_since: str | None = None,
) -> list[Article]:
    result = fetch_rss_with_metadata(
        source_key=source_key,
        url=url,
        timeout_seconds=timeout_seconds,
        fetcher=fetcher,
        if_none_match=if_none_match,
        if_modified_since=if_modified_since,
    )
    items = result.items
    if not extract_full_text:
        return _with_rss_metadata(items, result)

    for item in items[: max(0, full_text_max_items)]:
        try:
            if full_text_semaphore is not None:
                full_text_semaphore.acquire()
            text = _extract_linked_article_text(
                source_id=source_key,
                link=str(item.url),
                timeout_seconds=timeout_seconds,
                fetcher=fetcher,
            )
        except NonNewsPageError:
            items.remove(item)
            continue
        except Exception as exc:
            _LOGGER.warning(
                "event=rss.full_text_extract outcome=failed source_key=%s url=%s error=%s",
                source_key,
                item.url,
                type(exc).__name__,
            )
            continue
        finally:
            if full_text_semaphore is not None:
                full_text_semaphore.release()
        if text:
            item.content = text
        item.page_eligibility_checked = True
    return _with_rss_metadata(items, result)
