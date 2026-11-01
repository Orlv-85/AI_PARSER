# Prompt: fixes to PR #169 from review (2026-11-01)

Sent to the PR #169 implementer (same context). Push fix commits to `chore/deploy-sudoers-sample`.
Same rules as `prompt-sudoers-sample-2026-11-01.md`; test first (see each new check fail on a
mutation before relying on it).

Decided by the coordinator from the review:

1. Must fix: read `STAGE_DIR` and the default `UNIT_DIR` from `scripts/install_daily_timers.sh`
   instead of hardcoding them (or assert the script contains the two literals); a changed
   `STAGE_DIR` in the script must fail the test.
2. Guard against sudo calls the regex misses: every line of the two scripts that contains `SUDO` or
   `sudo` must either match the captured `^\s*\$SUDO ` form or be one of the known non-call lines
   (the two `SUDO=` assignments, comments); otherwise fail with the line. Mutations to show failing:
   literal `sudo -n systemctl restart foo`, `"$SUDO" x`, `true && $SUDO x`.
3. Clear failures for a malformed sample: assert a `deploy ALL=` line was parsed; assert every alias
   on it is defined (message names the unknown alias); a dropped trailing `\` should give a readable
   message, not a bare KeyError.
4. `scripts/install_daily_timers.sh:6-7`: comment-only change to point at
   `deploy/sudoers.d/ai-news-deploy`. No other change to the scripts.
5. Put back in `world.md` (Behavior or Decisions) the sentence that the install script has no
   `disable` path for the world timer and the switch is the way to turn it off.

Checks: ruff, scoped tests, `make lint PYTHON=...`, full pytest `-o addopts="" | tail -1`,
`check_code_docs.py`, `bash -n scripts/install_daily_timers.sh`. Update the PR body.

Report: commits, files, checks with counts, the mutations you ran and their failure messages.
