"""Isolated, resumable historical previews. Never writes the application database."""

import argparse
import fcntl
import json
import math
import sqlite3
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from app.config.settings import Settings
from app.core.weekly_analytics import windows
from app.core.weekly_enrichment import BudgetExhausted, WeeklyEnricher
from app.core.weekly_narrative import explain
from app.storage.weekly import encoded, fingerprint

NOTICE = "Historical data; coverage is not confirmed."
VERSION = "historical-preview-1"
# USD per million tokens; use peak cache-miss prices, with no discount assumptions.
PRICES = {"jev_input": 0.042, "ds_input": 0.30, "ds_output": 1.20}


class PreviewStore:
    """One durable cache, budget ledger and progress store for the entire backfill."""

    def __init__(self, path: Path):
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS decisions
                (key TEXT PRIMARY KEY, task TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS progress
                (key TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS calls
                (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, reserved INTEGER NOT NULL,
                 actual INTEGER, usage TEXT, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs
                (report_date TEXT PRIMARY KEY, input_key TEXT NOT NULL, status TEXT NOT NULL,
                 revision INTEGER NOT NULL DEFAULT 0, error TEXT);
        """)

    def close(self):
        self.db.close()

    def decision(self, key):
        row = self.db.execute("SELECT payload FROM decisions WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_decision(self, key, task, payload):
        self.db.execute("INSERT OR IGNORE INTO decisions VALUES (?,?,?)",
                        (key, task, encoded(payload)))
        self.db.commit()

    def progress(self, key):
        row = self.db.execute("SELECT payload FROM progress WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_progress(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO progress VALUES (?,?)", (key, encoded(value)))
        self.db.commit()

    def reserve(self, kind, maximum, limit):
        self.db.execute("BEGIN IMMEDIATE")
        spent = self.db.execute("SELECT COALESCE(SUM(reserved),0) FROM calls").fetchone()[0]
        if spent + maximum > limit:
            self.db.rollback()
            raise BudgetExhausted("total_backfill_budget")
        cursor = self.db.execute(
            "INSERT INTO calls(kind,reserved,created_at) VALUES (?,?,?)",
            (kind, maximum, datetime.now(UTC).isoformat()))
        self.db.commit()
        return cursor.lastrowid

    def reconcile(self, call_id, kind, usage):
        # Unknown usage (including failed attempts) retains its full reservation.
        prompt = usage.get("prompt_tokens", usage.get("input_tokens"))
        completion = usage.get("completion_tokens", usage.get("output_tokens"))
        if (not isinstance(prompt, int) or prompt < 0 or
                (kind != "jev" and (not isinstance(completion, int) or completion < 0))):
            return
        created = self.db.execute("SELECT created_at FROM calls WHERE id=?", (call_id,)).fetchone()
        at = datetime.fromisoformat(created[0])
        off_peak = at.weekday() >= 5 or not (1 <= at.hour < 4 or 6 <= at.hour < 10)
        factor = 0.5 if off_peak else 1
        hit = usage.get("prompt_cache_hit_tokens", 0)
        hit = hit if isinstance(hit, int) and 0 <= hit <= prompt else 0
        cost = math.ceil(prompt * PRICES["jev_input"] if kind == "jev" else
                         factor * ((prompt-hit)*PRICES["ds_input"] + hit*0.006 +
                                   completion*PRICES["ds_output"]))
        self.db.execute("UPDATE calls SET actual=?,reserved=?,usage=? WHERE id=?",
                        (cost, cost, encoded(usage), call_id))
        self.db.commit()

    def usage(self):
        calls = self.db.execute("SELECT kind,reserved,actual,usage FROM calls").fetchall()
        tokens = {}
        for kind, _, _, raw in calls:
            provider = "jev" if kind == "jev" else "deepseek"
            counts = tokens.setdefault(provider, Counter())
            if raw:
                counts.update({k: v for k, v in json.loads(raw).items() if isinstance(v, int)})
        return {"calls": dict(Counter(r[0] for r in calls)),
                "tokens_by_provider": {k: dict(v) for k, v in tokens.items()},
                "usage_priced_cost_usd": sum(r[2] or 0 for r in calls) / 1_000_000,
                "reserved_cost_usd": sum(r[1] for r in calls) / 1_000_000,
                "unknown_usage_attempts": sum(r[2] is None for r in calls),
                "prices": PRICES}


class BudgetedEnricher(WeeklyEnricher):
    """Reserve each HTTP attempt before sending, including retries and resumed runs."""

    def __init__(self, *args, total_limit, **kwargs):
        super().__init__(*args, **kwargs)
        self.total_limit = total_limit
        self.last_call = None

    def _budget(self, kind):
        super()._budget(kind)
        maximum = math.ceil(self.settings.weekly_input_token_cap * (
            PRICES["jev_input"] if kind == "jev" else PRICES["ds_input"]) +
            (0 if kind == "jev" else
             self.settings.weekly_output_token_cap * PRICES["ds_output"]))
        self.last_call = self.store.reserve(kind, maximum, self.total_limit)

    def _post(self, provider, body, kind):
        result = super()._post(provider, body, kind)
        self.store.reconcile(self.last_call, kind, result.get("usage", {}))
        return result


def prepare(export: dict, root: Path, budget_usd: float, report_dates=None, full_history=False):
    if budget_usd <= 0 or not math.isfinite(budget_usd):
        raise ValueError("A positive total backfill budget is required")
    packets = export["packets"]
    if report_dates:
        packets = [p for p in packets if p["report_date"] in report_dates]
        if {p["report_date"] for p in packets} != set(report_dates):
            raise ValueError("Requested report dates are absent from the export")
    if not 1 <= len(packets) <= 5:
        raise ValueError("Expected one to five report packets")
    dates = sorted(date.fromisoformat(p["report_date"]) for p in packets)
    if any(d.weekday() != 6 for d in dates) or any(
            (b-a).days != 7 for a, b in zip(dates, dates[1:], strict=False)):
        raise ValueError("Expected consecutive completed Sunday UTC report dates")
    configurations = {(encoded(p["provider_configuration"]), p["taxonomy_version"],
                       encoded(p["topics"])) for p in packets}
    if len(configurations) != 1 or any(not p["input_complete"] for p in packets):
        raise ValueError("Input must be complete with one frozen taxonomy/configuration")
    for p in packets:
        if datetime.fromisoformat(p["data_cutoff"]) < windows(
                date.fromisoformat(p["report_date"]))[0][1]:
            raise ValueError("Current week is incomplete")
    observations = {}
    start = windows(dates[0])[-1 if full_history else 1][0].isoformat()
    for packet in packets:
        for row in packet["observations"]:
            if row["published_at"] < start:
                continue
            if row["id"] in observations and observations[row["id"]] != row:
                raise ValueError("Conflicting frozen observations")
            observations[row["id"]] = row
    manifest = {"version": VERSION, "notice": NOTICE, "coverage_confirmed": False,
                "budget_usd": budget_usd, "prices": PRICES,
                "scope": "full_history" if full_history else "current_and_previous",
                "observation_start": start,
                "input_fingerprint": fingerprint(export), "packets": packets,
                "observations": sorted(observations.values(), key=lambda r: r["id"]),
                "original_legacy_reports": export.get("legacy_reports", [])}
    root.mkdir(parents=True, exist_ok=True)
    path = root / "manifest.json"
    if path.exists():
        if fingerprint(json.loads(path.read_text())) != fingerprint(manifest):
            raise ValueError("Frozen manifest differs; create a separate backfill revision")
    else:
        path.write_text(encoded(manifest) + "\n")
    with (root / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        store = PreviewStore(root / "preview.sqlite")
        try:
            for p in packets:
                store.db.execute("INSERT OR IGNORE INTO jobs(report_date,input_key,status) "
                                 "VALUES (?,?,'pending')",
                                 (p["report_date"], fingerprint(p)))
            store.db.commit()
        finally:
            store.close()
    return {"dates": [str(d) for d in dates], "unique_observations": len(observations),
            "total_budget_usd": budget_usd, "paid_calls": 0, "notice": NOTICE}


def preview(packet, rows, events_complete):
    periods = windows(date.fromisoformat(packet["report_date"]))
    sides = [[r for r in rows if start <= datetime.fromisoformat(r["published_at"]) < end]
             for start, end in periods[:2]]
    topics = []
    for topic in packet["topics"]:
        selected = [[r for r in side if r.get("eligible") and r["topic_id"] == topic["id"]]
                    for side in sides]
        if not any(selected):
            continue
        evidence = []
        seen = set()
        for side, window in zip(selected, ("current", "previous"), strict=True):
            for r in sorted(side, key=lambda r: (r["publisher"], r["id"])):
                if r["publisher"] in seen or not r["url"].startswith(("http://", "https://")):
                    continue
                seen.add(r["publisher"])
                evidence.append({k: r[k] for k in ("id", "title", "url", "publisher",
                                                  "published_at", "event_id")} |
                                {"window": window, "excerpt": (r.get("summary") or
                                  r.get("content") or r["title"])[:2000]})
                if sum(e["window"] == window for e in evidence) == 3:
                    break
        counts = [len(s) for s in selected]
        topics.append({"topic_id": topic["id"], "title": topic["label"],
                       "state": "historical_preview", "coverage_notice": NOTICE,
                       "observed_articles_current": counts[0],
                       "observed_articles_previous": counts[1],
                       "observed_article_difference": counts[0]-counts[1],
                       "observed_event_groups_current": len({r["event_id"] for r in selected[0]}),
                       "observed_event_groups_previous": len({r["event_id"] for r in selected[1]}),
                       "observed_publishers_current": len({r["publisher"] for r in selected[0]}),
                       "observed_publishers_previous": len({r["publisher"] for r in selected[1]}),
                       "summary": f"Stored articles: {counts[1]} -> {counts[0]}. {NOTICE}",
                       "url": evidence[0]["url"] if evidence else "", "evidence": evidence})
    topics.sort(key=lambda t: (-t["observed_articles_current"], t["topic_id"]))
    return {"report_date": packet["report_date"], "status": "historical_preview",
            "notice": NOTICE, "coverage_confirmed": False, "date_provenance": "unverified",
            "methodology_version": VERSION, "data_cutoff": packet["data_cutoff"],
            "taxonomy_version": packet["taxonomy_version"],
            "new": [], "trending_up": [], "trending_down": [], "topics": topics,
            "quality": {"reason": "coverage_unknown", "events_complete": events_complete,
                        "quality_counters": packet["quality_counters"],
                        "raw_articles_current": len(sides[0]),
                        "raw_articles_previous": len(sides[1]),
                        "non_ai": sum(not r["eligible"] for side in sides for r in side),
                        "unresolved": sum(r["eligible"] and r["topic_id"] is None
                                          for side in sides for r in side)},
            "publication_policy": "Artifact only; never publish into verified or legacy reports."}


def run(root: Path, settings: Settings):
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest["prices"] != PRICES or manifest["version"] != VERSION:
        raise ValueError("Pricing or methodology differs from the frozen manifest")
    with (root / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        store = PreviewStore(root / "preview.sqlite")
        try:
            packet = manifest["packets"][0]
            settings = settings.model_copy(update=packet["provider_configuration"])
            with httpx.Client() as client:
                enricher = BudgetedEnricher(settings, store, client, packet["topics"],
                    packet["taxonomy_version"], total_limit=int(manifest["budget_usd"]*1_000_000))
                store.db.execute("UPDATE jobs SET status='running' WHERE status!='complete'")
                store.db.commit()
                try:
                    classified = []
                    for row in manifest["observations"]:
                        key = "classified:" + row["id"]
                        result = store.progress(key)
                        if result is None:
                            # Legacy provenance remains unchanged. Semantic eligibility is
                            # only used inside the explicitly unverified preview.
                            result = {**row, **enricher.classify(row)}
                            if enricher.failed:
                                raise RuntimeError("provider_unavailable")
                            store.save_progress(key, result)
                        classified.append(result)
                    clustered = store.progress("clustered")
                    if clustered is None:
                        rows, complete = enricher.cluster(classified)
                        if enricher.failed:
                            raise RuntimeError("provider_unavailable")
                        clustered = {"rows": rows, "complete": complete,
                                     "ambiguities": enricher.event_ambiguities}
                        store.save_progress("clustered", clustered)
                    for p in manifest["packets"]:
                        state = store.db.execute(
                            "SELECT status,revision FROM jobs WHERE report_date=?",
                            (p["report_date"],)).fetchone()
                        if state[0] == "complete":
                            continue
                        before = store.usage()
                        result = preview(p, clustered["rows"], clustered["complete"])
                        definitions = {t["id"]: t for t in p["topics"]}
                        for item in result["topics"][:8]:
                            # Proven evidence validation and claim support gates are reused.
                            item["narrative_mode"] = "deepseek" if explain(
                                item, enricher, definitions[item["topic_id"]]) else "template"
                        revision = state[1]+1
                        while (root / f"{p['report_date']}.r{revision}.json").exists():
                            revision += 1
                        result.update({"revision": revision,
                                       "generated_at": datetime.now(UTC).isoformat(),
                                       "usage_before_report": before,
                                       "usage_after_report": store.usage(),
                                       "event_ambiguities": clustered["ambiguities"]})
                        path = root / f"{p['report_date']}.r{revision}.json"
                        with path.open("x") as artifact:
                            artifact.write(encoded(result) + "\n")
                        store.db.execute("UPDATE jobs SET status='complete',revision=?,error=NULL "
                                         "WHERE report_date=?", (revision, p["report_date"]))
                        store.db.commit()
                except (BudgetExhausted, RuntimeError) as exc:
                    store.db.execute(
                        "UPDATE jobs SET status='retry',error=? WHERE status='running'",
                        (str(exc),))
                    store.db.commit()
                return {"jobs": store.db.execute("SELECT report_date,status,revision,error "
                                                   "FROM jobs ORDER BY report_date").fetchall(),
                        "usage": store.usage()}
        finally:
            store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="Freeze exported read-only input; no model calls")
    prep.add_argument("--export", required=True, type=Path)
    prep.add_argument("--root", required=True, type=Path)
    prep.add_argument("--total-budget-usd", required=True, type=float)
    prep.add_argument("--report-date", action="append")
    prep.add_argument("--full-history", action="store_true")
    runner = commands.add_parser("run", help="Resume isolated jobs under the total budget")
    runner.add_argument("--root", required=True, type=Path)
    runner.add_argument("--approve-paid", required=True, action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(json.loads(args.export.read_text()), args.root, args.total_budget_usd,
                         args.report_date, args.full_history)
    else:
        result = run(args.root, Settings())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
