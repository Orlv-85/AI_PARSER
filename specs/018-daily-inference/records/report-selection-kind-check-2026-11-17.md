# Report: label check of the `kind` question (2026-11-17)

Coordinator, on prod, owner go 2026-11-17. 39 articles of the FR-022-reviewed bulletins of
2026-11-09..14 (night versions, `docs/work/fr022/`) and the stored bulletins of 2026-11-15..16;
reference labels by the coordinator from the review findings (F6). One Jev request per article
with the four questions plus `kind` (version `world-change-2-eval`), own journal in the
container's /tmp (removed after), cap $0.02, nothing stored. Cost: 39 calls, $0.003566.

## Result
- Exact kind 33 of 38 (one reference label ambiguous, not scored); event vs not 34 of 38.
- No real event called `promotion`. Caught: press releases (WhalesBot, AI Rudder), vendor
  blogs (NVIDIA, Qodo), case study (Duco on Amazon Bedrock), forecasts (Gartner, Systematix),
  explainer (Fact Check Team), interview (Baldini).
- Disagreements: "Inside China's drive to build an AI-native generation" (reference event,
  Jev explainer: Jev is probably right, a feature piece); Macron's call and Unesco's
  recommendation (reference opinion, Jev event); AI100 report (reference explainer, Jev event);
  Curative case study (reference promotion, Jev explainer: still not shown).
- Verdict: passes the plan's bar (most agree, no event called promotion).

## Answers
| day | reference | Jev | conf | title |
| --- | --- | --- | --- | --- |
| 2026-11-09 | event | event | 0.96 | Instagram’s Effect Builder makes new filters from AI prompts |
| 2026-11-09 | explainer | explainer | 0.81 | Environmental groups embrace AI, even as they warn of data center impacts |
| 2026-11-09 | event | event | 1.00 | UK judge instructs expert witnesses to be transparent about AI use |
| 2026-11-09 | ambiguous | event | 0.99 | Putting AI on pause: South Portland schools consider moratorium |
| 2026-11-09 | event | event | 0.95 | Claude Code is accidentally exposing secrets all over GitHub |
| 2026-11-10 | promotion | explainer | 0.41 | How Curative is building a national provider network with agents on Claude |
| 2026-11-10 | explainer | event | 0.82 | AI100 longitudinal study examines how AI has entered the mainstream |
| 2026-11-10 | promotion | promotion | 0.99 | WhalesBot Launches Pubbo: AI Companion Robot for US Kids |
| 2026-11-10 | event | event | 0.85 | Anthropic launches Claude Meetings to turn workplace discussions into plans and  |
| 2026-11-10 | event | event | 1.00 | OpenAI, Anthropic face new oversight as New York’s AI safety law takes effect |
| 2026-11-10 | opinion | event | 0.90 | Macron wants AI ban wherever it threatens children |
| 2026-11-10 | event | event | 1.00 | Grok Build coding agent leaks oodles of confidential info, some belonging to Spa |
| 2026-11-10 | promotion | promotion | 0.64 | Claude Code’s “Don’t Ask Again” Left Secrets in 1,122 Public GitHub Files. Your  |
| 2026-11-11 | promotion | promotion | 0.92 | How AI Helps Recyclers Turn Mixed Waste Into Reusable Material |
| 2026-11-11 | event | event | 0.73 | Google’s Tabletop AI experiment lets you build custom collaboration apps |
| 2026-11-11 | event | event | 0.70 | Claude Can Now Join Your Google Meet Calls Like Any Another Team Member |
| 2026-11-11 | event | event | 1.00 | United won’t let your AI agent book your flight |
| 2026-11-11 | event | event | 1.00 | Australia to adopt 'mandatory' AI safeguards |
| 2026-11-12 | event | event | 1.00 | Google pushes privacy angle as Gemini-powered smartglasses debut starting at $39 |
| 2026-11-12 | event | event | 0.99 | Claude Meetings lets Anthropic's AI join your video calls |
| 2026-11-12 | event | event | 1.00 | United Airlines blocks AI agents from booking flights, citing cybersecurity risk |
| 2026-11-12 | event | event | 1.00 | United moves to block AI agents |
| 2026-11-13 | forecast | forecast | 0.96 | AI to create more jobs than it kills by 2030, net gain of 1.7 million globally:  |
| 2026-11-13 | event | event | 1.00 | United Airlines bans AI bots from booking flights |
| 2026-11-13 | opinion | event | 0.98 | Letramento digital precisa vir antes de uso da IA, diz Unesco |
| 2026-11-13 | event | event | 1.00 | OpenAI Agent Accesses, Provides Feedback on User's Google Doc Unprompted |
| 2026-11-14 | promotion | promotion | 0.99 | CALL-E Lets AI Agents in ChatGPT, Muse and OpenClaw Make Real Phone Calls on The |
| 2026-11-14 | explainer | explainer | 0.98 | Fact Check Team: Is AI replacing American workers and how hard is it to find a n |
| 2026-11-14 | event | event | 1.00 | Court allows news publishers' copyright lawsuit against OpenAI to go ahead |
| 2026-11-15 | forecast | forecast | 0.99 | AI may deepen pricing pressure on Indian IT services before new demand offsets i |
| 2026-11-15 | opinion | opinion | 0.94 | Baldini professore Unimore / L'intelligenza artificiale una rivoluzione industri |
| 2026-11-15 | event | event | 1.00 | Lansohet "ChatGPT Wallet" – që u mundëson agjentëve të OpenAI të blejnë gjëra pë |
| 2026-11-15 | event | event | 1.00 | Japan Defense Ministry to Release AI Guidelines at End-Nov. |
| 2026-11-16 | event | explainer | 0.91 | Inside China's drive to build an AI-native generation |
| 2026-11-16 | event | event | 0.99 | Geordie and Scouse accents included in new Google AI update |
| 2026-11-16 | promotion | promotion | 1.00 | How Duco transforms financial data automation with Amazon Bedrock AgentCore |
| 2026-11-16 | event | event | 0.90 | Google Maps can now build trip itineraries with real-time details about each sto |
| 2026-11-16 | event | event | 1.00 | Primul atac cibernetic realizat complet automatizat cu ajutorul AI, raportat de  |
| 2026-11-16 | event | event | 1.00 | В Японии обнаружили 1000 серверов для ИИ-атак на сайты по всему миру |
