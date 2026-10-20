# Third independent review: Daily AI Signals Phase A, revision 3

Review date: 2026-10-18. Branch: `feat/006-daily-ai-signals` (working tree; revision 1 is commit
`22f3b67`). `plan.md`, `tasks.md`, `spec.md` and `dry-run.md` refer to
`specs/006-daily-ai-signals/`; line numbers are working-tree lines.

Pass 1 was written before reading review 1 or review 2 and frozen in
`tmp/runs/phase-a-review3-20261018/pass1-findings.md`, SHA256
`ad358c6fceccae2348a67b3a6e1923a851b1da66357c4ec3ebd3df2440e31466` (frozen 2026-10-18 08:23 UTC).
The plan's own "Review Response" table names S01-S15 and was visible during pass 1, as the prompt
required reading the plan. Pass 2 added no new findings. It only mapped T-ids to S/R items (sections 5-6).

## 1. Verdict: rework (narrow)

Revision 3 fixes the structural problems of revision 2. Reconciliation is a real pure function:
200 shuffles give identical output. Full recompute replaces the fingerprints. The ledger, job budget,
day states and task graph are now concrete and consistent. Two design rules still fail on real data,
and neither can be repaired inside a task without a design decision:

- Decision 2 makes identity depend on how vendors are spelled. On the plan's own fixtures this
  breaks the pinned Gemini 4 Argon 10-13 story (T01) and silently invalidates stored merge and alias
  overrides (T03). The vendor-strip step makes the resolution key depend on whether the vendor was
  named (T04).
- Decision 4's evidence-version rule drops all history at the next extraction version bump (T02).

The rework is limited to these rules plus the matching tests. Everything else is minor or a nit that
an implementer can fix inside the listed tasks.

## 2. Pass-1 findings (most severe first)

