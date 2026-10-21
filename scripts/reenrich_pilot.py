#!/usr/bin/env python3
"""Prepare or run an explicitly budgeted, cache-only 80-record diagnostic pilot."""
import argparse
import fcntl
import hashlib
import json
import logging
from collections import Counter, defaultdict
from pathlib import Path

import httpx
from reenrich_articles import read_plan

from app.config.settings import get_settings
from app.core.daily.reenrich_pilot import (
    CLEANUP_POLICY,
    DEEPSEEK_MODEL,
    JEV_MODEL,
    PILOT_VERSION,
    PRICES,
    SUMMARY_QUOTE_REPAIR_VERSION,
    SUMMARY_RECOVERY_VERSION,
    SUMMARY_VERSION,
    TAXONOMY_VERSION,
    TOPIC_CRITERIA,
    jev_request,
    parse_jev,
    parse_summary,
    request_key,
    reservation,
    summary_request,
)
from app.storage.article_evidence_cache import url_key
from app.storage.legacy_cleanup import fingerprint, private_write
from app.storage.reenrich_pilot_journal import PilotJournal, PilotStopped


def sha_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_items(items):
    """Keep all fresh/gap/negative examples, then balance 28 accepted controls."""
    fresh = [i for i in items if i["cohort"] == "unresolved_fresh"]
    accepted = [i for i in items if i["cohort"] == "previously_accepted"]
    controls = [i for i in accepted if i["selected_for"].startswith("existing_category:")]
    strata = defaultdict(list)
    for item in accepted:
        if item not in controls and item["selected_for"] != "diverse_fill":
            strata[item["selected_for"]].append(item)
    while len(controls) < 28:
        added = False
        for name in sorted(strata):
            if strata[name] and len(controls) < 28:
                controls.append(strata[name].pop(0))
                added = True
        if not added:
            raise ValueError("Insufficient accepted control strata")
    selected = fresh + controls
    if len(fresh) != 52 or len(selected) != 80 or len({i["article_id"] for i in selected}) != 80:
        raise ValueError("Expected the frozen 92-record sample with 52 fresh records")
    return selected


