# Prompt: review of PR #169, sudoers sample and check test (2026-11-01)

You review PR #169 (`chore/deploy-sudoers-sample`). You did not write it. **Read-only: no commits,
pushes, merges, PR comments, ssh or paid calls.** Report in English.

Read: `gh pr view 169`, `gh pr diff 169`, `gh pr checks 169`; the task
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/prompt-sudoers-sample-2026-11-01.md`;
`AGENTS.md`; `scripts/install_daily_timers.sh`, `scripts/deploy_prod.sh` on the PR branch (use your
own `git worktree add --detach` under your scratchpad; remove it at the end).

Coordinator already verified: the sample's non-comment lines equal the server file byte for byte
(2026-11-01); the test passes clean, fails when a script gains a new sudo call (assertion), and
fails when the last world line is removed from the sample (but with `KeyError: 'AINEWS_SYSTEMD'`,
because the alias continuation breaks).

Check:
1. The parser of the scripts finds every `$SUDO` / `sudo -n` call in both scripts, including loops
   and variables; would a sudo call written another way (for example `sudo -n` literal, a call in a
   function, a new unit name) be missed silently? Name concrete misses.
2. The parser of the sample: continuation lines, comments, aliases; does a malformed sample give a
   clear failure or a confusing one (see the KeyError above); suggest the smallest fix if confusing.
3. Hardcoded STAGE_DIR / FINAL_DIR match what the scripts use in production.
4. `docs/deploy.md` and `world.md` edits; the removed W4 test is fully covered by the new one; the
   `Docs-Skip` line in the commit is justified.
5. Run `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/pytest -q -o addopts="" tests/unit/test_deploy_sudoers.py tests/unit/test_daily_timers.py | tail -3` and ruff.

Report: verdict (merge / merge after fixes / do not merge); findings with file:line, failure, one-line
fix; must fix vs nice to have; checks run.
