# Prompt: ARCHIVE-LOG-DUP - one summary line per night in daily-archive.log (2026-10-30)

Repo `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`. Read `AGENTS.md` first. Small code fix, one PR.

## Cause (already found, do not re-investigate)

`ai-news archive capture` logs `archive_capture_finished` through `setup_json_logging` (a
`logging.StreamHandler`, i.e. stderr) and then the CLI also prints the same summary with
`typer.echo` (stdout), see `src/app/cli/main.py` `archive_capture_command`. The systemd unit
(`scripts/install_daily_timers.sh`) appends both stdout and stderr to `logs/daily-archive.log`,
so every night the summary is written twice.

## Fix (decided, keep it this narrow)

Only the nightly job drops the CLI's stdout copy; the CLI itself keeps printing (manual operators use it).

1. `scripts/run_daily_archive_job.sh`: add `>/dev/null` to the `docker compose ... ai-news archive
   capture --max-seconds 1500` command (before the `||`), with a one-line comment:
   `# The summary is already logged on stderr; drop the CLI's stdout copy so the log has it once.`
   Do not change anything else in the script (lock, timeouts, exit 0, stderr messages).
2. `tests/unit/test_deepseek_digest.py`: in `_archive_job`, make the fake `docker` print a line to
   stdout for the archive capture call, e.g.
   `case "$*" in *"archive capture"*) echo summary-stdout; exit "$CAPTURE_EXIT";; esac`.
   In `test_archive_job_script_is_isolated` add `assert result.stdout == ""` for the ok case and
   the timeout case. Keep all existing asserts.
3. Code doc `src/app/core/archive/capture.md` (covers the script; CI fails without it):
   - in the Behavior rule "The capture ends with one `archive_capture_finished` JSON log line, which
     the CLI also prints:" keep it, and in the rule about `run_daily_archive_job.sh` add: "it sends
     the CLI's stdout to /dev/null, so `logs/daily-archive.log` holds the summary once (the log line
     on stderr)." (`Tests: test_archive_job_script_is_isolated` is already there.)
   - add one Decisions line: "The nightly job, not the CLI, drops the stdout summary: operators
     running `archive capture` by hand still see it."
4. Bookkeeping in the same PR:
   - `docs/backlog/coordinator-todo.json`: item `PERIOD-1029` -> `"status": "done"`,
     `"done": "2026-10-29"`, `"result": "Night of 2026-10-29 on v0.1.139: fetch (152 sources, 178 new,
     7 errors), digest for 2026-10-28 (84 in scope, 75 published), archive (coverage 97.1%, gave_up 1)
     green; period-signals step: week 2026-10-19 unchanged, brief cached, month skipped, $0."`;
     item `ARCHIVE-LOG-DUP` -> `"status": "in_progress"`, add `"note": "Fix in PR <this PR>; check
     the log after the next deploy."` (fill in the PR number after `gh pr create`, amend + force-push
     the branch is NOT allowed - use a second commit). Set top-level `"updated": "2026-10-30"`.
     Keep JSON formatting (2-space indent, same key order style).
   - `git mv` is not possible (the file is git-ignored): copy
     `docs/work/prompt-coordinator-next-2026-10-29.md` and this prompt file
     `docs/work/prompt-archive-log-dup-2026-10-30.md` to `docs/archive/2026-10/` and add them.

## Steps

```
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch origin
git worktree add ../AI_PARSER-archive-log-dup -b fix/archive-log-dup-20261030 origin/master
cp docs/work/prompt-coordinator-next-2026-10-29.md docs/work/prompt-archive-log-dup-2026-10-30.md \
   ../AI_PARSER-archive-log-dup/docs/archive/2026-10/
cd ../AI_PARSER-archive-log-dup
```

Do all edits in the worktree only (never `git add`/commit in the main folder). Use
the Edit tool for edits.

## Checks (in the worktree)

```
bash -n scripts/run_daily_archive_job.sh
PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest -p no:cacheprovider -o addopts="" tests/unit/test_deepseek_digest.py -k archive_job | tail -1
PYTHONPATH=src ../AI_PARSER/venv1/bin/python -m ruff check src tests
PYTHONPATH=src ../AI_PARSER/venv1/bin/python scripts/check_code_docs.py
make lint PYTHON=../AI_PARSER/venv1/bin/python
PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest -p no:cacheprovider -o addopts="" | tail -1
```

(Without `PYTHONPATH=src` the venv imports the main folder's code.)

## Commit and PR

Commit message:

```
fix: write the nightly archive summary once in daily-archive.log

The archive job sends the CLI's stdout to /dev/null; the summary stays as the
archive_capture_finished log line on stderr. Also marks PERIOD-1029 done and
archives the coordinator prompts.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
```

```
git push -u origin fix/archive-log-dup-20261030
gh pr create --base master --title "fix: write the nightly archive summary once" --body "<what changed, checks run with their last lines>

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

Do not merge, tag or touch prod.

## Report

PR URL, `git diff --stat origin/master`, last line of each check command, anything that did not go
as described.