def build_plan(root):
    frozen = read_plan(root)
    receipt = json.loads((root / "cache-verification.json").read_text())
    if receipt["snapshot_hash"] != frozen["snapshot_hash"] or receipt["errors"]:
        raise ValueError("Successful matching cache verification required")
    sample = json.loads((root / "taxonomy-sample.json").read_text())
    snapshot = json.loads((root / "snapshot.json").read_text())
    rows = {r["id"]: r for r in snapshot["tables"]["articles"]}
    targets = {i["article_id"] for i in frozen["targets"]}
    records, estimates, maximums = [], Counter(), Counter()
    for item in select_items(sample["items"]):
        row = rows[item["article_id"]]
        if item["url"] != row["url"]:
            raise ValueError("Sample URL identity mismatch")
        source = {"article_id": row["id"], "url": row["url"], "title": item["title"],
                  "source_origin": item["source_origin"], "cohort": item["cohort"],
                  "selected_for": item["selected_for"], "domain": item["domain"],
                  "row_hash": fingerprint(row), "url_canonical_hash": row["url_canonical_hash"],
                  "diagnostic_only": item["cohort"] == "previously_accepted"}
        if item["source_origin"] == "fresh_cached_page":
            if row["id"] not in targets:
                raise ValueError("Fresh sample outside frozen unresolved IDs")
            directory = root / "pages" / url_key(row["url"])
            evidence = json.loads((directory / "evidence.json").read_text())
            attempt = json.loads((directory / "attempt.json").read_text())
            if (attempt["state"] != "completed" or evidence["quality"] != "extracted"
                    or fingerprint(evidence) != attempt["evidence_sha256"]
                    or item["title"] != (evidence.get("title") or row["title"])):
                raise ValueError("Fresh source quality, title or hash changed")
            text = (directory / "text.txt").read_text()
            source["source_artifact_hash"] = fingerprint(evidence)
        elif item["source_origin"] == "saved_article_content" and row["id"] not in targets:
            text = row.get("content") or ""
            if item["title"] != row["title"]:
                raise ValueError("Saved source title changed")
        else:
            raise ValueError("Unsupported source origin")
        if hashlib.sha256(text.encode()).hexdigest() != item["text_hash"]:
            raise ValueError("Sample source text hash mismatch")
        source["full_source_text_hash"] = item["text_hash"]
        source["content"] = text[:16000]
        jev = jev_request(source)
        summary = summary_request(source, True)
        source["jev_request"] = jev
        source["jev_key"] = request_key("jev", jev)
        # Summary key is derived later from source+comparison, never from generated text.
        for provider, body in (("jev", jev), ("deepseek", summary)):
            maximums[provider] += reservation(provider, body)
            input_estimate = len(json.dumps(body, ensure_ascii=False)) / 4
            estimates[provider] += (input_estimate * PRICES[provider]["input"] +
                                    (300 * PRICES[provider]["output"] if provider == "deepseek"
                                     else 0)) / 1e6
        records.append(source)
    return {"version": PILOT_VERSION, "taxonomy_version": TAXONOMY_VERSION,
            "topic_order": list(TOPIC_CRITERIA),
            "summary_version": SUMMARY_VERSION, "cleanup_policy": CLEANUP_POLICY,
            "screening": snapshot.get("screening"),
            "inputs": {"snapshot_hash": frozen["snapshot_hash"],
                       "source_plan_sha256": sha_file(root / "plan.json"),
                       "sample_sha256": sha_file(root / "taxonomy-sample.json"),
                       "cache_inventory_hash": receipt["artifacts_hash"]},
            "budget_approved": False, "production_writes": 0,
            "records": records, "count": len(records),
            "cohorts": dict(Counter(r["cohort"] for r in records)),
            "hostnames": len({r["domain"] for r in records}),
            "rough_chars_div_four_usd": dict(estimates),
            "all_calls_unknown_usage_reservation_usd": {k: v / 1e6 for k, v in maximums.items()},
            "prices": PRICES, "models": {"jev": JEV_MODEL, "deepseek": DEEPSEEK_MODEL},
            "price_sources": ["https://docs.typesafe.ai/models",
                              "https://api-docs.deepseek.com/quick_start/pricing/"],
            "price_checked_date": "2026-10-11", "concurrency": {"jev": 1, "deepseek": 1},
            "other_material_types": "pending; only Comparison is assigned"}


def plan_report(plan):
    return {k: v for k, v in plan.items() if k not in {"records", "screening"}} | {
        "plan_hash": fingerprint(plan), "provider_calls": {"jev": 0, "deepseek": 0}}


def prepare(args):
    plan = build_plan(args.run_dir)
    path = args.run_dir / "pilot-plan.json"
    if path.exists() and fingerprint(json.loads(path.read_text())) != fingerprint(plan):
        previous = json.loads(path.read_text())
        if (not args.refresh_unpaid_plan or previous["inputs"] != plan["inputs"]
                or (args.run_dir / "pilot-budget-approval.json").exists()
                or (args.run_dir / "pilot-journal.sqlite3").exists()):
            raise ValueError("Existing pilot plan changed; do not overwrite")
        private_write(args.run_dir / f"pilot-draft-{fingerprint(previous)}.json", previous)
    private_write(path, plan)
    private_write(args.run_dir / "pilot-preparation.json", plan_report(plan))
    print(json.dumps(plan_report(plan), sort_keys=True))


def load_plan(root):
    plan = json.loads((root / "pilot-plan.json").read_text())
    if fingerprint(build_plan(root)) != fingerprint(plan):
        raise ValueError("Frozen pilot source, rubric, model or input changed")
    return plan


