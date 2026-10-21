"""Frozen legacy cleanup manifests, dependency guards and targeted transactional restore."""
import json
import re
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Date, DateTime, delete, insert, inspect, select, text, update
from sqlalchemy.engine import Connection, Engine

from app.core.canonicalize import canonicalize_url
from app.core.ingestion.admission import admission_cache_key
from app.core.ingestion.legacy_cleanup import CLEANUP_POLICY, article_evidence_hash
from app.core.ingestion.pipeline import _assessment_from_cached
from app.storage.journal_files import encoded, fingerprint, private_write, serialize
from app.storage.models_sql import Base
from app.storage.non_news_cleanup import EXPORT_TABLES, _reference_ids


def cache_key(row: dict[str, Any], screening: dict[str, str]) -> str:
    return str(admission_cache_key(url_canonical_hash=row["url_canonical_hash"],
                                   evidence_hash=article_evidence_hash(row), **screening))


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


def build_manifest(snapshot: dict[str, Any], verdicts: dict[str, Any]) -> dict[str, Any]:
    from types import SimpleNamespace  # pylint: disable=import-outside-toplevel
    missing = set(EXPORT_TABLES) - set(snapshot["tables"])
    if missing:
        raise ValueError(f"Incomplete dependency export: {sorted(missing)}")
    screening = snapshot["screening"]
    cached = {row["key"]: row for row in snapshot["tables"]["admission_decisions"]}
    refs = dependencies(snapshot["tables"])
    entries = []
    for row in sorted(snapshot["tables"]["articles"], key=lambda item: item["id"]):
        key = cache_key(row, screening)
        current = cached.get(key)
        accepted = (current and current["provider_status"] == "ok"
                    and current["decision"] == "accept"
                    and _assessment_from_cached(SimpleNamespace(**current)) is not None)
        verdict = ({"outcome": "kept", "reason": "current_cached_accept"} if accepted
                   else verdicts.get(key, {"outcome": "unchecked", "reason": "not_evaluated"}))
        entries.append({"article_id": row["id"], "url": row["url"], "title": row["title"],
                        "url_canonical": row["url_canonical"],
                        "url_canonical_hash": row["url_canonical_hash"], "key": key,
                        "evidence_hash": article_evidence_hash(row), "row_hash": fingerprint(row),
                        "dependencies": refs[row["id"]], **verdict})
    manifest = {"snapshot_hash": fingerprint(snapshot), "screening": screening,
                "cleanup_policy": CLEANUP_POLICY, "entries": entries,
                "counts": dict(Counter(entry["outcome"] for entry in entries)),
                "retained_outputs": "Copied digest/weekly URLs, texts, narrative, metrics and "
                                    "frozen snapshots are preserved. Unlinked text mentions "
                                    "cannot be enumerated automatically."}
    manifest["manifest_hash"] = fingerprint(manifest)
    return manifest


def verify_manifest(snapshot: dict[str, Any], manifest: dict[str, Any]) -> None:
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    if (manifest["snapshot_hash"] != fingerprint(snapshot)
            or manifest["manifest_hash"] != fingerprint(unsigned)
            or manifest["cleanup_policy"] != CLEANUP_POLICY):
        raise ValueError("Snapshot/manifest integrity mismatch")
    # Recompute IDs, evidence and dependencies rather than trusting a modified manifest.
    verdicts = {entry["key"]: {key: value for key, value in entry.items() if key in {
        "outcome", "reason", "prefilter", "confidence", "assessment", "cleanup_policy",
    }} for entry in manifest["entries"]}
    if build_manifest(snapshot, verdicts)["manifest_hash"] != manifest["manifest_hash"]:
        raise ValueError("Manifest does not match frozen rows")
    from app.core.ingestion.legacy_cleanup import cleanup_verdict  # pylint: disable=import-outside-toplevel
    from app.core.jev import JevAssessment  # pylint: disable=import-outside-toplevel
    articles = {row["id"]: row for row in snapshot["tables"]["articles"]}
    for entry in manifest["entries"]:
        if entry["outcome"] == "rejected":
            verdict = cleanup_verdict(articles[entry["article_id"]],
                                      JevAssessment(**entry["assessment"]))
            if any(entry.get(key) != value for key, value in verdict.items()):
                raise ValueError("Reject does not meet current destructive cleanup policy")


