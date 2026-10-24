# Prompt: docs PR after v0.1.127 (2026-10-24)

Executor: DeepSeek (external model). Coordinator: Claude session `ai-parser-ba`; it reviews and
merges. Docs only: no code, no tests change. Do every step exactly; do not improvise extra edits.

Repo: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (main folder). Never run `git add`, `git commit`,
`git checkout` or `rm -rf` in the main folder. Work only in the worktree from step 1.

## Step 1. Worktree

```bash
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch -q origin
git worktree add -b docs/after-127-20261024 ../AI_PARSER-wt-docs127 origin/master
cd ../AI_PARSER-wt-docs127
git log --oneline -1
```
The last line must start with `3d38930` (Merge pull request #110). If not, stop and report.

## Step 2. Archive the three finished prompts

They are git-ignored files in the main folder `docs/work/`. Copy (do not move) them into the archive
of the worktree:

```bash
for f in prompt-web-static-split-2026-10-24.md prompt-web-static-finish-2026-10-24.md prompt-web-static-auth-fix-2026-10-24.md; do
  cp /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/$f docs/archive/2026-10/$f
done
ls docs/archive/2026-10/prompt-web-static-*
```
Three files must be listed.

## Step 3. Update the coordinator state

Save this script as `/tmp/edit_state_127.py` and run `python3 /tmp/edit_state_127.py` from the
worktree root. It must print `ok`. If an assert fails, stop and report the message; do not edit the
file by hand.

```python
import json
import pathlib

p = pathlib.Path("docs/work/coordinator-state-2026-10-24.json")
t = p.read_text(encoding="utf-8")


def sub(old, new):
    global t
    assert t.count(old) == 1, ("not found once", old[:60])
    t = t.replace(old, new)


sub('"master": "218eaa6 (PR #107)"',
    '"master": "3d38930 (PR #110)"')

start = t.index('"prod": "v0.1.126 deploy started')
end = t.index('\n', start)
t = (t[:start]
     + '"prod": "v0.1.127 tagged 2026-10-24 10:09 UTC on 3d38930 (deploy started by the tag; '
       'v0.1.126 deploy run 40081695444 was green, app healthy, archive coverage 95.5%). '
       'Owner: no browser check of the pages needed.",'
     + t[end:])

sub('signals_compute.py split into signals_{model,stories,lines,naming,history}.py (#107).",',
    'signals_compute.py split into signals_{model,stories,lines,naming,history}.py (#107); '
    'v0.1.127 move-only: inline CSS/JS of digest, admin, news_stats and login moved to '
    'src/app/web/static/ (no-cache, /static/admin/ needs a session, checked on the normalized path), '
    'code doc src/app/web/pages.md (#110). Docs: docs/ root holds guides only, docs/work/ for open '
    'process files (#109).",')

sub('"sessions": "No executor sessions open. ai-parser-ca closed. \'Limit resets\' is a Claude Desktop session, not ours."',
    '"sessions": "ai-parser-1e and ai-parser-d4 are the owner\'s sessions, not executors. '
    '\'Limit resets\' / dispatcher diagnostics are Claude Desktop sessions, not ours."')

sub('    "Owner decision 2026-10-24: very large modules',
    '    "Owner 2026-10-24: executors are background subagents (Agent tool, model sonnet, prompt '
    'saved to a file) or external models (DeepSeek) run by the owner; give a task to a live peer '
    'session only when the owner names it (a task once went to the owner\'s session by mistake).",\n'
    '    "Owner decision 2026-10-24: very large modules')

sub('{"id": "DEPLOY-126", "title": "Confirm v0.1.126 deploy green and the next nightly fetch/digest/archive (2026-10-25 logs) are fine after the pipeline split", "status": "todo"}',
    '{"id": "DEPLOY-127", "title": "Confirm the v0.1.127 deploy finished green and the next nightly '
    'fetch/digest/archive (2026-10-25 logs) are fine after the pipeline split (v0.1.126) and the '
    'static split (v0.1.127); no browser check (owner)", "status": "todo"}')

sub('Waiting for owner\'s go.", "status": "proposed"}',
    'Owner 2026-10-24: not now, smaller items first.", "status": "deferred"}')

json.loads(t)
p.write_text(t, encoding="utf-8")
print("ok")
```

Then check: `python3 -m json.tool docs/work/coordinator-state-2026-10-24.json > /dev/null && echo json-ok`.

## Step 4. Checks

```bash
git status --short
git diff --stat
PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest -q tests -k code_docs
```
Expected `git status --short`: exactly the three new `docs/archive/2026-10/prompt-web-static-*.md`
files (`??`) and ` M docs/work/coordinator-state-2026-10-24.json`. Nothing else. The pytest line
must end with `passed`. The full gate is not needed (docs only).

## Step 5. Commit, push, PR

```bash
git add docs/archive/2026-10/prompt-web-static-split-2026-10-24.md docs/archive/2026-10/prompt-web-static-finish-2026-10-24.md docs/archive/2026-10/prompt-web-static-auth-fix-2026-10-24.md docs/work/coordinator-state-2026-10-24.json
git commit -m "docs: coordinator state after v0.1.127, archive web static prompts" -m "Co-Authored-By: DeepSeek V4-Pro <noreply@deepseek.com>"
git push -u origin docs/after-127-20261024
gh pr create --base master --title "docs: coordinator state after v0.1.127, archive web static prompts" --body "Docs-only; full gate skipped (code_docs tests pass locally).

- Archive the three prompts of the web static split (#110).
- Coordinator state: master 3d38930, prod v0.1.127, release line, DEPLOY-127 replaces DEPLOY-126, B2 deferred by the owner, executor rule, sessions note."
```
Do not merge. Do not tag. Do not delete the main-folder copies in `docs/work/` (the coordinator does
that after the merge).

## Step 6. Report to the owner (paste as your final answer)

- PR URL;
- output of `git log --oneline -1` after the commit;
- output of steps 3 and 4 (`ok`, `json-ok`, `git status --short`, the pytest summary line);
- anything that did not go as written.
