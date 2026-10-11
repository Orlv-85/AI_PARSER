#!/usr/bin/env python3
"""Unpaid evidence collection only. Article bodies are never printed."""
import argparse
import asyncio
import fcntl
import hashlib
import json
import logging
from collections import Counter
from pathlib import Path

from app.core.legacy_cleanup import article_evidence_hash
from app.ingest.date_evidence import date_candidate, resolve_dates
from app.storage.article_evidence_cache import (
    CACHE_VERSION,
    PageCache,
    SourcePageDownloader,
    make_http_client,
    validate_source_url,
)
from app.storage.legacy_cleanup import (
    dependencies,
    fingerprint,
    normalize_snapshot,
    private_write,
)


def prepare(args):
    root = args.run_dir.resolve()
    repo = Path(__file__).resolve().parents[1]
    if root.is_relative_to(repo) and not any(
        root.is_relative_to(repo / directory) for directory in ("tmp", "data")
    ):
        raise ValueError("Private run must be outside Git or under ignored tmp/data")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    snapshot = normalize_snapshot(json.loads(args.snapshot.read_text()))
    review = json.loads(args.review.read_text())
    rows = {row["id"]: row for row in snapshot["tables"]["articles"]}
    refs = dependencies(snapshot["tables"])
    targets, missing, changed = [], [], []
    for entry in review["entries"]:
        row = rows.get(entry["article_id"])
        if row is None:
            missing.append(entry["article_id"])
            continue
        if row["url_canonical_hash"] != entry["url_canonical_hash"]:
            changed.append(entry["article_id"])
            continue
        targets.append({"article_id": row["id"], "url": row["url"], "title": row["title"],
                        "url_canonical_hash": row["url_canonical_hash"],
                        "row_hash": fingerprint(row), "evidence_hash": article_evidence_hash(row),
                        "dependencies": refs[row["id"]], "origin_row_hash": entry["row_hash"],
                        "origin_evidence_hash": entry["evidence_hash"]})
    plan = {"version": CACHE_VERSION, "snapshot_hash": fingerprint(snapshot),
            "review_hash": fingerprint(review), "original_review_count": len(review["entries"]),
            "targets": sorted(targets, key=lambda item: item["article_id"]),
            "missing_ids": missing, "changed_identity_ids": changed,
            "model_calls": 0, "production_writes": 0}
    path = root / "plan.json"
    if path.exists() and fingerprint(json.loads(path.read_text())) != fingerprint(plan):
        raise ValueError("Existing run belongs to a different snapshot/review")
    private_write(root / "snapshot.json", snapshot)
    private_write(path, plan)
    private_write(root / "review-origin.json", review)
    print(json.dumps({"prepared": len(targets), "missing": len(missing),
                      "changed_identity": len(changed), "snapshot_hash": plan["snapshot_hash"],
                      "urls": len({t["url"] for t in targets}), "model_calls": 0}))


def read_plan(root):
    plan = json.loads((root / "plan.json").read_text())
    if plan["version"] != CACHE_VERSION:
        raise ValueError("Unsupported cache version")
    snapshot = normalize_snapshot(json.loads((root / "snapshot.json").read_text()))
    if fingerprint(snapshot) != plan["snapshot_hash"]:
        raise ValueError("Frozen snapshot hash mismatch")
    review = json.loads((root / "review-origin.json").read_text())
    if fingerprint(review) != plan["review_hash"]:
        raise ValueError("Frozen review hash mismatch")
    rows = {row["id"]: row for row in snapshot["tables"]["articles"]}
    review_ids = {entry["article_id"] for entry in review["entries"]}
    for target in plan["targets"]:
        row = rows.get(target["article_id"])
        if (row is None or row["id"] not in review_ids or target["url"] != row["url"]
                or target["row_hash"] != fingerprint(row)
                or target["evidence_hash"] != article_evidence_hash(row)):
            raise ValueError("Frozen target identity/evidence mismatch")
    return plan


def status(args):
    plan = read_plan(args.run_dir)
    urls = sorted({target["url"] for target in plan["targets"]})
    report = PageCache(args.run_dir).status(urls)
    private_write(args.run_dir / "fetch-status.json", report)
    print(json.dumps(report, sort_keys=True))


def verify_cache(args):
    plan = read_plan(args.run_dir)
    cache = PageCache(args.run_dir)
    artifacts, errors = [], []
    for url in sorted({target["url"] for target in plan["targets"]}):
        attempt = cache.attempt(url)
        if attempt is None or attempt["state"] == "started":
            errors.append({"url": url, "error": "unfinished_attempt"})
            continue
        if attempt["state"] != "completed":
            continue
        directory = cache.page_dir(url)
        try:
            response = json.loads((directory / "response.json").read_text())
            evidence = json.loads((directory / "evidence.json").read_text())
            checks = [
                fingerprint(evidence) == attempt["evidence_sha256"],
                fingerprint(response) == evidence["response_sha256"],
            ]
            for filename, expected in (
                ("body.bin", response["body_sha256"]),
                ("page.html", evidence["html_sha256"]),
                ("text.txt", evidence["text_sha256"]),
            ):
                path = directory / filename
                checks.append(hashlib.sha256(path.read_bytes()).hexdigest() == expected)
                checks.append(path.stat().st_mode & 0o777 == 0o600)
            for hop in [response, *response["redirects"]]:
                validate_source_url(hop["final_url"])
                if hop.get("location"):
                    from urllib.parse import urljoin  # pylint: disable=import-outside-toplevel
                    validate_source_url(urljoin(hop["final_url"], hop["location"]))
            if not all(checks):
                raise ValueError("Cache hash or permissions mismatch")
            artifacts.append({"url": url, "evidence_sha256": attempt["evidence_sha256"],
                              "body_sha256": response["body_sha256"],
                              "text_sha256": evidence["text_sha256"]})
        except (KeyError, ValueError, OSError) as exc:
            errors.append({"url": url, "error": type(exc).__name__})
    receipt = {"snapshot_hash": plan["snapshot_hash"], "verified_responses": len(artifacts),
               "artifacts_hash": fingerprint(artifacts), "errors": errors,
               "artifacts": artifacts, "model_calls": 0}
    private_write(args.run_dir / "cache-verification.json", receipt)
    print(json.dumps({key: value for key, value in receipt.items()
                      if key not in {"artifacts", "errors"}} | {"errors": len(errors)}))
    if errors:
        raise SystemExit("Cache verification failed; inspect private receipt before models")


