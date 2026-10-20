# pylint: disable=too-many-lines
from contextlib import nullcontext
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any, ClassVar, Literal

from app.config.settings import Settings
from app.config.sources import SourceConfig
from app.core.models import Article
from app.core.pipeline import _managed_source_to_config, run_fetch_cycle


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

    def begin_nested(self):
        return nullcontext()


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


def test_managed_source_to_config_adds_empty_html_payload_for_html_sources() -> None:
    managed = SimpleNamespace(
        source_key="managed-html",
        name="Managed HTML",
        type="html",
        url="https://example.com/html",
        enabled=True,
        fetch_interval_minutes=30,
        source_weight=1.2,
    )

    config = _managed_source_to_config(managed)

    assert config.type == "html"
    assert config.html is not None
    assert config.html.list_selector is None
    assert config.html.link_selector is None


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


def test_run_fetch_cycle_includes_db_enabled_sources_without_sources_yaml_edits(
    monkeypatch,
) -> None:
    logger = _Logger()
    session = _Session()
    fetched_source_keys: list[str] = []

    managed_source = SimpleNamespace(
        id=77,
        source_key="managed-approved",
        name="Managed Approved",
        type="rss",
        url="https://example.com/managed-approved.xml",
        enabled=True,
        fetch_interval_minutes=30,
        source_weight=1.0,
    )

    class _DbOnlySourceRepo:
        def __init__(self, _session) -> None:
            pass

        def upsert_source(self, config: SourceConfig):
            return SimpleNamespace(id=abs(hash(config.id)) % 1000 + 1)

        def list_enabled_sources(self):
            return [managed_source]

        def get_fetch_state(self, *, source_id: int):
            assert source_id == managed_source.id
            return {
                "etag": None,
                "last_modified": None,
                "last_checked_at": None,
                "last_status_code": None,
            }

    def _fake_fetch_rss(source_key: str, *_args, **_kwargs):
        fetched_source_keys.append(source_key)
        return [
            Article(
                source_key=source_key,
                title="Managed Item",
                url="https://example.com/managed-item",
                published_at=None,
                summary=None,
                content=None,
            )
        ]

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: [])
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _DbOnlySourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _ArticleRepo)
    monkeypatch.setattr("app.core.pipeline.fetch_rss", _fake_fetch_rss)
    monkeypatch.setattr("app.core.pipeline.canonicalize_url", lambda u: f"c:{u}")
    monkeypatch.setattr("app.core.pipeline.canonical_url_hash", lambda u: f"h:{u}")
    monkeypatch.setattr("app.core.pipeline.ai_relevance_score", lambda _item: 0.5)
    monkeypatch.setattr("app.core.pipeline.freshness_score", lambda _dt: 0.5)
    monkeypatch.setattr("app.core.pipeline.rank_score", lambda **_kwargs: 0.5)

    summary = run_fetch_cycle(settings=Settings(sources_path="sources.yaml"), logger=logger)

    assert fetched_source_keys == ["managed-approved"]
    assert summary.fetched == 1
    assert summary.new == 1
    assert summary.errors == 0


def test_run_fetch_cycle_rss_fast_profile_fetches_rss_before_html(monkeypatch) -> None:
    logger = _Logger()
    session = _Session()
    order: list[str] = []

    configs = [
        SourceConfig(
            id="html_first",
            name="HTML First",
            type="html",
            url="https://example.com/html-first",
            enabled=True,
            html={"list_selector": "main", "link_selector": "a"},
        ),
        SourceConfig(
            id="rss_first",
            name="RSS First",
            type="rss",
            url="https://example.com/rss-first.xml",
            enabled=True,
        ),
        SourceConfig(
            id="html_second",
            name="HTML Second",
            type="html",
            url="https://example.com/html-second",
            enabled=True,
            html={"list_selector": "main", "link_selector": "a"},
        ),
        SourceConfig(
            id="rss_second",
            name="RSS Second",
            type="rss",
            url="https://example.com/rss-second.xml",
            enabled=True,
        ),
    ]

    class _ImmediateFuture:
        def __init__(self, result):
            self._result = result

        def result(self):
            return self._result

    class _ImmediateExecutor:
        def __init__(self, *, max_workers: int) -> None:
            self.max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> Literal[False]:
            return False

        def submit(self, fn, **kwargs):
            return _ImmediateFuture(fn(**kwargs))

    def _fake_fetch_source_items(*, config, **_kwargs):
        order.append(config.id)
        return []

    def _immediate_as_completed(futures):
        return list(futures)

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _SourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _ArticleRepo)
    monkeypatch.setattr("app.core.pipeline._fetch_source_items", _fake_fetch_source_items)
    monkeypatch.setattr("app.core.pipeline.ThreadPoolExecutor", _ImmediateExecutor)
    monkeypatch.setattr("app.core.pipeline.as_completed", _immediate_as_completed)

    settings = SimpleNamespace(
        sources_path="sources.yaml",
        concurrency_limit=1,
        rss_full_text_concurrency_limit=None,
        fetch_execution_profile="rss_fast",
        fetch_emit_source_metrics=False,
    )

    summary = run_fetch_cycle(settings=settings, logger=logger)

    assert summary.errors == 0
    assert order == ["rss_first", "rss_second", "html_first", "html_second"]


def test_run_fetch_cycle_execution_profile_applies_per_type_concurrency_caps(monkeypatch) -> None:
    logger = _Logger()
    session = _Session()
    max_workers_seen: list[int] = []

    configs = [
        SourceConfig(
            id="rss_one",
            name="RSS One",
            type="rss",
            url="https://example.com/rss-one.xml",
            enabled=True,
        ),
        SourceConfig(
            id="rss_two",
            name="RSS Two",
            type="rss",
            url="https://example.com/rss-two.xml",
            enabled=True,
        ),
        SourceConfig(
            id="rss_three",
            name="RSS Three",
            type="rss",
            url="https://example.com/rss-three.xml",
            enabled=True,
        ),
        SourceConfig(
            id="html_one",
            name="HTML One",
            type="html",
            url="https://example.com/html-one",
            enabled=True,
            html={"list_selector": "main", "link_selector": "a"},
        ),
        SourceConfig(
            id="html_two",
            name="HTML Two",
            type="html",
            url="https://example.com/html-two",
            enabled=True,
            html={"list_selector": "main", "link_selector": "a"},
        ),
    ]

    class _ImmediateFuture:
        def __init__(self, result):
            self._result = result

        def result(self):
            return self._result

    class _ImmediateExecutor:
        def __init__(self, *, max_workers: int) -> None:
            max_workers_seen.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> Literal[False]:
            return False

        def submit(self, fn, **kwargs):
            return _ImmediateFuture(fn(**kwargs))

    def _fake_fetch_source_items(**_kwargs):
        return []

    def _immediate_as_completed(futures):
        return list(futures)

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _SourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _ArticleRepo)
    monkeypatch.setattr("app.core.pipeline._fetch_source_items", _fake_fetch_source_items)
    monkeypatch.setattr("app.core.pipeline.ThreadPoolExecutor", _ImmediateExecutor)
    monkeypatch.setattr("app.core.pipeline.as_completed", _immediate_as_completed)

    settings = SimpleNamespace(
        sources_path="sources.yaml",
        concurrency_limit=8,
        rss_full_text_concurrency_limit=None,
        fetch_execution_profile="rss_fast",
        fetch_rss_concurrency_limit=2,
        fetch_html_concurrency_limit=1,
        fetch_emit_source_metrics=False,
    )

    summary = run_fetch_cycle(settings=settings, logger=logger)

    assert summary.errors == 0
    assert max_workers_seen == [2, 1]


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


