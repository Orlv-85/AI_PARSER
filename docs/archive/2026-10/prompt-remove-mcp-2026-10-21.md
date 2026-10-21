# Prompt: remove the MCP server (2026-10-21)

Repository `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, `ai-news-collector`).
Read `AGENTS.md` first. Work in a separate git worktree from `origin/master`; other sessions may
work in the main folder. `venv1` is installed editable on the main folder: in the worktree run
checks with `PYTHONPATH=src ../AI_PARSER/venv1/bin/...` (adjust the relative path).

## Context

`src/app/mcp/server.py` is a stdio MCP server (`ai-news mcp-serve`, tools `news.list`, `news.get`,
`news.update`, `news.update_status`) built on `fastmcp`. It never runs in production (the app
container runs only `ai-news serve`) and has no current client. The owner decided on 2026-10-21 to
remove it. A parallel session may be splitting `storage/repos.py`
(`docs/prompt-split-repos-2026-10-21.md`); if its PR merges first, rebase.

## Remove

- `src/app/mcp/` (package), the `mcp-serve` CLI command and its import in `src/app/cli/main.py`.
- MCP settings: `mcp_auth_enabled`, `mcp_auth_token` and `validate_mcp_auth_config` in
  `src/app/config/settings.py` (`extra="ignore"` there, so a production `.env` that still has
  `AINEWS_MCP_AUTH_*` keeps loading: confirm this with a test that builds `Settings` with those
  variables set). `log_mcp_auth_event` in `src/app/observability/logging.py` if nothing else uses it.
- Tests: `tests/unit/test_mcp_server.py` and the MCP parts of `test_cli_main.py`,
  `test_settings.py`, `test_observability_logging.py`. Keep every non-MCP test.
- Dependency: `fastmcp` in `build/requirements.txt` and any MCP entry in `pyproject.toml` (mypy or
  coverage config). Check `scripts/docker_dependency_fingerprint.sh` and `build/` for references.
  After removal, list which packages leave the environment (`pip install -r build/requirements-dev.txt`
  in a fresh venv, compare with `pip freeze` of one built from `origin/master`); `httpx2` and
  `httpcore2` came in through `mcp`.
- Docs: the MCP section of `docs/cli.md`, MCP lines in `README.md`, `src/app/README.md`,
  `docs/configuration.md`, `deploy/.env.prod.example`; not `specs/` or `docs/archive/`.

## Keep (do not touch)

- `.github/workflows/deploy-*.yml` and `docker-compose.prod.yml` lines with `AINEWS_MCP_AUTH_*`:
  production-sensitive and harmless once the settings are gone; list them in the PR as a later
  cleanup.
- `web/service.py` (`UpdateRunService`) and `ArticleRepo` methods the MCP tools used, if the web app
  or CLI still uses them; if a method becomes unused, list it, do not delete it in this PR.
- The word "MCP" in `src/app/core/daily/signals_entities.py` is an AI-term entity, not this server.

## Checks

- Full gate: `make lint PYTHON=...`, full `pytest` (report the pass count and how many tests were
  removed), `scripts/check_code_docs.py` and `--diff origin/master --strict`.
- Smoke: `ai-news --help` (no `mcp-serve`), the web app factory, `ai-news serve` starts locally with
  `AINEWS_MCP_AUTH_ENABLED=true` set in the environment.
- Package build like Docker: `pip wheel --no-deps` from a clean copy; `app/mcp` is not in the wheel.

## Output

- One PR, do not merge. In your reply: the PR link; files and lines removed; packages that left the
  environment; production lines left for later; exact checks with pass counts; open questions one
  line each (how settled, or a yes/no question for the owner with a recommendation, only if it
  changes what readers see or what is paid).
- Save any prompt you write for another session to a file per `AGENTS.md`.
