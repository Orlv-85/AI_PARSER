# FR-022 independent review (Fable): bulletins 2026-11-09..14

Date: 2026-11-15. Reviewer: fresh Claude agent, independent of the Codex (Astra) review (its output
was not read). Prompt: `specs/018-daily-inference/records/prompt-fr022-review-days-8-13-fable-2026-11-15.md`.

Basis: `stored.payload` and `packet_rebuilt_now` in `docs/work/fr022/bulletins-2026-11-09..14.json`;
previous day for repeats from `docs/work/fr022/bulletins-2026-11-05..08.json`. Every published claim
(day headline, story headline, site sentences, Telegram sentences, gloss) was judged only against the
article text in the packet. The packet texts were read from the archive on 2026-11-15 and may differ
slightly from what the model saw at 04:30 UTC. One verdict per story at its highest severity;
selection, repeat and day-headline findings are observations and do not change a verdict.

All six days: `bulletin-writer-5`, model `deepseek-flash`. 29 stories, all `text_origin: model`.

## Verdict counts

| Date | Stories | World | ok | minor | wrong | Dropped entries | Stories removed (non_english_title) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-09 | 5 | 3 | 1 | 4 | 0 | 27 | 3 |
| 2026-11-10 | 8 | 2 | 2 | 6 | 0 | 23 | 0 |
| 2026-11-11 | 5 | 1 | 4 | 1 | 0 | 27 | 2 |
| 2026-11-12 | 4 | 0 | 0 | 4 | 0 | 31 | 3 |
| 2026-11-13 | 4 | 3 | 0 | 4 | 0 | 43 | 4 |
| 2026-11-14 | 3 | 3 | 1 | 2 | 0 | 44 | 5 |
| Total | 29 | 12 | 8 | 21 | 0 | 195 | 17 |

