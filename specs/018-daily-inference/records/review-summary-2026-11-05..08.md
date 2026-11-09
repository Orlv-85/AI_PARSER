# FR-022 summary: 2026-11-05..08

Reviewed 28 stored preview stories against their own source packets rebuilt on 2026-11-09.
All four days used bulletin-writer-4, model deepseek-flash. Seventeen stories are origin: world.
Scope: story headlines (including original-title fallbacks), site, Telegram, glosses, selection,
day headlines, previous-day repeats and drop diagnostics. No code or prompt changes were made.

## Verdict counts

| Bulletin date | Model / title | World | ok | minor | wrong | Dropped |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [2026-11-05](review-2026-11-05.md) | 6 / 0 | 0 | 1 | 4 | 1 | 22 |
| [2026-11-06](review-2026-11-06.md) | 7 / 0 | 3 | 1 | 6 | 0 | 26 |
| [2026-11-07](review-2026-11-07.md) | 6 / 2 | 7 | 2 | 6 | 0 | 49 |
| [2026-11-08](review-2026-11-08.md) | 7 / 0 | 7 | 1 | 6 | 0 | 31 |
| Total | 26 / 2 | 17 | 5 | 22 | 1 | 128 |

One highest-severity verdict per story. Language failures without distorted facts are minor.
Selection, repeat and day-headline observations do not add stories to these counts.
Exact published strings and supporting source passages are in the daily reviews.

## F1 and F2 after writer-4

**F1 improves vendor-result attribution but is not fully solved.** November 6 s3 explicitly says
Greenlight Financial claims Luna resolves most cases unaided; November 8 s1 attributes uneven
customer-service returns to EY. November 5 s1 names Meta and s4 attributes its benchmark claim.
No new bare vendor-performance headline like batch 1's Circle K example was found.

One wrong attribution remains: November 5 s2 Telegram says, "Anthropic says the tool follows
similar personal finance features that OpenAI introduced for ChatGPT in May." The corresponding
TechCrunch paragraph makes that comparison in the reporter's voice, not Anthropic's. The fact
that a comparison is supported does not support assigning it to the company. Extend F1 to check
the actual speaker, rather than treating "Company says" as sufficient grounding. This is a
packet-relative wrong verdict; the rebuilt text may differ from the original call packet.

**F2 works on several retained claims but does not survive all channels/fallbacks.** Meta's
headline keeps US availability; Cognition's comparison remains American open-weight models.
November 6 s1 Telegram preserves beta/US/paid-plan scope, November 7 keeps the survey populations
and earlier robot-deployment date, and November 8 keeps EY groups, Mozambique's district/province
scope and Pennsylvania's proposed status. The Vietnamese public-service report's 12,300 files
remain the centre's workload, not a claimed robot throughput or causal productivity result.

Remaining scope problems: November 5 s2 loses beta/US/plan limits; November 6 s1 loses them on
the site despite retaining them in Telegram; November 6 s4 only says "users with access" and
loses the invitation/US restriction. November 6 s5's "turns off" headline is too immediate for
an undated future rollout. These are minor omissions/imprecision, not explicit claims of global
access or proof that a switch-off already happened. November 5's cut day headline loses the
AI-search qualification. Prompt improvements need checks on the text that survives drops.

## World stories

