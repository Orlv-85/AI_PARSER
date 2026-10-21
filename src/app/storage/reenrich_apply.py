"""Transactional re-enrichment with drift checks and conflict-safe targeted rollback."""

import json
from pathlib import Path
from typing import Any

from sqlalchemy import String, delete, insert, select, update
from sqlalchemy.engine import Engine

from app.storage.legacy_cleanup import (
    _lock,
    _typed,
    dependencies,
    fingerprint,
    private_write,
    read_tables,
)
from app.storage.models_sql import Base

EVIDENCE_DEFAULTS = {
    "publication_day": None,
    "modified_at": None,
    "publication_status": "legacy_unverified",
    "publication_precision": None,
    "date_provenance": None,
    "enrichment_provenance": None,
    "material_type": None,
    "compared_products": None,
}


def article_with_defaults(row: dict[str, Any]) -> dict[str, Any]:
    return {**EVIDENCE_DEFAULTS, **row}


def verify_manifest(manifest: dict[str, Any]) -> None:
    if manifest["manifest_hash"] != fingerprint(
        {k: v for k, v in manifest.items() if k != "manifest_hash"}
    ):
        raise ValueError("Re-enrichment manifest hash differs")
    entries = manifest["entries"]
    if len(entries) != len({e["article_id"] for e in entries}):
        raise ValueError("Duplicate manifest article IDs")
    for entry in entries:
        before, after = entry["before"], entry["after"]
        if before["id"] != entry["article_id"] or fingerprint(before) != entry["row_hash"]:
            raise ValueError("Manifest before-row identity differs")
        if after is not None and any(
            before[k] != after[k]
            for k in (
                "id",
                "source_id",
                "url",
                "url_canonical",
                "url_canonical_hash",
                "discovered_at",
            )
        ):
            raise ValueError("Cannot change article identity or discovery time")
        if after is not None:
            for column in Base.metadata.tables["articles"].columns:
                value = after.get(column.name)
                if (
                    isinstance(column.type, String)
                    and column.type.length is not None
                    and isinstance(value, str)
                    and len(value) > column.type.length
                ):
                    raise ValueError("Article field exceeds schema limit: " + column.name)
        if after is None:
            from app.core.ingestion.legacy_cleanup import cleanup_verdict  # pylint: disable=import-outside-toplevel
            from app.core.jev import JevAssessment  # pylint: disable=import-outside-toplevel

            verdict = cleanup_verdict(entry["source_row"], JevAssessment(**entry["assessment"]))
            if verdict["outcome"] != "rejected" or entry.get("review_required"):
                raise ValueError("Unsafe or disputed deletion")


def _state_matches(tables: dict[str, Any], backup: dict[str, Any], *, after: bool) -> bool:
    rows = {r["id"]: r for r in tables["articles"]}
    expected = backup["after"] if after else backup["before"]
    return all(
        (
            article_id not in rows
            if row is None
            else fingerprint(rows.get(article_id)) == fingerprint(row)
        )
        for article_id, row in ((int(k), v) for k, v in expected.items())
    )


