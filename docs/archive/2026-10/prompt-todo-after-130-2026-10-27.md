# Prompt: coordinator todo after v0.1.130 (2026-10-27)

Executor: DeepSeek, run by coordinator `ai-parser-ba`; the coordinator reviews and merges. Docs
only. Do every step exactly; no other edits.

Repo: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (main folder). Never run `git add`, `git commit`,
`git checkout` or `rm -rf` in the main folder. Work only in the worktree from step 1.

## Step 1. Worktree

```bash
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch -q origin
git worktree add -b docs/todo-after-130-20261027 ../AI_PARSER-wt-todo130 origin/master
cd ../AI_PARSER-wt-todo130
```

## Step 2. Run the edit script

Save as `/tmp/todo_after_130.py`, run `python3 /tmp/todo_after_130.py` from the worktree root. It
must print `ok`. If an assert fails, stop and report; do not edit by hand.

```python
import json
import pathlib
import shutil

MAIN = pathlib.Path("/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work")

p = pathlib.Path("docs/backlog/coordinator-todo.json")
d = json.loads(p.read_text(encoding="utf-8"))
items = {i["id"]: i for i in d["items"]}
for key in ["FUTURE-DATES", "BRIEF-1014", "BILLS", "DB-SIZE-LOOP", "ARCHIVE-TIMEOUTS", "ARCHIVE-week"]:
    assert key in items, key

d["updated"] = "2026-10-27"
d["items"] = [i for i in d["items"] if i["id"] not in {"BILLS", "BRIEF-1014"}]
done = {
    "FUTURE-DATES": "PR #119 (v0.1.130): a publication date more than FUTURE_DATE_TOLERANCE (24 h) ahead becomes the collection time; the original is kept in date_provenance. Owner 2026-10-27: the 45 stored articles with published_at > discovered_at + 24 h are not changed.",
    "DB-SIZE-LOOP": "PR #120 (v0.1.130): the size loop stops when a prune does not reduce the DB size. Prod DB 179 MB of the 5 GB limit; the loop has never fired.",
    "ARCHIVE-TIMEOUTS": "PR #118 (v0.1.130): httpx timeouts count toward the downloader outage (OUTAGE_HOSTS = 10) like ConnectError, also for daily-publish.",
}
for i in d["items"]:
    if i["id"] in done:
        i["status"] = "done"
        i["done"] = "2026-10-27"
        i["result"] = done[i["id"]]
        i.pop("question", None)
        i.pop("executor", None)
    if i["id"] == "ARCHIVE-week":
        i["title"] = ("`ai-news archive status` (with APP_IMAGE): coverage_pct >= 90 over 7 nights "
                      "(SC-002), gave_up counts (22 openai.com documents fail with http_403 and are "
                      "expected to give up), top hosts without text")
        i["note"] = ("The 4014 pending archive documents are the old articles of the 2026-10-24 seed "
                     "(capture --all --no-download); only documents first seen within "
                     "ARCHIVE_LOOKBACK_DAYS are due, so they stay pending by design. Decided "
                     "2026-10-27 (agent): no one-off download of them.")
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

bp = pathlib.Path("docs/backlog/backlog-todo.json")
b = json.loads(bp.read_text(encoding="utf-8"))
before = len(b["small_followups"])
drop = ("007: 2026-10-14 brief", "Check the real DeepSeek bill", "Future publication dates",
        "db_maintenance.sh size loop", "016 capture: timeouts")
b["small_followups"] = [s for s in b["small_followups"] if not s.startswith(drop)]
assert before - len(b["small_followups"]) == 5, before - len(b["small_followups"])
bp.write_text(json.dumps(b, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

for name in ["prompt-coordinator-todo-2026-10-27.md", "prompt-future-dates-2026-10-27.md",
             "prompt-db-size-loop-2026-10-27.md", "prompt-archive-timeouts-2026-10-27.md"]:
    shutil.copyfile(MAIN / name, pathlib.Path("docs/archive/2026-10") / name)
print("ok")
```

## Step 3. Checks

```bash
git add -A
git status --short
git diff --cached --stat
PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest tests -k code_docs -p no:cacheprovider -o addopts="" 2>&1 | tail -1
```
Expected status: four `A docs/archive/2026-10/prompt-*.md`, `M docs/backlog/coordinator-todo.json`,
`M docs/backlog/backlog-todo.json`. Nothing else. The pytest line shows `passed`.

## Step 4. Commit, push, PR

```bash
git commit -m "docs: coordinator todo after v0.1.130" -m "Co-Authored-By: DeepSeek V4-Pro <noreply@deepseek.com>"
git push -u origin docs/todo-after-130-20261027
gh pr create --base master --title "docs: coordinator todo after v0.1.130" --body "Docs-only; full gate skipped.

- coordinator-todo.json: FUTURE-DATES, DB-SIZE-LOOP, ARCHIVE-TIMEOUTS done (v0.1.130); BILLS and BRIEF-1014 removed (owner); ARCHIVE-week note on the 4014 seeded documents.
- backlog-todo.json: the five small follow-ups now done or decided are removed.
- Archive four finished prompts."
```
Do not merge.

## Step 5. Report (final answer)

PR URL, `git log --oneline -1`, outputs of steps 2 and 3, anything that did not go as written.