| ID | Sev | Area | Location | Evidence | Recommended change |
| --- | --- | --- | --- | --- | --- |
| T01 | major | Identity vs clustering on real data | `plan.md:328-333`, `tasks.md:71` | Gemini 4 Argon has vendor keys `google` (15 mentions) and `googledeepmind` (2 mentions, first seen 10-15), plus 3 mentions with no vendor. With evidence up to 10-14, the 10-13 top story is 5 publishers / 7 articles. With evidence up to 10-16, the automatic full recompute moves the vendor-less mentions to `auto:artifact:gemini4argon:?`. Edges from articles 98158 and 98265 are lost, so the stored 10-13 story is rewritten to 4/5 + 2/2 (`probe_gemini.out`). T1.4's test-first expectation (7/5) cannot pass under the written rules. The same mechanism splits counts for Rising and spikes. It can also put an established model in New: the `googledeepmind` entity is first seen on 10-15, and the family rule rejects it because the vendor keys differ. The 5 fixture days contain 14 groups with >= 2 vendor keys (probe A4). Most differ by parent vs sub-org or by spelling: Google vs Google DeepMind / Google Cloud, Black Forest Labs vs BFL, Epic vs Epic Games. | Make vendor keys equivalent before grouping: a token-prefix / sub-org rule (`googledeepmind` ~ `google`) plus a small vendor-alias table. Attach vendor-less mentions to the dominant vendor instead of `?` when the vendors are equivalent. Build clustering edges on `(type_group, base_key)` rather than `entity_key`. Pin the Gemini case at full 5-day evidence in T1.2/T1.4. |
| T02 | major | Evidence across extraction versions | `plan.md:320-321`, `plan.md:415-419`, `tasks.md:296` | The evidence set is "rows of the current extraction version + older-version rows of deleted articles". After a version bump, every existing history article that has not been re-extracted contributes nothing. first_seen collapses onto newly extracted days, which floods New. Window counts vanish. History days fall below 90% `extracted_ok` and become incomplete, and "History: N days" drops. The automatic full recompute at the end of the next daily run then rewrites up to 400 stored reports in that state. Recovery is capped at 200 calls / $0.50 per run, while re-extracting 75 days costs about $2. T7.2 allows a prompt change "with `EXTRACTION_VERSION` bump" inside a $2.50 budget that one 75-day backfill (~$1.93-2.02) nearly exhausts. | For each existing article, use evidence from its newest version that has an `ok` extraction, falling back to older versions. Count coverage on the same basis. Re-extraction then upgrades evidence instead of deleting it. Add a test: bump the version, extract only D, and check that first_seen and history reports are unchanged. In T7.2, run v3 on the 5 target days first (~$0.35) and review. Backfill history only after the prompt is frozen. |
| T03 | major | Overrides keyed on derived keys | `plan.md:322-327`, `plan.md:338`, `plan.md:358-362` | `merge` (source and target `entity_key`) and `alias` (target `entity_key`) point at `auto:` keys that change as evidence grows. A key ending in `:` becomes `:<vendor>` when a vendor is first named, and becomes `:?` when a second vendor appears. Probe B2: 8 auto keys that exist with evidence up to 10-14 no longer exist with evidence up to 10-16 (Codex, Claude Code, Claude Haiku 5.5, Waymo, ...). A stored merge then silently stops matching. A redirect target that is no longer produced becomes a stale entity holding only the redirected mentions. "Overrides survive re-extraction" is true only for `split`. | Overrides should select mentions by resolution key (`type_group`, `base_key`, optional vendor key), never by `auto:` key. Convert targets to stable `manual:<n>` keys when the override is created. Add a T1.2/T3.5 test where a merge survives a vendor appearing later. |
| T04 | major | Vendor-dependent `base_key` | `plan.md:296-299`, `plan.md:344-350` | Vendor-strip runs only when the mention carries a vendor, so one surface name gets two resolution keys. "Microsoft's Decision-1" gives `decision1` with a vendor and `microsoftdecision1` without one. "Reflection Beam" gives `beam` / `reflectionbeam`. "NVIDIA Nemotron 3.5 Bolt 74B" gives `nemotron3.5bolt74b` / `nvidianemotron3.5bolt74b`, and the family relation then also fails (vendor keys `''` vs `nvidia`). The plan's Decision-1 claim ("share `name_key`") is beside the point, because grouping uses `base_key`. 10-10 is not in the fixtures, so the claim is unverified. In today's fixtures every Beam, Nemotron and Decision-1 mention has a vendor (probe B), so these cases pass only conditionally. 5 vendor-less prefixed mentions miss their stripped entity (probe A5). | Strip a leading token run that equals any `vendor_key` seen in the same type group's evidence; this is still a pure function of the full evidence set. Infer the vendor from it. Add the Decision-1 10-10/10-12 and "Reflection Beam" (no vendor) vs "Beam" (Reflection) pairs to T1.1/T1.2. |
| T05 | minor | Deleted-article evidence; id reuse | `plan.md:408-413`, `plan.md:429-433`; `src/app/storage/legacy_cleanup.py:257-258` | Evidence of deleted articles is never touched. Besides retention prune, `legacy_cleanup` deletes non-news articles by id. Their evidence keeps suppressing New and counting in history, and no command removes it. The SQLite `articles` table has no AUTOINCREMENT (`data/ai_news.db` has no `sqlite_sequence`). Deleting the highest id therefore lets the next article reuse it. That article's evidence write then deletes the retained rows, and the old article's older-version rows leave the evidence set. PostgreSQL is not affected. | Store `url_canonical_hash` in `signal_mentions` and define "exists" as an `(id, hash)` match. Add `daily-signals-entities purge-evidence --article ID`. Mention cleanup deletes in OD6. |
| T06 | minor | Replacement unit undefined | `plan.md:408-413` | It is not stated whether a membership change replaces `(scope_day, article)` rows and a re-extraction replaces all rows of the article. | Specify both units and test each. |
| T07 | minor | Lifetime 4-POST limit | `plan.md:212-215` | `transient` overloads (cost 0) and content updates count toward the per-(article, version) limit. Pending order is deterministic, so the same first articles burn attempts on every outage day. After 4 attempts they are skipped permanently, and `--retry-skipped` is refused. | Exclude `transient` from the article limit, or key the limit by `(article, version, content_hash)`. Add an operator reset. |
| T08 | minor | Payload hash canonical form | `plan.md:421-427`, `plan.md:649` | `generated_at`, float formatting and dict order are not excluded or canonicalized, so every run could rewrite every report. | Hash `encoded(payload)` with `generated_at` removed and floats rounded. Pin this in T1.5 (T3.3 already expects a rerun to write 0 reports). |
| T09 | minor | Recompute cost claim | `plan.md:425-427` | At a synthetic 400-day scale, pure reconcile takes 0.5 s and clustering about 12 ms per day (`probe_scale.out`), so the claim holds for compute. The estimate leaves out loading about 150k evidence rows, upserting about 70k `ai_entities` rows and rewriting `signal_mentions.entity_key` on every run. | Write only changed assignments and entities. Measure a synthetic year in T2.5. |
| T10 | minor | Readiness date | `plan.md:25-27` vs `plan.md:447`; `tasks.md:305` | "All 14 days comparable" with comparable_from 2026-10-10 puts the earliest Rising/Cooling day at 2026-10-23. The window `prev` for 10-22 starts on legacy 10-09. | Use 10-23, or allow a non-comparable day in `prev` explicitly. |
| T11 | minor | Spike baseline | `plan.md:446` | Live digests (GET): 10-10 has 7 items, 10-11 has 1 and 10-17 has 14, against 56-92 on busy days. These still count as complete trailing days. Early spikes therefore reduce to ">= 3 articles and >= 2 publishers". Spikes are not volume-adjusted; Rising is. | Set a minimum item count per trailing day or normalize spikes by volume. List it as a T8.2 item. |
| T12 | minor | `partial` for any unmatched item | `plan.md:460-462` | Unmatched URLs count in `items`, so a 98% match rate makes a day `partial` forever even though it is `complete` (>= 90%). Status precedence then hides `building_history`. | Report `partial` only when the day is not complete. Otherwise keep the coverage line as a note. |
| T13 | minor | OD1 vs family regex | `plan.md:35`, `plan.md:301` | OD1 says the first public release after a preview qualifies as New, but it also lists preview as packaging. The regex includes `preview|beta`, so a GA "X" after a known "X Preview" is suppressed. `E4B` / `16E` size tokens are not treated as packaging. | The owner chooses. Extend the regex for effective-size tokens. |
| T14 | minor | Job script edges | `plan.md:757`, `plan.md:762`, `plan.md:770` | jobsim run: `cd scripts && sh ./job.sh 2026-10-03` fails with "No such file or directory" (exit 127), because the re-exec uses `"$0"` after `cd` to ROOT. A locked entry without START runs publish, then fails with "unbound variable" (exit 1 after a successful publish). Busybox `timeout` has no `--kill-after`. `$limit` word splitting works (argc 17). Same-date `--name` reruns collide only with an orphaned container, which the `rm -f` fallback covers. | Re-exec `"$SCRIPT_DIR/$(basename "$0")"`. Use `${AINEWS_DAILY_JOB_START:-$(date +%s)}`. Use `-k 30`. In T6.1, build a PATH without `timeout`: on merged-/usr runners `/bin/timeout` exists. |
| T15 | minor | Attempt deadline coverage | `plan.md:221-223` | The 60 s check runs per body chunk. Waiting for headers is bounded only by per-read timeouts, and DNS is not bounded by httpx. Caps cannot be exceeded and the outer `timeout` still bounds the job, but the 95 s reserve can be. | Add a watchdog that closes the response at 80 s after the POST starts. Test a delayed-header fake. |
| T16 | nit | `?` entity eligibility | `plan.md:331-333` | Not stated whether the `?` entity is eligible for New, Rising or spikes. | Suggest: excluded from New, counted, listed in `suspects`. |
| T17 | nit | Key forms | `plan.md:290`; `tasks.md:38-39` | Tokens are joined without a separator, so "Qwen 3 8B" == "Qwen 38B". The plan writes `family_key` joined; tasks write it space-joined. | Join with a separator between adjacent digit-led tokens. Use one representation. |
| T18 | nit | Stale wording | `dry-run.md:207`; `dry-run.md:232` vs `plan.md:272`; `plan.md:15-16` vs `plan.md:423` | dry-run.md:207 still says "average-link grouping (plan revision 2)". The cost upper bound is $2.03 in dry-run.md vs $2.02 in plan.md. The Summary says "all comparable days", but recompute is bounded to 400 days. | Fix the wording. |
| T19 | nit | "No production effect" | `plan.md:843` vs `plan.md:732` | Phase 5 adds a visible "not available" line to the public `/`. | Say so in the rollout, or hide the block when no report exists. |
| T20 | nit | Prune outside the host lock | `scripts/deploy_prod.sh:241` vs `plan.md:797` | A CASCADE delete racing a signals write becomes "DB error -> exit 1". Only 800-day-old articles are affected, so this is benign. | Note it in `docs/daily-signals.md`. |

