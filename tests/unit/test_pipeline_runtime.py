from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Literal

from app.config.settings import Settings
from app.config.sources import SourceConfig
from app.core.models import Article
from app.core.pipeline import run_fetch_cycle


class _Logger:
    def __init__(self) -> None:
        self.info_calls: list[tuple[str, dict[str, object]]] = []
        self.error_calls: list[tuple[str, dict[str, object]]] = []

    def info(self, event: str, payload: dict[str, object]) -> None:
        self.info_calls.append((event, payload))

    def error(self, event: str, payload: dict[str, object]) -> None:
        self.error_calls.append((event, payload))


class _Session:
    def __init__(self) -> None:
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> Literal[False]:
        return False

    def commit(self) -> None:
        self.committed = True


class _SourceRepo:
    def __init__(self, _session) -> None:
        pass

    def upsert_source(self, config: SourceConfig):
        return SimpleNamespace(id=abs(hash(config.id)) % 1000 + 1)


class _ArticleRepo:
    def __init__(self, _session) -> None:
        self.calls = 0

    def insert_article(self, **_kwargs):
        self.calls += 1
        return SimpleNamespace(id=self.calls), self.calls == 1


def test_run_fetch_cycle_counts_new_duplicates_and_errors(monkeypatch) -> None:
    logger = _Logger()
    session = _Session()

    configs = [
        SourceConfig(
            id="disabled",
            name="Disabled",
            type="rss",
            url="https://example.com/disabled.xml",
            enabled=False,
        ),
        SourceConfig(
            id="rss_ok",
            name="RSS OK",
            type="rss",
            url="https://example.com/feed.xml",
            enabled=True,
        ),
        SourceConfig(
            id="html_ok",
            name="HTML OK",
            type="html",
            url="https://example.com/news",
            enabled=True,
            html={"list_selector": "main", "link_selector": "a"},
        ),
        SourceConfig(
            id="rss_fail",
            name="RSS Fail",
            type="rss",
            url="https://example.com/fail.xml",
            enabled=True,
        ),
    ]

    def _fake_fetch_rss(source_key: str, *_args, **_kwargs):
        if source_key == "rss_fail":
            raise RuntimeError("boom")
        return [
            Article(
                source_key=source_key,
                title="RSS Item",
                url="https://example.com/rss-item",
                published_at=None,
                summary="sum",
                content="content",
            )
        ]

    def _fake_fetch_html(_config, *_args, **_kwargs):
        return [
            Article(
                source_key="html_ok",
                title="HTML Item",
                url="https://example.com/html-item",
                published_at=datetime(2026, 2, 21, 10, 0, tzinfo=UTC),
                summary=None,
                content=None,
            )
        ]

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _SourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _ArticleRepo)
    monkeypatch.setattr("app.core.pipeline.fetch_rss", _fake_fetch_rss)
    monkeypatch.setattr("app.core.pipeline.fetch_html", _fake_fetch_html)
    monkeypatch.setattr("app.core.pipeline.canonicalize_url", lambda u: f"c:{u}")
    monkeypatch.setattr("app.core.pipeline.canonical_url_hash", lambda u: f"h:{u}")
    monkeypatch.setattr("app.core.pipeline.ai_relevance_score", lambda _item: 0.5)
    monkeypatch.setattr("app.core.pipeline.freshness_score", lambda _dt: 0.5)
    monkeypatch.setattr("app.core.pipeline.rank_score", lambda **_kwargs: 0.5)

    settings = Settings(sources_path="sources.yaml")
    summary = run_fetch_cycle(settings=settings, logger=logger)

    assert summary.fetched == 2
    assert summary.new == 1
    assert summary.duplicates == 1
    assert summary.errors == 1
    assert session.committed is True
    assert any(event == "source_fetch_failed" for event, _ in logger.error_calls)
    assert any(event == "fetch_run_finished" for event, _ in logger.info_calls)


def test_run_fetch_cycle_handles_no_enabled_sources(monkeypatch) -> None:
    logger = _Logger()
    session = _Session()

    configs = [
        SourceConfig(
            id="disabled_only",
            name="Disabled",
            type="rss",
            url="https://example.com/disabled.xml",
            enabled=False,
        )
    ]

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _SourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _ArticleRepo)

    def _unexpected(*_args, **_kwargs):
        raise AssertionError("fetcher should not be called when all sources are disabled")

    monkeypatch.setattr("app.core.pipeline.fetch_rss", _unexpected)
    monkeypatch.setattr("app.core.pipeline.fetch_html", _unexpected)

    settings = Settings(sources_path="sources.yaml")
    summary = run_fetch_cycle(settings=settings, logger=logger)

    assert summary.fetched == 0
    assert summary.new == 0
    assert summary.duplicates == 0
    assert summary.errors == 0
    assert session.committed is True
