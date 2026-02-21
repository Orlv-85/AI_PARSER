from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import app.cli.main as cli_main
from app.config.sources import SourceConfig
from app.core.models import Article


class _Logger:
    def __init__(self) -> None:
        self.infos: list[tuple[str, dict]] = []
        self.errors: list[tuple[str, dict]] = []

    def info(self, message: str, payload: dict) -> None:
        self.infos.append((message, payload))

    def error(self, message: str, payload: dict) -> None:
        self.errors.append((message, payload))


class _SourceRepo:
    def __init__(self, session) -> None:
        self.session = session

    def upsert_source(self, source_config: SourceConfig):
        return SimpleNamespace(id=10, source_key=source_config.id)


class _ArticleRepo:
    def __init__(self, session) -> None:
        self.session = session
        self._insert_calls = 0

    def insert_article(self, **_kwargs):
        self._insert_calls += 1
        return SimpleNamespace(id=self._insert_calls), self._insert_calls == 1

    def query_top(self, *, hours: int, limit: int):
        _ = (hours, limit)
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


class _SessionCM:
    def __init__(self) -> None:
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def commit(self) -> None:
        self.committed = True


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
    logger = _Logger()
    session = _SessionCM()

    settings = SimpleNamespace(
        sources_path="sources.yaml",
        request_timeout_seconds=5.0,
        max_retries=1,
        per_source_min_interval_seconds=0.0,
    )
    sources = [
        SourceConfig(
            id="disabled",
            name="D",
            type="rss",
            url="https://example.com/d",
            enabled=False,
        ),
        SourceConfig(id="rss_ok", name="R", type="rss", url="https://example.com/r", enabled=True),
        SourceConfig(
            id="html_fail",
            name="H",
            type="html",
            url="https://example.com/h",
            enabled=True,
            html={"list_selector": "main"},
        ),
    ]

    rss_items = [
        Article(source_key="rss_ok", title="t1", url="https://example.com/1", published_at=None),
        Article(source_key="rss_ok", title="t2", url="https://example.com/2", published_at=None),
    ]

    monkeypatch.setattr(cli_main.typer, "echo", emitted.append)
    monkeypatch.setattr(cli_main, "get_settings", lambda: settings)
    monkeypatch.setattr(cli_main, "setup_json_logging", lambda: logger)
    monkeypatch.setattr(cli_main, "load_sources", lambda path: sources)
    monkeypatch.setattr(cli_main, "create_all", lambda: None)
    monkeypatch.setattr(cli_main, "Fetcher", lambda **kwargs: object())
    monkeypatch.setattr(cli_main, "SessionLocal", lambda: session)
    monkeypatch.setattr(cli_main, "SourceRepo", _SourceRepo)
    monkeypatch.setattr(cli_main, "ArticleRepo", _ArticleRepo)
    monkeypatch.setattr(cli_main, "canonicalize_url", lambda url: f"canon:{url}")
    monkeypatch.setattr(cli_main, "canonical_url_hash", lambda url: f"hash:{url}")
    monkeypatch.setattr(cli_main, "ai_relevance_score", lambda item: 0.7)
    monkeypatch.setattr(cli_main, "freshness_score", lambda dt: 0.8)
    monkeypatch.setattr(cli_main, "rank_score", lambda **kwargs: 0.9)
    monkeypatch.setattr(cli_main, "fetch_rss", lambda *args, **kwargs: rss_items)
    monkeypatch.setattr(
        cli_main,
        "fetch_html",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("network")),
    )

    cli_main.fetch(once=True)

    assert session.committed is True
    assert any("fetch complete: fetched=2 new=1 duplicates=1 errors=1" in line for line in emitted)
    assert logger.infos
    assert logger.errors


def test_fetch_command_rejects_non_once_mode() -> None:
    with pytest.raises(cli_main.typer.BadParameter):
        cli_main.fetch(once=False)


def test_top_and_search_commands(monkeypatch) -> None:
    emitted: list[str] = []

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