Checked and fine:

- Reconcile is permutation-invariant.
- Strict majority reproduces `cluster-avg-strict.txt`.
- The plan's stopwords equal `analyze.py` `TITLE_STOP`.
- `./data` is mounted, so the ledger persists across `run --rm`.
- `priced_usage` and the byte reservation are conservative (`ensure_ascii` bytes >= tokens).
- `BEGIN IMMEDIATE` check-and-insert is atomic, provided the connection uses `isolation_level=None` with a busy timeout.
- Migration head `a42b750d0c44` is correct.
- The public digest API returns the same shape for an absent day and an empty one.
- The DeepSeek keep-alive behavior makes the per-chunk deadline the right tool.

## 3. Probe results

All offline. Scratch directory: `tmp/runs/phase-a-review3-20261018/`. Nothing in
`tmp/daily-signals-dryrun/` was written.

**H - reproduction.** `V2=1 LINK=avg STRICT=1 SHOW_MEMBERS=1 LEXICAL=0 venv1/bin/python -I
probe_h_repro.py tmp/daily-signals-dryrun h_repro_strict.txt` loads `analyze.py` with `runpy`
(`load`, `resolve`, `snapshot`; `main` is never called). The diff against `cluster-avg-strict.txt`
shows only the diagnostic "POSSIBLE SPLIT" lines, which the probe does not print. **Match: yes**
(revision-1 identities). `cluster-avg.txt == cluster-avg-strict.txt`.

