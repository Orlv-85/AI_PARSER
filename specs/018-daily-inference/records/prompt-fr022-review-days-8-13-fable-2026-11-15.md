# Prompt (fresh Claude agent, Fable 5.2): independent FR-022 review of bulletins 2026-11-09..14 (2026-11-15)

Second, independent review beside the Codex (Astra) one. Do not read or wait for Astra's output:
ignore `docs/work/worktrees/` and `docs/work/tasks/`.

Repo `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (read only). Do not edit repo files, do not
commit, push or use gh. No network, no ssh, no paid calls. Do not spawn sub-agents. Do not change
code. The only file you write is the report named under Output.

Follow the task, rubric, data description, extra points and SC-002 question of
`specs/018-daily-inference/records/prompt-fr022-review-days-8-13-codex-2026-11-15.md` exactly
(read it first, then the two earlier prompts and the two summaries it names; open the earlier
per-day reviews only as far as needed for the format and the proposal ids). Its "Work only in this
directory" and "Output" sections do not apply to you.

Data: `docs/work/fr022/bulletins-2026-11-09..14.json` (about 200 KB; read it with a small Python
script per day rather than whole). Previous day for repeats: `docs/work/fr022/bulletins-2026-11-05..08.json`.

Judge every published claim (day headline, story headline, answers, glosses, Telegram text) only
against the article text in `packet_rebuilt_now`. One verdict per story at its highest severity:
ok / minor / wrong. For every "wrong" quote the published sentence and the packet sentence that
contradicts or fails to support it.

## Output

One file: `docs/work/report-fr022-review-fable-2026-11-09..14.md`. Per day: verdict counts and a
short table of stories (id, headline, verdict, finding in one line). Then: writer-5 results, world
stories, fallback titles, repeats, the volume finding (what is dropped, by reason and channel;
whether correct text is lost; whether a 3-story day reads as a complete bulletin), open proposals
seen again or not, and the SC-002 verdict for 2026-11-08..14 as yes/no with the stories (take
2026-11-08 from `records/review-2026-11-08.md`).

Final message (brief): the report path; per day the verdict counts; every "wrong" story in one
line each; the SC-002 verdict; the three most important fixes.
