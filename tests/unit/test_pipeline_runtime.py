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
    assert summary.not_modified_sources == 0
    assert summary.skipped_known_html_links == 0
    assert summary.early_stop_hits == 0
    assert session.committed is True
    assert any(event == "source_fetch_failed" for event, _ in logger.error_calls)
    fetch_finished_payload = next(
        payload for event, payload in logger.info_calls if event == "fetch_run_finished"
    )
    assert fetch_finished_payload["not_modified_sources"] == 0
    assert fetch_finished_payload["skipped_known_html_links"] == 0
    assert fetch_finished_payload["early_stop_hits"] == 0
    assert any(event == "source_fetch_finished" for event, _ in logger.info_calls)


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


def test_run_fetch_cycle_stops_rss_processing_after_known_streak(monkeypatch) -> None:
    logger = _Logger()
    session = _Session()

    configs = [
        SourceConfig(
            id="rss_feed",
            name="RSS Feed",
            type="rss",
            url="https://example.com/feed.xml",
            enabled=True,
        )
    ]
    rss_items = [
        Article(
            source_key="rss_feed",
            title="Old 1",
            url="https://example.com/old-1",
            published_at=None,
            summary=None,
            content=None,
        ),
        Article(
            source_key="rss_feed",
            title="Old 2",
            url="https://example.com/old-2",
            published_at=None,
            summary=None,
            content=None,
        ),
        Article(
            source_key="rss_feed",
            title="New 3",
            url="https://example.com/new-3",
            published_at=None,
            summary=None,
            content=None,
        ),
    ]

    class _TrackingArticleRepo:
        last_instance = None

        def __init__(self, _session) -> None:
            self.exists_calls: list[str] = []
            self.insert_calls: list[str] = []
            self._known = {"h:https://example.com/old-1", "h:https://example.com/old-2"}
            _TrackingArticleRepo.last_instance = self

        def exists_by_canonical_hash(self, canonical_hash: str) -> bool:
            self.exists_calls.append(canonical_hash)
            return canonical_hash in self._known

        def insert_article(self, **kwargs):
            self.insert_calls.append(kwargs["url_canonical_hash"])
            return SimpleNamespace(id=len(self.insert_calls)), True

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _SourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _TrackingArticleRepo)
    monkeypatch.setattr("app.core.pipeline.fetch_rss", lambda *_args, **_kwargs: rss_items)
    monkeypatch.setattr("app.core.pipeline.fetch_html", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.core.pipeline.canonicalize_url", lambda u: f"c:{u}")
    monkeypatch.setattr("app.core.pipeline.canonical_url_hash", lambda u: f"h:{u}")
    monkeypatch.setattr("app.core.pipeline.ai_relevance_score", lambda _item: 0.5)
    monkeypatch.setattr("app.core.pipeline.freshness_score", lambda _dt: 0.5)
    monkeypatch.setattr("app.core.pipeline.rank_score", lambda **_kwargs: 0.5)

    settings = SimpleNamespace(
        sources_path="sources.yaml",
        request_timeout_seconds=1.0,
        max_retries=0,
        concurrency_limit=1,
        per_source_min_interval_seconds=0.0,
        rss_extract_full_text=False,
        rss_full_text_max_items_per_source=0,
        rss_full_text_concurrency_limit=None,
        rss_known_streak_stop=2,
    )

    summary = run_fetch_cycle(settings=settings, logger=logger)
    repo = _TrackingArticleRepo.last_instance
    assert repo is not None

    assert summary.fetched == 3
    assert repo.exists_calls == [
        "h:https://example.com/old-1",
        "h:https://example.com/old-2",
    ]
    assert repo.insert_calls == []
    assert summary.new == 0
    assert summary.duplicates == 2


def test_run_fetch_cycle_rss_known_streak_stop_does_not_apply_to_html(monkeypatch) -> None:
    logger = _Logger()
    session = _Session()

    configs = [
        SourceConfig(
            id="rss_feed",
            name="RSS Feed",
            type="rss",
            url="https://example.com/feed.xml",
            enabled=True,
        ),
        SourceConfig(
            id="html_feed",
            name="HTML Feed",
            type="html",
            url="https://example.com/news",
            enabled=True,
            html={"list_selector": "main", "link_selector": "a"},
        ),
    ]
    rss_items = [
        Article(
            source_key="rss_feed",
            title="RSS Old 1",
            url="https://example.com/rss-old-1",
            published_at=None,
            summary=None,
            content=None,
        ),
        Article(
            source_key="rss_feed",
            title="RSS Old 2",
            url="https://example.com/rss-old-2",
            published_at=None,
            summary=None,
            content=None,
        ),
        Article(
            source_key="rss_feed",
            title="RSS New 3",
            url="https://example.com/rss-new-3",
            published_at=None,
            summary=None,
            content=None,
        ),
    ]
    html_items = [
        Article(
            source_key="html_feed",
            title="HTML 1",
            url="https://example.com/html-1",
            published_at=datetime(2026, 2, 21, 10, 0, tzinfo=UTC),
            summary=None,
            content=None,
        ),
        Article(
            source_key="html_feed",
            title="HTML 2",
            url="https://example.com/html-2",
            published_at=datetime(2026, 2, 21, 10, 1, tzinfo=UTC),
            summary=None,
            content=None,
        ),
        Article(
            source_key="html_feed",
            title="HTML 3",
            url="https://example.com/html-3",
            published_at=datetime(2026, 2, 21, 10, 2, tzinfo=UTC),
            summary=None,
            content=None,
        ),
    ]

    class _TrackingArticleRepo:
        last_instance = None

        def __init__(self, _session) -> None:
            self.exists_calls: list[str] = []
            self.insert_calls: list[str] = []
            self._known = {
                "h:https://example.com/rss-old-1",
                "h:https://example.com/rss-old-2",
            }
            _TrackingArticleRepo.last_instance = self

        def exists_by_canonical_hash(self, canonical_hash: str) -> bool:
            self.exists_calls.append(canonical_hash)
            return canonical_hash in self._known

        def insert_article(self, **kwargs):
            self.insert_calls.append(kwargs["url_canonical_hash"])
            return SimpleNamespace(id=len(self.insert_calls)), True

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _SourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _TrackingArticleRepo)
    monkeypatch.setattr("app.core.pipeline.fetch_rss", lambda *_args, **_kwargs: rss_items)
    monkeypatch.setattr("app.core.pipeline.fetch_html", lambda *_args, **_kwargs: html_items)
    monkeypatch.setattr("app.core.pipeline.canonicalize_url", lambda u: f"c:{u}")
    monkeypatch.setattr("app.core.pipeline.canonical_url_hash", lambda u: f"h:{u}")
    monkeypatch.setattr("app.core.pipeline.ai_relevance_score", lambda _item: 0.5)
    monkeypatch.setattr("app.core.pipeline.freshness_score", lambda _dt: 0.5)
    monkeypatch.setattr("app.core.pipeline.rank_score", lambda **_kwargs: 0.5)

    settings = SimpleNamespace(
        sources_path="sources.yaml",
        request_timeout_seconds=1.0,
        max_retries=0,
        concurrency_limit=1,
        per_source_min_interval_seconds=0.0,
        rss_extract_full_text=False,
        rss_full_text_max_items_per_source=0,
        rss_full_text_concurrency_limit=None,
        rss_known_streak_stop=2,
    )

    summary = run_fetch_cycle(settings=settings, logger=logger)
    repo = _TrackingArticleRepo.last_instance
    assert repo is not None

    assert summary.fetched == 6
    assert repo.exists_calls == [
        "h:https://example.com/rss-old-1",
        "h:https://example.com/rss-old-2",
    ]
    assert repo.insert_calls == [
        "h:https://example.com/html-1",
        "h:https://example.com/html-2",
        "h:https://example.com/html-3",
    ]
    assert summary.new == 3
    assert summary.duplicates == 2


