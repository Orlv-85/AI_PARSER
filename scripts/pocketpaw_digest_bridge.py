#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode, urlparse
from urllib.request import Request, urlopen

_DEFAULT_TITLE = "Daily AI News Digest"
_MAX_GROUPS = 8
_MAX_ITEMS_PER_GROUP = 6
_MAX_SUMMARY_LENGTH = 400
_MAX_TITLE_LENGTH = 120
_MAX_HEADLINE_LENGTH = 84
_DEFAULT_ANTIGRAVITY_CHUNK_SIZE = 12
_DEFAULT_ANTIGRAVITY_TITLE_CHUNK_SIZE = 8
_ANTIGRAVITY_RETRY_SUFFIX = (
    "\n\nYour previous response was invalid.\n"
    "Return valid JSON only.\n"
    "Do not include markdown.\n"
    "Do not include code fences.\n"
    "Do not include commentary.\n"
    "Do not omit any URL.\n"
)
_ANTIGRAVITY_REQUEST_RETRIES = 2
_CATEGORY_ORDER = (
    "AI Coding",
    "Agent Frameworks",
    "RAG & Data Systems",
    "Security",
    "QA & Observability",
    "Infrastructure",
    "Business & Product",
)
_RAG_STRONG_KEYWORDS = (
    "rag",
    "retrieval",
    "embedding",
    "embeddings",
    "vector database",
    "vector db",
    "vector search",
    "rerank",
    "re-ranking",
    "hybrid search",
    "knowledge base",
    "weaviate",
)
_RAG_WEAK_KEYWORDS = (
    "vector",
    "database",
)
_RAG_NEGATIVE_KEYWORDS = (
    "gpu",
    "h100",
    "cuda",
    "latency",
    "throughput",
    "kernel",
    "benchmark",
    "eval",
    "evaluation",
    "observability",
    "trace",
    "monitor",
    "testing",
    "regression",
)
_CATEGORY_RULES = (
    ("Security", ("security", "attack", "prompt injection", "vulnerability", "secure", "sast")),
    (
        "QA & Observability",
        (
            "benchmark",
            "eval",
            "evaluation",
            "observability",
            "trace",
            "monitor",
            "hallucination",
            "qa",
            "quality",
            "test",
            "testing",
            "regression",
            "verification",
        ),
    ),
    (
        "Agent Frameworks",
        ("agent", "autogen", "llamaindex", "workflow", "multi-agent", "orchestr", "tool loop"),
    ),
    (
        "AI Coding",
        ("code", "coding", "sdk", "developer", "devtool", "frontend", "react", "copilot"),
    ),
    (
        "Infrastructure",
        ("gpu", "server", "inference", "latency", "data center", "datacenter", "nvidia", "amd"),
    ),
)
_SCRIPT_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _SCRIPT_DIR.parent
_DEFAULT_PROMPT_PATH = _ROOT_DIR / "automation" / "pocketpaw" / "antigravity_digest_prompt.txt"
_UPPERCASE_TITLE_TOKENS = {
    "ai",
    "api",
    "apis",
    "ci",
    "cpu",
    "css",
    "gpu",
    "gpus",
    "html",
    "http",
    "https",
    "json",
    "llm",
    "llms",
    "qa",
    "rag",
    "sdk",
    "sql",
    "ui",
    "ux",
}
_TITLE_BRAND_REPLACEMENTS = (
    (r"\bNe Mo\b", "NeMo"),
    (r"\bCode Whisperer\b", "CodeWhisperer"),
    (r"\bLlama Index\b", "LlamaIndex"),
)
_TOPIC_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "by",
        "for",
        "from",
        "how",
        "in",
        "into",
        "is",
        "new",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "what",
        "week",
        "weeks",
        "with",
        "story",
        "stories",
        "recent",
        "prior",
        "trending",
        "trend",
        "latest",
        "up",
        "down",
    }
)
_TOPIC_TOKEN_MAX = 6
_TOPIC_MATCH_MIN_OVERLAP = 0.5
_TOPIC_MATCH_MIN_COMMON_TOKENS = 2