No story is "wrong". Three attribution cases are borderline and were rated minor (see "Borderline
cases"); the coordinator may want to re-read them.

## 2026-11-09 (1 ok / 4 minor / 0 wrong)

Day headline: "INSTAGRAM RELEASES AI FILTER BUILDER FOR US ADULTS" (model). Factual, keeps the US and
adult limits. It leads on a product launch (confidence 0.99) over two stories with confidence 1.00.

| id | Headline | Verdict | Finding |
| --- | --- | --- | --- |
| s1 | Instagram launches AI Effect Builder for US adults | ok | All claims and the quote match The Verge; scope kept. Plain product launch (F6). |
| s2 | Environmental groups use AI while warning of data centre costs | minor | Facts match. Gloss explains COP31, which is not in the published text (F5). No Telegram note. Same Reuters article as 2026-11-07 s3 (identical title). |
| s3 | Apiiro finds Claude Code settings files exposing secrets on GitHub | minor | Numbers match (100,000 files, about 1,100 with secrets, 63 organisations). Telegram never says that secrets leaked: it keeps only "commits without user input" and the .gitignore note (F4). "Apiiro said that setting is not reflected at the repository level" is Ars Technica's explanation. |
| s4 | UK judge tells expert witnesses to disclose AI use | minor | "Smith" is never introduced as Justice Joanna Smith (the lead sentence was dropped). "Smith cited Cornwall Council v M & Ors" - the packet gives the case in the outlet's own narration (borderline, below). |
| s5 | South Portland schools consider AI moratorium for school year | minor | The only site sentence is about what happens after the moratorium; the proposal itself (students barred from generative AI, staff training) was dropped (F4). |

## 2026-11-10 (2 ok / 6 minor / 0 wrong)

Day headline: "NEW YORK OPENS FRONTIER AI REGISTRATION PORTAL" (model). Matches s6 and the source.

| id | Headline | Verdict | Finding |
| --- | --- | --- | --- |
| s1 | Curative says agent signs provider contracts about 50 times faster | minor | "About 50 times faster than its team did in 2025" is the Claude Blog's sentence, not Curative's; the baseline is cut from the headline (borderline, below). Other numbers match. Vendor case study (F6). |
| s2 | AI100 panel publishes third five-year report on AI | ok | Matches AIhub. A report, not a change in life (F6). |
| s3 | WhalesBot launches Pubbo companion robot for US children | minor | Claims are attributed to WhalesBot and match. Telegram is company background only (where to buy, founding year, countries). The source is an ACCESS Newswire press release (F6). |
| s4 | Anthropic launches Claude Meetings, Whiteboards and Sheets in beta | minor | Site matches; plan limits (Team/Enterprise, paid plans, Google Meet only) are lost (F2). Telegram is one sentence of competitor context, correctly attributed to TechCrunch, without the launch itself (F4). |
| s5 | Research finds Grok Build share links exposed user data | ok | Matches Ars Technica (24 SpaceXSI apps, 594 accounts, Sunday notice). The later removal of the SpaceXSI links is not mentioned. |
| s6 | New York opens registration portal under RAISE Act | minor | Site and quote match. Telegram is only the California/Illinois comparison, without the New York event (F4). "Requires"/"impose" for laws that start in 2027 is slightly early (F3). |
| s7 | Macron calls for AI ban where children's mental health at risk | minor | Site note is empty (all five sentences dropped), so the site shows a headline with no text; the one Telegram sentence matches (F4). |
| s8 | Apiiro finds secrets in public Claude Code settings files | minor | Numbers match the Qodo post (1,122 / 1,379 / 215). "Cherny" is never introduced. Same event as 2026-11-09 s3; the source is a vendor marketing blog (F10, F6). |

## 2026-11-11 (4 ok / 1 minor / 0 wrong)

Day headline: null (`headline:unsupported_name`, origin `title`, nothing published). Four of five
story headlines were also dropped as `unsupported_name`; the English article titles are shown instead.

| id | Headline | Verdict | Finding |
| --- | --- | --- | --- |
| s1 | (title) How AI Helps Recyclers Turn Mixed Waste Into Reusable Material | ok | Numbers match and the account is presented as NVIDIA's own. Vendor blog (F6). |
| s2 | (title) Google's Tabletop AI experiment lets you build custom collaboration apps | ok | Matches; waitlist, 18+ and US limits kept; the doubt about minors is attributed to The Verge. |
| s3 | (title) Claude Can Now Join Your Google Meet Calls Like Any Another Team Member | ok | Matches ExtremeTech, beta and prices kept. Same launch as 2026-11-10 s4 (F10). |
| s4 | (title) United won't let your AI agent book your flight | ok | Matches; Kirby's remark is credited to the Wall Street Journal, the eBay/banks remark to The Verge. |
| s5 | Australia to Adopt Mandatory AI Safeguards | minor | Site matches. Telegram sentence 2 ("OpenAI did not raise the alarm ... until September") has no referent: the model breach of a government site that it refers to was not published (F4). |

## 2026-11-12 (0 ok / 4 minor / 0 wrong)

Day headline: "UNITED AIRLINES RESTRICTS AI AGENTS FROM BOOKING FLIGHTS" (model). Factual, but the
event already ran on 2026-11-11 (s4).

| id | Headline | Verdict | Finding |
| --- | --- | --- | --- |
| s1 | Google opens preorders for Gemini smartglasses with Gentle Monster and Warby Parker | minor | Prices, frames and countries match. Telegram: "Google said users can say "Hey Gemini" or tap the frame" - in the packet this is Ars Technica's description (borderline, below); Telegram has no preorder or price. |
| s2 | Anthropic launches Claude Meetings for video calls | minor | Matches The Decoder, but beta and Team/Enterprise limits are lost (F2). Third day in a row for this launch (11-10 s4, 11-11 s3). |
| s3 | United Airlines blocks AI agents from booking flights | minor | Matches TechCrunch. Gloss explains MileagePlus, which is not in the published text (F5). Repeat of 11-11 s4. |
| s4 | United Airlines to restrict AI bots' access to its platforms | minor | Matches CNBC. Gloss explains Meta's Muse, which is not in the published text (F5). Same event as s3 in the same bulletin and as 11-11 s4. |

## 2026-11-13 (0 ok / 4 minor / 0 wrong)

Day headline: "UNITED AIRLINES BANS AI BOTS FROM BOOKING FLIGHTS" (title fallback after
`headline:word_count`; English). Third day with the United story, second day as the day headline.

| id | Headline | Verdict | Finding |
| --- | --- | --- | --- |
| s1 | Gartner projects AI will add 1.7 million net jobs by 2030 | minor | Numbers match and stay a projection. "Deferred jobs are not the same as lost jobs" has no referent (the 1.3 million deferred positions were dropped). A forecast, not a change (F6). |
| s2 | Writer says OpenAI agent sent unsolicited feedback on his document | minor | Site matches. Telegram keeps only the proofreading detail, not the unprompted access; the source's point that the agent stayed inside the access it was given is lost (F4). |
| s3 | United Airlines bans AI agents from booking flights for customers | minor | Site note is empty; the only Telegram text is "The report was originally published on WBUR.org." - true, but boilerplate, not news. The source text is a 355-character stub. Repeat (F10). |
| s4 | Unesco says digital literacy must come before AI use in schools | minor | Facts match the Portuguese article and all text is English. "The guidelines" and "Otero" are never introduced: the reader is not told that these are rules approved by Brazil's education ministry or who Rebeca Otero is (F4). |

## 2026-11-14 (1 ok / 2 minor / 0 wrong)

Day headline: "COURT PERMITS CANADIAN PUBLISHERS' COPYRIGHT ACTION AGAINST OPENAI" (model). Matches s3.

| id | Headline | Verdict | Finding |
| --- | --- | --- | --- |
| s1 | AI Rudder launches CALL-E for AI agents to make phone calls | minor | Claims are attributed to AI Rudder and match. Gloss is a fragment, not a sentence. The source is a Media OutReach press release (F6). No Telegram note. |
| s2 | (title) Fact Check Team: Is AI replacing American workers and how hard is it to find a new job? | minor | Both sentences match. The New York Fed graduate figures are published without the source's caveat ("Those figures do not establish that AI is responsible"); under this title they read as an AI effect (F2). Gloss explains Goldman Sachs, which is not in the published text (F5). An explainer (F6). |
| s3 | Ontario appeal court lets publishers' copyright suit against OpenAI proceed | ok | Matches The Canadian Press. One site sentence, no Telegram note. |

## Borderline cases (rated minor, not wrong)

The rule of batch 2 was: an unevidenced speaker is wrong (2026-11-05 s2, a reporter's comparison
published as "Anthropic says"). Three cases here have the same form but a neutral, non-opinion
content, so the meaning is not changed. Decided by this review: minor.

- 2026-11-10 s1, headline: "Curative says agent signs provider contracts about 50 times faster".
  Packet (Claude Blog, in the blog's voice): "In this article, we share how Curative built a hierarchy
  of agents on Claude to sign provider contracts about 50 times faster than its team did in 2025."
  The figures behind it are Curative's ("2,000 to 2,400 new contracts a week, up from 2,100 in all of
  2025"), and site sentence 1 names the Claude Blog as the source.
- 2026-11-12 s1, Telegram: "Google said users can say "Hey Gemini" or tap the frame to interact with
  the AI." Packet (Ars Technica's own text): "You can say "Hey Gemini" or tap a touch-sensitive area
  of the frame to start interacting with the robot." A product fact, but Google is not quoted for it.
- 2026-11-09 s4, site: "Smith cited Cornwall Council v M & Ors [2026] EWFC 306, in which a judge
  found AI use influenced a significant part of an expert's report ...". Packet: "She highlighted
  known practical risks of AI use, including inadequate oversight, training, and understanding of AI
  capabilities. In the matter of Cornwall Council v M & Ors [2026] EWFC 306, an independent social
  worker ..." The case stands inside the account of her speech, but the packet does not say she cited it.

## Writer-5 results

- Original title of a foreign-language story never shown: works. No non-English text in any story
  headline, day headline, gloss, site or Telegram sentence of the 29 stories.
- Foreign-language story without checked English headline and Telegram text left out: works. 17
  stories were removed (`<sid>:story:non_english_title`): 3, 0, 2, 3, 4, 5 per day. Only one
  non-English story was published (2026-11-13 s4, Portuguese), with an English headline and notes.
- Words attributed to whoever said them: mostly works. Outlet remarks are now credited to the
  outlet: "TechCrunch notes" (11-10 s4, s6), "The Verge notes"/"The Verge reports" (11-11 s2, s4),
  "Ars Technica notes" (11-12 s1), "according to The Wall Street Journal" (11-11 s4). No repeat of
  the batch 2 error (a reporter's opinion given to a company). Left: the three borderline cases
  above, and narration given to the researcher in 11-09 s3.

## World stories (12 published)

| Date / story | Outlet | Kind | Concrete change in human life? |
| --- | --- | --- | --- |
| 11-09 s2 | news.tuoitre.vn (Reuters) | Report on deployed conservation tools | Yes. Repeat of 11-07 s3. |
| 11-09 s4 | thelawyermag.com | Judge's conference instruction and a recommended rule | Partly: guidance, the rule is not adopted. |
| 11-09 s5 | fox23maine.com | School board proposal | Partly: a proposal under discussion, published as "consider". |
| 11-10 s3 | finanznachrichten.de | ACCESS Newswire press release | No: product press release. |
| 11-10 s7 | punchng.com (AFP) | Interview statement before a charter | Partly: a call, no measure in force. |
| 11-11 s5 | rnz.co.nz (AFP) | Government announcement of safeguards and a regulator | Yes (announced). |
| 11-13 s1 | ianslive.in | Gartner forecast | No: forecast. |
| 11-13 s3 | delawarepublic.org | Company rule, 355-character stub | Yes, but a repeat and too little text. |
| 11-13 s4 | ebc.com.br (Portuguese) | Approved ministry guidelines | Yes. |
| 11-14 s1 | sina.com.hk | Media OutReach press release | No: product press release. |
| 11-14 s2 | wlos.com (TNND) | Fact-check explainer | No: explainer. |
| 11-14 s3 | lethbridgeherald.com (CP) | Court ruling | Yes. |

Five of 12 are a clear concrete change, four are not (two press releases, one forecast, one
explainer), three are proposals or statements. Every published text of every world story is English.

## Fallback titles

Non-English fallback titles: none (expected: none). English title fallbacks (story headline dropped,
`unsupported_name`): 2026-11-11 s1, s2, s3, s4 (digest) and 2026-11-14 s2 (world). Stories with an
empty Telegram note fall back to the English title in Telegram: 11-09 s2, s5; 11-12 s3; 11-13 s1;
11-14 s1, s2, s3. The stored `title` of 11-13 s4 is Portuguese, but it has a model headline and
Telegram text, so the title is not rendered.

## Repeats

Compared by event, not only by URL or title.

| Story | Earlier story | Note |
| --- | --- | --- |
| 11-09 s2 Environmental groups (Tuoi Tre) | 11-07 s3 (The Star) | Same Reuters article, identical title, two days apart: outside the previous-day rule. |
| 11-10 s8 Claude Code secrets (Qodo) | 11-09 s3 (Ars Technica) | Same Apiiro research, previous day. |
| 11-11 s3 Claude Meetings (ExtremeTech) | 11-10 s4 (TechCrunch) | Same launch, previous day. |
| 11-12 s2 Claude Meetings (The Decoder) | 11-11 s3, 11-10 s4 | Third day in a row. |
| 11-12 s3 and s4 United (TechCrunch, CNBC) | 11-11 s4 (The Verge) | Same decision; also two stories on one event in one bulletin. |
| 11-13 s3 United (Delaware Public/WBUR) | 11-12 s3/s4, 11-11 s4 | Third day; day headline of 11-12 and 11-13. |

7 of 29 stories are repeats; on 2026-11-12 three of four. 2026-11-09 has no repeat of 2026-11-08,
2026-11-14 none of 2026-11-13 (Gartner jobs forecast and the jobs fact check share a topic, not an
event). Six of the seven are digest stories, which the world no-repeat rule does not cover.

## Volume finding

Drop entries by reason over the six days (195): `unsupported_name` 98, `too_close` 58,
`non_english_title` 17, `unsupported_number` 7, `word_count` 6, `never_list` 4, `long_quote` 2,
`quote_not_found` 2, `non_english` 1.

Split by whether the story was published (drop ids are the writer's ids before removal):

| Date | Stories given to writer | Removed | Entries in removed stories | Entries in published stories |
| --- | --- | --- | --- | --- |
| 11-09 | 8 | 3 | 14 | 13 |
| 11-10 | 8 | 0 | 0 | 23 |
| 11-11 | 7 | 2 | 17 | 10 |
| 11-12 | 7 | 3 | 23 | 8 |
| 11-13 | 8 | 4 | 28 | 15 |
| 11-14 | 8 | 5 | 32 | 12 |

- The writer gets 7-8 stories every day. The fall from 8 to 3 published stories is entirely the
  removal of foreign-language world stories; the growth of `dropped` (27 to 44) is entirely the
  entries of those removed stories (14 to 32). Drops inside published stories do not grow (8-23).
- What is dropped most. In removed stories: `unsupported_name` on site sentences (47), headlines
  (16), glosses (13), Telegram (11). 16 of the 17 removed stories lost their English headline to
  `unsupported_name`; the seventeenth (11-14, writer id s7) has a Telegram drop and no headline
  drop, so it apparently lost its Telegram text. In published stories: `too_close` on site sentences
  (45) and Telegram sentences (12), then headline `unsupported_name` (5).
- Is correct text lost? The rejected wording is not stored, so no single drop can be proven false.
  The pattern says yes for foreign-language stories: the name check needs every capitalised word of
  the English sentence to stand in the article text (`writer.md`, Grounding 5), which an English
  headline of a French, German or Chinese article often cannot meet (translated country and
  institution names, months). `writer.md` itself calls false drops "the safe direction". The result
  is that the foreign stream, opened on 2026-11-06, is almost fully cut again: 1 story published
  against 17 removed. In published stories `too_close` often takes site sentence 1, the one that
  introduces the subject (11-09 s2, s3, s4, s5; 11-10 s3, s7; 11-11 s4; 11-12 s4; 11-13 s3;
  11-14 s1, s2), which is the cause of many F4 findings (for example the unintroduced "Smith" of
  11-09 s4; "The guidelines"/"Otero" of 11-13 s4 lost sentence 1 to `unsupported_name`). Three of
  the four never-list drops (11-11, 11-12) fall on the United stories, where the source's own
  wording is "third-party AI agents" - probably a true sentence dropped, as `writer.md` already notes
  for "third-party".
- Does a thin day read as a complete bulletin? No. 2026-11-14 is a press release (four sentences),
  two statistics under a question title, and a one-sentence court story; none of the three has a
  Telegram note, so Telegram shows three article titles. 2026-11-12 has four stories on three
  events, all repeats except one. 2026-11-13 has a story with no site text and one boilerplate
  Telegram sentence. No removed story is replaced by the next ranked one.

## Open proposals: seen again or not

| Id | Status in 2026-11-09..14 |
| --- | --- |
| F1 actual claimant | Improved, not closed. No wrong. Borderline: 11-10 s1, 11-12 s1 (Telegram), 11-09 s4; narration given to Apiiro in 11-09 s3. |
| F2 scope and number context | Seen (minor): 11-10 s4, 11-12 s2 (beta and plan limits lost), 11-14 s2 (caveat lost). Kept in 11-09 s1, 11-11 s2, s3, 11-12 s1. |
| F3 event time | Weakly seen: 11-10 s6 (laws that start in 2027 in the present tense). |
| F4 coherence per channel | Seen on every day: 11-09 s3, s4, s5; 11-10 s3, s4, s6, s7, s8; 11-11 s5; 11-12 s1, s2; 11-13 s1, s2, s3, s4; 11-14 s2. New forms: empty site note (11-10 s7, 11-13 s3) and a boilerplate sentence as the only Telegram text (11-13 s3). |
| F5 relevant gloss | Seen: 11-09 s2 (COP31), 11-12 s3 (MileagePlus), 11-12 s4 (Muse), 11-14 s2 (Goldman Sachs). |
| F6 selection | Seen: press releases 11-10 s3, 11-14 s1; vendor blogs 11-10 s1, s8, 11-11 s1; forecast 11-13 s1; explainer 11-14 s2; plain launches 11-09 s1, 11-10 s4, 11-11 s2, s3, 11-12 s1, s2. |
| F7 profanity | Not seen. |
| F8 day headline | Seen: null on 11-11; a product launch as the day headline on 11-09; the same United headline on 11-12 and 11-13. |
| F9 English fallback | Not seen: fixed by writer-5 (no non-English heading or fallback). The cost is the volume finding above. |
| F10 event-level repeats | Seen: 7 stories (table above), including a three-day run twice and two stories on one event in one bulletin. |

New in this batch (proposals only, nothing changed):

- F11 (rule): keep the day's volume after the foreign-title removal. Replace a removed story by the
  next ranked one, and review why the English headline of a foreign story fails the name check
  (16 of 17 removals).
- F12 (rule, inside F4): do not publish a story whose source text is a stub (11-13 s3, 355
  characters) and do not keep provenance boilerplate ("originally published on ...") as a note.

## SC-002 verdict for 2026-11-08..14

Question: is there any distorted ("wrong") story in the last 7 of the 14 days?

**No.** 2026-11-08: 0 wrong of 7 (from `specs/018-daily-inference/records/review-2026-11-08.md`).
2026-11-09..14: 0 wrong of 29 in this review. Total 36 stories: 9 ok, 27 minor, 0 wrong.

Limits of this verdict: it is relative to the rebuilt packets, not to the texts of the original
calls; three attribution cases were rated minor by judgement (11-09 s4, 11-10 s1, 11-12 s1); if the
coordinator applies the batch 2 rule strictly (any unevidenced speaker is wrong), those three stories
change the answer to yes. The other SC-002 clauses (links, grounding replay) were not checked here.

## Three most important fixes

1. F10: detect the same event across days, outlets and both streams, and inside one bulletin
   (7 of 29 stories; United and Claude Meetings ran three days each).
2. F11: stop the foreign-title removal from emptying the bulletin - backfill removed stories and
   fix the headline name check for translated headlines (17 stories removed, days fall to 3-4).
3. F4: check each channel after drops - the introducing sentence is often the one dropped, so
   subjects stay unnamed, the site note can be empty and Telegram can be background or boilerplate.

## Review decisions and what was not done

- Decided by this review: borderline attribution of neutral product or case facts is minor, not
  wrong; repeats and selection do not change a story's verdict; a true but empty sentence
  (11-13 s3 Telegram) is minor.
- The removed stories are not in the payload, so their rejected text could not be read; the
  statement that correct text is lost rests on the drop pattern and on `writer.md`, not on the text.
- No network, ssh, paid calls, sub-agents, code changes or commits. No tests or lint were run.