**A/B - revision-3 rules** (`probe_reconcile.py fixtures cluster-avg-strict.txt`,
`probe_reconcile.out`). The probe implements the written normalization, stoplist, company rule,
vendor-strip, family regex and `reconcile`. Assumption: keys are built from `canonical_name`, which
the plan does not specify.

- 1825 mentions, 369 articles, 1200 entities, 2 `needs_review`.
- A1 permutation invariance over 200 shuffles: **yes**.
- A2 growth: mentions whose `entity_key` differs from the final value after each day prefix were
  8/26/22/3 in forward order and 11/16/8/3 in backfill order. The final result is identical; the
  intermediate keys are not stable.
- A3 transitions after each added day:
  - Gemini moves from `:` to `:google`.
  - Qwen 3.8 27B moves from `:` to `:alibaba`.
  - After 10-15, Gemini 4 Argon moves from `:google` to `:?` (3 mentions), and Claude Code, Codex and
    Claude Haiku 5.5 move from `:` to `:<vendor>`.
- A4: 14 groups with >= 2 vendor keys (list in output).
- A5: 5 vendor-less prefixed mentions miss their stripped entity.

Real cases, at full fixture evidence:

| Case | Result |
| --- | --- |
| Beam | All three 10-16 forms -> `auto:artifact:beam:reflection`. Legacy 10-05 joins only if its extraction names the vendor or uses the bare name. |
| Nemotron 74B (10-13) vs 74B-A9B 24GB (10-15) | Separate entities, family `nemotron3.5bolt`, vendor `nvidia` -> family. Suppression OK while both mentions carry the vendor. |
| Nemotron E4B 4GB | Not family (regex gap). |
| Microsoft-Decision-1 (10-12, 10-15) | `decision1:microsoft`. A vendor-less 10-10 mention would be `microsoftdecision1`, a separate entity. |
| pplx v1 vs v1.1 | Distinct entities, not family. |
| Bee | `org:bee:amazon`. Bee Frontier/Eclipse/Pro become `frontier:bee`, `eclipse:bee`, `pro:bee`. No cross-group variant. |
| Muse Spark / 1.3 / Open | Distinct. Vendor-less "Muse Spark Open" is absorbed by Meta. |
| Glimpse 10-16 | `artifact:glimpse:elorian`. A 10-06 company would be `org:glimpse:`, a separate entity (fixed). |