def read_tables(connection: Connection) -> dict[str, Any]:
    return {name: [dict(row) for row in connection.execute(
        select(Base.metadata.tables[name])).mappings()] for name in EXPORT_TABLES}


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


def _lock(connection: Connection) -> None:
    if connection.dialect.name != "postgresql":
        raise ValueError("Destructive cleanup requires PostgreSQL")
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(text("LOCK TABLE " + ", ".join(sorted(EXPORT_TABLES))
                            + " IN SHARE ROW EXCLUSIVE MODE"))
    inspector = inspect(connection)
    for name in inspector.get_table_names():
        for foreign_key in inspector.get_foreign_keys(name):
            if foreign_key["referred_table"] == "articles" and not known_article_fk(
                    name, foreign_key):
                raise ValueError("Unknown article FK dependency: " + name)


# Derived Daily AI Signals rows (feature 006) are deleted with their article by ON DELETE
# CASCADE and are not restored; re-extraction rebuilds them (plan Decision 4).
DERIVED_CASCADE_TABLES = frozenset({"article_signals", "daily_signal_scope"})


def known_article_fk(name: str, foreign_key: Mapping[str, object]) -> bool:
    if foreign_key["constrained_columns"] != ["article_id"]:
        return False
    if name == "article_aliases":
        return True
    options = foreign_key.get("options")
    ondelete = options.get("ondelete") if isinstance(options, Mapping) else None
    return name in DERIVED_CASCADE_TABLES and str(ondelete or "").upper() == "CASCADE"


def apply_cleanup(engine: Engine, snapshot: dict[str, Any], manifest: dict[str, Any],
                  backup_path: Path) -> dict[str, Any]:
    """Caller must coordinate collector and verify a matching isolated restore receipt."""
    verify_manifest(snapshot, manifest)
    if backup_path.exists():
        backup = json.loads(backup_path.read_text())
        if (backup["snapshot_hash"] != manifest["snapshot_hash"]
                or backup["manifest_hash"] != manifest["manifest_hash"]):
            raise ValueError("Existing apply backup belongs to another manifest")
        with engine.begin() as connection:
            _lock(connection)
            tables = read_tables(connection)
            current_ids = {row["id"] for row in tables["articles"]}
            ids = {row["id"] for row in backup["articles"]}
            ledger = {row["key"]: row for row in tables["admission_decisions"]}
            intact = all(row["key"] in ledger and fingerprint(
                {key: ledger[row["key"]][key] for key in row}) == fingerprint(row)
                         for row in backup["ledger_after"])
            if ids & current_ids or not intact:
                raise ValueError("Existing backup incomplete or live state changed; inspect first")
        return {"deleted_ids": [], "skipped_changed_ids": [],
                "already_absent_ids": sorted(ids), "backup_hash": fingerprint(backup),
                "already_applied": True}
    target = [entry for entry in manifest["entries"] if entry["outcome"] == "rejected"]
    with engine.begin() as connection:
        _lock(connection)
        tables = read_tables(connection)
        live = {row["id"]: row for row in tables["articles"]}
        refs = dependencies(tables)
        unchanged, skipped, absent = [], [], []
        for entry in target:
            row = live.get(entry["article_id"])
            if row is None:
                absent.append(entry["article_id"])
            elif (fingerprint(row) != entry["row_hash"]
                  or article_evidence_hash(row) != entry["evidence_hash"]
                  or refs[row["id"]] != entry["dependencies"]):
                skipped.append(entry["article_id"])
            else:
                unchanged.append(entry)
        ids = {entry["article_id"] for entry in unchanged}
        ledger_before, ledger_after = _reject_ledger(tables, unchanged, snapshot["screening"])
        backup = {"snapshot_hash": manifest["snapshot_hash"],
                  "manifest_hash": manifest["manifest_hash"],
                  "articles": [row for row in tables["articles"] if row["id"] in ids],
                  "article_aliases": [row for row in tables["article_aliases"]
                                      if row["article_id"] in ids],
                  "ledger_before": ledger_before, "ledger_after": ledger_after}
        private_write(backup_path, backup)
        ledger = Base.metadata.tables["admission_decisions"]
        for row in ledger_after:
            values = typed_row("admission_decisions", row)
            if row["key"] in ledger_before:
                connection.execute(update(ledger).where(ledger.c.key == row["key"]).values(values))
            else:
                connection.execute(insert(ledger).values(values))
        aliases, articles = (Base.metadata.tables[name] for name in ("article_aliases", "articles"))
        if ids:
            connection.execute(delete(aliases).where(aliases.c.article_id.in_(ids)))
            connection.execute(delete(articles).where(articles.c.id.in_(ids)))
    return {"deleted_ids": sorted(ids), "skipped_changed_ids": skipped,
            "already_absent_ids": absent, "backup_hash": fingerprint(backup)}


