# Item 6a: bulletin preview design

Implementation: 2026-11-05. Final checks continued 2026-11-06 under
`prompt-item6a-codex-continue-2026-11-06.md`.

## What changed

- `src/app/web/pages.md`: current behavior, decisions, named tests and stylesheet code map.
- `src/app/web/bulletin_view.py`: complete stored issue in voice order, section headings,
  byline, source links, reactions, cut-headline footnote, full-report link and collapsed diagnostics.
  During final checks, extracted status rendering into `_status` to meet the CRAP threshold;
  no output behavior changed.
- `src/app/web/bulletin.html`: shared masthead, semantic shell and satire/GDELT footer.
- `src/app/web/static/css/bulletin.css`: dedicated system-font design, paper/ink palette,
  single-column phone layout, two story columns on wider screens, dark palette and focus states.
- `tests/unit/test_web_bulletin_page.py`: issue structure, empty sections, shared HTML states,
  metadata placement, asset/viewport contract, escaping and stored text regression checks.
  Existing tests remain, with layout assertions updated for the requested presentation.
- `tests/unit/test_web_static_assets.py`: register the bulletin stylesheet in the asset checks.
- This report.

Routes, APIs, publishing switches, storage, the public digest and its stylesheet are unchanged.
The preview remains public, unlinked and `noindex, nofollow`. No JavaScript or external assets
were added. Sample content was not copied into git.

## Decisions and questions settled

- Found in Q1/Q2 and the 2026-10-31 attribution decision: official masthead, serif typography,
  columns, satire notice and linked GDELT credit.
- decided 2026-11-05 (agent): use warm paper/ink colours, restrained rules and system serif/sans
  stacks; no external fonts, cookies, tracking or asset requests.
- decided 2026-11-05 (agent): put columns within each section so voice order stays consistent;
  wrap text and provide roomy source, navigation and disclosure targets.
- Found in the item 6a prompt: full report uses the stored items count but links to `/?date=D`;
  diagnostics live in one native collapsed "For checking" block after date navigation.
- decided 2026-11-05 (agent): display stored reactions and the existing phrase library's
  cut-headline footnote to preserve the complete issue without generating editorial text.
- Found in `_bulletin_response` and `parse_day`: malformed dates already return JSON 400 before
  HTML rendering. Preserve this response because routes must remain unchanged; shared-shell
  tests cover ready, skipped, missing, empty-store and storage-error HTML pages. Converting 400
  to an HTML page would require a separately authorized route change.
- decided 2026-11-06 (agent): extract the status-page helper after CRAP measured the combined
  renderer at 10.0; this reduces branch complexity without changing the requested presentation.

## Owner's answer on the look

Coordinator rendered 2026-11-04 (dark, light) and a skipped day at 360/390 px and 1280 px in
headless Chrome (phone widths through an iframe; no horizontal scroll) and asked on 2026-11-06:
"Так выглядит главная газета; оставляем?" Owner: "да".

Owner, same day, for 6b: "да" to showing a plain reader sentence instead of the stored skip
reason code (`no_assessments`) once the bulletin is on `/`.

## Render handoff

Script: `/private/tmp/item6a-render/render.py` (outside git).

It reads only the three `<date>.stored` objects from the specified private sample file,
reconstructs Bulletin/Story values, saves through `BulletinRepo` into temporary SQLite databases,
and renders through FastAPI `TestClient`. All three sample rows are ready, so it adds a synthetic
skipped row for 2026-11-01 with reason `no_assessments`. Temporary databases are removed on exit.
The script ran successfully once, with these six outputs and inline CSS:

| Output | HTTP result |
| --- | --- |
| `/private/tmp/item6a-render/bulletin-2026-11-02.html` | 200 |
| `/private/tmp/item6a-render/bulletin-2026-11-03.html` | 200 |
| `/private/tmp/item6a-render/bulletin-2026-11-04.html` | 200 |
| `/private/tmp/item6a-render/skipped.html` | 200 |
| `/private/tmp/item6a-render/missing.html` | 404 |
| `/private/tmp/item6a-render/empty.html` | 404 |

