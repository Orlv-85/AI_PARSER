# Prompt (Codex fix round, gpt-6.1-sol high): writer paragraph split, quotes (2026-11-03)

Same worktree and branch as your writer work:
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/writer-sentences`. Do not commit,
push or use gh. No network, no paid calls. Do not spawn a sub-agent.
Review report: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/tasks/writer-sentences.review-20261103-*.md`
(newest).

Fix exactly this (P2): splitting bypasses the quote check. Input
`Crosby said "We welcome applications. We welcome everyone."` is split into two strings with
unmatched quotes; both pass with `text_origin=model`, although the unsplit text fails
`quote_not_found` (the quote is not in the source). Grounding must never get weaker by splitting.

- `split_sentences` never splits inside an open quotation: a boundary is skipped while a double
  quotation (straight `"` or curly `“ ... ”`) opened before it is not yet closed. A
  sentence that ends with the closing quote still splits after it. An unbalanced quote (never
  closed) keeps the rest of the text as one piece, so the quote check sees it whole.
- Tests: `test_split_keeps_quotes_whole` (the input above stays one sentence and is dropped as
  `quote_not_found` against evidence without that quote; a two-sentence quote that IS in the source
  is kept whole), plus splitter edge cases for curly quotes and an unclosed quote. Name them in
  `writer.md` under the split rule, and state the rule there.

Checks: while working only `tests/unit/test_bulletin_writer.py` and ruff. Once at the end:
`PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" -n auto | tail -1`,
`PYTHONPATH=src make lint PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python 2>&1 | tail -3`
(if it fails, fix and rerun it until green), crapper on `src/app/core/bulletin/writer.py` (changed
functions under 10), and last, alone,
`PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python scripts/check_code_docs.py; echo exit=$?`.
Report: change (file:line), the new tests, each check's last line and exit code.