def test_run_fetch_cycle_rss_304_uses_stored_validators_and_persists_fetch_state(
    monkeypatch,
) -> None:
    logger = _Logger()
    session = _Session()

    configs = [
        SourceConfig(
            id="rss_stateful",
            name="RSS Stateful",
            type="rss",
            url="https://example.com/stateful.xml",
            enabled=True,
        )
    ]
    source_states = {
        101: {
            "etag": '"etag-old"',
            "last_modified": "Mon, 23 Feb 2026 10:00:00 GMT",
            "last_checked_at": None,
            "last_status_code": 200,
        }
    }
    fetch_meta_calls: list[dict[str, object]] = []
    legacy_fetch_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class _StatefulSourceRepo:
        last_instance: ClassVar[Any] = None

        def __init__(self, _session) -> None:
            self.state_updates: list[dict[str, object]] = []
            _StatefulSourceRepo.last_instance = self

        def upsert_source(self, _config: SourceConfig):
            return SimpleNamespace(id=101)

        def get_source_fetch_state(self, source_id: int):
            return dict(source_states[source_id])

        def update_source_fetch_state(
            self,
            source_id: int,
            *,
            etag,
            last_modified,
            last_status_code,
            last_checked_at,
        ) -> None:
            self.state_updates.append(
                {
                    "source_id": source_id,
                    "etag": etag,
                    "last_modified": last_modified,
                    "last_status_code": last_status_code,
                    "last_checked_at": last_checked_at,
                }
            )

    class _TrackingArticleRepo:
        last_instance = None

        def __init__(self, _session) -> None:
            self.insert_calls: list[dict[str, object]] = []
            _TrackingArticleRepo.last_instance = self

        def insert_article(self, **kwargs):
            self.insert_calls.append(kwargs)
            return SimpleNamespace(id=1), True

    def _fake_fetch_rss_with_metadata(source_key: str, url: str, timeout_seconds: float, **kwargs):
        fetch_meta_calls.append(
            {
                "source_key": source_key,
                "url": url,
                "timeout_seconds": timeout_seconds,
                **kwargs,
            }
        )
        return SimpleNamespace(
            items=[],
            not_modified=True,
            status_code=304,
            etag='"etag-304"',
            last_modified="Mon, 23 Feb 2026 12:00:00 GMT",
        )

    def _legacy_fetch_rss(*args, **kwargs):
        legacy_fetch_calls.append((args, kwargs))
        return []

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _StatefulSourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _TrackingArticleRepo)
    monkeypatch.setattr("app.core.pipeline.fetch_rss", _legacy_fetch_rss)
    monkeypatch.setattr(
        "app.core.pipeline.fetch_rss_with_metadata",
        _fake_fetch_rss_with_metadata,
        raising=False,
    )
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
        rss_known_streak_stop=0,
    )

    summary = run_fetch_cycle(settings=settings, logger=logger)
    source_repo = _StatefulSourceRepo.last_instance
    article_repo = _TrackingArticleRepo.last_instance
    assert source_repo is not None
    assert article_repo is not None

    assert not legacy_fetch_calls
    assert fetch_meta_calls and fetch_meta_calls[0]["if_none_match"] == '"etag-old"'
    assert fetch_meta_calls[0]["if_modified_since"] == "Mon, 23 Feb 2026 10:00:00 GMT"
    assert summary.not_modified_sources == 1
    assert summary.fetched == 0
    assert summary.new == 0
    assert article_repo.insert_calls == []
    source_finished_payload = next(
        payload
        for event, payload in logger.info_calls
        if event == "source_fetch_finished" and payload["source_id"] == "rss_stateful"
    )
    assert source_finished_payload["not_modified"] is True
    fetch_finished_payload = next(
        payload for event, payload in logger.info_calls if event == "fetch_run_finished"
    )
    assert fetch_finished_payload["not_modified_sources"] == 1
    assert source_repo.state_updates and source_repo.state_updates[0]["last_status_code"] == 304
    assert source_repo.state_updates[0]["last_checked_at"] is not None


def test_run_fetch_cycle_rss_200_persists_validators_and_processes_items(monkeypatch) -> None:
    logger = _Logger()
    session = _Session()

    configs = [
        SourceConfig(
            id="rss_stateful",
            name="RSS Stateful",
            type="rss",
            url="https://example.com/stateful.xml",
            enabled=True,
        )
    ]
    source_states = {
        202: {
            "etag": '"etag-prev"',
            "last_modified": "Mon, 23 Feb 2026 09:00:00 GMT",
            "last_checked_at": None,
            "last_status_code": 200,
        }
    }
    fetch_meta_calls: list[dict[str, object]] = []
    legacy_fetch_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class _StatefulSourceRepo:
        last_instance: ClassVar[Any] = None

        def __init__(self, _session) -> None:
            self.state_updates: list[dict[str, object]] = []
            _StatefulSourceRepo.last_instance = self

        def upsert_source(self, _config: SourceConfig):
            return SimpleNamespace(id=202)

        def get_source_fetch_state(self, source_id: int):
            return dict(source_states[source_id])

        def update_source_fetch_state(
            self,
            source_id: int,
            *,
            etag,
            last_modified,
            last_status_code,
            last_checked_at,
        ) -> None:
            self.state_updates.append(
                {
                    "source_id": source_id,
                    "etag": etag,
                    "last_modified": last_modified,
                    "last_status_code": last_status_code,
                    "last_checked_at": last_checked_at,
                }
            )

    class _TrackingArticleRepo:
        last_instance = None

        def __init__(self, _session) -> None:
            self.insert_calls: list[dict[str, object]] = []
            _TrackingArticleRepo.last_instance = self

        def insert_article(self, **kwargs):
            self.insert_calls.append(kwargs)
            return SimpleNamespace(id=1), True

    def _fake_fetch_rss_with_metadata(source_key: str, url: str, timeout_seconds: float, **kwargs):
        fetch_meta_calls.append(
            {
                "source_key": source_key,
                "url": url,
                "timeout_seconds": timeout_seconds,
                **kwargs,
            }
        )
        return SimpleNamespace(
            items=[
                Article(
                    source_key="rss_stateful",
                    title="Fresh item",
                    url="https://example.com/fresh",
                    published_at=datetime(2026, 2, 23, 12, 0, tzinfo=UTC),
                    summary="sum",
                    content="content",
                )
            ],
            not_modified=False,
            status_code=200,
            etag='"etag-new"',
            last_modified="Mon, 23 Feb 2026 12:05:00 GMT",
        )

    def _legacy_fetch_rss(*args, **kwargs):
        legacy_fetch_calls.append((args, kwargs))
        return []

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _StatefulSourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _TrackingArticleRepo)
    monkeypatch.setattr("app.core.pipeline.fetch_rss", _legacy_fetch_rss)
    monkeypatch.setattr(
        "app.core.pipeline.fetch_rss_with_metadata",
        _fake_fetch_rss_with_metadata,
        raising=False,
    )
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
        rss_known_streak_stop=0,
    )

    summary = run_fetch_cycle(settings=settings, logger=logger)
    source_repo = _StatefulSourceRepo.last_instance
    article_repo = _TrackingArticleRepo.last_instance
    assert source_repo is not None
    assert article_repo is not None

    assert not legacy_fetch_calls
    assert fetch_meta_calls and fetch_meta_calls[0]["if_none_match"] == '"etag-prev"'
    assert fetch_meta_calls[0]["if_modified_since"] == "Mon, 23 Feb 2026 09:00:00 GMT"
    assert summary.not_modified_sources == 0
    assert summary.fetched == 1
    assert summary.new == 1
    assert len(article_repo.insert_calls) == 1
    assert source_repo.state_updates and source_repo.state_updates[0]["etag"] == '"etag-new"'
    assert source_repo.state_updates[0]["last_modified"] == "Mon, 23 Feb 2026 12:05:00 GMT"
    assert source_repo.state_updates[0]["last_status_code"] == 200
    assert source_repo.state_updates[0]["last_checked_at"] is not None


