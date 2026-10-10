"""Read-only cleanup planning and reversible row backups. No deletion operation."""
import hashlib
import json
from collections import Counter
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, MetaData, create_engine, insert, select, text
from sqlalchemy.dialects import postgresql

from app.core.canonicalize import canonicalize_url
from app.ingest.page_filter import path_parts, text_exclusion_reason, url_exclusion_reason
from app.storage.models_sql import Base

EXPORT_TABLES = (
    "sources", "articles", "article_aliases", "news_digest_reports", "news_digest_groups",
    "news_digest_items", "weekly_analytics_reports", "weekly_analytics_items",
    "weekly_input_observations", "weekly_decisions", "weekly_jobs", "weekly_snapshots",
    "weekly_publications",
)


def export_database(database_url: str) -> dict[str, Any]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            if engine.dialect.name == "postgresql":
                connection = connection.execution_options(isolation_level="REPEATABLE READ")
            with connection.begin():
                if engine.dialect.name == "postgresql":
                    connection.execute(text("SET TRANSACTION READ ONLY"))
                elif engine.dialect.name == "sqlite":
                    connection.execute(text("PRAGMA query_only = ON"))
                else:
                    raise ValueError("Only PostgreSQL and SQLite read-only exports are supported")
                metadata = MetaData()
                metadata.reflect(bind=connection, only=EXPORT_TABLES)
                return {"exported_at": datetime.now(UTC).isoformat(),
                        "transaction": "READ ONLY", "tables": {
                    name: [dict(row) for row in connection.execute(
                        select(metadata.tables[name])).mappings()]
                    for name in EXPORT_TABLES
                }}
    finally:
        engine.dispose()


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
        matched = urls.get(canonicalize_url(value))
        return {matched} if matched is not None else set()
    return set()


def build_cleanup_plan(export: dict[str, Any]) -> dict[str, Any]:
    tables = export["tables"]
    missing = set(EXPORT_TABLES) - set(tables)
    if missing:
        raise ValueError(f"Incomplete dependency export: {sorted(missing)}")
    sources = {row["id"]: row for row in tables["sources"]}
    confident: list[dict[str, Any]] = []
    uncertain: list[dict[str, Any]] = []
    for row in sorted(tables["articles"], key=lambda item: item["id"]):
        reason = url_exclusion_reason(row["url"])
        destination = confident
        if reason is None:
            reason = text_exclusion_reason(row["url"], row["title"],
                                           row.get("content") or row.get("summary") or "")
            destination = uncertain
        parts = path_parts(row["url"])
        if reason is None and parts and parts[0] in {
            "products", "solutions", "services", "features", "platform", "capabilities",
            "industry", "industries", "need", "framework",
        }:
            reason = "commercial_section_requires_review"
            destination = uncertain
        if reason is None:
            continue
        source = sources.get(row["source_id"], {})
        destination.append({"id": row["id"], "url": row["url"], "title": row["title"],
                            "source_id": row["source_id"], "source": source.get("name"),
                            "source_key": source.get("source_key"), "reason": reason,
                            "published_at": str(row["published_at"])})
    ids = {row["id"] for row in confident}
    urls = {canonicalize_url(row["url"]): row["id"] for row in confident}
    hashes = {row["url_canonical_hash"]: row["id"] for row in tables["articles"]
              if row["id"] in ids}
    dependencies: dict[str, list[dict[str, Any]]] = {}
    for name in EXPORT_TABLES:
        if name in {"articles", "sources"}:
            continue
        matches = []
        for row in tables[name]:
            related = _reference_ids(row, urls, ids, hashes)
            if related:
                matches.append({"id": row.get("id", row.get("report_date")),
                                "article_ids": sorted(related)})
        dependencies[name] = matches
    for child, parent, foreign_key in (
        ("news_digest_items", "news_digest_groups", "group_id"),
        ("news_digest_groups", "news_digest_reports", "report_id"),
        ("weekly_analytics_items", "weekly_analytics_reports", "report_id"),
    ):
        child_matches = {row["id"]: row["article_ids"] for row in dependencies[child]}
        affected: dict[Any, set[int]] = {}
        for row in tables[child]:
            if row["id"] in child_matches:
                affected.setdefault(row[foreign_key], set()).update(child_matches[row["id"]])
        dependencies[parent] = [{"id": key, "article_ids": sorted(values)}
                                for key, values in sorted(affected.items())]
    snapshots = {row["id"]: row["article_ids"] for row in dependencies["weekly_snapshots"]}
    dependencies["weekly_publications"] = [
        {"id": str(row["report_date"]), "article_ids": snapshots[row["snapshot_id"]]}
        for row in tables["weekly_publications"] if row["snapshot_id"] in snapshots
    ]
    digest = hashlib.sha256(json.dumps(confident, sort_keys=True).encode()).hexdigest()
    return {
        "exported_at": export.get("exported_at"), "mode": "dry-run",
        "candidate_sha256": digest, "scanned_articles": len(tables["articles"]),
        "confident_count": len(confident), "uncertain_count": len(uncertain),
        "confident_by_reason": dict(sorted(Counter(r["reason"] for r in confident).items())),
        "uncertain_by_reason": dict(sorted(Counter(r["reason"] for r in uncertain).items())),
        "confident": confident, "uncertain": uncertain, "dependencies": dependencies,
        "dependency_counts": {name: len(rows) for name, rows in dependencies.items()},
        "proposed_deletions": {"articles": sorted(ids), "article_aliases": [
            row["id"] for row in tables["article_aliases"] if row["article_id"] in ids]},
        "consequences": [
            "Proposed article deletions remove these pages from live article queries.",
            "Aliases referencing proposed articles must be deleted first (foreign key).",
            "Digest and legacy weekly items copy URLs; deleting articles does not remove them.",
            "Weekly jobs, observations, decisions and snapshots are frozen; preserve them.",
            "Stored summaries/counts can still include excluded pages; no reports are regenerated.",
            "Uncertain records are excluded from the proposed deletion set.",
        ],
    }


def restoration_sql(export: dict[str, Any], plan: dict[str, Any]) -> str:
    lines = ["-- Restore only the proposed deletions; sources must still exist.", "BEGIN;"]
    for name in ("articles", "article_aliases"):
        ids = set(plan["proposed_deletions"][name])
        table = Base.metadata.tables[name]
        for row in export["tables"][name]:
            if row["id"] not in ids:
                continue
            values = dict(row)
            for column in table.columns:
                value = values.get(column.name)
                if isinstance(value, str) and isinstance(column.type, DateTime):
                    values[column.name] = datetime.fromisoformat(value)
                elif isinstance(value, str) and isinstance(column.type, Date):
                    values[column.name] = date.fromisoformat(value)
            statement = insert(table).values(values)
            lines.append(str(statement.compile(dialect=postgresql.dialect(),
                                               compile_kwargs={"literal_binds": True})) + ";")
    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"
