# Prompt: remove the leftover MCP variables from deploy files (2026-10-21)

You work in the repository `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14 app
`ai-news-collector`, GitHub `Orlv-85/AI_PARSER`). Read `AGENTS.md` in the repository root first
and follow it. Follow the steps below exactly, in order. Do not change anything that is not
listed. If a step fails or something does not look like described here, stop and report; do not
improvise.

## Background

The MCP server was removed from the app in PR #68. The app no longer reads `AINEWS_MCP_AUTH_ENABLED`
or `AINEWS_MCP_AUTH_TOKEN` (its settings ignore unknown variables). Three deploy files still pass
these two variables to production. Remove them. These files are production-sensitive: change only
the lines named below.

## Step 1. Create a separate worktree and branch

Other sessions use the main folder. Never run `git add`, `git commit` or `git checkout` in
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` itself.

```bash
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch origin
git worktree add -b chore/remove-mcp-deploy-vars-20261021 ../AI_PARSER-mcp-deploy-vars origin/master
cd ../AI_PARSER-mcp-deploy-vars
```

All further work happens in `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-mcp-deploy-vars`.

## Step 2. Edit `.github/workflows/deploy-release.yml`

In the step that writes `/tmp/ai_news_auth.env` (around lines 280-315), delete exactly these five
lines and nothing else:

```yaml
          AINEWS_MCP_AUTH_ENABLED: ${{ vars.AINEWS_MCP_AUTH_ENABLED || 'false' }}
          AINEWS_MCP_AUTH_TOKEN: ${{ secrets.AINEWS_MCP_AUTH_TOKEN }}
```
```bash
          AINEWS_MCP_AUTH_TOKEN_ESCAPED="$(printf '%s' "${AINEWS_MCP_AUTH_TOKEN}" | sed 's/[$]/$$/g')"
```
```bash
            printf 'AINEWS_MCP_AUTH_ENABLED=%s\n' "${AINEWS_MCP_AUTH_ENABLED}"
            printf 'AINEWS_MCP_AUTH_TOKEN=%s\n' "${AINEWS_MCP_AUTH_TOKEN_ESCAPED}"
```

**Do not touch** the long `ssh ... grep -vE '^(AINEWS_AUTH_ENABLED|...|AINEWS_MCP_AUTH_ENABLED|AINEWS_MCP_AUTH_TOKEN|...)='`
line (around line 349). That regex removes these keys from the server `.env` on every deploy, so
keeping the two names there cleans the old values out of production. It must stay as it is.

## Step 3. Edit `.github/workflows/deploy-by-tag.yml`

The same five lines as in step 2 (around lines 62-63, 70, 85-86). Delete them. Again, do not touch
the long `ssh ... grep -vE '^(...)='` line (around line 125).

## Step 4. Edit `docker-compose.prod.yml`

Delete exactly these two lines (around lines 39-40):

```yaml
      AINEWS_MCP_AUTH_ENABLED: ${AINEWS_MCP_AUTH_ENABLED:-false}
      AINEWS_MCP_AUTH_TOKEN: ${AINEWS_MCP_AUTH_TOKEN:-}
```

## Step 5. Verify the result

```bash
git diff --stat
git grep -n "AINEWS_MCP_AUTH" -- .github docker-compose.prod.yml
```

Expected: `git diff --stat` shows exactly 3 files changed, 0 insertions, 12 deletions
(5 + 5 + 2). `git grep` shows only the two long `grep -vE` lines (one per workflow). If anything
else remains or more lines changed, fix it before going on.

Then run the checks (`venv1` lives in the main folder; run from the worktree):

```bash
actionlint .github/workflows/deploy-release.yml .github/workflows/deploy-by-tag.yml
docker compose -f docker-compose.prod.yml config --quiet
PYTHONPATH=src ../AI_PARSER/venv1/bin/python -m pytest -q -p no:cacheprovider tests/unit/test_settings.py
```

- `actionlint` may print warnings that already exist on master (shellcheck notes in other lines).
  Compare with `git stash; actionlint ...; git stash pop`: report only new warnings; there must be
  none caused by your change. If `actionlint` is not installed: `brew install actionlint`.
- `docker compose ... config --quiet` must exit 0; it only parses the file. If Docker is not
  installed, run instead
  `python3 -c "import yaml; yaml.safe_load(open('docker-compose.prod.yml'))"` and say which one you ran.
- The settings test must pass (it checks that the app still starts with the old keys present).

## Step 6. Commit, push, open the PR

```bash
git add .github/workflows/deploy-release.yml .github/workflows/deploy-by-tag.yml docker-compose.prod.yml
git commit -m "chore(deploy): stop passing the removed MCP auth variables

The MCP server was removed in PR #68. The deploy workflows and the production
compose file still passed AINEWS_MCP_AUTH_ENABLED / AINEWS_MCP_AUTH_TOKEN. The
.env strip regex keeps both names, so the next deploy removes their old values
from the server .env.

Docs-Skip: deploy files only; no covered code changed.

Co-Authored-By: <your model name> <noreply@example.com>"
git push -u origin chore/remove-mcp-deploy-vars-20261021
gh pr create --base master --head chore/remove-mcp-deploy-vars-20261021 \
  --title "chore(deploy): stop passing the removed MCP auth variables" \
  --body "Removes AINEWS_MCP_AUTH_ENABLED / AINEWS_MCP_AUTH_TOKEN from deploy-release.yml, deploy-by-tag.yml and docker-compose.prod.yml (MCP server removed in #68). The .env strip regex in both workflows still lists the two names on purpose: the next deploy deletes their old values from the server .env.

After merge and the next deploy the owner deletes the GitHub variable AINEWS_MCP_AUTH_ENABLED and the secret AINEWS_MCP_AUTH_TOKEN (Settings -> Secrets and variables -> Actions).

Checks: actionlint (no new warnings), docker compose config, tests/unit/test_settings.py."
```

Replace `<your model name>` with your real model name. Do **not** merge the PR. Do not create a
tag. Do not touch the server or GitHub settings.

## Step 7. Report

Reply with:
- the PR link;
- the output of `git diff --stat` and of the `git grep` from step 5;
- the result of each check (pass/fail, new warnings if any);
- anything that did not match this prompt.
