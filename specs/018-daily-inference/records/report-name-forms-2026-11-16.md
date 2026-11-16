# Report: translated name forms for the writer's name check (2026-11-16)

Implementer: background Claude agent (Sonnet), prompt `prompt-name-forms-2026-11-16.md`; saved by
the coordinator from the agent's final message, shortened.

## Done
- `src/app/core/bulletin/name_forms.json`: 97 keys (countries and nationalities with plurals,
  `us`/`uk`/`eu`, 10 institution words, months, weekdays); forms in rus, ukr, spa, por, ita, fra,
  deu, ell, zho, vie, ara and English variants. Packaged in `pyproject.toml`.
- `writer_grounding.py`: `NAME_FORMS_PATH`, `load_name_forms` (folds, validates, compiles),
  `_form_pattern`, `_name_words` (table keys with a form in the text, adjacent tokens joined);
  Greek transliteration in `fold`; `HEADLINE_OPENERS` + Commentary Critics Analysts Hundreds
  Thousands Dozens. `WRITER_VERSION` `bulletin-writer-8`. `writer.md` Grounding check 5, Decisions.
- Tests in `tests/unit/test_bulletin_writer_names.py`, each failed first on `unsupported_name`
  (or the stub `ValueError`); `test_name_without_its_form_still_fails` is a guard.
- Agent decisions: a non-Latin form may have 2 characters ("中国"); no Chinese digit months ("1月"
  is inside "11月"); no 2-letter "UE".

## Coordinator changes
- Forms that collided with common words after folding were narrowed, test first (new cases of
  `test_name_without_its_form_still_fails`, all failed first): "gree*" (green) -> "greek*",
  "greec*"; "franc*" (franchise), "franz*" (Franz), Greek "Γαλλ*"/"Γάλλ*" (gallery) -> exact or
  longer forms; "russ*" (Russell) -> "russi*", "russo", "russe", "russes", "russland"; May "mai"
  removed (Vietnamese "ngay mai" = tomorrow).

## Check on real data (2026-11-12..14, model answers replayed from the prod journal)
| Texts | name fails before | after |
| --- | --- | --- |
| headlines, stories in other languages | 17/22 | 6/22 |
| sentences, stories in other languages | 105/162 | 79/162 |
| headlines, English | 2/13 | 0/13 |
| sentences, English | 14/98 | 5/98 |
All 13 headlines that now pass rest on honest translations (Hanoi, Russian, European Parliament,
Greek, US, Commentary, Critics, European).

## Checks
- Agent: bulletin/web/layer/monkeypatch/code-docs/deepseek-digest tests rc=0; ruff clean; pylint
  10.00; crapper with coverage: new functions under 10 (`_form_pattern` 7.1); dryer: none.
  crapper showed untouched `_promote_reserve` at 26.8 only because its tests were outside that
  coverage run.
- Coordinator after the table edits: `test_bulletin_writer_names.py` rc=0.

## Review 1 (fresh Claude agent, Sonnet, `prompt-name-forms-review-2026-11-16.md`)
Verdict: do not ship as is; code sound, the table had many false passes (Cyrillic/Greek forms
folded to Latin prefixes matched Latin words; Vietnamese syllables). Fixed by the coordinator,
tests first (`test_common_words_of_other_languages_ground_no_name`,
`test_inflected_and_vietnamese_forms_ground_a_name`, `test_duplicate_name_forms_key_is_rejected`,
new bad case of `test_name_forms_table_is_valid`; all failed first):
- Code: a `*` before the end is rejected (dead form "Соединенн* Штат*"); duplicate keys rejected;
  Arabic forms are word-bounded like Latin, only Chinese/Japanese forms are substrings; `fold` maps
  đ, ß, ł, ø (Vietnamese "Đại học", "Ấn Độ" now match).
- Data: dropped "usa", "ΗΠΑ", "marco", "مارس", "Март", "Май", "thang sau", "thang nam", Vietnamese
  weekday ordinals, "phap", "Đức" (-> "nuoc duc"), "Среда..", "Ελλάς", "Суд", "Суда", "corte",
  "rossi*", "nga", "russo", "polen", "bretagne", "印度"; narrowed "Инди*", "Ινδί*", "Ρωσι*", "Τριτ*",
  "Греч*", "Серп*", "kore*", "تركي*", "عرب*", Greek China "κινα*" and bank "Τράπεζ*" (kinase,
  trapeze: found by a scan of every Latin form against /usr/share/dict/words).
- Kept, documented: generic keys (court, council, bank) ground the common noun; joined words
  ignore punctuation.
After the fixes: real-data check unchanged (foreign headlines 6/22 fail, English 0/13); scoped
tests rc=0; ruff clean; pylint 10.00; crapper with coverage: `_form_pattern` 9.1, rest lower;
dryer none.

## Review 2 (fresh Claude agent, Sonnet, `prompt-name-forms-review-2-2026-11-16.md`)
Code fixes of review 1 confirmed. Found, fixed by the coordinator test first
(`test_plain_latin_words_do_not_join_into_a_name`, eight new cases of
`test_common_words_of_other_languages_ground_no_name`; all failed first):
- Joined words grounded any name from plain English ("met a" -> Meta, "I ran" -> Iran). Now only
  adjacent words with letters outside ASCII join (`_name_words(raw, text)`).
- Data: Chinese "周X"/"週X" (每周三次), Greek weekdays that are ordinals (Δευτέρα, Τρίτη, Τετάρτη,
  Πέμπτη, Παρασκευ*), Κυριακ* (Kyriakos) -> exact; Росси* (Rossi), Франц* (Franz, Франциск),
  frances* (Francesco), franca, Γάλλος (gallos), "nuoc phap" (nha nuoc phap quyen), Грудн*, Квіт*,
  Лют*, mayo (Mayo Clinic), india* (Indiana), "an do" (an do), arab*/Араб* (arable), "a rap",
  german*/Германи*/Γερμαν* (germanium), gericht* (gerichtet), banco (banco de datos), austral*,
  espan* (espanto), "thang muoi" (prefix of November/December) replaced or dropped. Added
  "البرتغال".
- Left, documented or low: council words also mean advice; julio, domingo, mars, Мая (Maya),
  turk* (Turku), ital* (italic), u.s (u.s.w.).
After: real-data check unchanged (foreign headlines 6/22 fail, English 0/13); scoped tests rc=0;
ruff clean; pylint 10.00; crapper `_form_pattern` 9.1, `_name_words` 3.

## Review 3 (fresh Claude agent, Sonnet, narrow: `prompt-name-forms-review-3-2026-11-16.md`)
Ship-able. Fixed by the coordinator, test first (new cases, failed first): Cyrillic and Greek
words no longer join ("и ран" grounded "Iran"): only accented Latin words join; "Совет*" (Советский
Союз) -> case forms and "Совбез*"; "frances" (the name Frances) -> "franceses", "francesa*";
"arabe*" (arabesque) -> exact; "polon*" (polonium) -> exact forms. Left as low: "nuoc y",
"Середа" (surname), "Воскресен*" (Resurrection); Vietnamese "Ấn Độ" no longer grounds India
(safe direction). Scoped tests rc=0, ruff clean, pylint 10.00. No fourth review: the last fixes
are one condition and four forms, each pinned by a test.