| Date / story | Kind and concrete-change finding |
| --- | --- |
| 11-06 s2 Der Bund | Podcast/explainer with a concrete recruitment change: Galaxus uses in-person casting for logistics applicants. The change is lost from the English note. |
| 11-06 s5 Free Malaysia Today | Announced school-account controls, with a future rollout; relevant human rule, but a repeat of the Google policy. |
| 11-06 s6 WGME | Post-election analysis, planned hearings/legislation and announced OpenAI commitments; not enacted guardrails. |
| 11-07 s1 Economic Times | Attributed survey of actual AI wellness use; behavioural evidence, not clinical efficacy. |
| 11-07 s2 Manila Times | Media OutReach promotional newswire/expo story. It contains an earlier deployment of 15 traffic robots, alongside demonstrations and forecasts; weak as a new world-change lead. |
| 11-07 s3 The Star/Reuters | Deployed conservation tools, with real environmental tradeoffs; strong fit. |
| 11-07 s4 Sina | Expert conference/explainer, advice and research discussion about workplace mental health; no new adopted support system. |
| 11-07 s6 UpNorthLive | Political commitments and advocacy; same Lieu announcement with additional expert proposals. |
| 11-07 s7 InfoWorld | Concrete joint regulator warning about existing law; fits Cooperation, though the outlet is specialist tech, not general news. |
| 11-07 s8 Kristeligt Dagblad | Concrete flood of public-records requests at schools/utilities; AI generation and motive remain qualified. |
| 11-08 s1 Mint | Automated agency-feed account of EY's adoption survey; concrete reported use, with consultancy framing and no independent causal proof. |
| 11-08 s2 Guardian | Real household trial with loaned equipment disclosed; source packet cuts off before the final result. |
| 11-08 s3 SAPO/Lusa | Concrete vaccination-data platform expansion, reported through Gavi and supplier/user statements. |
| 11-08 s4 Le Courrier | Concrete administrative robot deployments and a resident's use; centre-wide statistics are not robot performance. |
| 11-08 s5 ABC7 Amarillo | Concrete OpenAI energy-cost/transparency commitments in election analysis; not a new law. |
| 11-08 s6 Times Leader/Spotlight PA | Specific proposed court-filing rule, still open for comment; not enacted. |
| 11-08 s7 GenK | Specific Microsoft-reported AI-assisted hacking campaign; also recaps older attacks and exposed deployments. |

The stream adds human-life reporting, but admission does not reliably distinguish promotional
releases, explainers, forecasts and concrete changes (F6). Eleven of 17 world stories have
English headings and notes; six fail ER-12 through title fallback. All retained model notes in
this batch are English. No world stories are present on November 5.

## Every non-English headline fallback

The site renders headline or title, irrespective of text_origin. Empty Telegram notes use
the original title. Thus story-level model/title counts understate this failure.

| Date / story | Language | text_origin | Exact original title (JSON escaped) | Telegram |
| --- | --- | --- | --- | --- | --- |
| 11-06 s2 | German | model | "KI in der Arbeitswelt: Was du wissen musst" | Same non-English title |
| 11-07 s4 | Chinese | title | "AI\u65f6\u4ee3\u804c\u573a\u4eba\u7684\u5fc3\u7406\u5065\u5eb7\u9700\u8981\u66f4\u591a\u652f\u6301\u7cfb\u7edf" | Same non-English title |
| 11-07 s8 | Danish | model | "Erhvervsorganisation: AI-aktindsigtsanmodninger kan v\u00e6re drengestreger" | English note |
| 11-08 s3 | Portuguese | model | "Intelig\u00eancia Artificial est\u00e1 a ajudar campanhas de vacina\u00e7\u00e3o em Mo\u00e7ambique" | Same non-English title |
| 11-08 s4 | French | model | "Des robots IA pour all\u00e9ger le travail des services administratifs" | Same non-English title |
| 11-08 s7 | Vietnamese | model | "AI hack mi\u1ec5n ph\u00ed \u0111ang nh\u1eafm v\u00e0o c\u00e1c ng\u00e2n h\u00e0ng \u1edf \u0110\u00f4ng Nam \u00c1" | Same non-English title |

Five of these six remain model-origin; only Chinese s4 is title-only. The Danish story has an
English Telegram note; the other five also render a non-English Telegram fallback. November 7
InfoWorld is title-only but English. Across all stories, 12 model headlines are missing, including
these six. F9 must cover both failed headlines and channel-level fallbacks.

## Repeats and follow-ups

All stored stories were compared with the previous day's stored payload, including November 4
from the first JSON. No exact URL or normalised-title match was found across adjacent days.
That is compatible with the narrow URL/title exclusion; it does not demonstrate that an actual
duplicate was encountered and blocked. Event-level repeats still get through.