def test_run_fetch_cycle_uses_rss_validators_and_handles_not_modified(monkeypatch) -> None:
    logger = _Logger()
    session = _Session()

    configs = [
        SourceConfig(
            id="rss_stateful",
            name="RSS Stateful",
            type="rss",
            url="https://example.com/stateful.xml",
            enabled=True,
        )
    ]

    class _TrackingSourceRepo:
        last_instance = None

        def __init__(self, _session) -> None:
            self.get_calls: list[int] = []
            self.update_calls: list[tuple[int, dict[str, object]]] = []
            _TrackingSourceRepo.last_instance = self

        def upsert_source(self, config: SourceConfig):
            return SimpleNamespace(id=101, source_key=config.id)

        def get_fetch_state(self, *, source_id: int):
            self.get_calls.append(source_id)
            return {
                "etag": '"etag-old"',
                "last_modified": "Sun, 22 Feb 2026 10:00:00 GMT",
                "last_checked_at": None,
                "last_status_code": 200,
            }

        def update_fetch_state(self, *, source_id: int, **kwargs):
            self.update_calls.append((source_id, kwargs))

    class _NoInsertArticleRepo:
        def __init__(self, _session) -> None:
            self.insert_calls = 0

        def insert_article(self, **_kwargs):
            self.insert_calls += 1
            raise AssertionError(
                "insert_article should not be called for 304/not-modified RSS source"
            )

    class _Rss304Result(list):
        def __init__(self) -> None:
            super().__init__([])
            self.not_modified = True
            self.status_code = 304
            self.etag = '"etag-new"'
            self.last_modified = "Mon, 23 Feb 2026 11:00:00 GMT"

    rss_calls: list[dict[str, object]] = []

    def _fake_fetch_rss(source_key: str, url: str, *_args, **kwargs):
        rss_calls.append(
            {
                "source_key": source_key,
                "url": url,
                "if_none_match": kwargs.get("if_none_match"),
                "if_modified_since": kwargs.get("if_modified_since"),
            }
        )
        return _Rss304Result()

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _TrackingSourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _NoInsertArticleRepo)
    monkeypatch.setattr("app.core.pipeline.fetch_rss", _fake_fetch_rss)
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
        rss_known_streak_stop=0,
    )

    summary = run_fetch_cycle(settings=settings, logger=logger)
    repo = _TrackingSourceRepo.last_instance
    assert repo is not None

    assert rss_calls == [
        {
            "source_key": "rss_stateful",
            "url": "https://example.com/stateful.xml",
            "if_none_match": '"etag-old"',
            "if_modified_since": "Sun, 22 Feb 2026 10:00:00 GMT",
        }
    ]
    assert summary.not_modified_sources == 1
    assert summary.fetched == 0
    assert summary.new == 0
    assert summary.duplicates == 0

    assert repo.get_calls == [101]
    assert len(repo.update_calls) == 1
    source_id, payload = repo.update_calls[0]
    assert source_id == 101
    assert payload["etag"] == '"etag-new"'
    assert payload["last_modified"] == "Mon, 23 Feb 2026 11:00:00 GMT"
    assert payload["last_status_code"] == 304
    assert isinstance(payload["last_checked_at"], datetime)


def test_run_fetch_cycle_default_rss_path_persists_304_metadata_from_wrapper(monkeypatch) -> None:
    logger = _Logger()
    session = _Session()

    configs = [
        SourceConfig(
            id="rss_stateful_default_path",
            name="RSS Stateful Default Path",
            type="rss",
            url="https://example.com/stateful-default.xml",
            enabled=True,
        )
    ]

    class _TrackingSourceRepo:
        last_instance = None

        def __init__(self, _session) -> None:
            self.get_calls: list[int] = []
            self.update_calls: list[tuple[int, dict[str, object]]] = []
            _TrackingSourceRepo.last_instance = self

        def upsert_source(self, config: SourceConfig):
            return SimpleNamespace(id=303, source_key=config.id)

        def get_fetch_state(self, *, source_id: int):
            self.get_calls.append(source_id)
            return {
                "etag": '"etag-old"',
                "last_modified": "Sun, 22 Feb 2026 10:00:00 GMT",
                "last_checked_at": None,
                "last_status_code": 200,
            }

        def update_fetch_state(self, *, source_id: int, **kwargs):
            self.update_calls.append((source_id, kwargs))

    class _NoInsertArticleRepo:
        def __init__(self, _session) -> None:
            self.insert_calls = 0

        def insert_article(self, **_kwargs):
            self.insert_calls += 1
            raise AssertionError(
                "insert_article should not be called for 304/not-modified RSS source"
            )

    wrapper_calls: list[dict[str, object]] = []

    def _fake_wrapper_fetch_rss_with_metadata(source_key: str, url: str, *_args, **kwargs):
        wrapper_calls.append(
            {
                "source_key": source_key,
                "url": url,
                "if_none_match": kwargs.get("if_none_match"),
                "if_modified_since": kwargs.get("if_modified_since"),
            }
        )
        return SimpleNamespace(
            items=[],
            not_modified=True,
            status_code=304,
            etag='"etag-304"',
            last_modified="Mon, 23 Feb 2026 11:00:00 GMT",
        )

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _TrackingSourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _NoInsertArticleRepo)
    monkeypatch.setattr(
        "app.ingest.rss.fetch_rss_with_metadata",
        _fake_wrapper_fetch_rss_with_metadata,
    )
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
        rss_known_streak_stop=0,
    )

    summary = run_fetch_cycle(settings=settings, logger=logger)
    repo = _TrackingSourceRepo.last_instance
    assert repo is not None

    assert wrapper_calls == [
        {
            "source_key": "rss_stateful_default_path",
            "url": "https://example.com/stateful-default.xml",
            "if_none_match": '"etag-old"',
            "if_modified_since": "Sun, 22 Feb 2026 10:00:00 GMT",
        }
    ]
    assert summary.not_modified_sources == 1
    assert summary.fetched == 0
    assert summary.new == 0
    assert summary.duplicates == 0

    assert repo.get_calls == [303]
    assert len(repo.update_calls) == 1
    source_id, payload = repo.update_calls[0]
    assert source_id == 303
    assert payload["etag"] == '"etag-304"'
    assert payload["last_modified"] == "Mon, 23 Feb 2026 11:00:00 GMT"
    assert payload["last_status_code"] == 304
    assert isinstance(payload["last_checked_at"], datetime)


