from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import app.cli.main as cli_main
from app.config.sources import SourceConfig


class _ArticleRepo:
    def __init__(self, session) -> None:
        self.session = session
        self._insert_calls = 0

    def insert_article(self, **_kwargs):
        self._insert_calls += 1
        return SimpleNamespace(id=self._insert_calls), self._insert_calls == 1

    def query_top(self, *, hours: int, limit: int, min_ai_relevance: float):
        _ = (hours, limit, min_ai_relevance)
        return [
            SimpleNamespace(
                rank_score=0.9,
                published_at=datetime(2026, 2, 21, 12, 0, tzinfo=UTC),
                title="Top article",
                url_canonical="https://example.com/top",
            )
        ]

    def search(self, *, query: str, days: int):
        _ = days
        return [
            SimpleNamespace(
                published_at=datetime(2026, 2, 21, 11, 0, tzinfo=UTC),
                title=f"Result for {query}",
                url_canonical="https://example.com/result",
            )
        ]

    def count_older_than(self, *, older_than_days: int) -> int:
        _ = older_than_days
        return 7

    def prune_older_than(self, *, older_than_days: int) -> tuple[int, int]:
        _ = older_than_days
        return (7, 2)


def test_main_callback_noop() -> None:
    assert cli_main.main() is None


def test_sources_command_outputs_rows(monkeypatch) -> None:
    emitted: list[str] = []
    monkeypatch.setattr(cli_main.typer, "echo", emitted.append)
    monkeypatch.setattr(
        cli_main,
        "get_settings",
        lambda: SimpleNamespace(sources_path="sources.yaml"),
    )
    monkeypatch.setattr(
        cli_main,
        "load_sources",
        lambda path: [
            SourceConfig(id="aa", name="A", type="rss", url="https://example.com/a", enabled=True),
            SourceConfig(
                id="bb",
                name="B",
                type="html",
                url="https://example.com/b",
                enabled=False,
                html={"list_selector": "main"},
            ),
        ],
    )

    cli_main.sources()

    assert emitted[0].startswith("aa\trss\tenabled")
    assert emitted[1].startswith("bb\thtml\tdisabled")


def test_fetch_command_handles_success_duplicates_and_errors(monkeypatch) -> None:
    emitted: list[str] = []
    settings = SimpleNamespace()
    summary = SimpleNamespace(fetched=2, new=1, duplicates=1, errors=1)

    def _build_logger() -> object:
        return object()

    monkeypatch.setattr(cli_main.typer, "echo", emitted.append)
    monkeypatch.setattr(cli_main, "get_settings", lambda: settings)
    monkeypatch.setattr(cli_main, "setup_json_logging", _build_logger)
    monkeypatch.setattr(cli_main, "run_fetch_cycle", lambda **kwargs: summary)

    cli_main.fetch(once=True)

    assert any("fetch complete: fetched=2 new=1 duplicates=1 errors=1" in line for line in emitted)


def test_fetch_command_rejects_non_once_mode() -> None:
    with pytest.raises(cli_main.typer.BadParameter):
        cli_main.fetch(once=False)


def test_top_and_search_commands(monkeypatch) -> None:
    emitted: list[str] = []

    class _SessionCM:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _build_session() -> _SessionCM:
        return _SessionCM()

    monkeypatch.setattr(cli_main.typer, "echo", emitted.append)
    monkeypatch.setattr(cli_main, "create_all", lambda: None)
    monkeypatch.setattr(cli_main, "SessionLocal", _build_session)
    monkeypatch.setattr(cli_main, "ArticleRepo", _ArticleRepo)

    cli_main.top(hours=48, limit=5)
    cli_main.search(query="ai", days=3)

    assert "Top article" in emitted[0]
    assert "Result for ai" in emitted[1]


