# Report: whole-word name check of stored daily briefs (2026-10-30)

## Question

`parse_brief` accepts a capitalized word of a brief sentence when it occurs as a substring of the
cited text, names and publishers (`signals_brief.py`, rule `unsupported_name`), so an invented
"Meta" would pass next to "metadata". Would a whole-word check catch invented names in practice,
and how many briefs would it reject?

## Method

- Read-only export from production: every `daily_signal_briefs` row with its day's
  `daily_signal_reports.payload` and published digest items (20 days, 2026-10-10..2026-10-29).
- Local script: rebuild each packet with `brief_packet`, compare `input_hash` with the stored one,
  map stored sentence links back to article ids, and test every capitalized word that passes the
  substring rule against a whole-word match. No provider calls.

## Result

| | |
| --- | --- |
| Brief rows | 20: 18 `ok`, 2 `invalid` (2026-10-14: `quote_not_found`, `sentence_count`; 2026-10-29: `sentence_count` twice) |
| Packet rebuilt exactly (`input_hash` match) | 12 of 18 `ok`; 6 differ (the snapshot or publisher mapping changed after the brief) |
| Sentences checked | about 75 |
| Words passing only as a substring | 2, both "Verge" in "The Verge" (publisher `theverge.com`, context name `theverge`) |
| Invented names found | 0 |

## Conclusion

The substring rule let no invented name through in the stored briefs. A plain whole-word rule
would have rejected 2 correct publisher attributions and found nothing. Decision (agent,
2026-10-30): keep the rule; no `BRIEF_VERSION` bump, no paid regeneration. Revisit with a
whole-word rule that also splits publisher domains ("theverge" -> "the verge") if an invented
name is ever found.