def _reject_ledger(tables: dict[str, Any], entries: list[dict[str, Any]],
                   screening: dict[str, str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    current = {row["key"]: row for row in tables["admission_decisions"]}
    articles = {row["id"]: row for row in tables["articles"]}
    now = datetime.now(UTC)
    for entry in entries:
        row = articles[entry["article_id"]]
        key = entry["key"]
        if key in current:
            before[key] = current[key]
        candidate = {"kind": "article", "title": row["title"], "url": row["url"],
                     "canonical_url": row["url_canonical"], "summary": row["summary"],
                     "content": row["content"], "published_at": serialize(row["published_at"])
                     if isinstance(row["published_at"], datetime) else row["published_at"],
                     "publication_date_kind": "unknown"}
        after[key] = {**current.get(key, {}), "key": key,
                      "url_canonical_hash": row["url_canonical_hash"],
                      "source_id": row["source_id"], "evidence_hash": entry["evidence_hash"],
                      "model": screening["model"], "policy_version": screening["policy_version"],
                      "payload": encoded({"candidate": candidate, "assessment": entry["assessment"],
                                          "cleanup_policy": CLEANUP_POLICY}),
                      "decision": "reject", "reason": entry["reason"], "provider_status": "ok",
                      "attempts": current.get(key, {}).get("attempts", 1),
                      "created_at": current.get(key, {}).get("created_at", now), "updated_at": now}
        # Retire older pending evidence; do not assign a reject to unevaluated text.
        for old in current.values():
            if old["url_canonical_hash"] == row["url_canonical_hash"] and (
                old["provider_status"] == "pending" and old["key"] != key
            ):
                before[old["key"]] = old
                after[old["key"]] = {**old, "provider_status": "settled", "updated_at": now}
    return before, list(after.values())


def restore_cleanup(engine: Engine, backup: dict[str, Any]) -> None:
    """Restore exact rows and cache state atomically, refusing concurrent conflicts."""
    with engine.begin() as connection:
        _lock(connection)
        existing_tables = read_tables(connection)
        existing_hashes = {name: {row["id"]: fingerprint(row) for row in existing_tables[name]}
                           for name in ("articles", "article_aliases")}
        restored_already = all(
            existing_hashes[name].get(row["id"]) == fingerprint(row)
            for name in ("articles", "article_aliases") for row in backup[name]
        )
        for name in ("articles", "article_aliases"):
            table = Base.metadata.tables[name]
            for row in backup[name]:
                current = connection.execute(
                    select(table).where(table.c.id == row["id"])).mappings().first()
                if current:
                    if fingerprint(dict(current)) != fingerprint(row):
                        raise ValueError("Restore conflict: " + name)
                else:
                    connection.execute(insert(table).values(typed_row(name, row)))
        table = Base.metadata.tables["admission_decisions"]
        for expected in backup["ledger_after"]:
            current = connection.execute(
                select(table).where(table.c.key == expected["key"])).mappings().first()
            if not current:
                if restored_already and expected["key"] not in backup["ledger_before"]:
                    continue
                raise ValueError("Restore conflict: missing admission decision")
            actual = dict(current)
            # Newly inserted decision IDs are generated by the live database.
            comparable = {key: actual[key] for key in expected}
            previous = backup["ledger_before"].get(expected["key"])
            if previous and fingerprint(actual) == fingerprint(previous):
                continue
            if fingerprint(comparable) != fingerprint(expected):
                raise ValueError("Restore conflict: changed admission decision")
            if previous:
                connection.execute(update(table).where(table.c.key == expected["key"]).values(
                    typed_row("admission_decisions", previous)))
            else:
                connection.execute(delete(table).where(table.c.key == expected["key"]))
