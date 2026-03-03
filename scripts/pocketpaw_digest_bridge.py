#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

_DEFAULT_TITLE = "Daily AI News Digest"
_MAX_GROUPS = 8
_MAX_ITEMS_PER_GROUP = 6
_MAX_SUMMARY_LENGTH = 400
_DEFAULT_ANTIGRAVITY_CHUNK_SIZE = 12
_CATEGORY_ORDER = (
    "AI Coding",
    "Agent Frameworks",
    "RAG & Data Systems",
    "Security",
    "Evaluation & Observability",
    "Automation",
    "Infrastructure",
    "Business & Product",
)
_CATEGORY_RULES = (
    ("Security", ("security", "attack", "prompt injection", "vulnerability", "secure", "sast")),
    (
        "Evaluation & Observability",
        ("benchmark", "eval", "evaluation", "observability", "trace", "monitor", "hallucination"),
    ),
    (
        "RAG & Data Systems",
        ("rag", "retrieval", "vector", "embedding", "weaviate", "database", "search", "index"),
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
    (
        "Automation",
        ("automation", "workflow", "document", "business process", "tutorial", "serverless"),
    ),
)
_SCRIPT_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _SCRIPT_DIR.parent
_DEFAULT_PROMPT_PATH = _ROOT_DIR / "automation" / "pocketpaw" / "antigravity_digest_prompt.txt"


def _read_json_response(
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


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _fetch_feed_items(*, base_url: str, report_date: str, limit: int) -> list[dict[str, Any]]:
    query = urlencode({"date": report_date, "limit": limit})
    items = _read_json_response(f"{base_url.rstrip('/')}/api/news/links?{query}")
    if not isinstance(items, list):
        raise RuntimeError("news links API did not return a list")
    if not items:
        raise RuntimeError("news links API returned no articles for the requested date")
    if not all(isinstance(item, dict) for item in items):
        raise RuntimeError("news links API returned an invalid article entry")
    return items


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
    response = _read_json_response(
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
        normalized_row["title"] = title
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
    for category, keywords in _CATEGORY_RULES:
        if any(keyword in haystack for keyword in keywords):
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
        title = str((titles_by_url or {}).get(url) or row["title"]).strip()
        summary = str(
            (summaries_by_url or {}).get(url)
            or _default_feed_summary(row=row, report_date=report_date)
        ).strip()
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
    config = _read_json_response(
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


def _run_antigravity_chunk(
    *,
    admin_url: str,
    api_key: str,
    model: str,
    prompt: str,
    report_date: str,
    articles: list[dict[str, Any]],
) -> dict[str, Any]:
    llm_payload = {
        "model": model,
        "max_tokens": 4000,
        "messages": [
            {
                "role": "user",
                "content": (
                    f"{prompt}\n\n"
                    "You must include every article from the provided list exactly once.\n"
                    "If a story is weak, still include it.\n"
                    "Do not omit any URL.\n\n"
                    "Input payload:\n"
                    + json.dumps(
                        {"report_date": report_date, "articles": articles},
                        ensure_ascii=False,
                    )
                ),
            }
        ],
    }

    llm_response = _read_json_response(
        f"{admin_url.rstrip('/')}/v1/messages",
        body=json.dumps(llm_payload).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    llm_text = _extract_message_text(llm_response)
    try:
        generated = json.loads(llm_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("antigravity returned non-JSON content") from exc
    return normalize_digest(generated, report_date=report_date)


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
    normalized_chunks: list[dict[str, Any]] = []
    for chunk in chunk_feed_items(feed_items, chunk_size=chunk_size):
        normalized_chunks.append(
            _run_antigravity_chunk(
                admin_url=admin_url,
                api_key=api_key,
                model=model,
                prompt=prompt,
                report_date=report_date,
                articles=chunk,
            )
        )

    merged_groups: list[dict[str, Any]] = []
    for chunk_digest in normalized_chunks:
        groups = chunk_digest.get("groups")
        if isinstance(groups, list):
            merged_groups.extend(group for group in groups if isinstance(group, dict))

    repaired = repair_digest_coverage(
        digest={"report_date": report_date, "groups": merged_groups},
        feed_items=feed_items,
        report_date=report_date,
    )
    response = _read_json_response(
        f"{base_url.rstrip('/')}/api/news/digests",
        body=json.dumps(repaired).encode("utf-8"),
    )
    if not isinstance(response, dict):
        raise RuntimeError("publish response was not a JSON object")

    saved = _read_json_response(f"{base_url.rstrip('/')}/api/news/digests?date={report_date}")
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
        "chunk_count": len(normalized_chunks),
    }


def build_feed_digest_payload(*, items: object, report_date: str) -> dict[str, Any]:
    return build_categorized_digest_payload(items=items, report_date=report_date)


def publish_feed_digest(*, base_url: str, report_date: str, limit: int) -> dict[str, Any]:
    query = urlencode({"date": report_date, "limit": limit})
    items = _read_json_response(f"{base_url.rstrip('/')}/api/news/links?{query}")
    payload = build_feed_digest_payload(items=items, report_date=report_date)

    response = _read_json_response(
        f"{base_url.rstrip('/')}/api/news/digests",
        body=json.dumps(payload).encode("utf-8"),
    )
    if not isinstance(response, dict):
        raise RuntimeError("publish response was not a JSON object")

    saved = _read_json_response(f"{base_url.rstrip('/')}/api/news/digests?date={report_date}")
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