def obtain_summary(row, comparison, journal, client, secret, output_cap):
    body = summary_request(row, comparison)
    version = SUMMARY_VERSION
    if not journal.has_response("deepseek", body):
        body = summary_request(row, comparison, output_cap=output_cap)
        version = SUMMARY_RECOVERY_VERSION if output_cap != 300 else SUMMARY_VERSION
    if journal.has_reviewed_response("deepseek", body):
        body = summary_request(row, comparison, output_cap=output_cap, repair_quotes=True)
        version = SUMMARY_QUOTE_REPAIR_VERSION
    data = journal.call("deepseek", body, client, secret)
    try:
        summary = parse_summary(row, data, comparison, prompt_version=version)
    except (ValueError, KeyError, TypeError, IndexError):
        journal.fail(request_key("deepseek", body), "InvalidSummary")
        if (version == SUMMARY_QUOTE_REPAIR_VERSION or output_cap == 300 or
                not journal.review_quote_failure(row, comparison, body, version)):
            raise PilotStopped("invalid_summary_requires_review") from None
        body = summary_request(row, comparison, output_cap=output_cap, repair_quotes=True)
        data = journal.call("deepseek", body, client, secret)
        try:
            summary = parse_summary(row, data, comparison,
                                    prompt_version=SUMMARY_QUOTE_REPAIR_VERSION)
        except (ValueError, KeyError, TypeError, IndexError):
            journal.fail(request_key("deepseek", body), "InvalidSummary")
            raise PilotStopped("invalid_summary_requires_review") from None
    return {**summary, "request_key": request_key("deepseek", body)}