# pylint: disable=too-many-statements
def test_run_fetch_cycle_persists_rss_fetch_state_metadata_for_200(monkeypatch) -> None:
    logger = _Logger()
    session = _Session()

    configs = [
        SourceConfig(
            id="rss_stateful_200",
            name="RSS Stateful 200",
            type="rss",
            url="https://example.com/stateful-200.xml",
            enabled=True,
        )
    ]

    class _TrackingSourceRepo:
        last_instance = None

        def __init__(self, _session) -> None:
            self.get_calls: list[int] = []
            self.update_calls: list[tuple[int, dict[str, object]]] = []
            _TrackingSourceRepo.last_instance = self

        def upsert_source(self, config: SourceConfig):
            return SimpleNamespace(id=202, source_key=config.id)

        def get_fetch_state(self, *, source_id: int):
            self.get_calls.append(source_id)
            return {
                "etag": None,
                "last_modified": None,
                "last_checked_at": None,
                "last_status_code": None,
            }

        def update_fetch_state(self, *, source_id: int, **kwargs):
            self.update_calls.append((source_id, kwargs))

    class _TrackingArticleRepo:
        last_instance = None

        def __init__(self, _session) -> None:
            self.insert_calls: list[str] = []
            _TrackingArticleRepo.last_instance = self

        def insert_article(self, **kwargs):
            self.insert_calls.append(kwargs["url"])
            return SimpleNamespace(id=1), True

    class _Rss200Result(list):
        def __init__(self, items: list[Article]) -> None:
            super().__init__(items)
            self.not_modified = False
            self.status_code = 200
            self.etag = '"etag-200"'
            self.last_modified = "Mon, 23 Feb 2026 12:00:00 GMT"

    rss_calls: list[dict[str, object]] = []

    def _fake_fetch_rss(source_key: str, url: str, *_args, **kwargs):
        rss_calls.append(
            {
                "source_key": source_key,
                "url": url,
                "if_none_match": kwargs.get("if_none_match"),
                "if_modified_since": kwargs.get("if_modified_since"),
            }
        )
        return _Rss200Result(
            [
                Article(
                    source_key=source_key,
                    title="Fresh RSS Item",
                    url="https://example.com/fresh-rss-item",
                    published_at=datetime(2026, 2, 23, 12, 0, tzinfo=UTC),
                    summary=None,
                    content=None,
                )
            ]
        )

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _TrackingSourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _TrackingArticleRepo)
    monkeypatch.setattr("app.core.pipeline.fetch_rss", _fake_fetch_rss)
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
        rss_known_streak_stop=0,
    )

    summary = run_fetch_cycle(settings=settings, logger=logger)
    source_repo = _TrackingSourceRepo.last_instance
    article_repo = _TrackingArticleRepo.last_instance
    assert source_repo is not None
    assert article_repo is not None

    assert rss_calls == [
        {
            "source_key": "rss_stateful_200",
            "url": "https://example.com/stateful-200.xml",
            "if_none_match": None,
            "if_modified_since": None,
        }
    ]
    assert article_repo.insert_calls == ["https://example.com/fresh-rss-item"]
    assert summary.fetched == 1
    assert summary.new == 1
    assert summary.not_modified_sources == 0

    assert source_repo.get_calls == [202]
    assert len(source_repo.update_calls) == 1
    source_id, payload = source_repo.update_calls[0]
    assert source_id == 202
    assert payload["etag"] == '"etag-200"'
    assert payload["last_modified"] == "Mon, 23 Feb 2026 12:00:00 GMT"
    assert payload["last_status_code"] == 200
    assert isinstance(payload["last_checked_at"], datetime)


def test_run_fetch_cycle_html_304_uses_validators_and_skips_processing(monkeypatch) -> None:
    logger = _Logger()
    session = _Session()

    configs = [
        SourceConfig(
            id="html_stateful",
            name="HTML Stateful",
            type="html",
            url="https://example.com/news",
            enabled=True,
            html={"list_selector": "main", "link_selector": "a"},
        )
    ]

    class _TrackingSourceRepo:
        last_instance = None

        def __init__(self, _session) -> None:
            self.get_calls: list[int] = []
            self.update_calls: list[tuple[int, dict[str, object]]] = []
            _TrackingSourceRepo.last_instance = self

        def upsert_source(self, config: SourceConfig):
            return SimpleNamespace(id=404, source_key=config.id)

        def get_fetch_state(self, *, source_id: int):
            self.get_calls.append(source_id)
            return {
                "etag": '"html-etag-old"',
                "last_modified": "Sun, 22 Feb 2026 10:00:00 GMT",
                "last_checked_at": None,
                "last_status_code": 200,
            }

        def update_fetch_state(self, *, source_id: int, **kwargs):
            self.update_calls.append((source_id, kwargs))

    class _NoInsertArticleRepo:
        def __init__(self, _session) -> None:
            self.insert_calls = 0

        def insert_article(self, **_kwargs):
            self.insert_calls += 1
            raise AssertionError("insert_article should not be called for 304/not-modified HTML")

    html_calls: list[dict[str, object]] = []
    article_calls: list[str] = []

    def _fake_fetch_html_links_with_metadata(_source, *_args, **kwargs):
        html_calls.append(
            {
                "if_none_match": kwargs.get("if_none_match"),
                "if_modified_since": kwargs.get("if_modified_since"),
            }
        )
        return SimpleNamespace(
            links=[],
            not_modified=True,
            status_code=304,
            etag='"html-etag-new"',
            last_modified="Mon, 23 Feb 2026 12:00:00 GMT",
        )

    def _unexpected_fetch_html_article(*_args, **_kwargs):
        article_calls.append("called")
        raise AssertionError("fetch_html_article should not run for 304/not-modified HTML")

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _TrackingSourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _NoInsertArticleRepo)
    monkeypatch.setattr("app.core.pipeline.fetch_rss", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.core.pipeline.fetch_html", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        "app.core.pipeline.fetch_html_links_with_metadata",
        _fake_fetch_html_links_with_metadata,
        raising=False,
    )
    monkeypatch.setattr(
        "app.core.pipeline.fetch_html_article",
        _unexpected_fetch_html_article,
        raising=False,
    )
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
        rss_known_streak_stop=0,
        html_known_streak_stop=20,
        html_max_links_per_source=10,
        fetch_emit_source_metrics=True,
        fetch_conditional_html_list_enabled=True,
    )

    summary = run_fetch_cycle(settings=settings, logger=logger)
    repo = _TrackingSourceRepo.last_instance
    assert repo is not None

    assert html_calls == [
        {
            "if_none_match": '"html-etag-old"',
            "if_modified_since": "Sun, 22 Feb 2026 10:00:00 GMT",
        }
    ]
    assert not article_calls
    assert summary.not_modified_sources == 1
    assert summary.fetched == 0
    assert summary.new == 0
    source_finished_payload = next(
        payload
        for event, payload in logger.info_calls
        if event == "source_fetch_finished" and payload["source_id"] == "html_stateful"
    )
    assert source_finished_payload["not_modified"] is True
    assert repo.get_calls == [404]
    assert len(repo.update_calls) == 1
    source_id, payload = repo.update_calls[0]
    assert source_id == 404
    assert payload["etag"] == '"html-etag-new"'
    assert payload["last_modified"] == "Mon, 23 Feb 2026 12:00:00 GMT"
    assert payload["last_status_code"] == 304
    assert isinstance(payload["last_checked_at"], datetime)


