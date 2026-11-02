Both fixes are complete; behavior and tests remain unchanged.

- [pages.py:108](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4c-preview-page/src/app/web/routes/pages.py:108): extracted `_bulletin_response`; the route is a one-line wrapper.
- [bulletin.py:14](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4c-preview-page/src/app/web/routes/bulletin.py:14): renamed `_parse_day` to `parse_day` and updated both callers.
- [pages.md:175](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4c-preview-page/src/app/web/pages.md:175): updated the code map.

| Check | Result | Exit |
|---|---|---:|
| Scoped tests | `53 passed, 1 warning in 2.35s` | 0 |
| Ruff | `All checks passed!` | 0 |
| Full lint | mypy passed; Pylint `10.00/10` | 0 |
| Full suite | `2008 passed, 2 skipped, 8 warnings in 37.44s` | 0 |
| CRAP | Report written; metrics below | 0 |
| Strict code-doc | `code docs: 14 checked, ok` | 0 |

CRAP results: `build_pages_router` restored to **CC 21**, CRAP **21.2**; `_bulletin_response` is **CC 5**, **100% coverage**, CRAP **5.0**.

The two PostgreSQL integration tests were skipped because their test URL is unset.