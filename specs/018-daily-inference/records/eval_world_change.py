"""Offline check of the world_change questions (spec 018, FR-002). Not product code.

Run from the repo root:
  PYTHONPATH=src ./venv1/bin/python specs/018-daily-inference/records/eval_world_change.py \
      --env /path/to/.env [--dir <folder of the jsonl files>] [--max-usd 0.2]

Reads world-change-sample.jsonl, asks Jev (real API, capped journal) once per article, writes
world-change-jev.jsonl, and, when world-change-labels.jsonl is there, prints agreement.
"""
import argparse
import json
import logging
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import httpx

from app.core.bulletin.world_change import (
    WORLD_CHANGE_VERSION,
    WorldChangeAssessor,
)
from app.core.provider_costs import microdollars
from app.storage.provider_journal import PilotJournal

DEFAULT_DIR = Path("/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/"
                   "8230bf51-ec40-4f65-b975-34c791a2cee9/scratchpad")
BUCKETS = ((0.0, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01))


def read_key(env_path):
    for line in Path(env_path).read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*(?:export\s+)?JEV_API_KEY\s*=\s*(.*)$", line)
        if match:
            return match.group(1).strip().strip("'\"")
    raise SystemExit("JEV_API_KEY not found")


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class Row:
    """Attribute view over a sample dict, as the assessor reads articles."""

    def __init__(self, data):
        self.title, self.summary, self.content = (
            data.get("title"), data.get("summary"), data.get("content"))


def run_jev(directory, max_usd, key):
    sample = read_jsonl(directory / "world-change-sample.jsonl")
    out_path = directory / "world-change-jev.jsonl"
    done = {r["url"]: r for r in read_jsonl(out_path)} if out_path.exists() else {}
    cap = microdollars(max_usd)
    journal_path = Path(tempfile.gettempdir()) / f"wc-eval-{WORLD_CHANGE_VERSION}-{cap}.sqlite3"
    journal = PilotJournal(journal_path, {"version": WORLD_CHANGE_VERSION, "eval": True},
                           {"total": str((cap + 1) / 1e6), "jev": str(cap / 1e6),
                            "deepseek": "0.000001"})
    logger = logging.getLogger("wc-eval")
    logging.basicConfig(level=logging.WARNING)
    failures = 0
    try:
        with httpx.Client(timeout=60) as client:
            assessor = WorldChangeAssessor(client, "jev-1.13.0", logger,
                                           payment_journal=journal, secret=key)
            for item in sample:
                if (item["url"] in done and not done[item["url"]].get("failed")) \
                        or assessor.stopped:
                    continue
                answer = assessor.assess(Row(item))
                if answer is None:
                    failures += 1
                    done[item["url"]] = {"url": item["url"], "failed": True}
                else:
                    done[item["url"]] = {"url": item["url"], **answer.__dict__}
        report = journal.report()
    finally:
        journal.close()
    rows = [done[i["url"]] for i in sample if i["url"] in done]
    out_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    jev = report["providers"]["jev"]
    print(json.dumps({"requests": jev["calls"], "failures": failures,
                      "cost_usd": jev["usage_priced_usd"], "tokens": jev["tokens"],
                      "stopped": assessor.stopped}))
    return sample, rows