def test_run_fetch_cycle_html_conditional_disabled_uses_normal_two_stage_path(monkeypatch) -> None:
    logger = _Logger()
    session = _Session()

    configs = [
        SourceConfig(
            id="html_stateful_disabled",
            name="HTML Stateful Disabled",
            type="html",
            url="https://example.com/news",
            enabled=True,
            html={"list_selector": "main", "link_selector": "a"},
        )
    ]

    class _TrackingSourceRepo:
        def __init__(self, _session) -> None:
            pass

        def upsert_source(self, config: SourceConfig):
            return SimpleNamespace(id=405, source_key=config.id)

        def get_fetch_state(self, *, source_id: int):
            del source_id
            return {
                "etag": '"html-etag-old"',
                "last_modified": "Sun, 22 Feb 2026 10:00:00 GMT",
                "last_checked_at": None,
                "last_status_code": 200,
            }

        def update_fetch_state(self, *, source_id: int, **kwargs):
            raise AssertionError(
                "update_fetch_state should not be called when conditional HTML is disabled"
            )

    class _TrackingArticleRepo:
        last_instance = None

        def __init__(self, _session) -> None:
            self.insert_calls: list[str] = []
            _TrackingArticleRepo.last_instance = self

        def exists_by_canonical_hash(self, _canonical_hash: str) -> bool:
            return False

        def insert_article(self, **kwargs):
            self.insert_calls.append(kwargs["url"])
            return SimpleNamespace(id=len(self.insert_calls)), True

    metadata_calls: list[str] = []

    def _unexpected_fetch_html_links_with_metadata(*_args, **_kwargs):
        metadata_calls.append("called")
        raise AssertionError("metadata-aware HTML fetch path should not be used when disabled")

    def _fake_fetch_html_links(*_args, **_kwargs):
        return ["https://example.com/item-1"]

    def _fake_fetch_html_article(*args, **kwargs):
        url = kwargs.get("url")
        if not isinstance(url, str) and len(args) >= 2:
            url = args[1]
        assert isinstance(url, str)
        return Article(
            source_key="html_stateful_disabled",
            title="Fetched item",
            url=url,
            published_at=None,
            summary=None,
            content="content",
        )

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _TrackingSourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _TrackingArticleRepo)
    monkeypatch.setattr("app.core.pipeline.fetch_rss", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.core.pipeline.fetch_html", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        "app.core.pipeline.fetch_html_links_with_metadata",
        _unexpected_fetch_html_links_with_metadata,
        raising=False,
    )
    monkeypatch.setattr(
        "app.core.pipeline.fetch_html_links",
        _fake_fetch_html_links,
        raising=False,
    )
    monkeypatch.setattr(
        "app.core.pipeline.fetch_html_article",
        _fake_fetch_html_article,
        raising=False,
    )
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
        rss_known_streak_stop=0,
        html_known_streak_stop=20,
        html_max_links_per_source=10,
        fetch_emit_source_metrics=True,
        fetch_conditional_html_list_enabled=False,
    )

    summary = run_fetch_cycle(settings=settings, logger=logger)
    repo = _TrackingArticleRepo.last_instance
    assert repo is not None

    assert not metadata_calls
    assert summary.not_modified_sources == 0
    assert summary.fetched == 1
    assert summary.new == 1
    assert repo.insert_calls == ["https://example.com/item-1"]


def test_run_fetch_cycle_html_two_stage_skips_known_links_and_respects_max_links(
    monkeypatch,
) -> None:
    logger = _Logger()
    session = _Session()

    configs = [
        SourceConfig(
            id="html_two_stage",
            name="HTML Two Stage",
            type="html",
            url="https://example.com/news",
            enabled=True,
            html={"list_selector": "main", "link_selector": "a"},
        )
    ]

    class _TrackingArticleRepo:
        last_instance = None

        def __init__(self, _session) -> None:
            self.exists_calls: list[str] = []
            self.insert_calls: list[str] = []
            self._known = {"h:https://example.com/item-1"}
            _TrackingArticleRepo.last_instance = self

        def exists_by_canonical_hash(self, canonical_hash: str) -> bool:
            self.exists_calls.append(canonical_hash)
            return canonical_hash in self._known

        def insert_article(self, **kwargs):
            self.insert_calls.append(kwargs["url"])
            return SimpleNamespace(id=len(self.insert_calls)), True

    link_calls: list[dict[str, object]] = []
    article_calls: list[str] = []

    def _fake_fetch_html_links(*args, **kwargs):
        link_calls.append({"args": args, "kwargs": kwargs})
        return [
            "https://example.com/item-1",  # known, should skip article fetch
            "https://example.com/item-2",
            "https://example.com/item-3",
            "https://example.com/item-4",  # should be ignored by max-links=3
        ]

    def _fake_fetch_html_article(*args, **kwargs):
        link = kwargs.get("url")
        if not isinstance(link, str) and len(args) >= 2:
            link = args[1]
        assert isinstance(link, str)
        article_calls.append(link)
        return Article(
            source_key="html_two_stage",
            title=f"Title for {link.rsplit('/', maxsplit=1)[-1]}",
            url=link,
            published_at=None,
            summary=None,
            content="content",
        )

    def _unexpected_fetch_html(*_args, **_kwargs):
        raise AssertionError("legacy monolithic fetch_html path should not be used")

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _SourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _TrackingArticleRepo)
    monkeypatch.setattr("app.core.pipeline.fetch_html", _unexpected_fetch_html)
    monkeypatch.setattr("app.core.pipeline.fetch_rss", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.ingest.html.fetch_html_links", _fake_fetch_html_links, raising=False)
    monkeypatch.setattr(
        "app.ingest.html.fetch_html_article",
        _fake_fetch_html_article,
        raising=False,
    )
    monkeypatch.setattr("app.core.pipeline.fetch_html_links", _fake_fetch_html_links, raising=False)
    monkeypatch.setattr(
        "app.core.pipeline.fetch_html_article",
        _fake_fetch_html_article,
        raising=False,
    )
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
        rss_known_streak_stop=0,
        html_known_streak_stop=50,
        html_max_links_per_source=3,
        fetch_emit_source_metrics=True,
    )

    summary = run_fetch_cycle(settings=settings, logger=logger)
    repo = _TrackingArticleRepo.last_instance
    assert repo is not None

    assert len(link_calls) == 1
    assert article_calls == [
        "https://example.com/item-2",
        "https://example.com/item-3",
    ]
    assert repo.insert_calls == article_calls
    assert summary.errors == 0
    assert summary.new == 2
    assert summary.skipped_known_html_links == 1
    assert summary.early_stop_hits == 0


