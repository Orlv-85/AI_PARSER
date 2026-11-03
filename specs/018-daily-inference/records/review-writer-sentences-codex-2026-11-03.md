- **P2 — [writer.py:205](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/writer-sentences/src/app/core/bulletin/writer.py:205): splitting bypasses quote validation.** Input `Crosby said "We welcome applications. We welcome everyone."` becomes two strings with unmatched quotes. Both pass, with `text_origin=model` and no drops, although the unsplit input fails `quote_not_found`. **Fix:** preserve balanced quotation spans during splitting and add a regression test.

All five in-memory mutations were killed:

| Mutation | Failing cases | Representative test |
|---|---:|---|
| No split | 39 | `test_site_paragraph_is_split_into_sentences` |
| Cap before split | 2 | `test_cap_applies_after_split` |
| Numbering per item | 5 | `test_split_sentence_dropped_alone` |
| Remove abbreviation guard | 18 | `test_sentence_splitter_edges` |
| Split without whitespace | 20 | `test_sentence_splitter_edges` |

Requested suite: **123 passed, 1 warning**. Mutation baseline: **44 passed**.

`Plan B. Next` and `Acme Inc. The…` remain merged as specified; checks still apply to the combined text. Version/prompt changes match the decisions; journal identity and caps remain unchanged.

**Not clean:** fix quote handling before merge. No files edited.