def test_serve_command(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Uvicorn:
        @staticmethod
        def run(app: str, host: str, port: int) -> None:
            captured["app"] = app
            captured["host"] = host
            captured["port"] = port

    monkeypatch.setattr(cli_main, "uvicorn", _Uvicorn)

    cli_main.serve(host="0.0.0.0", port=9000)

    assert captured == {"app": "app.web.app:app", "host": "0.0.0.0", "port": 9000}


def test_mcp_serve_command_invokes_mcp_server_runner(monkeypatch) -> None:
    calls = {"count": 0}

    def _run_mcp_server() -> None:
        calls["count"] += 1

    monkeypatch.setattr(cli_main, "run_mcp_server", _run_mcp_server, raising=False)
    monkeypatch.setattr(
        cli_main,
        "get_settings",
        lambda: SimpleNamespace(mcp_auth_enabled=False, mcp_auth_token=None),
    )

    cli_main.mcp_serve()

    assert calls["count"] == 1


def test_mcp_serve_command_rejects_missing_mcp_auth_settings_when_enabled(monkeypatch) -> None:
    calls = {"count": 0}

    def _run_mcp_server() -> None:
        calls["count"] += 1

    monkeypatch.setattr(cli_main, "run_mcp_server", _run_mcp_server, raising=False)
    monkeypatch.setattr(
        cli_main,
        "get_settings",
        lambda: SimpleNamespace(mcp_auth_enabled=True, mcp_auth_token=None),
    )

    with pytest.raises(cli_main.typer.BadParameter, match="mcp auth"):
        cli_main.mcp_serve()

    assert calls["count"] == 0


def test_mcp_serve_command_rejects_blank_mcp_auth_token_when_enabled(monkeypatch) -> None:
    calls = {"count": 0}

    def _run_mcp_server() -> None:
        calls["count"] += 1

    monkeypatch.setattr(cli_main, "run_mcp_server", _run_mcp_server, raising=False)
    monkeypatch.setattr(
        cli_main,
        "get_settings",
        lambda: SimpleNamespace(mcp_auth_enabled=True, mcp_auth_token="   "),
    )

    with pytest.raises(cli_main.typer.BadParameter, match="mcp auth"):
        cli_main.mcp_serve()

    assert calls["count"] == 0


def test_prune_command_dry_run_and_apply(monkeypatch) -> None:
    emitted: list[str] = []
    commits: list[str] = []

    class _SessionCM:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def commit(self) -> None:
            commits.append("commit")

    monkeypatch.setattr(cli_main.typer, "echo", emitted.append)
    monkeypatch.setattr(cli_main, "create_all", lambda: None)
    monkeypatch.setattr(cli_main, "SessionLocal", _SessionCM)
    monkeypatch.setattr(cli_main, "ArticleRepo", _ArticleRepo)

    cli_main.prune(older_than_days=100, dry_run=True)
    cli_main.prune(older_than_days=100, dry_run=False)

    assert "prune dry-run:" in emitted[0]
    assert "prune complete:" in emitted[1]
    assert len(commits) == 1


def test_review_batch_outcomes_command_reports_deterministic_summary(monkeypatch) -> None:
    emitted: list[str] = []

    class _SessionCM:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _BatchRepo:
        def __init__(self, session) -> None:
            self.session = session

        def get_batch(self, batch_id: int):
            return SimpleNamespace(id=batch_id)

    class _SourceCandidateRepo:
        def __init__(self, session) -> None:
            self.session = session

        def summarize_batch(self, *, batch_id: int | None):
            assert batch_id == 17
            return {
                "batch_id": 17,
                "total_candidates": 6,
                "draft_count": 1,
                "validated_count": 2,
                "approved_count": 1,
                "rejected_count": 1,
                "duplicate_count": 1,
                "pending_review_count": 3,
                "rejected_review_count": 1,
            }

    assert hasattr(
        cli_main,
        "review_batch_outcomes",
    ), "Phase 5 CLI reporting command missing: app.cli.main.review_batch_outcomes"

    monkeypatch.setattr(cli_main.typer, "echo", emitted.append)
    monkeypatch.setattr(cli_main, "create_all", lambda: None)
    monkeypatch.setattr(cli_main, "SessionLocal", _SessionCM)
    monkeypatch.setattr(cli_main, "SourceImportBatchRepo", _BatchRepo)
    monkeypatch.setattr(cli_main, "SourceCandidateRepo", _SourceCandidateRepo)

    cli_main.review_batch_outcomes(batch_id=17)

    assert emitted == [
        "batch review outcomes: batch_id=17 total=6 pending_review=3 "
        "validated=2 approved=1 rejected=1 duplicates=1",
    ]