**B2 / clustering with revision-3 identities.** Top stories match the reference on 10-12, 10-14,
10-15 and 10-16. On 10-13 they do not: 4/5 + 2/2 instead of 5/7. With identities from evidence up to
10-14, 10-13 is 5/7 again (`probe_gemini.out`). Cause: the `?` move from T01. Ordering by
`article_id` differs from ordering by fixture key on all 5 days, without changing any story.

**Scale.** `probe_scale.py` replicates the fixtures to 400 days (146k mentions, 73k entities):
reconcile 0.52 s, clustering 4.7 s in total.

**Job script.** `jobsim/` extracts the plan's script with fake `docker`, `flock` and `timeout`:

- Publish ok -> two calls. The second is `timeout --kill-after=30 2700 ... --name
  ai-news-signals-2026-10-03 ... --max-seconds 2520`, exit 0.
- The relative-path and missing-START failures are reported in T14.

## 4. Internal consistency (I)

1. Earliest Rising/Cooling day: `plan.md:27` says 10-22, but the rule at `plan.md:447` gives 10-23.
   `tasks.md:305` uses 10-22..30.
2. Decision-1 claim: `plan.md:347-348` says the two names "share `name_key`", but grouping is by
   `base_key` (`plan.md:328`).
3. `plan.md:344` says identities were "verified against fixtures/digests by the review", while
   `dry-run.md:32-34` and `report:88-89` say they were not re-run. Probe A/B shows the claim holds
   only conditionally (T04) and not for Gemini (T01).
4. `tasks.md:71` (Gemini 10-13 = 7/5) contradicts `plan.md:328-333` combined with Decision 3 at full
   fixture evidence (T01).
5. `tasks.md:37-39` uses a space-joined `family_key` ("nemotron 3.5 bolt"); `plan.md:299-302` uses
   the joined form for keys.
6. `dry-run.md:207` still says "average-link grouping (plan revision 2)", while `plan.md:366` uses
   strict majority. `dry-run.md:232` gives $1.93-2.03; `plan.md:272` gives $1.93-2.02.
7. `plan.md:15-16` says "all comparable days", while `plan.md:423` bounds recompute to 400 days.
8. `plan.md:843` says "without production effect", while `plan.md:732` puts a visible unavailable
   line on `/`.
9. `plan.md:797` says "All writers run under the host lock", but `scripts/deploy_prod.sh:241` runs
   prune without it (cascade writer).
10. `plan.md:35` (OD1, preview qualifies) contradicts `plan.md:301` (`preview` is packaging).

Consistent: the approval rule (`plan.md:6`, `tasks.md:6`), 7 tables, 6 settings, the caps and flags
in the CLI, operator and T7.2 commands, the budget definition (`plan.md:485` vs `plan.md:762`), and
task dependencies, with the T8.0 gate after T0.1-T7.2 and T4.1 after T3.3.

## 5. Closure of review 2 (S01-S15)

