"""Frozen table snapshots: typed rows and the article references held by other tables."""
import json
import re
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime

from app.core.canonicalize import canonicalize_url
from app.storage.journal_files import fingerprint
from app.storage.models_sql import Base

EXPORT_TABLES = (
    "sources", "articles", "article_aliases", "news_digest_reports", "news_digest_groups",
    "news_digest_items", "weekly_analytics_reports", "weekly_analytics_items",
    "weekly_input_observations", "weekly_decisions", "weekly_jobs", "weekly_snapshots",
    "weekly_publications",
    "admission_decisions", "collection_status",
)


# pylint: disable=too-many-return-statements
def _reference_ids(value: Any, urls: dict[str, int], ids: set[int],
                   hashes: dict[str, int]) -> set[int]:
    if isinstance(value, dict):
        found = set()
        for key, nested in value.items():
            if key == "article_id" and isinstance(nested, int) and nested in ids:
                found.add(nested)
            found.update(_reference_ids(nested, urls, ids, hashes))
        return found
    if isinstance(value, list):
        return (set().union(*(_reference_ids(v, urls, ids, hashes) for v in value))
                if value else set())
    if not isinstance(value, str):
        return set()
    if value.startswith(("{", "[")):
        try:
            return _reference_ids(json.loads(value), urls, ids, hashes)
        except ValueError:
            return set()
    if value in hashes:
        return {hashes[value]}
    if value.startswith("article-") and value[8:].isdigit() and int(value[8:]) in ids:
        return {int(value[8:])}
    if value.startswith(("http://", "https://")):
        try:
            matched = urls.get(canonicalize_url(value))
        except ValueError:
            return set()
        return {matched} if matched is not None else set()
    return set()


def dependencies(  # pylint: disable=too-many-branches
    tables: dict[str, Any],
) -> dict[int, list[dict[str, Any]]]:
    articles = tables["articles"]
    ids = {row["id"] for row in articles}
    urls = {canonicalize_url(row["url_canonical"]): row["id"] for row in articles}
    hashes = {row["url_canonical_hash"]: row["id"] for row in articles}
    for alias in tables["article_aliases"]:
        urls[canonicalize_url(alias["url"])] = alias["article_id"]
    result: dict[int, list[dict[str, Any]]] = {key: [] for key in ids}
    matches: dict[str, dict[str, set[int]]] = {}
    for name in EXPORT_TABLES:
        if name in {"articles", "sources", "collection_status"}:
            continue
        matches[name] = {}
        for row in tables[name]:
            related = _reference_ids(row, urls, ids, hashes)
            # Copied Markdown/HTML links in narrative are retained too.
            for value in row.values():
                if isinstance(value, str):
                    for url in re.findall(r'https?://[^\s<>"\)\]}]+', value):
                        related.update(_reference_ids(url.rstrip(".,;"), urls, ids, hashes))
            identity = str(row.get("id", row.get("key", row.get("report_date"))))
            matches[name][identity] = related
    for child, parent, key in (
        ("news_digest_items", "news_digest_groups", "group_id"),
        ("news_digest_groups", "news_digest_reports", "report_id"),
        ("weekly_analytics_items", "weekly_analytics_reports", "report_id"),
        ("weekly_publications", "weekly_snapshots", "snapshot_id"),
    ):
        for row in tables[child]:
            identity = str(row.get("id", row.get("report_date")))
            if child == "weekly_publications":
                matches[child][identity].update(matches[parent].get(str(row[key]), set()))
            else:
                matches[parent][str(row[key])].update(matches[child][identity])
    for name, matched in matches.items():
        for row in tables[name]:
            identity = str(row.get("id", row.get("key", row.get("report_date"))))
            row_hash = fingerprint(row) if matched[identity] else ""
            for article_id in matched[identity]:
                result[article_id].append({"table": name, "identity": identity,
                                           "row_hash": row_hash,
                                           "action": "delete" if name == "article_aliases"
                                           else "cache_update" if name == "admission_decisions"
                                           else "retain_copied_reference"})
    return {key: sorted(value, key=lambda item: (item["table"], item["identity"]))
            for key, value in result.items()}


def typed_row(name: str, row: dict[str, Any]) -> dict[str, Any]:
    values = dict(row)
    for column in Base.metadata.tables[name].columns:
        value = values.get(column.name)
        if isinstance(value, str) and (isinstance(column.type, DateTime)
                                       or column.type.python_type is datetime):
            values[column.name] = datetime.fromisoformat(value)
        elif isinstance(value, str) and isinstance(column.type, Date):
            values[column.name] = date.fromisoformat(value)
    return values


def normalize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    snapshot = dict(snapshot)
    snapshot["tables"] = {name: [typed_row(name, row) for row in rows]
                          for name, rows in snapshot["tables"].items()}
    return snapshot
