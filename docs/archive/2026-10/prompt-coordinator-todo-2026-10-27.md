# Prompt: coordinator todo list as JSON (2026-10-27)

Executor: DeepSeek, run by coordinator `ai-parser-ba`; the coordinator reviews and merges. Docs
only. Do every step exactly; no other edits.

Repo: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (main folder). Never run `git add`, `git commit`,
`git checkout` or `rm -rf` in the main folder. Work only in the worktree from step 1.

## Step 1. Worktree

```bash
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch -q origin
git worktree add -b docs/coordinator-todo-20261027 ../AI_PARSER-wt-todo origin/master
cd ../AI_PARSER-wt-todo
```

## Step 2. Run the edit script

Save as `/tmp/coordinator_todo.py`, run `python3 /tmp/coordinator_todo.py` from the worktree root.
It must print `ok`. If an assert fails, stop and report; do not edit by hand.

```python
import json
import pathlib
import shutil

SCRATCH = pathlib.Path("/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/ef9ee6d8-3194-45a0-9a65-7c1b58b42256/scratchpad")
MAIN = pathlib.Path("/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work")

# 1. The todo list (written by the coordinator).
todo = pathlib.Path("docs/backlog/coordinator-todo.json")
shutil.copyfile(SCRATCH / "coordinator-todo.json", todo)
json.loads(todo.read_text(encoding="utf-8"))

# 2. Register it in docs/README.md.
rp = pathlib.Path("docs/README.md")
r = rp.read_text(encoding="utf-8")
anchor = "- [tooling-todo.json](backlog/tooling-todo.json) - agent tooling (spec pipeline), not product\n"
assert r.count(anchor) == 1
r = r.replace(anchor, anchor + "- [coordinator-todo.json](backlog/coordinator-todo.json) - coordinator checks, fixes and open decisions\n")
rp.write_text(r, encoding="utf-8")

# 3. State file: the "next" list moves to the todo file.
sp = pathlib.Path("docs/work/coordinator-state-2026-10-24.json")
s = sp.read_text(encoding="utf-8")
a = s.index('  "next": [\n')
b = s.index('  ],\n  "carried_unverified"', a)
s = s[:a] + '  "next": "docs/backlog/coordinator-todo.json (kept current by the coordinator)",\n' + s[b + len('  ],\n'):]
old_master = '"master": "d789ede (PR #114)"'
assert s.count(old_master) == 1
s = s.replace(old_master, '"master": "dbf824d (PR #116)"')
a = s.index('"prod": "v0.1.128')
b = s.index("\n", a)
s = (s[:a]
     + '"prod": "v0.1.129 (2026-10-27 20:55 UTC, PR #116: stale_pending rows are not reopened by the '
       'feed). SSH since 2026-10-24: password login off, root by key only, CI and operators as '
       'deploy (docker group, narrow sudoers), fail2ban sshd jail on /var/log/auth.log; owner changed '
       'the root password 2026-10-27 (time4vps console only); SERVER_PASSWORD removed from GitHub '
       'and the local .env.",'
     + s[b:])
json.loads(s)
sp.write_text(s, encoding="utf-8")

# 4. Archive finished prompts (git-ignored copies in the main folder).
for name in ["prompt-docs-after-ssh-2026-10-24.md", "prompt-stale-pending-reopen-2026-10-27.md"]:
    shutil.copyfile(MAIN / name, pathlib.Path("docs/archive/2026-10") / name)
print("ok")
```

## Step 3. Checks

```bash
git add -A
git status --short
python3 -m json.tool docs/work/coordinator-state-2026-10-24.json > /dev/null && echo state-ok
PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest tests -k code_docs -p no:cacheprovider 2>&1 | tail -1
```
Expected status: `A docs/backlog/coordinator-todo.json`, two `A docs/archive/2026-10/prompt-*.md`,
`M docs/README.md`, `M docs/work/coordinator-state-2026-10-24.json`. Nothing else. `state-ok`; the
pytest line shows `passed`.

## Step 4. Commit, push, PR

```bash
git commit -m "docs: coordinator todo as JSON, state points to it" -m "Co-Authored-By: DeepSeek V4-Pro <noreply@deepseek.com>"
git push -u origin docs/coordinator-todo-20261027
gh pr create --base master --title "docs: coordinator todo as JSON, state points to it" --body "Docs-only; full gate skipped.

- New docs/backlog/coordinator-todo.json: current checks, fixes and open decisions (English), registered in docs/README.md.
- Coordinator state: next -> the todo file; master dbf824d, prod v0.1.129.
- Archive two finished prompts."
```
Do not merge.

## Step 5. Report (final answer)

PR URL, `git log --oneline -1`, outputs of steps 2 and 3, anything that did not go as written.