def run(args):
    plan = load_plan(args.run_dir)
    if not args.approval_note.strip():
        raise ValueError("Explicit approval note required")
    caps = {"total": args.approved_total_usd, "jev": args.approved_jev_usd,
            "deepseek": args.approved_deepseek_usd}
    approval = {"plan_hash": fingerprint(plan), "caps_usd": caps,
                "approval_note": args.approval_note, "scope": "pilot_only"}
    approval_path = args.run_dir / "pilot-budget-approval.json"
    if approval_path.exists() and json.loads(approval_path.read_text()) != approval:
        raise ValueError("Stored budget approval differs; review instead of resetting spend")
    settings = get_settings()
    keys = {"jev": settings.jev_api_key, "deepseek": settings.ds_api_key}
    if any(key is None or not key.get_secret_value().strip() for key in keys.values()):
        raise ValueError("Both provider keys are required")
    journal = PilotJournal(args.run_dir / "pilot-journal.sqlite3", approval, caps)
    results, stopped = [], None
    private_write(approval_path, approval)
    try:
        if args.summary_output_cap != 300:
            revision = {"parent_plan_hash": fingerprint(plan),
                        "summary_version": SUMMARY_RECOVERY_VERSION,
                        "summary_output_cap": args.summary_output_cap,
                        "reason": "User authorised continuation after known output truncation",
                        "caps_usd": caps}
            revision_path = args.run_dir / "pilot-summary-revision.json"
            if revision_path.exists() and json.loads(revision_path.read_text()) != revision:
                raise ValueError("Stored summary revision differs")
            if not revision_path.exists():
                for name in ("pilot-report", "pilot-results", "pilot-usage"):
                    path = args.run_dir / (name + ".json")
                    if path.exists():
                        private_write(args.run_dir / (name + "-before-recovery.json"),
                                      json.loads(path.read_text()))
            private_write(revision_path, revision)
            results_path = args.run_dir / "pilot-results.json"
            previous = {r["article_id"]: r for r in json.loads(results_path.read_text())} \
                if results_path.exists() else {}
            for row in plan["records"]:
                previous_result = previous.get(row["article_id"], {})
                if previous_result.get("outcome") != "kept":
                    continue
                comparison = previous_result.get("material_type") == "Comparison"
                body = summary_request(row, comparison, output_cap=args.summary_output_cap)
                journal.restore_valid_summary(row, comparison, body, SUMMARY_RECOVERY_VERSION)
                journal.review_quote_failure(row, comparison, body, SUMMARY_RECOVERY_VERSION)
                repair_body = summary_request(row, comparison, output_cap=args.summary_output_cap,
                                              repair_quotes=True)
                journal.restore_valid_summary(row, comparison, repair_body,
                                              SUMMARY_QUOTE_REPAIR_VERSION)
            journal.review_truncated_summaries(revision["reason"])
        with httpx.Client(timeout=60, transport=httpx.HTTPTransport(retries=0),
                          follow_redirects=False) as client:
            for row in plan["records"]:
                body = row["jev_request"]
                try:
                    data = journal.call("jev", body, client, keys["jev"].get_secret_value())
                    result = parse_jev(row, data)
                except (ValueError, KeyError, TypeError, IndexError):
                    journal.fail(row["jev_key"], "InvalidAssessment")
                    raise PilotStopped("invalid_assessment_requires_review") from None
                entry = {"article_id": row["article_id"], "diagnostic_only": row["diagnostic_only"],
                         "source_origin": row["source_origin"], "jev_key": row["jev_key"],
                         "source_text_hash": row["full_source_text_hash"], **result}
                results.append(entry)
                private_write(args.run_dir / "pilot-results.json", results)
                if result["outcome"] == "kept":
                    comparison = result["material_type"] == "Comparison"
                    entry["summary"] = obtain_summary(
                        row, comparison, journal, client, keys["deepseek"].get_secret_value(),
                        args.summary_output_cap)
                    private_write(args.run_dir / "pilot-results.json", results)
                private_write(args.run_dir / "pilot-usage.json", journal.report())
                if len(results) % 10 == 0:
                    print(json.dumps({"processed": len(results),
                                      "committed_usd": journal.report()["total_committed_usd"]}),
                          flush=True)
    except PilotStopped as exc:
        stopped = str(exc)
    finally:
        usage = journal.report()
        private_write(args.run_dir / "pilot-usage.json", usage)
        journal.close()
    report = {"plan_hash": fingerprint(plan), "processed": len(results), "total": plan["count"],
              "outcomes": dict(Counter(r["outcome"] for r in results)),
              "topics": dict(Counter(r["topic"] or "Unclassified" for r in results
                                     if r["outcome"] == "kept")),
              "summaries": sum("summary" in r for r in results),
              "boundary_review": sum(r["boundary_review"] for r in results),
              "usage": usage, "stopped": stopped, "production_writes": 0,
              "next_stage": "stop_for_pilot_review_and_mass_budget"}
    private_write(args.run_dir / "pilot-report.json", report)
    print(json.dumps(report, sort_keys=True))
    if stopped:
        raise SystemExit(2)


def main():
    logging.basicConfig(level=logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, handler in (("prepare", prepare), ("run", run)):
        command = commands.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)
        command.set_defaults(handler=handler)
        if name == "prepare":
            command.add_argument("--refresh-unpaid-plan", action="store_true")
        if name == "run":
            for provider in ("total", "jev", "deepseek"):
                command.add_argument(f"--approved-{provider}-usd", required=True)
            command.add_argument("--approval-note", required=True)
            command.add_argument("--summary-output-cap", type=int, choices=(300, 4096), default=300)
    args = parser.parse_args()
    root = args.run_dir.resolve()
    repo = Path(__file__).resolve().parents[1]
    if root.is_relative_to(repo) and not any(
        root.is_relative_to(repo / d) for d in ("tmp", "data")
    ):
        parser.error("Private run must be outside Git or under ignored tmp/data")
    if not root.is_dir() or root.stat().st_mode & 0o777 != 0o700:
        parser.error("Existing private source run (0700) required")
    args.run_dir = root
    with (root / "pilot.lock").open("a") as lock:
        (root / "pilot.lock").chmod(0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        args.handler(args)


if __name__ == "__main__":
    main()