Open these files directly for static inspection. Their date/source/report links retain the live
page URLs; relative navigation requires the local app rather than a file URL.

## Validation

All commands run from this worktree, using the main folder's virtualenv, `PYTHONPATH=src` and
`PYTHONDONTWRITEBYTECODE=1`. No network, production access, paid calls, agents, commit, push or
`gh` commands were used.

- TDD: initial scoped run **20 failed, 24 passed**. New requirements failed on the missing issue
  structure, masthead/footer, checking block and stylesheet. The extra proposed HTML 400
  assertion was removed after confirming the existing JSON contract and route restriction.
- Scoped bulletin/route tests: **43 passed**, one existing Starlette/httpx deprecation warning.
- Scoped Ruff: **passed** on all changed Python files.
- Full pytest: **2326 passed, 2 skipped**, recorded by the continuation prompt from the completed
  previous run; not repeated at the start of this continuation.
- `make lint`: **passed**; Ruff clean, mypy **274 source files** with no issues, pylint **10.00/10**.
- `scripts/check_code_docs.py`: **passed, 15 checked**.
- Initial Crapper run: **threshold failure**, renderer CRAP **10.0** (required strictly below 10),
  despite tool exit status 0. Its coverage collection passed **2326 tests, 2 skipped**.
  After extracting `_status`, the bulletin/route tests again passed **43 tests**.
- Crapper after the fix: **passed**, all **12 functions** at **100% reported coverage** and CRAP
  below 10; maximum **7.0** (`_status`), public renderer **4.0**. Its coverage collection again
  passed **2326 tests, 2 skipped**. Report: `.metrics/crap.edn`.
- Dryer at threshold **0.8**: **passed, 0 duplicate candidates**. Report: `.metrics/dry.edn`.
- Mutator with existing coverage and the two bulletin/route test files: initially **17 killed,
  0 survived, 3 uncovered**. The three concatenation operators on continuation lines 81-83
  match the existing `mutator-lcov-multiline-sites-uncovered` troubleshooting case. A follow-up
  with `--no-coverage --lines 81,82,83` and the same test command killed all three. Final merged
  result: **20 killed, 0 survived, 0 uncovered, 100% score**. No survivor waivers or additional
  tests needed. Report: `.metrics/mutate/app.web.bulletin_view.edn`.
- Final standalone full pytest after the helper extraction: **passed, 2326 passed, 2 skipped**,
  one existing Starlette/httpx deprecation warning (161.37 seconds).
- Final `git diff --check`: **passed**, no whitespace errors.

The quality-tool commands used `PIP_NO_INDEX=1`; crapper and mutator also used the main virtualenv
first on `PATH`, exactly as specified. Lint and code-doc checks were not repeated after the
behavior-preserving helper extraction, following the continuation's instruction to rerun only
the failed check and bulletin tests, then full pytest at the end. The existing troubleshooting
entry covered the LCOV issue, so no duplicate case was added.

## Not run and handoff limits

- The two PostgreSQL integration tests are skipped because `AINEWS_TEST_POSTGRES_URL` is not
  set (`test_article_upsert_postgres.py`, `test_bulletin_store_postgres.py`). SQLite-backed
  rendering and the rest of the suite run locally; no production database is used.
- As explicitly required by the Codex override, this executor did not run a local web server,
  take screenshots, create an Artifact or ask the owner about appearance. Browser verification
  at 360/390 px, tablet and desktop widths, overflow checks and light/dark visual review remain
  with the coordinator. HTML tests alone cannot establish those visual properties.
- No separate document review or sub-agent was spawned; the coordinator's separate review
  covers the doc and implementation.

## Open points for 6b

- Skipped day on `/`: replace the stored reason code with a plain reader sentence (owner yes 2026-11-06).
- Move the bulletin to `/` behind `bulletin_home_page`; move the digest to `/daily` and then
  switch full-report and skipped-day links to the intended digest URL.
- Hide the checking block on the home page and implement the FR-023 page counter in 6b.
- No additional owner product or budget question is pending in this executor session.

For any further session prompt: save it first in `specs/018-daily-inference/records/`, never
overwrite earlier prompts, and give the owner a link to that saved file.