def read_json_response(
    url: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    request = Request(url=url, data=body)
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    if body is not None:
        request.add_header("Content-Type", "application/json")
        request.method = "POST"
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except TimeoutError as exc:
        raise RuntimeError(f"Network timeout for {url}") from exc
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error for {url}: {exc.reason}") from exc


def _is_http_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _title_case_url_token(token: str) -> str:
    if not token:
        return ""
    if token.isdigit():
        return token
    lowered = token.lower()
    if lowered in _UPPERCASE_TITLE_TOKENS:
        return lowered.upper()
    if any(char.isdigit() for char in token):
        return token.upper() if len(token) <= 4 else token[0].upper() + token[1:]
    return token.capitalize()


def _title_from_url(url: str) -> str:
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    candidate = unquote(path_parts[-1] if path_parts else parsed.netloc)
    candidate = candidate.rsplit(".", 1)[0]
    candidate = candidate.replace("_", " ").replace("-", " ").replace(".", " ")
    words = [_title_case_url_token(word) for word in candidate.split() if word]
    return " ".join(words).strip()


def _normalize_display_title(*, raw_title: str, url: str) -> str:
    title = raw_title.strip()
    if _is_http_url(title):
        return _title_from_url(title) or title
    if "://" not in title:
        return title
    parsed = urlparse(title)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return _title_from_url(title) or title
    return title


def _is_generic_digest_summary(summary: str) -> bool:
    normalized = summary.strip().lower()
    return normalized.startswith("source:") and "included in the daily digest" in normalized


def _is_weak_display_title(title: str) -> bool:
    normalized = " ".join(title.split()).strip()
    if not normalized:
        return True
    words = normalized.split()
    if len(normalized) <= 18 and len(words) <= 3:
        return True
    if len(words) == 1 and len(normalized) <= 28:
        return True
    return False


def _should_prefer_summary_title(title: str) -> bool:
    normalized = _clean_display_title_text(title)
    lowered = normalized.lower()
    if not normalized:
        return True
    if _is_weak_display_title(normalized):
        return True
    if re.match(r"^[A-Z][a-z]+ \d{4} .*update$", normalized):
        return True
    if lowered.endswith(" pricing update") or lowered.endswith(" release notes"):
        return True
    if len(normalized) > 72 and any(
        phrase in lowered
        for phrase in (
            " is ",
            " are ",
            " designed to ",
            " used to ",
            " using ",
            " with guarantees",
        )
    ):
        return True
    return False


def _summary_title_fragment(summary: str) -> str:
    candidate = summary.strip().splitlines()[0].strip()
    if not candidate:
        return ""
    for separator in (". ", "! ", "? ", ":", ";"):
        if separator in candidate:
            candidate = candidate.split(separator, 1)[0].strip()
            break
    candidate = candidate.strip(" .!?:;-")
    if len(candidate) > 84:
        candidate = candidate[:81].rstrip(" ,.;:-") + "..."
    return candidate


def _clean_display_title_text(title: str) -> str:
    normalized = " ".join(title.split()).strip()
    if not normalized:
        return ""
    normalized = re.sub(r"([.!?:;,&])([A-Za-z0-9])", r"\1 \2", normalized)
    normalized = re.sub(r"([a-z])([A-Z])", r"\1 \2", normalized)
    normalized = re.sub(
        r"\b([A-Z][a-z]{3,})(with|for|and|of|to|in)\b",
        lambda match: f"{match.group(1)} {match.group(2)}",
        normalized,
    )
    for pattern, replacement in _TITLE_BRAND_REPLACEMENTS:
        normalized = re.sub(pattern, replacement, normalized)
    return " ".join(normalized.split()).strip()


def _has_keyword(haystack: str, keyword: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(keyword).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
    return re.search(pattern, haystack) is not None


def _truncate_title(title: str) -> str:
    normalized = _clean_display_title_text(title)
    if len(normalized) <= _MAX_TITLE_LENGTH:
        return normalized
    fragments = [
        fragment.strip(" .")
        for fragment in normalized.split(". ")
        if fragment.strip(" .")
    ]
    for fragment_count in (2, 1):
        if len(fragments) >= fragment_count:
            candidate = ". ".join(fragments[:fragment_count]).strip()
            if candidate and len(candidate) <= _MAX_TITLE_LENGTH:
                return candidate
    return normalized[: _MAX_TITLE_LENGTH - 3].rstrip(" ,.;:-") + "..."


def _build_display_title(
    *,
    row: dict[str, Any],
    preferred_title: str,
    summary: str,
) -> str:
    base_title = _normalize_display_title(
        raw_title=preferred_title,
        url=str(row.get("url", "")),
    )
    source_name = str(row.get("source_name") or "").strip()
    if summary and not _is_generic_digest_summary(summary):
        fragment = _summary_title_fragment(summary)
        if fragment:
            if _should_prefer_summary_title(base_title):
                if base_title and len(base_title) <= 24:
                    lowered_fragment = fragment.lower()
                    lowered_base = base_title.lower()
                    if lowered_base not in lowered_fragment:
                        return _truncate_title(f"{base_title}: {fragment}")
                return _truncate_title(fragment)

    if not _is_weak_display_title(base_title):
        return _truncate_title(base_title)

    if source_name and base_title:
        lowered_source = source_name.lower()
        lowered_title = base_title.lower()
        if not lowered_title.startswith(lowered_source):
            return _truncate_title(f"{source_name}: {base_title}")

    return _truncate_title(base_title)


def _validate_group(group: object) -> dict[str, Any] | None:
    if not isinstance(group, dict):
        return None
    title = str(group.get("title", "")).strip()
    items = group.get("items")
    if not title or not isinstance(items, list):
        return None

    normalized_items: list[dict[str, Any]] = []
    for item in items[:_MAX_ITEMS_PER_GROUP]:
        if not isinstance(item, dict):
            continue
        item_title = str(item.get("title", "")).strip()
        summary = str(item.get("summary", "")).strip()
        url = item.get("url")
        article_id = item.get("article_id")
        if not item_title or not summary or len(summary) > _MAX_SUMMARY_LENGTH:
            continue
        if not _is_http_url(url):
            continue
        normalized_item: dict[str, Any] = {
            "title": item_title,
            "summary": summary,
            "url": str(url),
        }
        if isinstance(article_id, int):
            normalized_item["article_id"] = article_id
        normalized_items.append(normalized_item)

    if not normalized_items:
        return None
    return {"title": title, "items": normalized_items}


def normalize_digest(payload: object, *, report_date: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("digest payload must be a JSON object")
    if payload.get("report_date") != report_date:
        raise ValueError("digest report_date does not match requested report_date")

    groups = payload.get("groups")
    if not isinstance(groups, list):
        raise ValueError("digest groups must be a JSON array")

    normalized_groups: list[dict[str, Any]] = []
    for group in groups[:_MAX_GROUPS]:
        normalized = _validate_group(group)
        if normalized is not None:
            normalized_groups.append(normalized)

    if not normalized_groups:
        raise ValueError("digest contains no valid groups after normalization")

    return {
        "report_date": report_date,
        "groups": normalized_groups,
    }


def normalize_summary_batch(payload: object, *, report_date: str) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("summary payload must be a JSON object")
    if payload.get("report_date") != report_date:
        raise ValueError("summary report_date does not match requested report_date")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("summary items must be a JSON array")

    summaries_by_url: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        summary = str(item.get("summary", "")).strip()
        if not _is_http_url(url) or not summary:
            continue
        summaries_by_url[str(url)] = summary[:_MAX_SUMMARY_LENGTH]

    if not summaries_by_url:
        raise ValueError("summary payload contains no valid items")
    return summaries_by_url


def normalize_title_batch(payload: object, *, report_date: str) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("title payload must be a JSON object")
    if payload.get("report_date") != report_date:
        raise ValueError("title report_date does not match requested report_date")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("title items must be a JSON array")

    titles_by_url: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        title = _truncate_title(str(item.get("title", "")).strip())
        if not _is_http_url(url) or not title:
            continue
        titles_by_url[str(url)] = title

    if not titles_by_url:
        raise ValueError("title payload contains no valid items")
    return titles_by_url


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _fetch_feed_items(*, base_url: str, report_date: str, limit: int) -> list[dict[str, Any]]:
    query = urlencode({"date": report_date, "limit": limit})
    items = read_json_response(f"{base_url.rstrip('/')}/api/news/links?{query}")
    if not isinstance(items, list):
        raise RuntimeError("news links API did not return a list")
    if not items:
        raise RuntimeError("news links API returned no articles for the requested date")
    if not all(isinstance(item, dict) for item in items):
        raise RuntimeError("news links API returned an invalid article entry")
    return items


def _fetch_news_links_range(
    *,
    base_url: str,
    date_from: str,
    date_to: str,
    limit: int,
) -> list[dict[str, Any]]:
    start = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)
    if start > end:
        raise ValueError("date_from must be <= date_to")

    rows: list[dict[str, Any]] = []
    current = start
    while current <= end:
        offset = 0
        while True:
            query = urlencode(
                {"date": current.isoformat(), "limit": limit, "offset": offset}
            )
            daily_rows = read_json_response(f"{base_url.rstrip('/')}/api/news/links?{query}")
            if not isinstance(daily_rows, list):
                raise RuntimeError("news links API did not return a list")
            if not all(isinstance(row, dict) for row in daily_rows):
                raise RuntimeError("news links API returned an invalid article entry")
            rows.extend(daily_rows)
            if len(daily_rows) < limit:
                break
            offset += limit
        current += timedelta(days=1)
    return rows


def fetch_bundle(
    *,
    base_url: str,
    report_date: str,
    limit: int,
    out_path: Path,
    prompt_path: Path,
) -> None:
    items = _fetch_feed_items(base_url=base_url, report_date=report_date, limit=limit)

    prompt = prompt_path.read_text(encoding="utf-8")
    bundle = {
        "report_date": report_date,
        "title": _DEFAULT_TITLE,
        "prompt": prompt,
        "articles": items,
    }
    _write_json(out_path, bundle)


def validate_digest(*, report_date: str, input_path: Path, out_path: Path | None) -> dict[str, Any]:
    payload = _load_json(input_path)
    normalized = normalize_digest(payload, report_date=report_date)
    if out_path is not None:
        _write_json(out_path, normalized)
    return normalized


def publish_digest(*, base_url: str, report_date: str, input_path: Path) -> dict[str, Any]:
    normalized = validate_digest(report_date=report_date, input_path=input_path, out_path=None)
    response = read_json_response(
        f"{base_url.rstrip('/')}/api/news/digests",
        body=json.dumps(normalized).encode("utf-8"),
    )
    if not isinstance(response, dict):
        raise RuntimeError("publish response was not a JSON object")
    return response


def _default_feed_summary(*, row: dict[str, Any], report_date: str) -> str:
    source_name = str(row.get("source_name") or "unknown source").strip() or "unknown source"
    published_at = str(row.get("published_at") or report_date).strip() or report_date
    return f"Source: {source_name}. Published at {published_at}. Included in the daily digest."


def _normalize_feed_rows(items: object) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(items, list):
        raise ValueError("news links API did not return a list")
    if not items:
        raise ValueError("news links API returned no articles for the requested date")

    feed_by_url: dict[str, dict[str, Any]] = {}
    ordered_urls: list[str] = []
    for row in items:
        if not isinstance(row, dict):
            raise ValueError("news links API returned an invalid article entry")
        title = str(row.get("title", "")).strip()
        url = row.get("url")
        if not title or not _is_http_url(url):
            raise ValueError("news links API returned an article without a valid title/url")
        normalized_url = str(url)
        normalized_row = dict(row)
        normalized_row["title"] = _normalize_display_title(raw_title=title, url=normalized_url)
        normalized_row["url"] = normalized_url
        if normalized_url not in feed_by_url:
            feed_by_url[normalized_url] = normalized_row
            ordered_urls.append(normalized_url)
    return [feed_by_url[url] for url in ordered_urls], ordered_urls


def categorize_digest_item(*, row: dict[str, Any], summary: str = "") -> str:
    haystack = " ".join(
        (
            str(row.get("title", "")),
            str(row.get("source_name", "")),
            str(row.get("url", "")),
            summary,
        )
    ).lower()
    has_rag_negative = any(
        _has_keyword(haystack, keyword) for keyword in _RAG_NEGATIVE_KEYWORDS
    )
    if (
        any(_has_keyword(haystack, keyword) for keyword in _RAG_STRONG_KEYWORDS)
        and not has_rag_negative
    ):
        return "RAG & Data Systems"
    if (
        any(_has_keyword(haystack, keyword) for keyword in _RAG_WEAK_KEYWORDS)
        and not has_rag_negative
        and any(
            _has_keyword(haystack, signal)
            for signal in ("retrieval", "embedding", "knowledge", "semantic")
        )
    ):
        return "RAG & Data Systems"
    for category, keywords in _CATEGORY_RULES:
        if any(_has_keyword(haystack, keyword) for keyword in keywords):
            return category
    return "Business & Product"


def build_categorized_digest_payload(
    *,
    items: object,
    report_date: str,
    summaries_by_url: dict[str, str] | None = None,
    titles_by_url: dict[str, str] | None = None,
) -> dict[str, Any]:
    normalized_rows, ordered_urls = _normalize_feed_rows(items)

    grouped_items: dict[str, list[dict[str, str]]] = {category: [] for category in _CATEGORY_ORDER}
    row_by_url = {str(row["url"]): row for row in normalized_rows}

    for url in ordered_urls:
        row = row_by_url[url]
        preferred_title = str((titles_by_url or {}).get(url) or row["title"]).strip()
        summary = str(
            (summaries_by_url or {}).get(url)
            or _default_feed_summary(row=row, report_date=report_date)
        ).strip()
        title = _build_display_title(
            row=row,
            preferred_title=preferred_title,
            summary=summary,
        )
        category = categorize_digest_item(row=row, summary=summary)
        grouped_items[category].append(
            {
                "title": title,
                "summary": summary[:_MAX_SUMMARY_LENGTH],
                "url": url,
            }
        )

    groups = [
        {"title": category, "items": grouped_items[category]}
        for category in _CATEGORY_ORDER
        if grouped_items[category]
    ]
    if not groups:
        raise RuntimeError("categorized digest contains no groups")
    return {"report_date": report_date, "groups": groups}


def repair_digest_coverage(
    *,
    digest: dict[str, Any],
    feed_items: list[dict[str, Any]],
    report_date: str,
) -> dict[str, Any]:
    normalized_rows, _ = _normalize_feed_rows(feed_items)
    feed_by_url = {str(row["url"]): row for row in normalized_rows}
    titles_by_url: dict[str, str] = {}
    summaries_by_url: dict[str, str] = {}
    seen_urls: set[str] = set()
    for group in digest.get("groups", []):
        if not isinstance(group, dict):
            continue
        for item in group.get("items", []):
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", ""))
            if url not in feed_by_url or url in seen_urls:
                continue
            title = (
                str(item.get("title", "")).strip()
                or str(feed_by_url[url].get("title") or "").strip()
            )
            summary = str(item.get("summary", "")).strip() or _default_feed_summary(
                row=feed_by_url[url],
                report_date=report_date,
            )
            if not title or not _is_http_url(url):
                continue
            titles_by_url[url] = title
            summaries_by_url[url] = summary[:_MAX_SUMMARY_LENGTH]
            seen_urls.add(url)
    return build_categorized_digest_payload(
        items=normalized_rows,
        report_date=report_date,
        summaries_by_url=summaries_by_url,
        titles_by_url=titles_by_url,
    )


def _extract_message_text(payload: object) -> str:
    if not isinstance(payload, dict):
        raise RuntimeError("antigravity response was not a JSON object")
    content = payload.get("content")
    if not isinstance(content, list):
        raise RuntimeError("antigravity response did not include a content array")
    text_parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type", ""))
        if item_type in {"text", "output_text"}:
            text = item.get("text")
            if isinstance(text, str):
                text_parts.append(text)
    if not text_parts:
        raise RuntimeError("antigravity response did not include text content")
    return "\n".join(text_parts).strip()


def _fetch_antigravity_proxy_api_key(*, admin_url: str, admin_password: str) -> str:
    config = read_json_response(
        f"{admin_url.rstrip('/')}/api/config",
        headers={"Authorization": admin_password},
    )
    if not isinstance(config, dict):
        raise RuntimeError("antigravity config response was not a JSON object")
    proxy = config.get("proxy")
    if not isinstance(proxy, dict):
        raise RuntimeError("antigravity config did not include proxy settings")
    api_key = proxy.get("api_key")
    if not isinstance(api_key, str) or not api_key.strip():
        raise RuntimeError("antigravity proxy api_key is missing")
    return api_key


def chunk_feed_items(
    feed_items: list[dict[str, Any]],
    *,
    chunk_size: int,
) -> list[list[dict[str, Any]]]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    return [
        feed_items[start : start + chunk_size]
        for start in range(0, len(feed_items), chunk_size)
    ]


def _is_transient_request_error(exc: RuntimeError) -> bool:
    message = str(exc).lower()
    return "network error" in message or "network timeout" in message


def run_antigravity_chunk(
    *,
    admin_url: str,
    api_key: str,
    model: str,
    prompt: str,
    report_date: str,
    articles: list[dict[str, Any]],
) -> dict[str, str]:
    base_content = (
        f"{prompt}\n\n"
        "You must return only per-article summaries for the provided list.\n"
        "Do not group the articles.\n"
        "Do not omit any URL.\n"
        "Every returned item must include the original URL and a concise technical summary.\n\n"
        "Input payload:\n"
        + json.dumps(
            {"report_date": report_date, "articles": articles},
            ensure_ascii=False,
        )
    )

    errors: list[str] = []
    for attempt in range(2):
        content = base_content if attempt == 0 else base_content + _ANTIGRAVITY_RETRY_SUFFIX
        llm_payload = {
            "model": model,
            "max_tokens": 4000,
            "messages": [{"role": "user", "content": content}],
        }
        llm_response: Any | None = None
        for request_attempt in range(_ANTIGRAVITY_REQUEST_RETRIES):
            try:
                llm_response = read_json_response(
                    f"{admin_url.rstrip('/')}/v1/messages",
                    body=json.dumps(llm_payload).encode("utf-8"),
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                )
                break
            except RuntimeError as exc:
                if not _is_transient_request_error(exc):
                    raise
                errors.append(str(exc))
                if request_attempt + 1 == _ANTIGRAVITY_REQUEST_RETRIES:
                    llm_response = None
        if llm_response is None:
            continue
        llm_text = _extract_message_text(llm_response)
        try:
            generated = json.loads(llm_text)
        except json.JSONDecodeError:
            errors.append("non-JSON content")
            continue
        try:
            return normalize_summary_batch(generated, report_date=report_date)
        except ValueError as exc:
            errors.append(str(exc))
            continue

    raise RuntimeError(
        "antigravity returned invalid content after retry: "
        + ", ".join(errors or ["unknown error"])
    )


def run_antigravity_title_chunk(
    *,
    admin_url: str,
    api_key: str,
    model: str,
    report_date: str,
    articles: list[dict[str, Any]],
) -> dict[str, str]:
    base_content = (
        "Rewrite weak article titles into short editorial headlines.\n"
        "Return only JSON.\n"
        "Use this exact structure:\n"
        '{"report_date":"YYYY-MM-DD","items":[{"url":"https://...","title":"Short headline"}]}\n'
        "Rules:\n"
        "- Include every input URL exactly once.\n"
        "- Keep each title factual and technical.\n"
        "- Keep each title concise, ideally under 12 words.\n"
        "- Do not add markdown or commentary.\n"
        "- Do not end titles with a period.\n\n"
        "Input payload:\n"
        + json.dumps(
            {"report_date": report_date, "articles": articles},
            ensure_ascii=False,
        )
    )

    errors: list[str] = []
    for attempt in range(2):
        content = base_content if attempt == 0 else base_content + _ANTIGRAVITY_RETRY_SUFFIX
        llm_payload = {
            "model": model,
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": content}],
        }
        llm_response: Any | None = None
        for request_attempt in range(_ANTIGRAVITY_REQUEST_RETRIES):
            try:
                llm_response = read_json_response(
                    f"{admin_url.rstrip('/')}/v1/messages",
                    body=json.dumps(llm_payload).encode("utf-8"),
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                )
                break
            except RuntimeError as exc:
                if not _is_transient_request_error(exc):
                    raise
                errors.append(str(exc))
                if request_attempt + 1 == _ANTIGRAVITY_REQUEST_RETRIES:
                    llm_response = None
        if llm_response is None:
            continue
        llm_text = _extract_message_text(llm_response)
        try:
            generated = json.loads(llm_text)
        except json.JSONDecodeError:
            errors.append("non-JSON content")
            continue
        try:
            return normalize_title_batch(generated, report_date=report_date)
        except ValueError as exc:
            errors.append(str(exc))
            continue

    raise RuntimeError(
        "antigravity returned invalid title content after retry: "
        + ", ".join(errors or ["unknown error"])
    )


def publish_antigravity_digest(
    *,
    base_url: str,
    report_date: str,
    limit: int,
    admin_url: str,
    admin_password: str,
    model: str,
    prompt_path: Path,
    chunk_size: int = _DEFAULT_ANTIGRAVITY_CHUNK_SIZE,
) -> dict[str, Any]:
    feed_items = _fetch_feed_items(base_url=base_url, report_date=report_date, limit=limit)
    prompt = prompt_path.read_text(encoding="utf-8").strip()
    api_key = _fetch_antigravity_proxy_api_key(admin_url=admin_url, admin_password=admin_password)
    summaries_by_url: dict[str, str] = {}
    for chunk in chunk_feed_items(feed_items, chunk_size=chunk_size):
        chunk_summaries = run_antigravity_chunk(
            admin_url=admin_url,
            api_key=api_key,
            model=model,
            prompt=prompt,
            report_date=report_date,
            articles=chunk,
        )
        summaries_by_url.update(chunk_summaries)

    normalized_rows, _ = _normalize_feed_rows(feed_items)
    title_rewrite_candidates = [
        {
            "url": str(row["url"]),
            "title": str(row["title"]),
            "summary": str(summaries_by_url.get(str(row["url"]), "")),
        }
        for row in normalized_rows
        if _should_prefer_summary_title(str(row["title"]))
        and str(summaries_by_url.get(str(row["url"]), "")).strip()
    ]
    rewritten_titles_by_url: dict[str, str] = {}
    for chunk in chunk_feed_items(
        title_rewrite_candidates,
        chunk_size=_DEFAULT_ANTIGRAVITY_TITLE_CHUNK_SIZE,
    ):
        try:
            rewritten_titles_by_url.update(
                run_antigravity_title_chunk(
                    admin_url=admin_url,
                    api_key=api_key,
                    model=model,
                    report_date=report_date,
                    articles=chunk,
                )
            )
        except RuntimeError:
            continue

    payload = build_categorized_digest_payload(
        items=feed_items,
        report_date=report_date,
        summaries_by_url=summaries_by_url,
        titles_by_url=rewritten_titles_by_url,
    )
    response = read_json_response(
        f"{base_url.rstrip('/')}/api/news/digests",
        body=json.dumps(payload).encode("utf-8"),
    )
    if not isinstance(response, dict):
        raise RuntimeError("publish response was not a JSON object")

    saved = read_json_response(f"{base_url.rstrip('/')}/api/news/digests?date={report_date}")
    if not isinstance(saved, dict):
        raise RuntimeError("saved digest response was not a JSON object")
    saved_groups = saved.get("groups")
    if not isinstance(saved_groups, list):
        raise RuntimeError("saved digest response did not contain a valid groups array")

    expected_urls = sorted(str(row["url"]) for row in feed_items)
    actual_urls = sorted(
        str(item["url"])
        for group in saved_groups
        if isinstance(group, dict)
        for item in group.get("items", [])
        if isinstance(item, dict) and "url" in item
    )
    if expected_urls != actual_urls:
        raise RuntimeError(
            "saved digest links do not match fetched links: "
            f"expected={len(expected_urls)} actual={len(actual_urls)}"
        )

    return {
        "report_date": report_date,
        "fetched_count": len(expected_urls),
        "saved_count": len(actual_urls),
        "group_count": len(saved_groups),
        "model": model,
        "mode": "antigravity",
        "chunk_count": len(chunk_feed_items(feed_items, chunk_size=chunk_size)),
    }


def build_feed_digest_payload(*, items: object, report_date: str) -> dict[str, Any]:
    return build_categorized_digest_payload(items=items, report_date=report_date)


def publish_feed_digest(*, base_url: str, report_date: str, limit: int) -> dict[str, Any]:
    query = urlencode({"date": report_date, "limit": limit})
    items = read_json_response(f"{base_url.rstrip('/')}/api/news/links?{query}")
    payload = build_feed_digest_payload(items=items, report_date=report_date)

    response = read_json_response(
        f"{base_url.rstrip('/')}/api/news/digests",
        body=json.dumps(payload).encode("utf-8"),
    )
    if not isinstance(response, dict):
        raise RuntimeError("publish response was not a JSON object")

    saved = read_json_response(f"{base_url.rstrip('/')}/api/news/digests?date={report_date}")
    if not isinstance(saved, dict):
        raise RuntimeError("saved digest response was not a JSON object")
    saved_groups = saved.get("groups")
    if not isinstance(saved_groups, list):
        raise RuntimeError("saved digest response did not contain a valid groups array")

    expected_urls = sorted(str(row["url"]) for row in items)
    actual_urls = sorted(
        str(item["url"])
        for group in saved_groups
        if isinstance(group, dict)
        for item in group.get("items", [])
        if isinstance(item, dict) and "url" in item
    )
    if expected_urls != actual_urls:
        raise RuntimeError(
            "saved digest links do not match fetched links: "
            f"expected={len(expected_urls)} actual={len(actual_urls)}"
        )

    return {
        "report_date": report_date,
        "fetched_count": len(expected_urls),
        "saved_count": len(actual_urls),
        "group_count": len(saved_groups),
    }


def _parse_iso_dt(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _weekly_item_fallback_summary(*, row: dict[str, Any]) -> str:
    source_name = str(row.get("source_name") or "unknown source").strip() or "unknown source"
    published_raw = str(row.get("published_at") or "").strip()
    published_on = ""
    if published_raw:
        try:
            published_on = _parse_iso_dt(published_raw).date().isoformat()
        except ValueError:
            published_on = published_raw
    if published_on:
        return f"Reported by {source_name} on {published_on}."
    return f"Reported by {source_name}."


def _weekly_item_summary(*, row: dict[str, Any]) -> str:
    for key in ("summary", "content"):
        candidate = str(row.get(key) or "").strip()
        if candidate and candidate.lower() != "no summary available.":
            return candidate
    return _weekly_item_fallback_summary(row=row)


def _normalize_topic_token(token: str) -> str:
    normalized = token.lower().strip()
    if len(normalized) <= 2:
        return normalized
    for suffix in ("ing", "ed", "es", "s"):
        if normalized.endswith(suffix) and len(normalized) > len(suffix) + 2:
            normalized = normalized[: -len(suffix)]
            break
    return normalized


def _topic_tokens_from_title(title: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", title.lower())
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in words:
        token = _normalize_topic_token(raw)
        if (
            not token
            or token in _TOPIC_STOPWORDS
            or (len(token) <= 2 and not token.isdigit())
            or token in seen
        ):
            continue
        seen.add(token)
        tokens.append(token)
        if len(tokens) >= _TOPIC_TOKEN_MAX:
            break
    if tokens:
        return tokens
    fallback = " ".join(words).strip() or title.lower().strip()
    return [fallback]


def _topic_overlap_score(left_tokens: set[str], right_tokens: set[str]) -> tuple[int, float]:
    if not left_tokens or not right_tokens:
        return (0, 0.0)
    common_count = len(left_tokens & right_tokens)
    smaller_len = float(min(len(left_tokens), len(right_tokens)))
    return (common_count, common_count / smaller_len)


def _find_best_topic_match(
    *,
    recent_tokens: set[str],
    prior_topics: dict[str, dict[str, Any]],
    excluded_keys: set[str],
) -> str | None:
    best_key: str | None = None
    best_common = 0
    best_ratio = 0.0
    for prior_key, prior_topic in prior_topics.items():
        if prior_key in excluded_keys:
            continue
        common_count, overlap_ratio = _topic_overlap_score(
            recent_tokens,
            set(cast(list[str], prior_topic["tokens"])),
        )
        if (
            common_count < _TOPIC_MATCH_MIN_COMMON_TOKENS
            or overlap_ratio < _TOPIC_MATCH_MIN_OVERLAP
        ):
            continue
        if (common_count, overlap_ratio) > (best_common, best_ratio):
            best_key = prior_key
            best_common = common_count
            best_ratio = overlap_ratio
    return best_key


def _weekly_best_by_title(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    for row in rows:
        title = str(row.get("title", "")).strip()
        url = str(row.get("url", "")).strip()
        if not title or not _is_http_url(url):
            continue
        topic_tokens = set(_topic_tokens_from_title(title))
        topic_key = " ".join(sorted(topic_tokens))
        counts[topic_key] = counts.get(topic_key, 0) + 1
        try:
            published_at = _parse_iso_dt(str(row.get("published_at", "")))
        except ValueError:
            continue
        try:
            raw_rank_score = float(row.get("rank_score", 0.0))
        except (TypeError, ValueError):
            raw_rank_score = 0.0
        has_explicit_rank = raw_rank_score > 0.0
        rank_score = raw_rank_score if has_explicit_rank else float(counts[topic_key])
        normalized = {
            "title": title,
            "summary": _weekly_item_summary(row=row),
            "url": url,
            "published_at": published_at,
            "rank_score": rank_score,
            "has_explicit_rank": has_explicit_rank,
            "tokens": list(topic_tokens),
        }
        current = grouped.get(topic_key)
        if current is None or (rank_score, published_at) > (
            float(current["rank_score"]),
            current["published_at"],
        ):
            grouped[topic_key] = normalized
        else:
            if not bool(current.get("has_explicit_rank", False)):
                current["rank_score"] = max(
                    float(current["rank_score"]),
                    float(counts[topic_key]),
                )

    for topic_key, item in grouped.items():
        if not bool(item.get("has_explicit_rank", False)):
            item["rank_score"] = max(
                float(item["rank_score"]),
                float(counts.get(topic_key, 1)),
            )
    return grouped


def _weekly_to_items(
    rows: list[dict[str, Any]],
    *,
    sort_key: str,
    limit: int = 3,
) -> list[dict[str, str]]:
    if sort_key == "published_at":
        ordered = sorted(rows, key=lambda row: row["published_at"], reverse=True)
    else:
        ordered = sorted(
            rows,
            key=lambda row: (float(row["rank_score"]), row["published_at"]),
            reverse=True,
        )
    return [
        {
            "title": str(row["title"]),
            "summary": str(row["summary"]),
            "url": str(row["url"]),
        }
        for row in ordered[:limit]
    ]


def _weekly_build_summary(
    *,
    date_from: date,
    date_to: date,
    recent_rows: list[dict[str, Any]],
    prior_rows: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
    trending_up_rows: list[dict[str, Any]],
    trending_down_rows: list[dict[str, Any]],
) -> str:
    recent_count = len(recent_rows)
    prior_count = len(prior_rows)
    if recent_count == 0:
        return f"No AI news signals between {date_from.isoformat()} and {date_to.isoformat()}."
    delta = recent_count - prior_count
    if delta > 0:
        trend = "Momentum increased versus the previous week."
    elif delta < 0:
        trend = "Momentum cooled versus the previous week."
    else:
        trend = "Momentum held steady versus the previous week."
    change = f"+{delta}" if delta > 0 else str(delta)
    top_titles = [str(row["title"]) for row in recent_rows[:2]]
    top_focus = ", ".join(top_titles) if top_titles else "no dominant topic"
    return (
        f"Weekly summary for {date_from.isoformat()} to {date_to.isoformat()}: "
        f"{recent_count} notable AI stories ({change} vs previous week). {trend} "
        f"Signals: {len(new_rows)} new, {len(trending_up_rows)} trending up, "
        f"{len(trending_down_rows)} trending down. Top focus: {top_focus}."
    )


def build_feed_weekly_payload(
    *,
    recent_items: list[dict[str, Any]],
    prior_items: list[dict[str, Any]],
    report_date: str,
) -> dict[str, Any]:
    report_date_obj = date.fromisoformat(report_date)
    date_from = report_date_obj - timedelta(days=6)
    date_to = report_date_obj
    prior_date_to = date_from - timedelta(days=1)
    prior_date_from = prior_date_to - timedelta(days=6)

    recent_by_title = _weekly_best_by_title(recent_items)
    prior_by_title = _weekly_best_by_title(prior_items)

    new_rows: list[dict[str, Any]] = []
    trending_up_rows: list[dict[str, Any]] = []
    matched_prior_keys: set[str] = set()
    for _, recent_row in recent_by_title.items():
        prior_key = _find_best_topic_match(
            recent_tokens=set(cast(list[str], recent_row["tokens"])),
            prior_topics=prior_by_title,
            excluded_keys=matched_prior_keys,
        )
        if prior_key is None:
            new_rows.append(recent_row)
            continue
        matched_prior_keys.add(prior_key)
        if float(recent_row["rank_score"]) > float(prior_by_title[prior_key]["rank_score"]):
            trending_up_rows.append(recent_row)

    trending_down_rows: list[dict[str, Any]] = []
    for prior_key, prior_row in prior_by_title.items():
        if prior_key not in matched_prior_keys:
            trending_down_rows.append(prior_row)

    summary = _weekly_build_summary(
        date_from=date_from,
        date_to=date_to,
        recent_rows=list(recent_by_title.values()),
        prior_rows=list(prior_by_title.values()),
        new_rows=new_rows,
        trending_up_rows=trending_up_rows,
        trending_down_rows=trending_down_rows,
    )

    return {
        "report_date": report_date,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "summary": summary,
        "new": _weekly_to_items(new_rows, sort_key="published_at"),
        "trending_up": _weekly_to_items(trending_up_rows, sort_key="rank_score"),
        "trending_down": _weekly_to_items(trending_down_rows, sort_key="rank_score"),
        "window": {
            "recent_date_from": date_from.isoformat(),
            "recent_date_to": date_to.isoformat(),
            "prior_date_from": prior_date_from.isoformat(),
            "prior_date_to": prior_date_to.isoformat(),
        },
    }


def publish_feed_weekly(
    *,
    base_url: str,
    report_date: str,
    limit: int,
) -> dict[str, Any]:
    report_date_obj = date.fromisoformat(report_date)
    date_from = report_date_obj - timedelta(days=6)
    prior_date_to = date_from - timedelta(days=1)
    prior_date_from = prior_date_to - timedelta(days=6)

    recent_items = _fetch_news_links_range(
        base_url=base_url,
        date_from=date_from.isoformat(),
        date_to=report_date,
        limit=limit,
    )
    prior_items = _fetch_news_links_range(
        base_url=base_url,
        date_from=prior_date_from.isoformat(),
        date_to=prior_date_to.isoformat(),
        limit=limit,
    )
    payload = build_feed_weekly_payload(
        recent_items=recent_items,
        prior_items=prior_items,
        report_date=report_date,
    )
    window = payload.pop("window", {})

    response = read_json_response(
        f"{base_url.rstrip('/')}/api/news/weekly-analytics",
        body=json.dumps(payload).encode("utf-8"),
    )
    if not isinstance(response, dict):
        raise RuntimeError("publish weekly response was not a JSON object")

    saved = read_json_response(
        f"{base_url.rstrip('/')}/api/news/weekly-analytics?date={report_date}"
    )
    if not isinstance(saved, dict):
        raise RuntimeError("saved weekly response was not a JSON object")

    return {
        "report_date": report_date,
        "recent_fetched_count": len(recent_items),
        "prior_fetched_count": len(prior_items),
        "saved_new_count": len(saved.get("new", [])) if isinstance(saved.get("new"), list) else 0,
        "saved_trending_up_count": (
            len(saved.get("trending_up", [])) if isinstance(saved.get("trending_up"), list) else 0
        ),
        "saved_trending_down_count": (
            len(saved.get("trending_down", []))
            if isinstance(saved.get("trending_down"), list)
            else 0
        ),
        "window": window,
        "mode": "feed_weekly",
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PocketPaw bridge for AI_PARSER daily digests")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser(
        "fetch-bundle",
        help="Fetch article links and write bundle JSON",
    )
    fetch_parser.add_argument("--base-url", required=True)
    fetch_parser.add_argument("--report-date", required=True)
    fetch_parser.add_argument("--limit", type=int, default=50)
    fetch_parser.add_argument("--out", required=True)
    fetch_parser.add_argument("--prompt", default=str(_DEFAULT_PROMPT_PATH))

    validate_parser = subparsers.add_parser(
        "validate-digest",
        help="Validate and normalize digest JSON",
    )
    validate_parser.add_argument("--report-date", required=True)
    validate_parser.add_argument("--input", required=True)
    validate_parser.add_argument("--out", required=False)

    publish_parser = subparsers.add_parser(
        "publish-digest",
        help="Validate and publish digest JSON",
    )
    publish_parser.add_argument("--base-url", required=True)
    publish_parser.add_argument("--report-date", required=True)
    publish_parser.add_argument("--input", required=True)

    publish_feed_parser = subparsers.add_parser(
        "publish-feed-digest",
        help="Build a digest from the public link feed, publish it, and verify full link coverage",
    )
    publish_feed_parser.add_argument("--base-url", required=True)
    publish_feed_parser.add_argument("--report-date", required=True)
    publish_feed_parser.add_argument("--limit", type=int, default=200)

    publish_feed_weekly_parser = subparsers.add_parser(
        "publish-feed-weekly",
        help=(
            "Build weekly analytics from news export ranges, publish to weekly endpoint, "
            "and verify saved payload"
        ),
    )
    publish_feed_weekly_parser.add_argument("--base-url", required=True)
    publish_feed_weekly_parser.add_argument("--report-date", required=True)
    publish_feed_weekly_parser.add_argument("--limit", type=int, default=200)

    publish_ai_parser = subparsers.add_parser(
        "publish-antigravity-digest",
        help=(
            "Generate a digest via Antigravity, repair coverage, "
            "publish it, and verify full link coverage"
        ),
    )
    publish_ai_parser.add_argument("--base-url", required=True)
    publish_ai_parser.add_argument("--report-date", required=True)
    publish_ai_parser.add_argument("--limit", type=int, default=200)
    publish_ai_parser.add_argument("--antigravity-url", required=True)
    publish_ai_parser.add_argument(
        "--antigravity-admin-password",
        default=os.environ.get("ANTIGRAVITY_ADMIN_PASSWORD", ""),
    )
    publish_ai_parser.add_argument(
        "--antigravity-model",
        default=os.environ.get("ANTIGRAVITY_MODEL", "gemini-3-flash"),
    )
    publish_ai_parser.add_argument(
        "--antigravity-chunk-size",
        type=int,
        default=int(os.environ.get("ANTIGRAVITY_CHUNK_SIZE", _DEFAULT_ANTIGRAVITY_CHUNK_SIZE)),
    )
    publish_ai_parser.add_argument("--prompt", default=str(_DEFAULT_PROMPT_PATH))

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        if args.command == "fetch-bundle":
            fetch_bundle(
                base_url=args.base_url,
                report_date=args.report_date,
                limit=args.limit,
                out_path=Path(args.out),
                prompt_path=Path(args.prompt),
            )
            return 0
        if args.command == "validate-digest":
            normalized = validate_digest(
                report_date=args.report_date,
                input_path=Path(args.input),
                out_path=Path(args.out) if args.out else None,
            )
            if not args.out:
                sys.stdout.write(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n")
            return 0
        if args.command == "publish-digest":
            response = publish_digest(
                base_url=args.base_url,
                report_date=args.report_date,
                input_path=Path(args.input),
            )
            sys.stdout.write(json.dumps(response, ensure_ascii=False, indent=2) + "\n")
            return 0
        if args.command == "publish-feed-digest":
            response = publish_feed_digest(
                base_url=args.base_url,
                report_date=args.report_date,
                limit=args.limit,
            )
            sys.stdout.write(json.dumps(response, ensure_ascii=False, indent=2) + "\n")
            return 0
        if args.command == "publish-feed-weekly":
            response = publish_feed_weekly(
                base_url=args.base_url,
                report_date=args.report_date,
                limit=args.limit,
            )
            sys.stdout.write(json.dumps(response, ensure_ascii=False, indent=2) + "\n")
            return 0
        if args.command == "publish-antigravity-digest":
            if not args.antigravity_admin_password:
                raise RuntimeError("antigravity admin password is required")
            response = publish_antigravity_digest(
                base_url=args.base_url,
                report_date=args.report_date,
                limit=args.limit,
                admin_url=args.antigravity_url,
                admin_password=args.antigravity_admin_password,
                model=args.antigravity_model,
                prompt_path=Path(args.prompt),
                chunk_size=args.antigravity_chunk_size,
            )
            sys.stdout.write(json.dumps(response, ensure_ascii=False, indent=2) + "\n")
            return 0
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
