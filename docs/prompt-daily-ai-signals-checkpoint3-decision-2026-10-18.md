# Checkpoint 3 decision for the 006 implementer (2026-10-18)

Coordinator review of PR #39 (head 1b49520): the direction, UI screenshots and deviations 1-4 are
accepted. Thank you for reporting the CI failure honestly. Two independent review sessions will now
review the PR; their findings come back to you as a separate message.

## Step 1 (now): resolve the conflict with master, then stop briefly

PR #39 is `CONFLICTING`: master gained PR #38 (auth for write methods on public API paths, publish
token; touched `src/app/web/app.py`, `docker-compose.prod.yml`, `README.md`, `docs/configuration.md`,
`docs/deploy.md`, `docs/troubleshooting.md`, settings, auth, workflows).

- `git fetch origin && git merge origin/master` (merge, not rebase: the branch is pushed and reviewed).
- Resolve conflicts keeping both behaviours. Check specifically: the new public
  `GET /api/news/daily-signals` must work through the new method-aware middleware (public for
  GET/HEAD only); add/keep a test that a non-GET to it returns 401 when auth is enabled.
- Full gate in a clean copy with PostgreSQL as in CI, `bash -n scripts/*.sh`, push.
- Reply with the new head SHA. Do not change anything else on the branch until review findings
  arrive (reviewers pin that SHA).

## Step 2 (approved, may run while the reviews run): Phase 7

- Phase 7 history validation on a scratch DB as planned, within the remaining $1.818 (hard stop).
  Never touch production.
- Report precision for the displayed 8 and for the full uncapped New list per day, recall, top-story
  membership precision, spend, terminal reasons.
- Record results in `dry-run.md` ("Phase B validation"), commit only docs; no code changes during
  the review window. If Phase 7 reveals a code bug, write it down and wait.
- Do not add or commit any `docs/daily-ai-signals-pr39-review-*.md` files; the coordinator handles
  them.

## Step 3 (later)

The coordinator sends consolidated review findings; you fix, re-run the gate and re-measure Phase 7
with `--recompute-only` (cached, $0), then stop for the final approval.