def test_run_fetch_cycle_resets_rss_known_streak_on_new_item(monkeypatch) -> None:
    logger = _Logger()
    session = _Session()

    configs = [
        SourceConfig(
            id="rss_feed",
            name="RSS Feed",
            type="rss",
            url="https://example.com/feed.xml",
            enabled=True,
        )
    ]
    rss_items = [
        Article(
            source_key="rss_feed",
            title="Old 1",
            url="https://example.com/old-1",
            published_at=None,
            summary=None,
            content=None,
        ),
        Article(
            source_key="rss_feed",
            title="New 2",
            url="https://example.com/new-2",
            published_at=None,
            summary=None,
            content=None,
        ),
        Article(
            source_key="rss_feed",
            title="Old 3",
            url="https://example.com/old-3",
            published_at=None,
            summary=None,
            content=None,
        ),
    ]

    class _TrackingArticleRepo:
        last_instance = None

        def __init__(self, _session) -> None:
            self.exists_calls: list[str] = []
            self.insert_calls: list[str] = []
            self._known = {"h:https://example.com/old-1", "h:https://example.com/old-3"}
            _TrackingArticleRepo.last_instance = self

        def exists_by_canonical_hash(self, canonical_hash: str) -> bool:
            self.exists_calls.append(canonical_hash)
            return canonical_hash in self._known

        def insert_article(self, **kwargs):
            self.insert_calls.append(kwargs["url_canonical_hash"])
            return SimpleNamespace(id=len(self.insert_calls)), True

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _SourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _TrackingArticleRepo)
    monkeypatch.setattr("app.core.pipeline.fetch_rss", lambda *_args, **_kwargs: rss_items)
    monkeypatch.setattr("app.core.pipeline.fetch_html", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.core.pipeline.canonicalize_url", lambda u: f"c:{u}")
    monkeypatch.setattr("app.core.pipeline.canonical_url_hash", lambda u: f"h:{u}")
    monkeypatch.setattr("app.core.pipeline.ai_relevance_score", lambda _item: 0.5)
    monkeypatch.setattr("app.core.pipeline.freshness_score", lambda _dt: 0.5)
    monkeypatch.setattr("app.core.pipeline.rank_score", lambda **_kwargs: 0.5)

    settings = SimpleNamespace(
        sources_path="sources.yaml",
        request_timeout_seconds=1.0,
        max_retries=0,
        concurrency_limit=1,
        per_source_min_interval_seconds=0.0,
        rss_extract_full_text=False,
        rss_full_text_max_items_per_source=0,
        rss_full_text_concurrency_limit=None,
        rss_known_streak_stop=2,
    )

    summary = run_fetch_cycle(settings=settings, logger=logger)
    repo = _TrackingArticleRepo.last_instance
    assert repo is not None

    assert repo.exists_calls == [
        "h:https://example.com/old-1",
        "h:https://example.com/new-2",
        "h:https://example.com/old-3",
    ]
    assert repo.insert_calls == ["h:https://example.com/new-2"]
    assert summary.new == 1
    assert summary.duplicates == 2
