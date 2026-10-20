# Second independent review: Daily AI Signals Phase A, revision 2

Review date: 2026-10-18. Branch: `feat/006-daily-ai-signals`.
Reviewed the working-tree revision 2 against the contract, repository code and
local evidence; revision 1 is commit `22f3b67`.

## 1. Verdict: rework

Revision 2 cannot yet be implemented without choosing between incompatible rules.
The resolver cannot satisfy its own insertion-order test, and family suppression
can hide the very Glimpse model the acceptance criteria require.
Snapshot invalidation, missing-day semantics, total execution deadlines and the
overall paid-validation cap still have concrete gaps. Resolve these contracts and
record the owner decisions before Phase B.

This is a planning review, not an implementation test or approval of spec changes.
`plan.md`, `tasks.md`, `spec.md` and `dry-run.md` below refer to
`specs/006-daily-ai-signals/`. Locations are working-tree line numbers.
`key N` means a dry-run corpus/fixture key, not an Article database id.

Pass 1 was frozen before opening the first review, the plan's Review Response
table or review diffs: `tmp/runs/phase-a-review2-20261018/pass1-frozen.md`, SHA256
`2ecec72b11902fc400c6ee06c7c515c0ff27ec12c72e923452f73534966b682a`.
The required revision-2 dry-run/report themselves contain first-review summaries;
those were necessarily visible during pass 1. Findings below retain the frozen
identifiers; pass 2 added corroborating evidence and precise citations.

## 2. Pass-1 findings

