# Prompt: refresh stale backlog statuses (2026-10-27)

Executor: DeepSeek, run by coordinator `ai-parser-ba`; the coordinator reviews and merges. Docs
only. Do every step exactly; no other edits.

Repo: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (main folder). Never run `git add`, `git commit`,
`git checkout` or `rm -rf` in the main folder. Work only in the worktree from step 1.

## Step 1. Worktree

```bash
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch -q origin
git worktree add -b docs/backlog-status-20261027 ../AI_PARSER-wt-bstatus origin/master
cd ../AI_PARSER-wt-bstatus
```

## Step 2. Run the edit script

Save as `/tmp/backlog_status.py`, run `python3 /tmp/backlog_status.py` from the worktree root. It
must print `ok`. If an assert fails, stop and report; do not edit by hand.

```python
import json
import pathlib
import shutil


def load(path):
    p = pathlib.Path(path)
    return p, json.loads(p.read_text(encoding="utf-8"))


def save(p, d):
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def item(items, key):
    found = [i for i in items if i.get("id") == key]
    assert len(found) == 1, key
    return found[0]


# backlog-todo.json
p, d = load("docs/backlog/backlog-todo.json")
b2 = item(d["items"], "B2")
assert b2["status"] == "todo"
b2["status"] = "deferred"
b2["status_note"] = "Owner 2026-10-24: not now, smaller items first."
b3 = item(d["items"], "B3")
assert b3["status"] == "in_progress"
b3["status"] = "done"
b3["status_note"] = ("Spec 016 phases 1-4 live since v0.1.124 (archive before prune, nightly capture "
                     "03:00 UTC, status, purge, import-db); phase 5 (admin stats) only on owner "
                     "request. Details: docs/backlog/article-archive-todo.json.")
save(p, d)

# article-archive-todo.json
p, d = load("docs/backlog/article-archive-todo.json")
assert d["status"] == "backlog"
d["status"] = "in_progress"
d["status_note"] = "2026-10-27: A0, A1, A3 done; A2 partly; A4-A7 open."
notes = {
    "A1": ("done", "Spec 016: tables archive_documents and archive_texts, archive before prune; code doc src/app/core/archive/capture.md."),
    "A2": ("partly", "2026-10-24 seed: 7000 documents, 2959 with text. Old seeded documents are not downloaded (only documents first seen within ARCHIVE_LOOKBACK_DAYS are due); decided 2026-10-27 (agent): no one-off download."),
    "A3": ("done", "Nightly capture job 03:00 UTC since v0.1.124; network timeouts count as an outage since v0.1.130."),
}
for key, (status, note) in notes.items():
    t = item(d["tasks"], key)
    assert t.get("status") == "todo", key
    t["status"] = status
    t["status_note"] = note
save(p, d)

# coordinator-todo.json
p, d = load("docs/backlog/coordinator-todo.json")
t = item(d["items"], "BACKLOG-STATUS")
t["status"] = "done"
t["done"] = "2026-10-27"
t["result"] = "backlog-todo.json B2 deferred, B3 done; article-archive-todo.json A1, A3 done, A2 partly."
t.pop("executor", None)
save(p, d)

shutil.copyfile("/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/prompt-todo-after-130-2026-10-27.md",
                "docs/archive/2026-10/prompt-todo-after-130-2026-10-27.md")
print("ok")
```

## Step 3. Checks

```bash
git add -A
git status --short
PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest tests -k code_docs -p no:cacheprovider -o addopts="" 2>&1 | tail -1
```
Expected status: `A docs/archive/2026-10/prompt-todo-after-130-2026-10-27.md` and `M` for
`docs/backlog/backlog-todo.json`, `docs/backlog/article-archive-todo.json`,
`docs/backlog/coordinator-todo.json`. Nothing else. The pytest line shows `passed`.

## Step 4. Commit, push, PR

```bash
git commit -m "docs: refresh stale backlog statuses" -m "Co-Authored-By: DeepSeek V4-Pro <noreply@deepseek.com>"
git push -u origin docs/backlog-status-20261027
gh pr create --base master --title "docs: refresh stale backlog statuses" --body "Docs-only; full gate skipped.

- backlog-todo.json: B2 deferred (owner), B3 done (016 phases 1-4 live).
- article-archive-todo.json: in progress; A1, A3 done, A2 partly.
- coordinator-todo.json: BACKLOG-STATUS done. Archive one finished prompt."
```
Do not merge.

## Step 5. Report (final answer)

PR URL, `git log --oneline -1`, outputs of steps 2 and 3, anything that did not go as written.
