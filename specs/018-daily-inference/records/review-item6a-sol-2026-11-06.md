No blockers or should-fix findings.

- **Nit — stale styling decision.** [pages.md:164](src/app/web/pages.md:164) still says the preview reuses public digest styles, contradicting the dedicated stylesheet. Remove that clause or describe `bulletin.css`.

- **Nit — incomplete Behavior-to-test references.** [pages.md:85](src/app/web/pages.md:85) names tests that do not assert the date; [pages.md:101](src/app/web/pages.md:101) names a checking-block test that checks `assessed` but not writer diagnostics; [pages.md:119](src/app/web/pages.md:119) omits the test covering newly rendered issue fields. Add `test_bulletin_page_shows_ready_day` to the first two rules and `test_bulletin_page_escapes_issue_fields` to the escaping rule.

- **Nit — nullable payload regression coverage is incomplete.** The fixture at [test_web_bulletin_page.py:58](tests/unit/test_web_bulletin_page.py:58) always supplies a non-null issue headline and rubric name. The cases at [test_web_bulletin_page.py:258](tests/unit/test_web_bulletin_page.py:258) also omit zero incidents with a populated incident story and empty source links. Add those cases with assertions scoped to reader sections. Current handling is correct for builder-produced payloads, but these branches lack regression protection.

No findings in:

- **Payload rendering:** nullable story headlines fall back to titles; missing/None reactions are omitted; zero incidents suppress the incident section; empty links render without crashing. Required top-level keys are always emitted by `Bulletin.as_dict()`; absent keys raise `KeyError`. A rubric story paired with a null name renders “None”, but the builder never produces that combination.
- **Escaping and links:** displayed stored values are escaped; only HTTP/HTTPS source URLs become links.
- **Structure and scope:** issue order, section names, story content, empty-section omission and interim digest links match the instructions. Routes, switches, storage, `digest.css` and other pages are unchanged.
- **CSS inspection:** no obvious phone overflow risk; long text and `pre` wrap, dark text colours appear readable, and links/disclosure controls have visible focus states. This was static inspection, without browser verification.

Test result: **70 passed, 1 warning in 3.02s** — existing Starlette/httpx deprecation warning.