| ID | Severity | Area | Location | Evidence | Recommended change |
| --- | --- | --- | --- | --- | --- |
| S01 | blocker | Entity identity is insertion-order dependent; ambiguity grows without bound | `plan.md:317`, `plan.md:332`; `tasks.md:123` | For three same-name artifact mentions U with unknown vendor, A with vendor A, B with vendor B: U,A,B yields partitions {U,A}/{B}; A,B,U yields {A}/{B}/{U}; B,U,A yields {B,U}/{A}. Every later unknown-vendor mention then creates another entity because multiple compatible candidates remain. `probes.py` reproduces this even using the favorable convention of ignoring nulls in vendor voting. The required shuffled-partition equality cannot hold. | Define deterministic batch/reconciliation semantics or keep unresolved mentions separate from canonical identities until evidence resolves them. Reuse a bounded ambiguity record instead of creating an entity per mention. Specify null voting and deterministic ties; test both arrival and backfill orders. |
| S02 | major | Family rules bypass identity protections and miss real packaging aliases | `plan.md:289`, `plan.md:329`, `plan.md:425` | Packaging suppression checks equal family plus compatible vendor, with no type-group restriction. An older Glimpse company with unknown vendor suppresses Elorian's distinct Glimpse model. Same-day grouping has neither a vendor nor type restriction. Fixture key 114 is **NVIDIA Nemotron 3.5 Bolt 74B**, whereas key 220 is **Nemotron 3.5 Bolt 74B-A9B 24GB**: stripping trailing packaging alone leaves unequal families. | Define family identity as a type-compatible, vendor-aware relation over a specified vendor-stripped base. Require an actual packaging relationship, not merely equal text. Add full-path New tests for Glimpse and the real prefixed Nemotron names, plus same-name different-vendor candidates. |
| S03 | major | Snapshot fingerprint does not cover everything that changes the payload | `plan.md:405`, `plan.md:429`; `tasks.md:144` | Fingerprint inputs name D's membership/extractions, candidate first_seen and window counts, but omit all-history coverage used by `novelty_history_days`, historical family suppression, registry display/type/vendor changes and section readiness. Completing a day D-40 containing no D candidate changes the history note without changing those inputs. An older same-family entity can suppress a candidate without changing that candidate's first_seen. | Define a canonical complete input object, including coverage/readiness and every identity/family attribute used for rendering/ranking. Test coverage-only and family-only invalidation. Specify creation of new reports as well as refresh of existing ones, and detect membership changes semantically rather than from replacement row ids/timestamps. |
| S04 | major | Claimed wall-clock bound is not enforced | `plan.md:217`, `plan.md:242`, `plan.md:774`; `tasks.md:170` | `httpx.Client(timeout=60)` limits connection/read/write/pool operations; it is not a total request deadline. A response that keeps producing chunks can outlive 60 seconds. Thus remaining >=75 seconds does not bound the request, let alone container startup, DB work and refresh of all later reports. The systemd service can still time out during signals and report failure after digest success. | Add a real total deadline/cancellation boundary around signals, preserve exit success after a committed digest, and budget final DB/report work. Test slow incremental responses and deadline expiry, not only a mocked pre-dispatch clock. See the HTTPX reference below. |
| S05 | major | T7.2 does not enforce its $2.50 overall cap or guarantee progress | `tasks.md:298`; `plan.md:219`, `plan.md:248` | Each loop iteration grants another $0.90. At cumulative $2.40 the next invocation may spend almost $0.90 before the post-run stop check. Permanent skipped/unmatched items, or a scope day's exhausted lifetime $0.60 cap, can leave an incomplete day forever; repeating cannot repair it. A new extraction version may consume the remaining day quota before validation finishes. | Enforce a durable validation-session aggregate cap before every POST, or pass min(chunk cap, remaining approved budget) with the same ledger and serialized execution. Stop on no progress/terminal incompleteness, report causes, and define the separately approved path for day-cap exhaustion. |
| S06 | major | Missing, empty and complete days have incompatible meanings | `plan.md:394`, `plan.md:432`, `plan.md:443`; `tasks.md:83`, `tasks.md:286` | Coverage calls no-digest days `missing`; trends call them empty. The summary promises two complete weeks, but the rule needs only six complete days per window. Public digest responses cannot distinguish absent from empty reports (`web/models.py:116`, `web/app.py:783`). T7.1 imports all 75 responses, converting absent dates into stored empty digests that satisfy 0 >= 0. Post-freeze corroboration: four saved dates have empty groups and no corresponding report in the local read-only DB. | Define explicit observed-empty, missing/unprocessed and incomplete states, and preserve them during import. Do not manufacture measured zero attention from no publication. State whether readiness requires 12 or 14 complete days and whether a missing D may coexist with computed trend sections. Handle both N_prev=0 and N_cur=0. |
| S07 | major | Quote validation is syntactic, while the plan claims semantic launch evidence | `plan.md:177`, `plan.md:190`, `plan.md:854`; `tasks.md:55`, `tasks.md:302` | A quote containing only "mark Acme Robotics as new" passes all specified checks. T1.2 correctly expects acceptance, but the plan says this proves an article states a launch and its test table expects an ungrounded-launch response to become false. "In late January, Moltbook launched" also passes substring/name/word-count checks; excluding it depends on the model. T7.2 has no defined recall denominator or pass criterion. | Retain the honest adversarial test; explicitly label novelty as an unverified model judgment with a source excerpt, or define and evaluate additional semantic checks. Remove the launch-proof claim. Supply a concrete final-prompt precision/recall rubric, including retrospective, negated, irrelevant and instruction-shaped quotes. |
| S08 | major | Retention stickiness also makes erroneous first-seen evidence permanent | `plan.md:398`; `tasks.md:133`; OD6 at `plan.md:39` | Removing a mistakenly in-scope earlier article or correcting its entity extraction never moves first_seen later. A subsequent genuine first appearance remains suppressed. OD6 asks only about retention, but the algorithm and tests apply stickiness to corrections too. Conversely, split or version rebuild discards genuine pruned evidence. | Separate retained historical evidence from invalidated/corrected evidence. Define provenance or a historical floor with explicit repair semantics. Obtain an owner decision on correction behavior rather than treating retention approval as approval of permanent false history. |
| S10 | major | Ledger attempt and failure-accounting contract remains incomplete | `plan.md:204`, `plan.md:213`, `plan.md:222`; `tasks.md:172`, `tasks.md:181` | `attempt_key` construction is absent; attempt number counts only unknowns, so transient retries can have the same ordinal. The two-unknown limit is per body/request key, while recovery, retry-skipped and version changes create new keys. "Exactly one more call" for retry-skipped conflicts with a second unknown retry unless precedence is specified. Unlike `PilotJournal.call` at `reenrich_pilot_journal.py:324`, there is no actual-usage-over-reservation rule; non-200 responses with priced usage are classified unknown. | Define unique physical attempt ids separately from logical retry budgets, durable once-only retry flags and response accounting for known usage on all statuses. Check/reserve atomically, define exceeded-bound fail-stop behavior, and distinguish per-request attempts from per-article/day spending guarantees. |
| S09 | minor | Task graph and approval boundary are contradictory | `plan.md:5`; `tasks.md:6`, `tasks.md:217`, `tasks.md:314` | Plan says Phase B starts after all owner decisions; tasks allow earlier implementation under defaults. T8.0 depends on all tasks except T6.4, including T8.1/T8.2, which depend on T8.0. T4.1 patches `daily_signals.run_signals` and ledger dispatch but its only dependency is T2.5; those symbols arrive in T3.3/T3.2. | Make gate dependencies explicitly T0-T7, add test-symbol dependencies or change the test boundary, and give one approval rule. Early mechanical work is possible only after that rule is reconciled. |
| S11 | minor | Greedy half-link clustering is not bridge-free and leaves ordering inputs unspecified | `plan.md:358`, `plan.md:361`; `tasks.md:70` | With A-B and B-C edges, C joins {A,B}: 1/2 meets >=1/2. The negative bridge wording therefore does not establish "No transitive bridging." There are 24 null published_at values in the 369-row corpus. The evidence script orders nulls last and ties by corpus key; plan orders by article_id and gives no null policy. Fixtures contain key but no article_id. The fixed title stopword list is not pinned in the plan. | Name the algorithm accurately, choose a meaningful negative bridge criterion, pin null/timezone/tie handling and stopwords, and supply fixture identifiers matching that contract. Keep the reproduced precision improvement, without treating it as a proof against all bridges. |
| S12 | minor | Repair/recompute persistence and enable-gate behavior need explicit rules | `plan.md:343`, `plan.md:405`, `plan.md:809`, `plan.md:831`, `plan.md:887` | Entity commands refresh only with `--recompute`, while rollout says refresh happens automatically. Split moves mentions but does not specify alias redistribution or a durable per-mention override, so changed-content extraction can resolve them back to the original entity. The documented recompute-only command omits enabled=true although disabled runs leave snapshots untouched. | Choose automatic or explicit refresh; preserve split decisions through re-extraction; define recompute-only precedence over enabled/key gates and demonstrate the documented command with flag off. |
| S13 | minor | Validated values can violate PostgreSQL field lengths | `plan.md:172`, `plan.md:177`, `plan.md:534` | A <=30-word grounded quote can exceed `String(400)`; a grounded vendor or canonical name has no specified character bound for `String(255)` fields. PostgreSQL rejects overlength values that SQLite accepts. | Align parser limits and storage types. Test a short-word-count quote longer than 400 characters and a long grounded canonical/vendor string; preserve evidence without silent corruption. |
| S14 | minor | Job example and job-test setup disagree in small but executable ways | `plan.md:477`, `plan.md:754`, `plan.md:763`; `tasks.md:259` | Architecture says signals start with >=600 seconds remaining; script requires >=300 after subtracting 600. Merely supplying an old AINEWS_DAILY_JOB_START in the test does nothing: the unlocked entry resets it. | State one budget definition. Test a consumed budget via a controlled clock/publication duration or the complete locked-entry environment, including REPORT_DATE. Retain the existing release-image preamble. |
| S15 | minor | Some validation labels remain stale or broader than the evidence | `dry-run.md:23`, `dry-run.md:28`; `plan.md:256`, `plan.md:371`, `plan.md:938` | Dry-run introduction still says the plan adopts v2 and expects little precision change; plan now uses untested single-article v3. Clustering evidence uses revision-1 identities, not the final resolver. SD10 promises recall notes, but T7.2's done criteria do not require them. The cost arithmetic is corrected; the 2100/250 token production assumption remains unmeasured. | Update version/evidence labels, add explicit recall recording, and distinguish reproduced old-extraction clustering from validation of the combined production pipeline. |