def test_run_fetch_cycle_html_two_stage_stops_after_known_streak(monkeypatch) -> None:
    logger = _Logger()
    session = _Session()

    configs = [
        SourceConfig(
            id="html_known_streak",
            name="HTML Known Streak",
            type="html",
            url="https://example.com/news",
            enabled=True,
            html={"list_selector": "main", "link_selector": "a"},
        )
    ]

    class _TrackingArticleRepo:
        last_instance = None

        def __init__(self, _session) -> None:
            self.exists_calls: list[str] = []
            self.insert_calls: list[str] = []
            self._known = {
                "h:https://example.com/item-1",
                "h:https://example.com/item-2",
            }
            _TrackingArticleRepo.last_instance = self

        def exists_by_canonical_hash(self, canonical_hash: str) -> bool:
            self.exists_calls.append(canonical_hash)
            return canonical_hash in self._known

        def insert_article(self, **kwargs):
            self.insert_calls.append(kwargs["url"])
            return SimpleNamespace(id=len(self.insert_calls)), True

    link_calls: list[int] = []
    article_calls: list[str] = []

    def _fake_fetch_html_links(*_args, **_kwargs):
        link_calls.append(1)
        return [
            "https://example.com/item-1",
            "https://example.com/item-2",
            "https://example.com/item-3",  # should not be fetched after streak stop=2
        ]

    def _fake_fetch_html_article(*args, **kwargs):
        link = kwargs.get("url")
        if not isinstance(link, str) and len(args) >= 2:
            link = args[1]
        assert isinstance(link, str)
        article_calls.append(link)
        return Article(
            source_key="html_known_streak",
            title="Should not be reached",
            url=link,
            published_at=None,
            summary=None,
            content="content",
        )

    def _unexpected_fetch_html(*_args, **_kwargs):
        raise AssertionError("legacy monolithic fetch_html path should not be used")

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _SourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _TrackingArticleRepo)
    monkeypatch.setattr("app.core.pipeline.fetch_html", _unexpected_fetch_html)
    monkeypatch.setattr("app.core.pipeline.fetch_rss", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.ingest.html.fetch_html_links", _fake_fetch_html_links, raising=False)
    monkeypatch.setattr(
        "app.ingest.html.fetch_html_article",
        _fake_fetch_html_article,
        raising=False,
    )
    monkeypatch.setattr("app.core.pipeline.fetch_html_links", _fake_fetch_html_links, raising=False)
    monkeypatch.setattr(
        "app.core.pipeline.fetch_html_article",
        _fake_fetch_html_article,
        raising=False,
    )
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
        rss_known_streak_stop=0,
        html_known_streak_stop=2,
        html_max_links_per_source=20,
        fetch_emit_source_metrics=True,
    )

    summary = run_fetch_cycle(settings=settings, logger=logger)
    repo = _TrackingArticleRepo.last_instance
    assert repo is not None

    assert link_calls == [1]
    assert not article_calls
    assert repo.insert_calls == []
    assert summary.errors == 0
    assert summary.skipped_known_html_links == 2
    assert summary.early_stop_hits == 1
    source_finished_payload = next(
        payload
        for event, payload in logger.info_calls
        if event == "source_fetch_finished" and payload["source_id"] == "html_known_streak"
    )
    assert source_finished_payload["skipped_known_items"] == 2
    assert source_finished_payload["early_stop_hit"] is True


def test_run_fetch_cycle_html_two_stage_skips_known_links_before_article_fetch_future(
    monkeypatch,
) -> None:
    logger = _Logger()
    session = _Session()

    configs = [
        SourceConfig(
            id="html_future_two_stage",
            name="HTML Future Two Stage",
            type="html",
            url="https://example.com/news",
            enabled=True,
            html={"list_selector": "main", "link_selector": "a"},
        )
    ]

    class _TrackingArticleRepo:
        last_instance = None

        def __init__(self, _session) -> None:
            self.exists_calls: list[str] = []
            self.insert_calls: list[str] = []
            _TrackingArticleRepo.last_instance = self

        def exists_by_canonical_hash(self, canonical_hash: str) -> bool:
            self.exists_calls.append(canonical_hash)
            return canonical_hash == "h:https://example.com/known"

        def insert_article(self, **kwargs):
            self.insert_calls.append(kwargs["url"])
            return SimpleNamespace(id=len(self.insert_calls)), True

    article_calls: list[str] = []

    def _fake_fetch_html_links(*_args, **_kwargs):
        return [
            "https://example.com/known",
            "https://example.com/new",
        ]

    def _fake_fetch_html_article(*args, **kwargs):
        url = kwargs.get("url")
        if not isinstance(url, str) and len(args) >= 2:
            url = args[1]
        assert isinstance(url, str)
        article_calls.append(url)
        return Article(
            source_key="html_future_two_stage",
            title="New item",
            url=url,
            published_at=None,
            summary=None,
            content="content",
        )

    def _unexpected_fetch_html(*_args, **_kwargs):
        raise AssertionError("legacy monolithic fetch_html path should not be used")

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _SourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _TrackingArticleRepo)
    monkeypatch.setattr("app.core.pipeline.fetch_rss", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.core.pipeline.fetch_html", _unexpected_fetch_html)
    monkeypatch.setattr("app.core.pipeline.fetch_html_links", _fake_fetch_html_links)
    monkeypatch.setattr("app.core.pipeline.fetch_html_article", _fake_fetch_html_article)
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
        rss_known_streak_stop=0,
        html_known_streak_stop=50,
        html_max_links_per_source=10,
        fetch_emit_source_metrics=True,
    )

    summary = run_fetch_cycle(settings=settings, logger=logger)
    repo = _TrackingArticleRepo.last_instance
    assert repo is not None
    assert repo.exists_calls == [
        "h:https://example.com/known",
        "h:https://example.com/new",
    ]
    assert article_calls == ["https://example.com/new"]
    assert repo.insert_calls == ["https://example.com/new"]
    assert summary.skipped_known_html_links == 1