| Current story | Earlier stored story | Assessment |
| --- | --- | --- |
| 11-05 s5 TechCrunch election/data centres | 11-04 s5 Ars Technica election/data centres | Same election backlash, with new exit-poll and forecast detail; label as follow-up, not a fresh outcome. |
| 11-06 s1 Claude Personal Finance | 11-05 s2 Claude Personal Finance | Same launch from another outlet; no material new rollout established. |
| 11-06 s5 Google schools | 11-05 s6 Google schools | Same policy, different outlet/URL/title; does not carry forward the Gemini-versus-Search clarification. |
| 11-06 s6 WGME post-election policy | 11-05 s5 TechCrunch post-election policy | Same election event, with additional Lieu/OpenAI commitments; explicit follow-up needed. |
| 11-07 s6 UpNorthLive guardrails | 11-06 s6 WGME guardrails | Same Lieu hearings/guardrails promise, both TNND, with added Common Sense Media proposals. |

November 8 has no clear identical previous-day announcement or campaign. Its s5 shares the
election backdrop with November 7 s6 but shifts to OpenAI's concrete commitments; those commitments
already appeared two days earlier, November 6 s6. Its s7 revisits November 6's Artex background,
but leads on a distinct Storm-3358 campaign; November 7's Vals benchmark is not that event.
F10 should recognise both duplicates and substantive follow-ups, without suppressing every story
on the same topic. November 5's Google clarification has no November 4 counterpart; its earlier
policy story was November 3.

## F3..F8 recurrence

| Fix | 11-05 | 11-06 | 11-07 | 11-08 |
| --- | --- | --- | --- | --- |
| F3 event time | Seen: s5 earlier-year bill becomes undated | Seen: s5 immediate-sounding headline for undated rollout | Not seen; s2 preserves earlier timing | Not seen as a new time error |
| F4 surviving-channel coherence | Seen: s1/s2/s4/s5/s6 | Seen: s2/s6/s7 | Seen: s3/s5/s6/s8 | Seen: s1/s2/s3/s5/s7 |
| F5 relevant/evidenced gloss | Seen: s4 Devin | Seen: s5 K-12, s6 SSRS | Seen: s1 McKinsey, s3 COP31, s5 Vals | Seen: s4 MISA |
| F6 selection/section | Seen: launches, s3 explainer, s5 analysis | Seen: launches and s6 plans/analysis | Seen: s2 promotional expo, s4 explainer, s6 plans | Seen: s1 survey/promotional framing; most others concrete |
| F7 profanity/register | Not seen | Not seen | Not seen | Not seen |
| F8 ranked day headline | Seen: s6 chosen over s1 (3.00 vs 0.99) | Not seen; selected s1 tied at 1.00 | Not seen; selected s7 tied at 1.00 | Seen: null headline despite eligible stories |

November 5's fragments "TechCrunch reports that Sen." and "Bernie Sanders and Rep." show a new
mechanism within F4: sentence splitting around abbreviated titles, followed by the sentence cap.
Keep this within F4 rather than create a duplicate fix ID. November 8's missing day headline
likewise extends F8 to the fallback path.

## Ranked fixes across both batches

Proposals only; no implementation, new paid call or publishing change is implied. Old IDs are
kept; F9 and F10 are new. Ranking prioritises unsupported meaning, English output and readability.

1. **F1 -- prompt: Preserve the actual claimant.** Keep company/outlet attribution on performance
   claims and attach each statement to its evidenced speaker; never convert an outlet's comparison
   into something the company said. Batch 1: November 2 s1. Batch 2: November 5 s2.
   Writer-4 improves headlines but does not close the latter failure.
2. **F9 -- rule: Make every fallback English and supported.** Require a usable English heading and
   per-channel fallback even when other model sentences survive; if unavailable, do not expose an
   untranslated source title. Evidence: six German/Chinese/Danish/Portuguese/French/Vietnamese
   headings listed above. A repair must preserve grounding and ER-9.
3. **F4 -- rule: Check complete surviving accounts per channel.** Retain subject, event, essential
   conditions/tradeoffs and introduced referents after drops; otherwise use a complete fallback.
   Keep Sen./Rep. and similar titles intact when splitting. Evidence: both batches; strongest new
   cases are November 5 s5's fragments and November 8 s3/s7's unidentified platform/group.
4. **F2 -- prompt: Preserve scope and number context through publication.** Keep beta, geography,
   eligible audience, proposal status and count populations in headlines and notes, including fallback
   titles. Batch 1: Netflix, Apple and data-centre tally. Batch 2: November 5 s2 and November 6
   s1/s4/s5. Writer-4 has clear successes, but uneven channel coverage.