def compare(sample, rows, labels):
    by_url = {r["url"]: r for r in rows if not r.get("failed")}
    lab = {r["url"]: r for r in labels}
    days = {s["url"]: s["day"] for s in sample}
    paired = [(by_url[u], lab[u]) for u in by_url if u in lab]
    print(f"compared: {len(paired)} of {len(sample)}")
    print("distribution jev:", dict(Counter(j["world_change"] for j, _ in paired)))
    print("distribution labels:", dict(Counter(lab_["world_change"] for _, lab_ in paired)))
    for name in ("world_change", "area", "actor"):
        agree = sum(j[name] == lab_[name] for j, lab_ in paired)
        print(f"agreement {name}: {agree}/{len(paired)} = {agree / max(len(paired), 1):.3f}")
    harm = sum((j["harm_to_people"] >= 0.5) == (lab_["harm_to_people"] == "yes")
               for j, lab_ in paired)
    print(f"agreement harm_to_people (p>=0.5): {harm}/{len(paired)}")
    for threshold in (0.3, 0.5, 0.7):
        tp = sum(j["harm_to_people"] >= threshold and lab_["harm_to_people"] == "yes"
                 for j, lab_ in paired)
        jev_yes = sum(j["harm_to_people"] >= threshold for j, _ in paired)
        lab_yes = sum(lab_["harm_to_people"] == "yes" for _, lab_ in paired)
        print(f"  harm p>={threshold}: jev yes {jev_yes}, label yes {lab_yes}, both {tp}")
    names = sorted({lab_["world_change"] for _, lab_ in paired} |
                   {j["world_change"] for j, _ in paired})
    table = Counter((lab_["world_change"], j["world_change"]) for j, lab_ in paired)
    print("confusion world_change (rows labels, columns jev):")
    print("label\\jev".ljust(10) + "".join(n.rjust(9) for n in names))
    for row in names:
        print(row.ljust(10) + "".join(str(table[(row, col)]).rjust(9) for col in names))
    print("agreement of world_change by Jev confidence bucket:")
    for low, high in BUCKETS:
        bucket = [(j, lab_) for j, lab_ in paired if low <= j["world_change_confidence"] < high]
        agree = sum(j["world_change"] == lab_["world_change"] for j, lab_ in bucket)
        print(f"  [{low:.1f},{min(high, 1.0):.1f}) n={len(bucket)} "
              f"agree={agree / max(len(bucket), 1):.3f}")
    print("cumulative: confidence >= t -> kept, agreement, kept shown (added/changed/issue/limit)")
    for t in (0.5, 0.6, 0.7, 0.8, 0.9):
        kept = [(j, lab_) for j, lab_ in paired if j["world_change_confidence"] >= t]
        agree = sum(j["world_change"] == lab_["world_change"] for j, lab_ in kept)
        print(f"  t={t}: kept {len(kept)}, agreement {agree / max(len(kept), 1):.3f}")
    per_day = defaultdict(lambda: [0, 0])
    for j, lab_ in paired:
        per_day[days[j["url"]]][0] += 1
        per_day[days[j["url"]]][1] += j["world_change"] == lab_["world_change"]
    print("agreement per day:", {d: f"{a}/{n}" for d, (n, a) in sorted(per_day.items())})
    titles = {s["url"]: s["title"] for s in sample}
    wrong = sorted((p for p in paired if p[0]["world_change"] != p[1]["world_change"]),
                   key=lambda p: -p[0]["world_change_confidence"])
    print("most confident disagreements:")
    for j, lab_ in wrong[:12]:
        print(f"  jev={j['world_change']}({j['world_change_confidence']:.2f}) "
              f"label={lab_['world_change']}({lab_.get('confidence')}) "
              f"{titles[j['url']][:80]!r} | {lab_.get('note', '')}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True)
    parser.add_argument("--dir", default=str(DEFAULT_DIR))
    parser.add_argument("--max-usd", default="0.2")
    parser.add_argument("--compare-only", action="store_true")
    args = parser.parse_args()
    directory = Path(args.dir)
    if args.compare_only:
        sample = read_jsonl(directory / "world-change-sample.jsonl")
        rows = read_jsonl(directory / "world-change-jev.jsonl")
    else:
        sample, rows = run_jev(directory, args.max_usd, read_key(args.env))
    labels_path = directory / "world-change-labels.jsonl"
    if labels_path.exists():
        compare(sample, rows, read_jsonl(labels_path))
    else:
        print("world-change-labels.jsonl not found: comparison skipped", file=sys.stderr)


if __name__ == "__main__":
    main()