def apply_reenrichment(  # pylint: disable=too-many-branches
    engine: Engine, manifest: dict[str, Any], backup_path: Path, *, fail_after_write: bool = False
) -> dict[str, Any]:
    verify_manifest(manifest)
    with engine.begin() as connection:
        _lock(connection)
        tables = read_tables(connection)
        if backup_path.exists():
            backup = json.loads(backup_path.read_text())
            if backup["manifest_hash"] != manifest["manifest_hash"]:
                raise ValueError("Backup belongs to another manifest")
            ledger = {r["key"]: r for r in tables["admission_decisions"]}
            ledger_intact = all(
                r["key"] in ledger
                and fingerprint({k: ledger[r["key"]][k] for k in r}) == fingerprint(r)
                for r in backup["ledger_after"]
            )
            if _state_matches(tables, backup, after=True) and ledger_intact:
                return {**backup["result"], "already_applied": True}
            if not _state_matches(tables, backup, after=False):
                raise ValueError("Existing backup has conflicting live state")
        else:
            live = {r["id"]: r for r in tables["articles"]}
            refs = dependencies(tables)
            eligible, skipped, absent = [], [], []
            for entry in manifest["entries"]:
                article_id = entry["article_id"]
                if article_id not in live:
                    absent.append(article_id)
                elif (
                    fingerprint(live[article_id]) != entry["row_hash"]
                    or refs[article_id] != entry["dependencies"]
                ):
                    skipped.append(article_id)
                else:
                    eligible.append(entry)
            ids = {e["article_id"] for e in eligible}
            old_ledger = {r["key"]: r for r in tables["admission_decisions"]}
            ledger_after = [e["ledger"] for e in eligible if e.get("ledger")]
            if any(
                r["key"] in old_ledger
                and fingerprint({k: old_ledger[r["key"]][k] for k in r}) != fingerprint(r)
                for r in ledger_after
            ):
                raise ValueError("Conflicting assessment ledger key")
            backup = {
                "manifest_hash": manifest["manifest_hash"],
                "before": {str(e["article_id"]): live[e["article_id"]] for e in eligible},
                "after": {str(e["article_id"]): e["after"] for e in eligible},
                "aliases": [
                    r
                    for r in tables["article_aliases"]
                    if r["article_id"] in ids
                    and any(
                        e["article_id"] == r["article_id"] and e["after"] is None for e in eligible
                    )
                ],
                "ledger_before": {r["key"]: old_ledger.get(r["key"]) for r in ledger_after},
                "ledger_after": ledger_after,
                "result": {
                    "updated_ids": sorted(
                        e["article_id"] for e in eligible if e["after"] is not None
                    ),
                    "deleted_ids": sorted(e["article_id"] for e in eligible if e["after"] is None),
                    "skipped_changed_ids": skipped,
                    "already_absent_ids": absent,
                },
            }
            private_write(backup_path, backup)
        ledger_table = Base.metadata.tables["admission_decisions"]
        for row in backup["ledger_after"]:
            existing = connection.execute(
                select(ledger_table.c.key).where(ledger_table.c.key == row["key"])
            ).scalar_one_or_none()
            if existing is None:
                connection.execute(insert(ledger_table).values(_typed("admission_decisions", row)))
        articles, aliases = (Base.metadata.tables[n] for n in ("articles", "article_aliases"))
        for article_id, row in backup["after"].items():
            if row is None:
                connection.execute(delete(aliases).where(aliases.c.article_id == int(article_id)))
                connection.execute(delete(articles).where(articles.c.id == int(article_id)))
            else:
                connection.execute(
                    update(articles)
                    .where(articles.c.id == int(article_id))
                    .values(_typed("articles", row))
                )
        if fail_after_write:
            raise RuntimeError("Injected rollback probe")
    return {**backup["result"], "already_applied": False, "backup_hash": fingerprint(backup)}


def restore_reenrichment(engine: Engine, backup: dict[str, Any]) -> None:
    with engine.begin() as connection:
        _lock(connection)
        tables = read_tables(connection)
        if not _state_matches(tables, backup, after=True):
            if _state_matches(tables, backup, after=False):
                return
            raise ValueError("Restore refuses changed article rows")
        articles, aliases = (Base.metadata.tables[n] for n in ("articles", "article_aliases"))
        for article_id, row in backup["before"].items():
            values = _typed("articles", row)
            if backup["after"][article_id] is None:
                connection.execute(insert(articles).values(values))
            else:
                connection.execute(
                    update(articles).where(articles.c.id == int(article_id)).values(values)
                )
        for row in backup["aliases"]:
            connection.execute(insert(aliases).values(_typed("article_aliases", row)))
        table = Base.metadata.tables["admission_decisions"]
        for expected in backup["ledger_after"]:
            current = (
                connection.execute(select(table).where(table.c.key == expected["key"]))
                .mappings()
                .one()
            )
            if fingerprint({k: current[k] for k in expected}) != fingerprint(expected):
                raise ValueError("Restore refuses changed assessment ledger")
            previous = backup["ledger_before"][expected["key"]]
            if previous is None:
                connection.execute(delete(table).where(table.c.key == expected["key"]))
            else:
                connection.execute(
                    update(table)
                    .where(table.c.key == expected["key"])
                    .values(_typed("admission_decisions", previous))
                )