| ID | Closure | Note |
| --- | --- | --- |
| S01 | partially | Order independence and the bounded `?` entity are achieved (A1). Stability under evidence growth is not: T01 and T03. |
| S02 | partially | Family is restricted to `artifact` with equal vendor keys. Glimpse is fixed, and real Nemotron works with the vendor present. Vendor-less prefixed names fail (T04); preview and E4B issues remain (T13). |
| S03 | resolved | Full recompute and missing-report creation; coverage-only and family-only tests are listed (T2.5). Canonical hash form is T08. |
| S04 | resolved | Streaming deadline, 95 s reserve, outer `timeout` with `rm -f`, 180 s reserve. Residual edges: T14, T15. |
| S05 | resolved | Budget id checked before every POST; stop on zero progress; terminal reasons. The version-bump budget interaction is T02. |
| S06 | resolved | Explicit day states; ambiguous empty responses skipped on import; `N_cur`/`N_prev` handled; >= 6 complete days stated. The 10-22 vs 10-23 slip is T10. |
| S07 | resolved | Check labeled syntactic; quote shown as evidence; T7.2 precision/recall rubric. |
| S08 | partially | Corrections now replace evidence of existing articles. Evidence of deleted articles stays permanent even when wrong (T05). A version bump drops history (T02). |
| S09 | resolved | One approval rule; gate after T0-T7; T4.1 depends on T3.3. |
| S10 | resolved | Attempt keys, limits with precedence, usage on any status, stop on over-reservation, atomic checks. Lifetime-limit liveness is T07. |
| S11 | resolved | Strict majority (bridge test valid), null and tie order, pinned stopwords, `article_id` in fixtures; reproduced (H). |
| S12 | partially | Entity commands always recompute; split survives re-extraction; recompute-only ignores the flag. Merge and alias go stale as evidence grows (T03). |
| S13 | resolved | Limits of 120 / 300 chars fit columns of 255 / 400 / 300. Nit: validate lengths after NFKC, because NFKC can lengthen strings. |
| S14 | resolved | One budget definition; the test drives the locked entry with `REPORT_DATE`. |
| S15 | partially | Intro and recall fixed; `dry-run.md:207` is still stale (T18). |

Totals: **10 resolved, 5 partially, 0 not resolved, 0 regressed.**

Review 1 items: none of R01-R17 is reopened in its original form. One example, though, can come back
under a new mechanism. R06's Microsoft-Decision-1 false New (already seen on 10-10) returns if the
10-10 history extraction omits the vendor (T04).

## 6. Owner decisions and spec deltas (only where there is risk)

- **OD1**: resolve the preview contradiction (T13). Either a GA release after a known preview is
  New, or preview is packaging; it cannot be both.
- **OD5**: $2.50 covers one 75-day backfill, not a second one after a prompt change (T02). With the
  staged T7.2 (target days first, then a single history backfill with the frozen prompt), $2.50 is
  enough. If the owner wants a mid-validation version bump with re-backfill, the budget must be
  about $5.
- **OD6**: the default should also say what happens to evidence of articles removed by
  `legacy_cleanup` (non-news) as opposed to retention prune (T05).
- **SD12**: correct for retention. It needs the version-transition rule from T02, or FR-004
  ("recompute from stored history") is violated after every bump.
- **SD3**: depends on T04 for Beam. Fine if legacy 10-05 extraction yields "Beam" or names the
  vendor; otherwise Beam is New on 10-16 again.
- No disagreement with OD2-OD4, OD7, SD1-SD2, SD4-SD11 or SD13.

None of the major findings needs an owner decision. T01-T04 are planner design fixes inside
Decision 2 and Decision 4. Only T13 (OD1 wording) and possibly the OD5 amount (if the staged
validation is rejected) are the owner's to decide.

## 7. Not verified

- No implementation exists; no pytest, lint, migration or PostgreSQL check was run. This review does
  not claim any check passes.
- No provider calls. v3 prompt quality, `is_new` and quote behavior, token sizes and latency are
  unmeasured. Fixtures carry v1/v2 fields, so New eligibility could not be probed on real data, only
  identity and clustering.
- The legacy 10-05 (Beam), 10-06 (Glimpse company) and 10-10 (Decision-1) extractions do not exist.
  Their outcomes are predicted from the written rules.
- httpx and DeepSeek streaming behavior (keep-alive lines, header timing) were not exercised. The
  T15 assessment comes from reading the code and documentation.
- Docker `compose run` signal forwarding, `--rm` behavior on SIGKILL and host `timeout` flavour
  (coreutils vs busybox) were not checked on the VPS.
- The probe assumes keys are built from `canonical_name` (the plan does not say). Results for the
  real cases do not change if `name` is used, except "Decisions API" vs "OpenAI Decisions API".
- Only read-only GETs to the public digest API (2026-10-09..17) were made. No production DB access,
  no commits.
