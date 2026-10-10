# Production activation of semantic admission

Verified at: 2026-10-10 21:55 UTC.

## Activation

- User explicitly authorized enabling JEV for ordinary collection of new candidates.
- Production image: `ghcr.io/orlv-85/ai-parser:v0.1.77`.
- Deployed commit: `834c48db87b3687a7fae3c5d046e98ea32602a57` (merged PR #13).
- Migration `f31a640c9b33` was already applied before activation.
- Server settings now include `AINEWS_SEMANTIC_ADMISSION_ENABLED=true`,
  `AINEWS_JEV_ENABLED=true`, `AINEWS_WEEKLY_V2_ENABLED=false`.
- Recreated only app, using its existing image. Database and proxy were not recreated.
- Restored weekly-cron disablement: deployment had reinstated one active entry;
  activation commented that entry, leaving zero active weekly jobs.
- GitHub repository variable `AINEWS_WEEKLY_V2_ENABLED` remains `false`.
- Private rollback copies of server .env and crontab:
  `/opt/ai-news/backups/semantic-admission-enable-20261010T213941Z/`.

No provider secrets are included in this report.

## First ordinary fetch cycle

Run ID: `20261010214029`.

Started at approximately 21:40 UTC; completed before 21:55 UTC.

| Metric | Result |
| --- | ---: |
| Enabled sources | 152 |
| Fetched candidates (not necessarily unique) | 3454 |
| New articles stored | 846 |
| Semantic rejects | 437 |
| Insufficient-evidence decisions | 186 |
| Duplicates counted | 949 |
| Source acquisition errors | 6 |
| Not-modified sources | 39 |
| Semantic screening paused | 0 |

Protected server log:
`/opt/ai-news/logs/semantic-admission-first-cycle-20261010T214027Z.log`.

The cycle used real JEV decisions. It did not invoke DeepSeek digest publication
or the paid weekly worker. No historical-date backfill, cleanup, or deletion ran.

## Final verification

- Effective container settings: semantic admission true, JEV true, weekly v2 false.
- Articles before the cycle: 8300; after the cycle: 9146. Increase equals 846.
- Durable ledger: 846 accept, 437 reject, 186 unresolved, 1366 pending,
  253 settled placeholders.
- The 1366 pending candidates are still awaiting processing in later ordinary
  cycles. Completion of this cycle does not mean every discovered candidate was
  evaluated. Existing early-stop/cap behavior and temporary acquisition failures
  can defer candidates. No additional manual run was started to drain the ledger.
- Collection status: paused false, message null.
- Health endpoint: status ok.
- Active weekly-cron entries: 0.

## Meaning of collection scope

New means not already stored in articles, rather than published today. Existing
articles are skipped, without semantic reclassification or deletion. Cached
rejections/unresolved decisions are reused until sent evidence or model/policy/
prompt version changes. Unchecked candidates can be retried in ordinary cycles.

There is no fixed publication-date window. RSS exposes its current entries;
HTML reads the current listing with an existing limit of up to 50 candidate links
per source. Current listings can contain older publications.

The daily DeepSeek digest is a separate existing process; it was not run as part
of activation. Weekly stays disabled. At activation time deploy_prod.sh installed
weekly cron by default, causing the manual disablement recorded above. The
deployment policy introduced alongside this report enforces JEV/admission on,
weekly v2 off, and AINEWS_WEEKLY_CRON_ENABLED=0 for both deployment workflows.