HTTPX documents read timeout per received chunk, with separate connection, write
and pool timeouts: [HTTPX timeout documentation](https://www.python-httpx.org/advanced/timeouts/).
That directly supports S04; no provider endpoint was contacted.

## 3. Internal consistency and executability

The following disagreements need one authoritative wording, even where they are
already represented by a finding:

1. Approval: `plan.md:5` versus `tasks.md:6` (all Phase B versus selected tasks).
2. Identity: `plan.md:317` versus `tasks.md:126` (online wildcard matching versus
   insertion-order-invariant partitions).
3. Homonyms: `plan.md:329` and SD3 at `plan.md:926` promise Glimpse separation and
   New, but `plan.md:425` permits cross-group family suppression.
4. Novelty: `plan.md:177`/`plan.md:854` versus `tasks.md:55` (launch proof/rejection
   versus an accepted instruction quote). The task's assertion is possible and
   honest; the narrative and test table are not aligned with it.
5. Coverage: `plan.md:394` says absent digest means missing;
   `plan.md:432` and `tasks.md:83` say empty. The two-complete-weeks text at
   `plan.md:25`/`plan.md:658` disagrees with six complete days per window.
6. First seen: the retention-only owner question (`plan.md:39`) is narrower than
   permanent stickiness for membership corrections (`tasks.md:133`). This is an
   additional FR-004 deviation, absent from SD1-SD11.
7. Refresh: optional `--recompute` (`plan.md:346`, `tasks.md:202`) versus every-run
   invalidation (`plan.md:405`) and automatic rollout refresh (`plan.md:887`).
8. Status: cap handling says snapshot partial (`plan.md:251`), but the status
   precedence makes zero extracted rows unavailable (`plan.md:454`). Clarify that
   precedence always wins; an empty stored digest is also complete yet unavailable.
9. Bridge protection: `plan.md:361` versus the >=half rule and the T1.3 bridge
   example. C connected only to B passes; do not call that example a rejection.
10. Budget: the architecture's >=600 seconds (`plan.md:477`) versus the code's
    >=300 after safety subtraction (`plan.md:763`). The shell's `&&` cap assignment
    is safe under `set -e`; that is not a failure.
11. Versions/evidence: `dry-run.md:28` says v2 adopted; `plan.md:104` says v3.
    `plan.md:938` says recall notes; `tasks.md:304` does not require them.
12. Gate: `tasks.md:314` creates a dependency cycle with `tasks.md:317` and
    `tasks.md:319`; the intended gate is evidently after phases 0-7, not after rollout.
13. Limits: parser word count (`plan.md:177`) versus DB quote character count
    (`plan.md:534`); canonical/vendor validation versus varchar columns.
14. Smaller contract ambiguities: `plan.md:860` says downgrade leaves existing
    tables/rows, while `tasks.md:102` explicitly drops the seven new tables; say
    "pre-feature tables/rows." `plan.md:574` requests default factories, but the
    illustrative models use literal defaults. Pydantic's copying means this is
    not, by itself, a shared-mutable-default bug.

T0.1 can start with the local fixtures currently present; a fresh checkout cannot
do so until those gitignored files are delivered. The stop-if-missing rule is
appropriate. T1.1 can start most normalization work mechanically, but needs the
family contract fixed before tests encode the wrong suppression behavior. T1.2's
adversarial case no longer demands an impossible assertion. T5.3 now explicitly
targets a scratch DB but still requires the implementer to author a seeding script;
it is a task, not a ready-to-run validation command. Read-only review does not
authorize any of the later paid work, production configuration or rollout.

## 4. Entity identity walkthrough on real evidence

Predictions below apply the written rules, not a silently improved implementation.
Legacy dates lack final-prompt entity extractions, so their exact vendor/name
outputs remain conditional. Fixtures contain v1/v2 fields, not v3 novelty quotes;
identity correctness alone cannot prove final New eligibility.

| Case | Evidence | Predicted revision-2 result |
| --- | --- | --- |
| Glimpse company (10-06) vs Elorian Glimpse model (10-16) | Saved 10-06 digest title concerns CT inspection; fixture 10-16 key 311 has Glimpse/model/Elorian, primary. | Registry separation succeeds: org versus artifact. But if the company's vendor is unknown, its `family_key=glimpse` is vendor-compatible with the model and the unqualified older-family rule suppresses New. This contradicts T7.2. Add type-group and real packaging constraints. |
| pplx-decider-v1 vs v1.1 | 10-12 key 9 contains primary `pplx-decider-v1.1-27b` and mentioned `pplx-decider-v1-27b`, both vendor null. | Distinct name keys and distinct families: `pplx decider v1.1` versus `pplx decider v1`. A new-version quote can make v1.1 eligible; v1 does not suppress it. The old normalizer's version collision is fixed. |
| Nemotron 3.5 Bolt 74B vs 74B-A9B 24GB | 10-13 key 114 is `NVIDIA Nemotron 3.5 Bolt 74B`; 10-15 keys 220/242 use the unprefixed packaging name. | Distinct entities is correct. Abstract unprefixed examples share a family, but the real fixture families are `nvidia nemotron 3.5 bolt` and `nemotron 3.5 bolt`. Vendor-stripped aliases used in lookup do not specify the stored family. As written, 10-15 suppression is not assured; do not substitute the easier names in the regression test. |
| Bee vs Bee Frontier | 10-15 key 278 has product `Bee Frontier`, vendor Bee; the source distinguishes the maker/existing device. | No prefix auto-merge; `bee` and `bee frontier` remain distinct families. Company versus product is also separated by type group. Frontier may be New with valid v3 evidence; Bee is not its packaging variant. This specific prior grouping defect is fixed. |
| Microsoft's Decision-1 (10-10) vs Microsoft-Decision-1 (10-12) | Saved 10-10 digest title/summary; fixture 10-12 key 8, model/Microsoft. | Possessive removal and separator normalization give `microsoftdecision1` for both full names. If 10-10 extraction emits only Decision-1, vendor-strip lookup/alias connects the full form. With the grounded Microsoft vendor retained, first_seen is 10-10 and 10-12 is not New. Final historical extraction remains unrun. |
| Muse Spark vs Muse Spark Open | 10-12 keys 0/2 have Muse Spark; many 10-15 rows have Muse Spark Open, mostly vendor Meta. | `open` is not a packaging token, so identities and families remain separate. The older token-prefix relative supports `variant_of=Muse Spark`; it does not suppress New. A final-prompt release quote is still required. Some null vendors match a sole Meta candidate, subject to S01 if another compatible homonym later appears. |
| Reflection Beam vs Beam | 10-16 keys 313/316/317 are Beam with Reflection/Reflection AI; key 343 is Reflection Beam with Reflection AI; saved 10-05 digest explicitly mentions Reflection and Beam. | Company normalization makes both vendors `reflection`. Known-vendor prefix stripping and aliases link the full and short model names in either order when there is no competing candidate. Historical extraction can set first_seen=10-05, making 10-16 not New. Unknown vendor or conflicting homonyms can still prevent that result. The four-member story reproduces under the old resolver, not under a completed revision-2 implementation. |

Stable display attributes also require a tie rule independent of processing order.
The plan gives earliest mention for type/vendor ties but no precise definition
of earliest across multi-day membership/null timestamps, and no display-name tie
rule. Surrogate ids avoid destructive uniqueness collisions; they do not by
themselves provide stable partitions, grouping or displayed names.

## 5. Pass-2 closure of R01-R17

"Resolved" means addressed in the proposed design, not proven by unimplemented
tests or approved by the owner. The Review Response table is a claim, not evidence.

| Finding | Closure | Evidence and remaining issue |
| --- | --- | --- |
| R01 identity/versions | partially | Surrogate ids, type groups and preserved dots/versions address the original destructive key. S01/S02 show that order dependence and family-based suppression still defeat the required outcome; see `plan.md:317`, `plan.md:425`. |
| R02 retention | resolved | All three article FKs use CASCADE (`plan.md:502`), loaders ignore SQLite orphans, prune tests enforce FKs (`tasks.md:136`), and PG validation precedes rollout (`tasks.md:315`). Retention default stays unchanged. S08 concerns broader historical semantics, not the original FK deletion failure. |
| R03 journal/caps/recovery | partially | Separate ledger, one POST, recovery bodies and physical-call tests are concrete improvements. Total deadline and full attempt/accounting rules remain open (S04/S10). |
| R04 scope/stale snapshots | partially | Separate membership and outside-range refresh are specified (`plan.md:384`, `plan.md:405`). Fingerprint omissions and sticky incorrect first_seen still leave stale/incorrect reports (S03/S08). |
| R05 history/readiness | partially | Coverage counters, N_prev guard and per-section states are added. Missing/empty, six-versus-seven days, and import semantics remain contradictory (S06). |
| R06 dry-run quality | partially | Corrected 26/6/8 assessment and explicit v2 retrospective failures are adopted (`dry-run.md:166` onward); T7.2 covers all five dates and named regressions. A final-prompt recall rubric and semantic-novelty acceptance remain insufficiently specified (S07/S15). |
| R07 clustering | partially | Same-family simhash and an offline half-link rerun fix the observed 10-16 four-publisher over-merge. The algorithm still accepts the elementary bridge, and pricing/robotics remains an admitted weak grouping; S11. |
| R08 migration race | resolved | `plan.md:553` distinguishes guarded idempotence from concurrency and explicitly accepts/retries the residual race; downgrade requires stopped app/jobs. This is a documented operational risk, not serialization or a concurrency-safety proof. Owner rollout must accept that risk. |
| R09 validation/impossible test | partially | Strict types and the honest accepted-injection test in `tasks.md:55` resolve the impossible assertion. `plan.md:177`/`plan.md:854` still overclaim or contradict that test (S07). |
| R10 alias ambiguity | partially | Manual precedence, candidates and cycle refusal are added. Unknown vendors still produce order-dependent partitions and duplicate growth; split persistence is undefined (S01/S12). |
| R11 job lock/timeout | partially | One flock, shared date, savepoint insert recovery and locked operator commands address ordinary paths. HTTPX inactivity timeout cannot guarantee the service budget; S04. |
| R12 meaning of New | resolved | OD1/OD2 explicitly request product decisions, define named versions versus packaging/ports, and explain legacy display restrictions (`plan.md:34`, `plan.md:924`). These choices are proposed, not already approved; they must enter the accepted contract before implementation. |
| R13 cost/validation | partially | Estimates now reproduce and chunk flags pin date/cache/wall/calls. The overall $2.50 authorization can still be exceeded and an incomplete loop can stall (S05); a cap is only cumulative within the retained ledger. |
| R14 denominator/page failure | resolved | Digest item count includes unmatched entries (`plan.md:391`); isolated signals read/parse failure preserves digest rendering (`plan.md:739`, `tasks.md:230`). Correct for the read path; this does not eliminate the separately documented create_all race. |
| R15 ordering/events/config | resolved | Ranking, event links, event_type filtering and code-release threshold configuration are specified (`plan.md:432`, `plan.md:617`, SD11). SD11/OD4 still need explicit acceptance as contract changes. |
| R16 executable handoff | partially | Full gates before commits, corrected counts/dependencies, no invented fixtures, scratch DB targeting/commits and weekly-page test file are addressed. New gate cycles/dependency gaps remain (S09), and fixture-to-DB setup is still an implementation task. |
| R17 evidence/references | partially | Two spike days and unvalidated trends/v3 are disclosed; most task references and daily cost agree. The dry-run introduction still adopts v2/assumes similar precision and the final combined algorithm is untested (S15). |

Closure total: **5 resolved, 12 partially, 0 not resolved, 0 regressed**.
Partial closure can include a newly introduced defect; it does not mean the
revision made no improvement.

## 6. Spec deltas and owner decisions

| Delta | Assessment |
| --- | --- |
| SD1 | Reasonable separation of legacy admission from comparable trends; requires OD2. Legacy title-only extraction is useful first-seen evidence but does not establish complete semantic history. Preserve missing/empty provenance. |
| SD2 | Per-section degradation is appropriate. Decide six versus seven complete days per window, missing-day treatment and the meaning of "two complete weeks" before approval. |
| SD3 | Beam's 10-05 mention is real in the available corpus. Not showing a legacy snapshot is a product restriction, not evidence that SC-002 was wrong. OD2 can authorize the replacement criteria, but S02 currently breaks Glimpse. |
| SD4 | Hardware/policy and per-entity novelty fields are justified by the observed rejects. Quote fields add inspectable evidence; they do not establish semantic truth. Align field limits with storage. |
| SD5 | A material change from corpus-first-seen to launch-first-seen. OD1 is required. It may improve usefulness, but it also excludes newly discovered established entities; measure recall under the approved definition. |
| SD6 | Story counts plus article counts and links are explainable. Because clusters can group related but distinct events, do not present the counts as verified unique real-world events. |
| SD7 | Volume adjustment and publisher floors are reasonable hypotheses. They change the meaning of rising/cooling from raw growth to relative attention; show expected counts and keep the empirical validation gate. |
| SD8 | Withdrawal of the global unique name key is justified. Family keys must not reintroduce the same suppression defect. |
| SD9 | Correct: the weekly preview already follows the digest groups (`digest.html:217` and live HTML). No move is needed. |
| SD10 | Evaluating the actual final prompt across all five dates is necessary, not a weaker SC-001. Add the promised recall notes and explicit semantic-novelty rubric to T7.2. |
| SD11 | Code constants with version bumps are reproducible but narrower than FR-008 configurable thresholds. This needs owner acceptance; it is not listed as a clear question in OD1-OD6. |

Additional deltas are currently implicit: sticky first_seen after a correction
changes FR-004; display-only event chips defer US4 interaction; the readiness rule
can accept fewer than fourteen complete days. Make them explicit in the approved
contract rather than relying on traceability labels.

| Decision | Assessment of question/default |
| --- | --- |
| OD1 | The right product question. Named versions and packaging are distinguished, but first public release after a preview/pilot and renames need examples. Define whether the UI says "newly announced" or "first seen" and how uncertain novelty is labeled. |
| OD2 | The right history/display choice. Suppressing New from legacy evidence is defensible only with correct type/vendor identity; hiding legacy snapshots explains the SC-002 change. |
| OD3 | The right statistical choice; the default is not yet validated. Resolve missing/empty and completeness language before the owner approves it. |
| OD4 | Clear and low-risk default, but display-only chips are a conscious deferral of US4, not satisfaction of it. |
| OD5 | Necessary budget/rollout decision; the $2.50 default has plausible estimated headroom but is not enforced by the listed loop. State validation versus production caps separately and keep the one-line compose change explicitly owner-gated. |
| OD6 | Preserving genuine novelty history under retention is sensible. This question does not authorize keeping corrected false history forever or discarding pruned history after version rebuild; split those cases. |

No deploy defaults, timer values, ports, authentication behavior or retention
policy are proposed to change outside the stated feature scope. The enabled
compose line, production backfill and flag activation have explicit owner gates.
The plan accurately documents the existing deployment/create_all race; accepting
that residual risk should be part of rollout review. Correcting a documentation
sentence about existing deploy order is not itself a deploy behavior change.

## 7. Reproduction, costs and operational checks

Offline probe: `rtk proxy python3 tmp/runs/phase-a-review2-20261018/probes.py`.
It loads `analyze.py` with runpy, `V2=1`, `LINK=avg`, calls load/resolve/snapshot,
and never calls main. Output is in `probes.txt` in the same scratch directory.
No existing evidence file was rewritten.

| Date | Digest items | Reproduced average-link stories | Multi-publisher stories | Checked components |
| --- | ---: | ---: | ---: | --- |
| 2026-10-12 | 56 | 50 | 2 | Muse Wonder 6 articles / 6 publishers |
| 2026-10-13 | 90 | 79 | 4 | Gemini 4 Argon 7/5; arrest 3/3 |
| 2026-10-14 | 73 | 67 | 2 | Arrest 3/3, reduced from union-find 4/4 |
| 2026-10-15 | 92 | 70 | 6 | Muse Spark Open 7/7; Nemotron Super VL 4/3; pricing/robotics pair remains |
| 2026-10-16 | 58 | 52 | 4 | Beam 4/4; RTX laptop and Surface stories each 2/2 |

These match `cluster-avg.txt`. Replacing corpus-key tie ordering with actual
article ids did not change top-story results for these five dates. That does not
remove the need to define null ordering: 24 corpus rows have no published_at.
This is evidence for the existing offline script with revision-1 identities,
not an end-to-end reproduction of the unimplemented revision-2 plan.

Saved calls contain 39 responses and 459 article extractions: 176144 prompt tokens
and 97611 completion tokens. At `reenrich_pilot.PRICES` ($0.30/$1.20 per million),
the recorded usage prices to **$0.1699764**; mean completion is **212.66 tokens per
article extraction**. It is not an invoice or a measurement of v3.

At the revised assumed 2100 input +250 output tokens, one article costs $0.00093:

- 1772 articles / 60 days: $1.647960; with 5% recovery, $1.730358.
- 2072 articles / 75 days: $1.926960; with 5% recovery, $2.023308.
- 60-90 articles: $0.0558-$0.0837, or $0.05859-$0.087885 with 5% recovery.

The corrected estimates are arithmetically sound. They do not guarantee that
longer single-article inputs, novelty quotes, errors or prompt-version reruns fit
$2.50. The conservative byte reservation agrees with the existing helper's
design. Charging a crash-left reservation as unknown is conservative even when
the crash preceded POST; two unknown attempts can overcount and skip an article,
but do not by themselves undercount normal bounded calls. It is a liveness and
accounting policy, not exactly-once delivery. All cumulative claims depend on
retaining the same ledger; changing cache directories creates a fresh ledger.

The re-exec shell design uses one flock and preserves the selected report date.
The existing fake flock (`shift 3; exec "$@"`) fits `flock -w 7200 LOCK sh "$0"`.
Ordinary publish failure exits under set -e; signals failure is swallowed by the
explicit OR branch. The GNU `date -d` / BSD `date -v` fallback is plausible on
Linux/macOS and needs both-path tests; it was not run on a Linux host here.
Compose explicitly enumerates environment variables, so the proposed enabled
line is required; other settings need documented `run -e` overrides. Host-only
variables such as START/LOCKED do not need forwarding to the container because
the script passes the remaining budget as a CLI argument.

Migration head and prune behavior match the plan: current head is
`a42b750d0c44`; bulk prune deletes aliases then articles; CASCADE is the appropriate
new FK deletion behavior. PostgreSQL and concurrent-create validation remain
future checks. Derived signals being omitted from cleanup exports means restoring
articles alone does not restore signals; recomputation may require paid extraction
and should be stated in the cleanup note.

Read-only live GETs succeeded for the 2026-10-16 digest and page. The digest has
58 items in 9 groups and is equal to the saved dry-run JSON. The weekly preview
follows digest content. Scratch copies are `live-digest-2026-10-16.json` and
`live-page.html`. Four saved empty dates (09-19, 09-20, 09-26, 09-27) have no
`news_digest_reports` rows in the local SQLite copy opened with `mode=ro`; the
public API shape cannot establish observed-empty publication for those dates.

## 8. What was not verified

- No production feature implementation exists. No pytest, lint, migration,
  cleanup, retention or rollout operation was run; existing tests would not
  validate these proposed algorithms. This review does not claim all checks pass.
- No provider calls or extract scripts ran. Single-article v3 precision/recall,
  quote quality, latency, actual token distribution and billing remain unverified.
  Offline counterexamples are direct transcriptions of the written rules, not
  tests against implemented production code.
- No production database, credentials, POST endpoint, auth configuration, timer
  or environment was accessed or changed. Local SQLite access was read-only.
- No fourteen-day comparable extraction is supplied; Rising/Cooling and volume
  adjustment remain unvalidated. No browser/mobile rendering or timing was tested.
- No full revision-2 registry was rebuilt from the local corpus: final-prompt
  historical extractions are absent. Real-case predictions state those limits.
- Publisher text was used as untrusted corpus evidence, not independently
  verified external fact. HTTPX documentation was checked only for timeout
  semantics. The public page was read, not exercised as a new UI.
- Only this ASCII deliverable and this review's files under
  `tmp/runs/phase-a-review2-20261018/` were written. Plan, spec, tasks, source,
  tests, existing evidence and existing dirty files were left unchanged. No
  commit, push, PR or further delegation was performed.
