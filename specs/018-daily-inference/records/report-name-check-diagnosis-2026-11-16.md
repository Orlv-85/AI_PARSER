# Report: why the writer's name check rejects most headlines (2026-11-16)

Coordinator, read-only on production. Bulletins of 2026-11-12, -13, -14 (rebuilt on v0.1.181):
the writer packets were rebuilt from the database and matched the journal keys of the real day
2026-11-16 exactly (repeat check and writer), so the model answers are the stored ones. For each
model text the script listed every name `grounding_error` would reject, not only the first.
Script: scratchpad `names_diag.py` (replays the journal by `request_key`, no provider call).

## Numbers
- Headlines: 19 of 35 fail `unsupported_name`. Stories in other languages: 17 of 22 fail; English
  and digest stories: 2 of 13.
- Site and Telegram sentences: other languages 105 of 162 fail; English 14 of 98.
- A story in another language without a checked headline and Telegram note is removed
  (`_needs_english_text`), and a reserve story without a checked headline is not promoted. So the
  name check on translated headlines is what makes bulletins thin.

## What fails
1. Honest translations of places, nationalities and institutions: US (Stati Uniti, American),
   European, Italian, Russian, Greek, Spanish, Brazil, China, European Parliament (Parlamento
   Europeo), November/October. About 10 of the 19 headlines fail only on these.
2. Spacing and script: Hanoi (evidence "Ha Noi" after folding), Kerameos (Greek is not
   transliterated by `fold`, only Cyrillic), Netology (Нетология folds to "Netologiya").
3. A common noun opening the headline: Commentary, Critics, Hundreds (the `HEADLINE_OPENERS` gap).
4. Real names that need the original script or are not in the text: Hong Kong University of Science
   and Technology (港科大), Double 11 (双11), Bomb-threat (content word): these stay rejected.

## Proposal
- (owner question, changes what readers see) Teach the check translations instead of freeing the
  names: a curated table of English place, nationality, institution and month names with their
  forms in the languages the world stream brings (rus, ukr, spa, por, ita, fra, deu, ell, zho, vie,
  ara); a name passes when one of its forms is in the evidence. The decision of 2026-11-15 ("stay
  under the name check") holds: the name must still be found in the source, in any of its forms.
- (agent) A name also passes when it equals two adjacent evidence words joined ("Ha Noi");
  Greek transliteration in `fold`; more common openers (Commentary, Critics, Analysts, Hundreds,
  Thousands).
- Estimate on these three days: about 14 of the 19 failing headlines would pass. No model call is
  added; cost unchanged.
