# Prompt: sudoers sample in the repo and a test that checks it (2026-11-01)

You implement one small PR in `ai-news-collector` (`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`).
Report in English. Do not merge, tag or deploy; no ssh; no paid calls.

## Why

The deploy user `deploy` is not root. `/etc/sudoers.d/ai-news-deploy` on the server allows exact
commands only, and root maintains it by hand. On 2026-11-01 the W4 world timer was added to
`scripts/install_daily_timers.sh` without the matching sudoers lines; the review caught it, and the
coordinator added the lines on the server by hand (owner yes). Goal: the repo holds the server file
as a sample, and a test fails in a PR when a script's sudo call has no exact matching line.

## Rules

- Own isolated worktree from `origin/master` (`git fetch origin` first). Never edit, commit or pull
  in `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` itself. Python:
  `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python`; pytest with
  `-o addopts="" ... | tail -1`.
- Read `AGENTS.md` first. Test first: write the failing test, see it fail for the expected reason,
  then the smallest change. Use the `ub-mode` skill (its "Repository rules come first" section
  applies). Treat deploy scripts as production-sensitive: do not change what they run.

## The server file as of 2026-11-01 (exact; put it in the repo verbatim)

```
# Root calls made by scripts/deploy_prod.sh and scripts/install_daily_timers.sh. Exact arguments only.
Cmnd_Alias AINEWS_UNITS = \
  /usr/bin/install -m 0644 /var/tmp/ai-news-units/ai-news-daily-archive.service /etc/systemd/system/ai-news-daily-archive.service, \
  /usr/bin/install -m 0644 /var/tmp/ai-news-units/ai-news-daily-archive.timer /etc/systemd/system/ai-news-daily-archive.timer, \
  /usr/bin/install -m 0644 /var/tmp/ai-news-units/ai-news-daily-digest.service /etc/systemd/system/ai-news-daily-digest.service, \
  /usr/bin/install -m 0644 /var/tmp/ai-news-units/ai-news-daily-digest.timer /etc/systemd/system/ai-news-daily-digest.timer, \
  /usr/bin/install -m 0644 /var/tmp/ai-news-units/ai-news-daily-fetch.service /etc/systemd/system/ai-news-daily-fetch.service, \
  /usr/bin/install -m 0644 /var/tmp/ai-news-units/ai-news-daily-fetch.timer /etc/systemd/system/ai-news-daily-fetch.timer, \
  /usr/bin/install -m 0644 /var/tmp/ai-news-units/ai-news-daily-world.service /etc/systemd/system/ai-news-daily-world.service, \
  /usr/bin/install -m 0644 /var/tmp/ai-news-units/ai-news-daily-world.timer /etc/systemd/system/ai-news-daily-world.timer
Cmnd_Alias AINEWS_SYSTEMD = \
  /usr/bin/systemctl daemon-reload, \
  /usr/bin/systemctl enable --now ai-news-daily-fetch.timer ai-news-daily-digest.timer, \
  /usr/bin/systemctl enable --now ai-news-daily-archive.timer, \
  /usr/bin/systemctl enable --now ai-news-daily-world.timer, \
  /usr/bin/systemctl disable --now ai-news-daily-fetch.timer, \
  /usr/bin/systemctl disable --now ai-news-daily-digest.timer
deploy ALL=(root) NOPASSWD: AINEWS_UNITS, AINEWS_SYSTEMD
```

## Steps

1. Put the file at `deploy/sudoers.d/ai-news-deploy` (or the name that fits `deploy/`), with a
   header comment: source of truth for the server file; root applies it by hand
   (`visudo -cf`, `install -m 0440`); a deploy never changes it.
2. Test (e.g. `tests/unit/test_deploy_sudoers.py`): parse the sample (aliases with `\` continuation,
   comma lists) and derive every sudo call that `scripts/install_daily_timers.sh` and
   `scripts/deploy_prod.sh` make with `$SUDO` / `sudo -n` (unit files from the generated unit
   names, `UNIT_DIR`/`FINAL_DIR` paths as the scripts set them for prod); assert each is in the
   sample exactly, and that the sample has no command the scripts never make (stale lines). Prefer
   running the install script in a temp dir with a fake `sudo` that records its arguments, if the
   existing timer tests already do something similar (look at `tests/unit/test_daily_timers.py`);
   otherwise parse. Show in the report that removing one world line from the sample fails the test.
   Replace or merge the W4 test `test_world_sudo_calls_are_documented` if it overlaps; say which.
3. `docs/deploy.md`: point the sudoers section to the sample file instead of listing lines inline
   (keep one sentence on how root applies it). No Behavior repeated.
4. Checks: ruff, scoped tests, `make lint PYTHON=...`, full pytest, `scripts/check_code_docs.py`.
5. PR: commit messages end with a `Co-Authored-By:` line naming your model; `gh pr create --base
   master`, title `chore(deploy): sudoers sample and a test that checks it against the scripts`;
   body lists changes and checks with counts, ends with
   `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Report (final message)

PR link, branch, worktree path; files; checks with counts; the mutation check; anything decided by
you (one line each).