5. **F10 -- rule: Compare previous-day events across streams and outlets.** Detect same-event
   reruns beyond URL/title keys; retain a follow-up only with an explicit material development.
   Evidence: Claude and Google on November 6; Lieu on November 7; repeated election coverage.
6. **F8 -- rule: Bind every day-headline path to an eligible ranked story.** Check confidence times
   outlet count, retain material qualifications, and ensure model rejection leaves a meaningful
   supported fallback. Batch 1: November 2/3. Batch 2: November 5 wrong anchor and November 8 null.
7. **F6 -- rule: Require evidenced human-life relevance and correct section.** Review launch-only,
   explainer, promotional-release and forecast selections; keep plans as plans and do not treat
   warnings as realised incidents. Evidence spans both batches; world-specific cases include
   November 7 s2/s4 and repeated post-election plans.
8. **F5 -- rule: Keep relevant, packet-supported glosses only.** Drop a gloss when its referent
   disappears or its definition is outside the source; distinguish experimental instances from a
   model family. Seen in both batches, including Devin, K-12, SSRS, McKinsey, COP31, Vals and MISA here.
9. **F3 -- prompt: Preserve event time.** Distinguish publication date, earlier events, current
   conditions and future rollout; do not make an earlier bill appear newly introduced. Evidence:
   batch 1 Legora/election timing; November 5 s5 and November 6 s5 here.
10. **F7 -- prompt: Paraphrase profanity with attribution.** Keep criticism in the official register.
    Evidence remains November 4 s7; not seen again in these four days.

## SC-002 so far

The sample does **not** satisfy "no story with distorted meaning": November 5 s2 has wrong
attribution. The first-batch coordinator retained one wrong story (Circle K) after downgrading
three original wrong verdicts to minor. On that reconciled basis the seven reviewed days total
**49 stories: 11 ok, 36 minor, 2 wrong**. Keeping the original first-review verdicts instead gives
11 ok, 33 minor, 5 wrong. These alternatives are explicit; no earlier record was rewritten.

SC-002's formal semantic window is the **last seven of the first fourteen published days**.
These are days 1-7, so that final window is still unevaluated. No claim that SC-002 has been
achieved is justified, and this review does not prejudge days 8-14.

Every reviewed story has a source link and a corresponding rebuilt packet story. That does not
certify same-day source provenance: several links/datelines precede the bulletin date (for
example November 5's TechCrunch election article is dated November 4). Collection timestamps
and original call packets are not supplied. No replay of the grounding checks was performed,
so the "zero failed grounding sentences published" clause is not independently certified.

## Review decisions and validation

Decided by this review: language/coherence failures are minor unless they distort a factual
claim; an unevidenced speaker is wrong under the requested rubric. Selection concerns are kept
separate from factual verdicts. A source's own inconsistency (November 8 s5's 40-of-41 tally
versus Bean's attributed "every" statement) is not silently corrected or charged as a new
writer invention. A clipped source (November 8 s2) limits what can be established.

Checked exact published fields and source-quote substrings, ASCII escaping, all 28 story blocks,
verdict/drop totals, all 17 world classifications, six non-English headline fallbacks and
previous-day URL/title comparisons. Checked current renderer code for headline/title and
Telegram fallback behaviour; did not access the deployed site.

The 128 drops comprise 67 too_close, 54 unsupported_name, 3 word_count, 3 never_list and
1 long_quote. Rejected wording is absent, so these counts do not prove false-positive drops
or warrant weakening copying/name checks. Source text rebuilt on November 9 can differ from
the text seen at the original 04:30 UTC calls.

No network, paid calls, sub-agents, application-code changes, commit, push or gh. Pytest, lint
and repo-wide quality gates were not run: only review records were added, and commit/push were
forbidden. Data outside the worktree was read only.

## Coordinator check (2026-11-09)

The only `wrong` (November 5 s2) is confirmed against the packet: the Telegram note says
"Anthropic says the tool follows similar personal finance features that OpenAI introduced for
ChatGPT in May", while the source sentence is TechCrunch's own framing ("Claude is playing
catch-up to OpenAI's ChatGPT, which introduced similar personal finance tools in May ...").
The verdict stands. Data export: stored payloads and packets built from the stored stories' own
links (read-only, in the app container); article texts stay outside git.
