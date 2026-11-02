Implemented the hidden `/bulletin` preview.

Files changed:

- [pages.md](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4c-preview-page/src/app/web/pages.md): behavior, decisions, invariants and coverage.
- [pages.py](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4c-preview-page/src/app/web/routes/pages.py): stored-row route and status responses.
- [bulletin_view.py](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4c-preview-page/src/app/web/bulletin_view.py): escaped rendering, safe links and date navigation.
- [bulletin.html](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4c-preview-page/src/app/web/bulletin.html): English template with robots metadata.
- [app.py](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4c-preview-page/src/app/web/app.py): public path registration.
- [pyproject.toml](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4c-preview-page/pyproject.toml): template packaging.
- [test_web_bulletin_page.py](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4c-preview-page/tests/unit/test_web_bulletin_page.py): preview regressions.
- [test_web_route_table.py](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4c-preview-page/tests/unit/test_web_route_table.py): pinned route and access expectations.

Expected failing-test run: `24 failed, 1 passed, 1 warning in 1.83s` (exit 1). The packaging regression also failed before its fix. Scoped validation subsequently passed 27 tests.

| Final check | Output / result | Exit |
|---|---|---:|
| Full suite | `2007 passed, 2 skipped, 8 warnings in 41.41s` | 0 |
| `make lint` | Unused fixture argument; fixed. Pylint rerun: `10.00/10`; Ruff and mypy already passed | 2 → 0 |
| CRAP | Wrote `.metrics/crap.edn` | 0 |
| Dryer | `No duplicate candidates found.` | 0 |
| Mutator | 14 sites, 14 killed, 0 survived, 0 uncovered; 100% | 0 |
| Strict code-doc | `code docs: 14 checked, ok` | 0 |

CRAP ≥10 in changed outer functions: `build_pages_router` **25.2**, `create_app` **25.0**. New view functions peak at **9.0**.

The initial mutation survivor (`> → >=` at the earliest calendar date) was killed by adding a boundary regression test.

Decided: reuse `digest.css` and explicitly package the template. PostgreSQL integration tests were skipped because `AINEWS_TEST_POSTGRES_URL` was unset. After the boundary test addition, only the failed mutation check was repeated, following the speed rule.