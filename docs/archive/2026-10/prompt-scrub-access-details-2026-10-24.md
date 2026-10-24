# Prompt: remove server access details from public docs (2026-10-24)

Executor: DeepSeek, run by coordinator `ai-parser-ba`; the coordinator reviews and merges. Docs
only. Do every step exactly; no other edits.

Repo: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (main folder). Never run `git add`, `git commit`,
`git checkout` or `rm -rf` in the main folder. Work only in the worktree from step 1.

## Step 1. Worktree

```bash
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch -q origin
git worktree add -b docs/scrub-access-20261024 ../AI_PARSER-wt-scrub origin/master
cd ../AI_PARSER-wt-scrub
```

## Step 2. Edits

Save as `/tmp/scrub_access.py`, run `python3 /tmp/scrub_access.py` from the worktree root. It must
print `ok`. If an assert fails, stop and report; do not edit by hand.

```python
import json
import pathlib


def sub(path, old, new):
    p = pathlib.Path(path)
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (path, old[:60])
    p.write_text(t.replace(old, new), encoding="utf-8")


ctx = "docs/archive/2026-10-10-12/session-context-2026-10-10.json"
sub(ctx,
    '"ssh": "root@5kzt.l.time4vps.cloud; private SERVER_PASSWORD in local .env. Never print credentials/full environments; use sshpass -e.",',
    '"ssh": "Access details are private (not in the repo). Never print credentials/full environments.",')
json.loads(pathlib.Path(ctx).read_text(encoding="utf-8"))

plan = "docs/archive/2026-10/plan-offsite-backups-2026-10-21.md"
sub(plan, "over SSH (sshpass, root). No server", "over SSH. No server")
sub(plan, "(same sshpass login\n   as today;", "(same SSH login\n   as today;")
sub(plan, "The runner already has root on the server (`SERVER_PASSWORD`), so seeing the",
          "The runner already has full access to the server, so seeing the")
print("ok")
```

## Step 3. Checks

```bash
git diff --stat
git grep -nE "sshpass|SERVER_PASSWORD|root@" -- docs specs
```
`git diff --stat` must show exactly the two files. The `git grep` must print only lines from
`docs/archive/2026-10/prompt-digest-waits-for-collection-2026-10-22.md` (secret names, same as in the
public workflows; leave it), or nothing. Report the output either way.

## Step 4. Commit, push, PR

```bash
git commit -am "docs: remove server access details from archived records" -m "Co-Authored-By: DeepSeek V4-Pro <noreply@deepseek.com>"
git push -u origin docs/scrub-access-20261024
gh pr create --base master --title "docs: remove server access details from archived records" --body "Docs-only; full gate skipped.

Owner request: login user, password location and SSH tool of the prod server are not described in public docs. Two archived files edited; history is not rewritten."
```
Do not merge.

## Step 5. Report (final answer)

PR URL, `git log --oneline -1`, outputs of steps 2 and 3, anything that did not go as written.