def test_run_fetch_cycle_html_two_stage_uses_batch_known_hash_precheck_when_available(
    monkeypatch,
) -> None:
    logger = _Logger()
    session = _Session()

    configs = [
        SourceConfig(
            id="html_two_stage_batch",
            name="HTML Two Stage Batch",
            type="html",
            url="https://example.com/news",
            enabled=True,
            html={"list_selector": "main", "link_selector": "a"},
        )
    ]

    class _TrackingArticleRepo:
        last_instance = None

        def __init__(self, _session) -> None:
            self.batch_calls: list[list[str]] = []
            self.exists_calls: list[str] = []
            self.insert_calls: list[str] = []
            self._known = {"h:https://example.com/item-1"}
            _TrackingArticleRepo.last_instance = self

        def existing_canonical_hashes(self, hashes: list[str]) -> set[str]:
            self.batch_calls.append(list(hashes))
            return {h for h in hashes if h in self._known}

        def exists_by_canonical_hash(self, canonical_hash: str) -> bool:
            self.exists_calls.append(canonical_hash)
            return canonical_hash in self._known

        def insert_article(self, **kwargs):
            self.insert_calls.append(kwargs["url"])
            return SimpleNamespace(id=len(self.insert_calls)), True

    article_calls: list[str] = []

    def _fake_fetch_html_links(*_args, **_kwargs):
        return [
            "https://example.com/item-1",
            "https://example.com/item-2",
            "https://example.com/item-3",
            "https://example.com/item-4",
        ]

    def _fake_fetch_html_article(*args, **kwargs):
        url = kwargs.get("url")
        if not isinstance(url, str) and len(args) >= 2:
            url = args[1]
        assert isinstance(url, str)
        article_calls.append(url)
        return Article(
            source_key="html_two_stage_batch",
            title="Fetched item",
            url=url,
            published_at=None,
            summary=None,
            content="content",
        )

    def _unexpected_fetch_html(*_args, **_kwargs):
        raise AssertionError("legacy monolithic fetch_html path should not be used")

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _SourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _TrackingArticleRepo)
    monkeypatch.setattr("app.core.pipeline.fetch_rss", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.core.pipeline.fetch_html", _unexpected_fetch_html)
    monkeypatch.setattr("app.core.pipeline.fetch_html_links", _fake_fetch_html_links)
    monkeypatch.setattr("app.core.pipeline.fetch_html_article", _fake_fetch_html_article)
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
        rss_known_streak_stop=0,
        html_known_streak_stop=50,
        html_max_links_per_source=3,
        fetch_emit_source_metrics=True,
    )

    summary = run_fetch_cycle(settings=settings, logger=logger)
    repo = _TrackingArticleRepo.last_instance
    assert repo is not None

    assert repo.batch_calls == [
        [
            "h:https://example.com/item-1",
            "h:https://example.com/item-2",
            "h:https://example.com/item-3",
        ]
    ]
    assert repo.exists_calls == []
    assert article_calls == [
        "https://example.com/item-2",
        "https://example.com/item-3",
    ]
    assert repo.insert_calls == article_calls
    assert summary.new == 2
    assert summary.skipped_known_html_links == 1


def test_run_fetch_cycle_uses_batch_article_upsert_when_enabled(monkeypatch) -> None:
    logger = _Logger()
    session = _Session()

    configs = [
        SourceConfig(
            id="rss_batch",
            name="RSS Batch",
            type="rss",
            url="https://example.com/rss-batch.xml",
            enabled=True,
        )
    ]

    class _BatchArticleRepo:
        last_instance = None

        def __init__(self, _session) -> None:
            self.batch_calls: list[list[str]] = []
            self.insert_calls = 0
            _BatchArticleRepo.last_instance = self

        def upsert_articles_batch(self, rows: list[dict[str, object]]) -> tuple[int, int]:
            self.batch_calls.append([str(row["url_canonical_hash"]) for row in rows])
            return 1, 1

        def insert_article(self, **_kwargs):
            self.insert_calls += 1
            raise AssertionError("insert_article should not be used when batch upsert is enabled")

    rss_items = [
        Article(
            source_key="rss_batch",
            title="One",
            url="https://example.com/one",
            published_at=None,
            summary=None,
            content=None,
        ),
        Article(
            source_key="rss_batch",
            title="Two",
            url="https://example.com/two",
            published_at=None,
            summary=None,
            content=None,
        ),
    ]

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _SourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _BatchArticleRepo)
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
        rss_known_streak_stop=0,
        article_batch_upsert_enabled=True,
        fetch_emit_source_metrics=True,
    )

    summary = run_fetch_cycle(settings=settings, logger=logger)
    repo = _BatchArticleRepo.last_instance
    assert repo is not None

    assert repo.batch_calls == [["h:https://example.com/one", "h:https://example.com/two"]]
    assert repo.insert_calls == 0
    assert summary.fetched == 2
    assert summary.new == 1
    assert summary.duplicates == 1


def test_run_fetch_cycle_batch_upsert_does_not_advance_rss_known_streak_for_in_run_duplicates(
    monkeypatch,
) -> None:
    logger = _Logger()
    session = _Session()

    configs = [
        SourceConfig(
            id="rss_batch_streak",
            name="RSS Batch Streak",
            type="rss",
            url="https://example.com/rss-batch-streak.xml",
            enabled=True,
        )
    ]

    class _BatchArticleRepo:
        last_instance = None

        def __init__(self, _session) -> None:
            self.exists_calls: list[str] = []
            self.batch_calls: list[list[str]] = []
            _BatchArticleRepo.last_instance = self

        def exists_by_canonical_hash(self, canonical_hash: str) -> bool:
            self.exists_calls.append(canonical_hash)
            return False

        def upsert_articles_batch(self, rows: list[dict[str, object]]) -> tuple[int, int]:
            self.batch_calls.append([str(row["url_canonical_hash"]) for row in rows])
            return 2, 0

        def insert_article(self, **_kwargs):
            raise AssertionError("insert_article should not be used when batch upsert is enabled")

    rss_items = [
        Article(
            source_key="rss_batch_streak",
            title="One",
            url="https://example.com/one",
            published_at=None,
            summary=None,
            content=None,
        ),
        Article(
            source_key="rss_batch_streak",
            title="One again",
            url="https://example.com/one",
            published_at=None,
            summary=None,
            content=None,
        ),
        Article(
            source_key="rss_batch_streak",
            title="Two",
            url="https://example.com/two",
            published_at=None,
            summary=None,
            content=None,
        ),
    ]

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _SourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _BatchArticleRepo)
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
        rss_known_streak_stop=1,
        article_batch_upsert_enabled=True,
        fetch_emit_source_metrics=True,
    )

    summary = run_fetch_cycle(settings=settings, logger=logger)
    repo = _BatchArticleRepo.last_instance
    assert repo is not None

    assert repo.batch_calls == [["h:https://example.com/one", "h:https://example.com/two"]]
    assert repo.exists_calls == [
        "h:https://example.com/one",
        "h:https://example.com/one",
        "h:https://example.com/two",
    ]
    assert summary.fetched == 3
    assert summary.new == 2
    assert summary.duplicates == 1
    assert summary.early_stop_hits == 0


