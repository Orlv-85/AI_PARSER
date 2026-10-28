# Prompt: backlog after v0.1.132 (2026-10-28)

Executor: DeepSeek, run by coordinator `ai-parser-ba`; the coordinator reviews and merges. Docs
only. Do every step exactly; no other edits.

Repo: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (main folder). Never run `git add`, `git commit`,
`git checkout` or `rm -rf` in the main folder. Work only in the worktree from step 1.

## Step 1. Worktree

```bash
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch -q origin
git worktree add -b docs/todo-after-132-20261028 ../AI_PARSER-wt-todo132 origin/master
cd ../AI_PARSER-wt-todo132
```

## Step 2. Run the edit script

Save as `/tmp/todo_after_132.py`, run `python3 /tmp/todo_after_132.py` from the worktree root. It
must print `ok`. If an assert fails, stop and report; do not edit by hand.

```python
import json
import pathlib
import shutil

MAIN = pathlib.Path("/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work")
ARCH = pathlib.Path("docs/archive/2026-10")


def item(items, key):
    found = [i for i in items if i.get("id") == key]
    assert len(found) == 1, key
    return found[0]


p = pathlib.Path("docs/backlog/coordinator-todo.json")
d = json.loads(p.read_text(encoding="utf-8"))
d["updated"] = "2026-10-28"
results = {
    "PENDING-check": ("2026-10-28", "Night of 2026-10-28 on v0.1.132: admission pending 516 -> 72, openai_news pending 0, stale_pending 763 -> 1208; fetch, digest (86 in scope), archive (coverage 95.7%) green; fetch_run_finished shows fetched 4225, examined 1769, sources_fetched 152."),
    "UA": ("2026-10-28", "PR #127 (v0.1.132): one bot user agent ai-news-collector/<version> (+https://5kzt.l.time4vps.cloud/) for fetch, archive, evidence, robots.txt and probes; robots rules matched on the bot token. Measured before the switch: 88 enabled sources answer the same to both user agents; www.intel.com newsroom 403 -> 200. Note: docs/archive/2026-10/report-ua-options-2026-10-28.md."),
    "S-onb": ("2026-10-28", "PR #126 (v0.1.132): an HTML candidate is validated by HTML_SAMPLE_LINKS (3) fetched links that all pass the article check (warning otherwise; a warning candidate is added by hand in sources.yaml); onboarding and intake use candidate_url_key, the pipeline's canonical key."),
}
for key, (done, result) in results.items():
    i = item(d["items"], key)
    i["status"] = "done"
    i["done"] = done
    i["result"] = result
    for k in ("needs", "executor", "question"):
        i.pop(k, None)
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

sp = pathlib.Path("docs/work/coordinator-state-2026-10-24.json")
s = sp.read_text(encoding="utf-8")
old = '"master": "dbf824d (PR #116)"'
assert s.count(old) == 1
s = s.replace(old, '"master": "4538423 (PR #127)"')
a = s.index('"prod": "v0.1.129')
b = s.index("\n", a)
s = (s[:a]
     + '"prod": "v0.1.132 (2026-10-27 23:45 UTC): #118 archive timeouts as outage, #119 future dates, '
       '#120 size loop, #123 F1 counters, #126 S-onb, #127 honest bot user agent. SSH by key only '
       '(deploy user, root by key), fail2ban on auth.log, root password changed by the owner '
       '2026-10-27.",'
     + s[b:])
json.loads(s)
sp.write_text(s, encoding="utf-8")

for name in ["prompt-todo-after-131-2026-10-28.md", "prompt-s-onb-2026-10-28.md",
             "prompt-ua-options-2026-10-28.md", "prompt-honest-ua-2026-10-28.md",
             "report-ua-options-2026-10-28.md"]:
    shutil.copyfile(MAIN / name, ARCH / name)
print("ok")
```

## Step 3. Checks

```bash
git add -A
git status --short
PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest tests -k code_docs -p no:cacheprovider -o addopts="" 2>&1 | tail -1
```
Expected status: five `A docs/archive/2026-10/*.md` and `M` for
`docs/backlog/coordinator-todo.json` and `docs/work/coordinator-state-2026-10-24.json`. Nothing
else. The pytest line shows `passed`.

## Step 4. Commit, push, PR

```bash
git commit -m "docs: backlog and state after v0.1.132" -m "Co-Authored-By: DeepSeek V4-Pro <noreply@deepseek.com>"
git push -u origin docs/todo-after-132-20261028
gh pr create --base master --title "docs: backlog and state after v0.1.132" --body "Docs-only; full gate skipped.

- coordinator-todo.json: PENDING-check, UA, S-onb done.
- Coordinator state: master 4538423, prod v0.1.132.
- Archive four prompts and the UA decision note."
```
Do not merge.

## Step 5. Report (final answer)

PR URL, `git log --oneline -1`, outputs of steps 2 and 3, anything that did not go as written.