def _payload(row):
    value = row.get("payload")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def audit_dates(args):
    plan = read_plan(args.run_dir)
    tables = json.loads((args.run_dir / "snapshot.json").read_text())["tables"]
    original = json.loads(args.legacy_snapshot.read_text())["tables"]
    original_keys = {row["key"] for row in original["admission_decisions"]}
    trusted, ignored = {}, Counter()
    for row in tables["admission_decisions"]:
        payload = _payload(row)
        if payload.get("cleanup_policy") or row["key"] not in original_keys:
            ignored["cleanup_or_unverified_ledger"] += 1
            continue
        candidate = payload.get("candidate", {})
        if not isinstance(candidate, dict) or candidate.get("kind") != "article":
            continue
        field = ("publication_evidence_at" if candidate.get("publication_evidence_at")
                 else "published_at" if candidate.get("publication_date_kind") == "published"
                 else None)
        if field and isinstance(candidate.get(field), str):
            proof = date_candidate(candidate[field], kind="published", source="ingestion_ledger",
                                   locator=f"admission_decisions:{row['id']}:{field}")
            proof["precision_origin"] = "normalized_ingestion_timestamp; raw literal unavailable"
            trusted.setdefault(row["url_canonical_hash"], []).append(proof)
    for row in tables["weekly_input_observations"]:
        if _payload(row).get("publication_provenance") == "source" and row.get("published_at"):
            proof = date_candidate(row["published_at"], kind="published",
                                   source="ingestion_observation",
                                   locator=f"weekly_input_observations:{row['id']}:published_at")
            proof["precision_origin"] = "normalized_ingestion_timestamp; raw literal unavailable"
            trusted.setdefault(row["canonical_hash"], []).append(proof)
    review_ids = {target["article_id"] for target in plan["targets"]}
    entries, counts = [], Counter()
    for row in tables["articles"]:
        if row["id"] in review_ids:
            continue
        evidence = trusted.get(row["url_canonical_hash"], [])
        resolution = resolve_dates(evidence, "published")
        counts[resolution["status"]] += 1
        entries.append({"article_id": row["id"], "url": row["url"],
                        "row_hash": fingerprint(row), "stored_published_at": row["published_at"],
                        "source_candidates": evidence, "resolution": resolution,
                        "needs_date_only_fetch": resolution["status"] != "confirmed"})
    report = {"version": "offline-date-audit-1", "snapshot_hash": plan["snapshot_hash"],
              "legacy_snapshot_hash": fingerprint(original), "other_articles": len(entries),
              "counts": dict(counts), "ignored": dict(ignored), "entries": entries,
              "note": "Stored article dates and cleanup copies never constitute source proof."}
    private_write(args.run_dir / "offline-date-audit.json", report)
    print(json.dumps({key: value for key, value in report.items() if key != "entries"}))


async def fetch_async(args):
    plan = read_plan(args.run_dir)
    urls = sorted({target["url"] for target in plan["targets"]})
    if args.limit is not None:
        urls = urls[:args.limit]
    cache = PageCache(args.run_dir)
    async with make_http_client(args.concurrency) as client:
        downloader = SourcePageDownloader(cache, client, concurrency=args.concurrency,
                                          host_interval=args.host_interval)
        tasks = [asyncio.create_task(downloader.fetch_one(url)) for url in urls]
        pending = set(tasks)
        while pending:
            done, pending = await asyncio.wait(pending, timeout=30,
                                               return_when=asyncio.ALL_COMPLETED)
            for task in done:
                task.result()
            report = cache.status(urls)
            report["outage"] = downloader.outage
            private_write(args.run_dir / "fetch-status.json", report)
            print(json.dumps(report, sort_keys=True), flush=True)
    return downloader.outage


def fetch(args):
    with (args.run_dir / "fetch.lock").open("a") as lock:
        (args.run_dir / "fetch.lock").chmod(0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if asyncio.run(fetch_async(args)):
            raise SystemExit("Network outage detected; remaining pages preserved as pending")


def main():
    logging.basicConfig(level=logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--review", type=Path, required=True)
    p.add_argument("--run-dir", type=Path, required=True)
    p.set_defaults(handler=prepare)
    p = commands.add_parser("audit-dates")
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--legacy-snapshot", type=Path, required=True)
    p.set_defaults(handler=audit_dates)
    for name, handler in (("status", status), ("fetch", fetch), ("verify", verify_cache)):
        p = commands.add_parser(name)
        p.add_argument("--run-dir", type=Path, required=True)
        p.set_defaults(handler=handler)
        if name == "fetch":
            p.add_argument("--concurrency", type=int, choices=range(1, 17), default=8)
            p.add_argument("--host-interval", type=float, default=1.0)
            p.add_argument("--limit", type=int)
    args = parser.parse_args()
    if hasattr(args, "host_interval") and args.host_interval < 1:
        parser.error("Host interval must be at least one second")
    if getattr(args, "limit", None) is not None and args.limit < 0:
        parser.error("Limit must not be negative")
    args.handler(args)


if __name__ == "__main__":
    main()