def test_run_fetch_cycle_publishes_previous_monday_sunday_weekly_report_on_monday(
    monkeypatch,
) -> None:
    logger = _Logger()
    session = _Session()
    publish_calls: list[date] = []

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 9, 8, 0, tzinfo=tz or UTC)

    class _WeeklyAnalyticsRepo:
        def __init__(self, current_session) -> None:
            assert current_session is session

        def save_weekly_report(self, *, report_date: date, **_kwargs) -> None:
            publish_calls.append(report_date)

    configs = [
        SourceConfig(
            id="rss_weekly_publish",
            name="RSS Weekly Publish",
            type="rss",
            url="https://example.com/rss-weekly-publish.xml",
            enabled=True,
        )
    ]

    monkeypatch.setattr("app.core.pipeline.datetime", _FrozenDateTime)
    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _SourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _ArticleRepo)
    monkeypatch.setattr(
        "app.core.pipeline.WeeklyAnalyticsRepo",
        _WeeklyAnalyticsRepo,
        raising=False,
    )
    monkeypatch.setattr("app.core.pipeline.fetch_rss", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.core.pipeline.fetch_html", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.core.pipeline.canonicalize_url", lambda u: f"c:{u}")
    monkeypatch.setattr("app.core.pipeline.canonical_url_hash", lambda u: f"h:{u}")
    monkeypatch.setattr("app.core.pipeline.ai_relevance_score", lambda _item: 0.5)
    monkeypatch.setattr("app.core.pipeline.freshness_score", lambda _dt: 0.5)
    monkeypatch.setattr("app.core.pipeline.rank_score", lambda **_kwargs: 0.5)

    summary = run_fetch_cycle(settings=Settings(sources_path="sources.yaml"), logger=logger)

    assert summary.fetched == 0
    assert summary.new == 0
    assert summary.duplicates == 0
    assert summary.errors == 0
    assert publish_calls == [date(2026, 3, 8)]


def test_run_fetch_cycle_html_heavy_profile_fetches_html_before_rss(monkeypatch) -> None:
    order: list[str] = []
    configs = [
        SourceConfig(id="rss_first", name="RSS First", type="rss",
                     url="https://example.com/rss-first.xml"),
        SourceConfig(id="html_first", name="HTML First", type="html",
                     url="https://example.com/html-first", html={"link_selector": "a"}),
        SourceConfig(id="rss_second", name="RSS Second", type="rss",
                     url="https://example.com/rss-second.xml"),
        SourceConfig(id="html_second", name="HTML Second", type="html",
                     url="https://example.com/html-second", html={"link_selector": "a"}),
    ]

    class _ImmediateFuture:
        def __init__(self, result):
            self._result = result

        def result(self):
            return self._result

    class _ImmediateExecutor:
        def __init__(self, *, max_workers: int) -> None:
            self.max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> Literal[False]:
            return False

        def submit(self, fn, **kwargs):
            return _ImmediateFuture(fn(**kwargs))

    def _fake_fetch_source_items(*, config, **_kwargs):
        order.append(config.id)
        return []

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", _Session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _SourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _ArticleRepo)
    monkeypatch.setattr("app.core.pipeline._fetch_source_items", _fake_fetch_source_items)
    monkeypatch.setattr("app.core.pipeline.ThreadPoolExecutor", _ImmediateExecutor)
    monkeypatch.setattr("app.core.pipeline.as_completed", list)

    settings = SimpleNamespace(
        sources_path="sources.yaml",
        concurrency_limit=1,
        rss_full_text_concurrency_limit=None,
        fetch_execution_profile="html_heavy",
        fetch_emit_source_metrics=False,
    )

    summary = run_fetch_cycle(settings=settings, logger=_Logger())

    assert summary.errors == 0
    assert order == ["html_first", "html_second", "rss_first", "rss_second"]


def test_run_fetch_cycle_fetches_every_enabled_source_regardless_of_interval(
    monkeypatch,
) -> None:
    fetched: list[str] = []
    configs = [
        SourceConfig(id=f"rss_{minutes}", name=f"RSS {minutes}", type="rss",
                     url=f"https://example.com/rss-{minutes}.xml",
                     fetch_interval_minutes=minutes)
        for minutes in (60, 1440)
    ]

    class _CheckedJustNowSourceRepo(_SourceRepo):
        def get_fetch_state(self, *, source_id: int):
            del source_id
            return {"etag": None, "last_modified": None, "last_status_code": 200,
                    "last_checked_at": datetime.now(UTC)}

        def update_fetch_state(self, **_kwargs) -> None:
            pass

    def _fake_fetch_source_items(*, config, **_kwargs):
        fetched.append(config.id)
        return []

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", _Session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _CheckedJustNowSourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _ArticleRepo)
    monkeypatch.setattr("app.core.pipeline._fetch_source_items", _fake_fetch_source_items)

    settings = SimpleNamespace(
        sources_path="sources.yaml",
        concurrency_limit=1,
        rss_full_text_concurrency_limit=None,
        fetch_emit_source_metrics=False,
    )

    first = run_fetch_cycle(settings=settings, logger=_Logger())
    second = run_fetch_cycle(settings=settings, logger=_Logger())

    assert first.source_count == second.source_count == 2
    assert sorted(fetched) == ["rss_1440", "rss_1440", "rss_60", "rss_60"]


def test_run_fetch_cycle_rss_conditional_disabled_sends_no_validators(monkeypatch) -> None:
    configs = [SourceConfig(id="rss_stateful", name="RSS Stateful", type="rss",
                            url="https://example.com/stateful.xml")]
    rss_calls: list[tuple[object, object]] = []

    class _StatefulSourceRepo(_SourceRepo):
        def get_fetch_state(self, *, source_id: int):
            del source_id
            return {"etag": '"etag-old"', "last_modified": "Sun, 22 Feb 2026 10:00:00 GMT",
                    "last_status_code": 200, "last_checked_at": None}

        def update_fetch_state(self, **_kwargs) -> None:
            pass

    def _fake_fetch_rss(*_args, **kwargs):
        rss_calls.append((kwargs.get("if_none_match"), kwargs.get("if_modified_since")))
        return []

    def _unexpected_fetch_rss_with_metadata(*_args, **_kwargs):
        raise AssertionError("conditional RSS path must not be used when disabled")

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", _Session)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", _StatefulSourceRepo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", _ArticleRepo)
    monkeypatch.setattr("app.core.pipeline.fetch_rss", _fake_fetch_rss)
    monkeypatch.setattr(
        "app.core.pipeline.fetch_rss_with_metadata", _unexpected_fetch_rss_with_metadata,
    )

    settings = SimpleNamespace(
        sources_path="sources.yaml",
        request_timeout_seconds=1.0,
        max_retries=0,
        concurrency_limit=1,
        per_source_min_interval_seconds=0.0,
        rss_extract_full_text=False,
        rss_full_text_max_items_per_source=0,
        rss_full_text_concurrency_limit=None,
        rss_known_streak_stop=0,
        fetch_conditional_rss_enabled=False,
        fetch_emit_source_metrics=False,
    )

    summary = run_fetch_cycle(settings=settings, logger=_Logger())

    assert summary.errors == 0
    assert rss_calls == [(None, None)]
