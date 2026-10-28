# Prompt: backlog after v0.1.133 (2026-10-28)

Executor: DeepSeek, run by the coordinator; the coordinator reviews and merges. Docs only. Do every
step exactly; no other edits.

Repo: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (main folder). Never run `git add`, `git commit`,
`git checkout` or `rm -rf` in the main folder. Work only in the worktree from step 1.

## Step 1. Worktree

```bash
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch -q origin
git worktree add -b docs/todo-after-133-20261028 ../AI_PARSER-wt-todo133 origin/master
cd ../AI_PARSER-wt-todo133
```

## Step 2. Run the edit script

Save as `/tmp/todo_after_133.py`, run `python3 /tmp/todo_after_133.py` from the worktree root. It
must print `ok`. If an assert fails, stop and report; do not edit by hand.

```python
import json
import pathlib
import shutil

MAIN = pathlib.Path("/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work")
ARCH = pathlib.Path("docs/archive/2026-10")
SPEC = "specs/017-weekly-monthly-signals"


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
old = "Statuses: todo, waiting_owner, backlog, deferred, done."
assert d["how_to_use"].count(old) == 1
d["how_to_use"] = d["how_to_use"].replace(
    old, "Statuses: todo, in_progress, waiting_owner, backlog, deferred, done.")

aw = item(d["items"], "ARCHIVE-week")
assert aw["status"] == "todo"
aw["status"] = "done"
aw["done"] = "2026-10-28"
aw["result"] = ("Checked 2026-10-28: coverage 95.7% (600/627), every day >= 91%, gave_up 0, no outage; "
                "29 documents failed http_403 (22 openai.com, expected to give up); the 4020 pending "
                "are the old 2026-10-24 seed and stay pending by design.")

fw = item(d["items"], "FIREWALL")
assert fw["status"] == "backlog"
fw["note"] = "Owner 2026-10-28: later, the current setup is safe enough."

b2 = item(d["items"], "B2")
assert b2["status"] == "deferred"
b2["status"] = "in_progress"
b2.pop("decided", None)
b2["source"] = SPEC
b2["note"] = ("Spec 017: R1 (weekly v2 code and its collection hooks deleted, F1 finding 4 closed by "
              "deleting the recorder) live as v0.1.133 on 2026-10-28. Next: R2 numbers, R3 page, "
              "R4 briefs, R5 retire legacy weekly, R6 month.")

assert all(i["id"] != "ARCHIVE-LOG-DUP" for i in d["items"])
d["items"].append({
    "id": "ARCHIVE-LOG-DUP",
    "title": "daily-archive.log writes each nightly summary line twice",
    "priority": "P3",
    "status": "todo",
    "source": "coordinator, night of 2026-10-28"
})
save(p, d)

p, d = load("docs/backlog/backlog-todo.json")
b2 = item(d["items"], "B2")
assert b2["status"] == "deferred"
b2["status"] = "in_progress"
b2["status_note"] = "Spec " + SPEC + " (2026-10-28); R1 live as v0.1.133."
save(p, d)

sp = pathlib.Path("docs/work/coordinator-state-2026-10-24.json")
s = sp.read_text(encoding="utf-8")
old = '"master": "4538423 (PR #127)"'
assert s.count(old) == 1
s = s.replace(old, '"master": "9142b35 (PR #130)"')
old = '"prod": "v0.1.132 (2026-10-27 23:45 UTC): '
assert s.count(old) == 1
s = s.replace(old, '"prod": "v0.1.133 (2026-10-28 12:30 UTC): #130 spec 017 R1, weekly v2 code '
                   'deleted. Before: v0.1.132 (2026-10-27 23:45 UTC): ')
json.loads(s)
sp.write_text(s, encoding="utf-8")

for name in ["prompt-todo-after-132-2026-10-28.md", "prompt-coordinator-next-2026-10-28.md"]:
    assert not (ARCH / name).exists(), name
    shutil.copyfile(MAIN / name, ARCH / name)
print("ok")
```

## Step 3. Checks

```bash
git add -A
git status --short
PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest tests -k code_docs -p no:cacheprovider -o addopts="" 2>&1 | tail -1
```
Expected status: two `A docs/archive/2026-10/*.md` and `M` for `docs/backlog/coordinator-todo.json`,
`docs/backlog/backlog-todo.json` and `docs/work/coordinator-state-2026-10-24.json`. Nothing else.
The pytest line shows `passed`.

## Step 4. Commit, push, PR

```bash
git commit -m "docs: backlog and state after v0.1.133" -m "Co-Authored-By: DeepSeek V4-Pro <noreply@deepseek.com>"
git push -u origin docs/todo-after-133-20261028
gh pr create --base master --title "docs: backlog and state after v0.1.133" --body "Docs-only; full gate skipped.

- coordinator-todo.json: ARCHIVE-week done; FIREWALL later (owner); new ARCHIVE-LOG-DUP; B2 in_progress (spec 017).
- backlog-todo.json: B2 in_progress.
- Coordinator state: master 9142b35, prod v0.1.133.
- Archive two prompts."
```
Do not merge.

## Step 5. Report (final answer)

PR URL, `git log --oneline -1`, outputs of steps 2 and 3, anything that did not go as written.
