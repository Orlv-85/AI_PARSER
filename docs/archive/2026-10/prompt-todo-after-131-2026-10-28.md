# Prompt: backlog after v0.1.131 and J1 (2026-10-28)

Executor: DeepSeek, run by coordinator `ai-parser-ba`; the coordinator reviews and merges. Docs
only. Do every step exactly; no other edits.

Repo: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (main folder). Never run `git add`, `git commit`,
`git checkout` or `rm -rf` in the main folder. Work only in the worktree from step 1.

## Step 1. Worktree

```bash
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch -q origin
git worktree add -b docs/todo-after-131-20261028 ../AI_PARSER-wt-todo131 origin/master
cd ../AI_PARSER-wt-todo131
```

## Step 2. Run the edit script

Save as `/tmp/todo_after_131.py`, run `python3 /tmp/todo_after_131.py` from the worktree root. It
must print `ok`. If an assert fails, stop and report; do not edit by hand.

```python
import json
import pathlib
import shutil

J1 = "specs/006-daily-ai-signals/records/report-jev-novelty-j1-2026-10-27.md"


def load(path):
    p = pathlib.Path(path)
    return p, json.loads(p.read_text(encoding="utf-8"))


def save(p, d):
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def item(items, key):
    found = [i for i in items if i.get("id") == key]
    assert len(found) == 1, key
    return found[0]


p, d = load("docs/backlog/coordinator-todo.json")
d["updated"] = "2026-10-28"
f1 = item(d["items"], "F1")
f1["status"] = "done"
f1["done"] = "2026-10-27"
f1["result"] = ("PR #123 (v0.1.131): new log fields examined_items (source_fetch_finished), examined "
                "and sources_fetched (fetch_run_finished); source_fetch_finished also for a failed "
                "fetch with admission off; old fields unchanged. Finding 4 (fetch_failure counted as "
                "complete weekly coverage) not changed: weekly does not run on prod; moved to B2.")
f1.pop("executor", None)
b2 = item(d["items"], "B2")
b2["note"] = ("When weekly work starts, also decide F1 finding 4: a failed source fetch is recorded "
              "as complete weekly coverage (cycle.py record_attempt outcome fetch_failure, "
              "complete=True); recommended complete=False.")
d["items"].append({
    "id": "B4-J1",
    "title": "Jev as a second opinion for New: J1 offline experiment (534 Jev calls, $0.035)",
    "status": "done",
    "done": "2026-10-27",
    "result": ("Article-level AND gate at t=0.5: displayed precision 85% -> 96%, recall 81% -> 64%. "
               "Owner 2026-10-27: keep New as it is, drop the Jev gate. Report: " + J1 + ".")
})
save(p, d)

p, d = load("docs/backlog/backlog-todo.json")
b4 = item(d["items"], "B4")
assert b4["status"] == "todo"
b4["status"] = "dropped"
b4["status_note"] = "Owner 2026-10-27 after J1: keep New as it is (recall over precision). Report: " + J1 + "."
save(p, d)

p, d = load("docs/backlog/jev-novelty-second-opinion-todo.json")
assert d["status"] == "backlog"
d["status"] = "dropped"
d["status_note"] = ("2026-10-27: J1 done (" + J1 + "); the gate costs too much recall. Owner: keep "
                    "New as it is. J2-J4 will not be done.")
j1 = item(d["tasks"], "J1")
j1["status"] = "done"
for key in ("J2", "J3", "J4"):
    item(d["tasks"], key)["status"] = "dropped"
save(p, d)

for name in ["prompt-backlog-status-2026-10-27.md", "prompt-f1-pipeline-findings-2026-10-27.md"]:
    shutil.copyfile("/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/" + name,
                    "docs/archive/2026-10/" + name)
print("ok")
```

## Step 3. Checks

```bash
git add -A
git status --short
PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest tests -k code_docs -p no:cacheprovider -o addopts="" 2>&1 | tail -1
```
Expected status: two `A docs/archive/2026-10/prompt-*.md` and `M` for
`docs/backlog/coordinator-todo.json`, `docs/backlog/backlog-todo.json`,
`docs/backlog/jev-novelty-second-opinion-todo.json`. Nothing else. The pytest line shows `passed`.

## Step 4. Commit, push, PR

```bash
git commit -m "docs: backlog after v0.1.131 and the J1 result" -m "Co-Authored-By: DeepSeek V4-Pro <noreply@deepseek.com>"
git push -u origin docs/todo-after-131-20261028
gh pr create --base master --title "docs: backlog after v0.1.131 and the J1 result" --body "Docs-only; full gate skipped.

- coordinator-todo.json: F1 done (v0.1.131), its finding 4 moved to B2; B4-J1 done.
- backlog-todo.json B4 and jev-novelty-second-opinion-todo.json: dropped after J1 (owner).
- Archive two finished prompts."
```
Do not merge.

## Step 5. Report (final answer)

PR URL, `git log --oneline -1`, outputs of steps 2 and 3, anything that did not go as written.
