# Report: ub-mode pass 2, bulletin modules (2026-11-02)

Executor: Claude Opus agent (Codex limit); reviewer: a fresh Claude Opus agent; coordinator ran the
full suite and returned two rounds of fixes.

- CRAP before -> after: `validate_phrases` 18.2 -> 1.0, `_digest_candidates` 12.0 -> 6.0,
  `run_assessment` 10.2 -> 5.0, `sentence_error` 10.1 -> 2.0; no function of the four files at 10+.
- Pure refactor: helpers extracted, check order, messages, queries, summary keys and caps unchanged.
  `_outlet` now shared by digest and world candidates (same fallback).
- Characterization tests in test_bulletin_builder.py, test_bulletin_writer.py, test_world_change.py;
  docs builder.md, world_change.md, writer.md list them.
- Mutator (executor): phrases 26/26, bulletin_input 22/25, world_change 32/37, writer_grounding 15/15
  killed, 0 survived; uncovered sites are continuation lines, killed by hand.
- Round 1 (coordinator full run): new journal test patched `PilotJournal` where the monkeypatch guard
  sees no reader; rewritten against the real journal.
- Round 2 (review): behavior equivalent; 6 surviving hand mutants (phrase check order pairs, length
  strip, world `source_domain`, `cost_usd` float) -> 13-case order test and three assertions; all 15
  mutants then killed by hand.
- Final: full suite 2072 passed / 2 skipped (PostgreSQL), make lint 10.00, code docs ok.
- Executor note: a stale `.pyc` can hide a hand mutant when the restored file keeps size and mtime;
  run hand mutations with PYTHONDONTWRITEBYTECODE=1.
