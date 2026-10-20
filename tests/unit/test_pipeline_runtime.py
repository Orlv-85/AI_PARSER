"""run_fetch_cycle with fake sessions, repos and fetch functions; real Settings."""
from contextlib import nullcontext
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any, ClassVar, Literal
from zlib import crc32

import httpx
import pytest

from app.config.settings import Settings
from app.config.sources import SourceConfig
from app.core.models import Article
from app.core.pipeline import FetchSummary, _managed_source_to_config, run_fetch_cycle
from app.ingest import rss as rss_module
from app.ingest.html import HtmlListPageResult
from app.ingest.rss import RssFetchResult, _with_rss_metadata

OLD_VALIDATORS: dict[str, object | None] = {
    "etag": '"etag-old"', "last_modified": "Sun, 22 Feb 2026 10:00:00 GMT",
    "last_checked_at": None, "last_status_code": 200,
}


class _Logger:
    def __init__(self) -> None:
        self.info_calls: list[tuple[str, dict[str, object]]] = []
        self.error_calls: list[tuple[str, dict[str, object]]] = []

    def info(self, event: str, payload: dict[str, object]) -> None:
        self.info_calls.append((event, payload))

    def error(self, event: str, payload: dict[str, object]) -> None:
        self.error_calls.append((event, payload))

    def payload(self, event: str, source_id: str | None = None) -> dict[str, object]:
        return next(
            payload for name, payload in self.info_calls
            if name == event and (source_id is None or payload["source_id"] == source_id)
        )


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
    """The SourceRepo methods run_fetch_cycle calls; subclasses set the stored state."""

    fetch_state: ClassVar[dict[str, object | None]] = {
        "etag": None, "last_modified": None, "last_checked_at": None, "last_status_code": None,
    }
    managed: ClassVar[list[object]] = []
    last: ClassVar[Any] = None

    def __init__(self, _session) -> None:
        self.get_calls: list[int] = []
        self.updates: list[dict[str, object]] = []
        type(self).last = self

    @staticmethod
    def source_id(key: str) -> int:
        return crc32(key.encode()) % 100000 + 1

    def upsert_source(self, config: SourceConfig):
        return SimpleNamespace(id=self.source_id(config.id))

    def list_enabled_sources(self) -> list[object]:
        return list(self.managed)

    def get_fetch_state(self, *, source_id: int) -> dict[str, object | None]:
        self.get_calls.append(source_id)
        return dict(self.fetch_state)

    def update_fetch_state(self, *, source_id: int, **kwargs) -> None:
        self.updates.append({"source_id": source_id, **kwargs})


class _ArticleRepo:
    """The ArticleRepo methods ingestion calls; `known` holds stored canonical hashes."""

    known: ClassVar[set[str]] = set()
    last: ClassVar[Any] = None

    def __init__(self, session) -> None:
        self.session = session
        self.exists_calls: list[str] = []
        self.known_batches: list[list[str]] = []
        self.inserts: list[dict[str, Any]] = []
        self.batches: list[list[str]] = []
        type(self).last = self

    def exists_by_canonical_hash(self, canonical_hash: str) -> bool:
        self.exists_calls.append(canonical_hash)
        return canonical_hash in self.known

    def existing_canonical_hashes(self, canonical_hashes: list[str]) -> set[str]:
        self.known_batches.append(list(canonical_hashes))
        return {value for value in canonical_hashes if value in self.known}

    def insert_article(self, **row):
        self.inserts.append(row)
        return SimpleNamespace(id=len(self.inserts)), True

    def upsert_articles_batch(self, rows: list[dict[str, Any]]) -> tuple[int, int]:
        self.batches.append([str(row["url_canonical_hash"]) for row in rows])
        return len(rows), 0

    def inserted_urls(self) -> list[str]:
        return [str(row["url"]) for row in self.inserts]


def _no_fetch(name: str):
    def fetch(*_args, **_kwargs):
        pytest.fail(f"{name} must not be called")
    return fetch


def _settings(**overrides) -> Settings:
    values: dict[str, Any] = {
        "_env_file": None, "sources_path": "sources.yaml", "max_retries": 0,
        "per_source_min_interval_seconds": 0.0, "concurrency_limit": 1,
        "rss_known_streak_stop": 0, "html_known_streak_stop": 0,
        "html_max_links_per_source": None,
    }
    values.update(overrides)
    return Settings(**values)


def _run(
    monkeypatch, configs: list[SourceConfig], *, settings: Settings | None = None,
    source_repo: type = _SourceRepo, article_repo: type = _ArticleRepo,
    session: _Session | None = None, logger: _Logger | None = None, **patches: object,
) -> FetchSummary:
    """Run one cycle; `patches` replace attributes of app.core.pipeline (fetch functions)."""
    current = session or _Session()
    defaults = {name: _no_fetch(name) for name in (
        "fetch_rss", "fetch_html_links", "fetch_html_links_with_metadata", "fetch_html_article",
    )}
    for name, value in {**defaults, **patches}.items():
        monkeypatch.setattr(f"app.core.pipeline.{name}", value)
    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", lambda: current)
    monkeypatch.setattr("app.core.pipeline.SourceRepo", source_repo)
    monkeypatch.setattr("app.core.pipeline.ArticleRepo", article_repo)
    monkeypatch.setattr("app.core.pipeline.canonicalize_url", lambda u: f"c:{u}")
    monkeypatch.setattr("app.core.pipeline.canonical_url_hash", lambda u: f"h:{u}")
    monkeypatch.setattr("app.core.pipeline.ai_relevance_score", lambda _item: 0.5)
    monkeypatch.setattr("app.core.pipeline.freshness_score", lambda _dt: 0.5)
    monkeypatch.setattr("app.core.pipeline.rank_score", lambda **_kwargs: 0.5)
    return run_fetch_cycle(settings=settings or _settings(), logger=logger or _Logger())


def _inline_fetches(monkeypatch) -> tuple[list[str], list[int]]:
    """Run source fetches inline; return the fetch order and each group's worker count."""
    order: list[str] = []
    workers: list[int] = []

    class _Future:
        def __init__(self, result) -> None:
            self._result = result

        def result(self):
            return self._result

    class _Executor:
        def __init__(self, *, max_workers: int) -> None:
            workers.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> Literal[False]:
            return False

        def submit(self, fn, **kwargs):
            return _Future(fn(**kwargs))

    def fetch(*, config, **_kwargs):
        order.append(config.id)
        return _rss_result([]) if config.type == "rss" else HtmlListPageResult(links=[])

    monkeypatch.setattr("app.core.pipeline._fetch_source_items", fetch)
    monkeypatch.setattr("app.core.pipeline.ThreadPoolExecutor", _Executor)
    monkeypatch.setattr("app.core.pipeline.as_completed", list)
    return order, workers


def _rss(key: str, url: str | None = None) -> SourceConfig:
    return SourceConfig(id=key, name=key, type="rss", url=url or f"https://example.com/{key}.xml")


def _html(key: str, url: str = "https://example.com/news") -> SourceConfig:
    return SourceConfig(id=key, name=key, type="html", url=url,
                        html={"list_selector": "main", "link_selector": "a"})


def _item(source_key: str, url: str, title: str = "Item", **fields) -> Article:
    return Article(source_key=source_key, title=title, url=url, **fields)


def _links(*urls: str):
    calls: list[int] = []

    def fetch(*_args, **_kwargs):
        calls.append(1)
        return list(urls)

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


def _articles(source_key: str, **fields):
    calls: list[str] = []

    def fetch(*, url: str, **_kwargs):
        calls.append(url)
        return _item(source_key, url, **fields)

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


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
        SourceConfig(id="disabled", name="Disabled", type="rss",
                     url="https://example.com/disabled.xml", enabled=False),
        _rss("rss_ok", "https://example.com/feed.xml"),
        _html("html_ok"),
        _rss("rss_fail", "https://example.com/fail.xml"),
    ]

    class _FirstNewArticleRepo(_ArticleRepo):
        def insert_article(self, **row):
            self.inserts.append(row)
            return SimpleNamespace(id=len(self.inserts)), len(self.inserts) == 1

    def fetch_rss(source_key: str, *_args, **_kwargs):
        if source_key == "rss_fail":
            raise RuntimeError("boom")
        return _rss_result([_item(source_key, "https://example.com/rss-item", "RSS Item",
                                  summary="sum", content="content")])

    summary = _run(
        monkeypatch, configs, article_repo=_FirstNewArticleRepo, session=session,
        logger=logger, fetch_rss=fetch_rss,
        fetch_html_links=_links("https://example.com/html-item"),
        fetch_html_article=_articles(
            "html_ok", title="HTML Item", published_at=datetime(2026, 2, 21, 10, tzinfo=UTC)),
    )

    assert summary.fetched == 2
    assert summary.new == 1
    assert summary.duplicates == 1
    assert summary.errors == 1
    assert summary.not_modified_sources == 0
    assert summary.skipped_known_html_links == 0
    assert summary.early_stop_hits == 0
    assert session.committed is True
    assert any(event == "source_fetch_failed" for event, _ in logger.error_calls)
    fetch_finished_payload = logger.payload("fetch_run_finished")
    assert fetch_finished_payload["not_modified_sources"] == 0
    assert fetch_finished_payload["skipped_known_html_links"] == 0
    assert fetch_finished_payload["early_stop_hits"] == 0
    assert any(event == "source_fetch_finished" for event, _ in logger.info_calls)


def test_run_fetch_cycle_handles_no_enabled_sources(monkeypatch) -> None:
    session = _Session()
    configs = [SourceConfig(id="disabled_only", name="Disabled", type="rss",
                            url="https://example.com/disabled.xml", enabled=False)]

    summary = _run(monkeypatch, configs, session=session)

    assert summary.fetched == 0
    assert summary.new == 0
    assert summary.duplicates == 0
    assert summary.errors == 0
    assert session.committed is True


def test_run_fetch_cycle_includes_db_enabled_sources_without_sources_yaml_edits(
    monkeypatch,
) -> None:
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

    class _DbOnlySourceRepo(_SourceRepo):
        managed: ClassVar[list[object]] = [managed_source]

    def fetch_rss(source_key: str, *_args, **_kwargs):
        fetched_source_keys.append(source_key)
        return _rss_result([_item(source_key, "https://example.com/managed-item", "Managed Item")])

    summary = _run(monkeypatch, [], source_repo=_DbOnlySourceRepo, fetch_rss=fetch_rss)

    assert fetched_source_keys == ["managed-approved"]
    assert _DbOnlySourceRepo.last.get_calls == [managed_source.id]
    assert summary.fetched == 1
    assert summary.new == 1
    assert summary.errors == 0


def test_run_fetch_cycle_rss_fast_profile_fetches_rss_before_html(monkeypatch) -> None:
    order, _workers = _inline_fetches(monkeypatch)
    configs = [_html("html_first"), _rss("rss_first"), _html("html_second"), _rss("rss_second")]

    summary = _run(monkeypatch, configs, settings=_settings(
        fetch_execution_profile="rss_fast", fetch_emit_source_metrics=False,
    ))

    assert summary.errors == 0
    assert order == ["rss_first", "rss_second", "html_first", "html_second"]


def test_run_fetch_cycle_execution_profile_applies_per_type_concurrency_caps(monkeypatch) -> None:
    _order, workers = _inline_fetches(monkeypatch)
    configs = [_rss("rss_one"), _rss("rss_two"), _rss("rss_three"),
               _html("html_one"), _html("html_two")]

    summary = _run(monkeypatch, configs, settings=_settings(
        concurrency_limit=8, fetch_execution_profile="rss_fast",
        fetch_rss_concurrency_limit=2, fetch_html_concurrency_limit=1,
        fetch_emit_source_metrics=False,
    ))

    assert summary.errors == 0
    assert workers == [2, 1]


def test_run_fetch_cycle_html_heavy_profile_fetches_html_before_rss(monkeypatch) -> None:
    order, _workers = _inline_fetches(monkeypatch)
    configs = [_rss("rss_first"), _html("html_first"), _rss("rss_second"), _html("html_second")]

    summary = _run(monkeypatch, configs, settings=_settings(
        fetch_execution_profile="html_heavy", fetch_emit_source_metrics=False,
    ))

    assert summary.errors == 0
    assert order == ["html_first", "html_second", "rss_first", "rss_second"]


def test_run_fetch_cycle_fetches_every_enabled_source_regardless_of_interval(
    monkeypatch,
) -> None:
    order, _workers = _inline_fetches(monkeypatch)
    configs = [
        SourceConfig(id=f"rss_{minutes}", name=f"RSS {minutes}", type="rss",
                     url=f"https://example.com/rss-{minutes}.xml",
                     fetch_interval_minutes=minutes)
        for minutes in (60, 1440)
    ]

    class _CheckedJustNowSourceRepo(_SourceRepo):
        fetch_state: ClassVar[dict[str, object | None]] = {
            "etag": None, "last_modified": None, "last_status_code": 200,
            "last_checked_at": datetime.now(UTC),
        }

    settings = _settings(fetch_emit_source_metrics=False)
    first = _run(monkeypatch, configs, settings=settings, source_repo=_CheckedJustNowSourceRepo)
    second = _run(monkeypatch, configs, settings=settings, source_repo=_CheckedJustNowSourceRepo)

    assert first.source_count == second.source_count == 2
    assert sorted(order) == ["rss_1440", "rss_1440", "rss_60", "rss_60"]


def test_run_fetch_cycle_stops_rss_processing_after_known_streak(monkeypatch) -> None:
    rss_items = [
        _item("rss_feed", "https://example.com/old-1", "Old 1"),
        _item("rss_feed", "https://example.com/old-2", "Old 2"),
        _item("rss_feed", "https://example.com/new-3", "New 3"),
    ]

    class _KnownArticleRepo(_ArticleRepo):
        known: ClassVar[set[str]] = {"h:https://example.com/old-1", "h:https://example.com/old-2"}

    summary = _run(
        monkeypatch, [_rss("rss_feed")], settings=_settings(rss_known_streak_stop=2),
        article_repo=_KnownArticleRepo, fetch_rss=lambda *_args, **_kwargs: _rss_result(rss_items),
    )
    repo = _KnownArticleRepo.last

    assert summary.fetched == 3
    assert repo.exists_calls == ["h:https://example.com/old-1", "h:https://example.com/old-2"]
    assert repo.inserts == []
    assert summary.new == 0
    assert summary.duplicates == 2
    assert summary.early_stop_hits == 1


def test_run_fetch_cycle_rss_known_streak_stop_does_not_apply_to_html(monkeypatch) -> None:
    rss_items = [
        _item("rss_feed", "https://example.com/rss-old-1", "RSS Old 1"),
        _item("rss_feed", "https://example.com/rss-old-2", "RSS Old 2"),
        _item("rss_feed", "https://example.com/rss-new-3", "RSS New 3"),
    ]
    html_links = _links("https://example.com/html-1", "https://example.com/html-2",
                        "https://example.com/html-3")
    html_articles = _articles("html_feed", published_at=datetime(2026, 2, 21, 10, tzinfo=UTC))

    class _KnownArticleRepo(_ArticleRepo):
        known: ClassVar[set[str]] = {
            "h:https://example.com/rss-old-1", "h:https://example.com/rss-old-2",
            "h:https://example.com/html-1", "h:https://example.com/html-2",
        }

    summary = _run(
        monkeypatch, [_rss("rss_feed"), _html("html_feed")],
        settings=_settings(rss_known_streak_stop=2, html_known_streak_stop=0),
        article_repo=_KnownArticleRepo, fetch_rss=lambda *_args, **_kwargs: _rss_result(rss_items),
        fetch_html_links=html_links, fetch_html_article=html_articles,
    )
    repo = _KnownArticleRepo.last

    # RSS stops after two known items; HTML continues past two known links.
    assert repo.exists_calls == ["h:https://example.com/rss-old-1", "h:https://example.com/rss-old-2"]
    assert html_articles.calls == ["https://example.com/html-3"]
    assert repo.inserted_urls() == ["https://example.com/html-3"]
    assert summary.fetched == 4
    assert summary.new == 1
    assert summary.duplicates == 4
    assert summary.skipped_known_html_links == 2
    assert summary.early_stop_hits == 1


def test_run_fetch_cycle_resets_rss_known_streak_on_new_item(monkeypatch) -> None:
    rss_items = [
        _item("rss_feed", "https://example.com/old-1", "Old 1"),
        _item("rss_feed", "https://example.com/new-2", "New 2"),
        _item("rss_feed", "https://example.com/old-3", "Old 3"),
    ]

    class _KnownArticleRepo(_ArticleRepo):
        known: ClassVar[set[str]] = {"h:https://example.com/old-1", "h:https://example.com/old-3"}

    summary = _run(
        monkeypatch, [_rss("rss_feed")], settings=_settings(rss_known_streak_stop=2),
        article_repo=_KnownArticleRepo, fetch_rss=lambda *_args, **_kwargs: _rss_result(rss_items),
    )
    repo = _KnownArticleRepo.last

    assert repo.exists_calls == [
        "h:https://example.com/old-1",
        "h:https://example.com/new-2",
        "h:https://example.com/old-3",
    ]
    assert [row["url_canonical_hash"] for row in repo.inserts] == ["h:https://example.com/new-2"]
    assert summary.new == 1
    assert summary.duplicates == 2
    assert summary.early_stop_hits == 0


def _feed_request(monkeypatch, response: httpx.Response) -> list[dict[str, object]]:
    """Serve one response through the real fetch_rss; record the conditional headers."""
    requests: list[dict[str, object]] = []

    def request(_self, *, source_id, url, if_none_match=None, if_modified_since=None):
        requests.append({"source_id": source_id, "url": url, "if_none_match": if_none_match,
                         "if_modified_since": if_modified_since})
        response.request = httpx.Request("GET", url)
        return response

    monkeypatch.setattr("app.ingest.fetcher.Fetcher.request", request)
    return requests


def test_run_fetch_cycle_rss_304_uses_stored_validators_and_persists_fetch_state(
    monkeypatch,
) -> None:
    logger = _Logger()
    requests = _feed_request(monkeypatch, httpx.Response(304, headers={
        "ETag": '"etag-304"', "Last-Modified": "Mon, 23 Feb 2026 12:00:00 GMT",
    }))

    class _StatefulSourceRepo(_SourceRepo):
        fetch_state: ClassVar[dict[str, object | None]] = OLD_VALIDATORS

    summary = _run(
        monkeypatch, [_rss("rss_stateful", "https://example.com/stateful.xml")],
        source_repo=_StatefulSourceRepo, logger=logger,
        fetch_rss=rss_module.fetch_rss,
    )
    source_repo = _StatefulSourceRepo.last

    assert requests == [{
        "source_id": "rss_stateful", "url": "https://example.com/stateful.xml",
        "if_none_match": '"etag-old"', "if_modified_since": "Sun, 22 Feb 2026 10:00:00 GMT",
    }]
    assert summary.not_modified_sources == 1
    assert summary.fetched == 0
    assert summary.new == 0
    assert _ArticleRepo.last.inserts == []
    assert logger.payload("source_fetch_finished", "rss_stateful")["not_modified"] is True
    assert logger.payload("fetch_run_finished")["not_modified_sources"] == 1
    assert [(row["etag"], row["last_modified"], row["last_status_code"])
            for row in source_repo.updates] == [
        ('"etag-304"', "Mon, 23 Feb 2026 12:00:00 GMT", 304),
    ]
    assert isinstance(source_repo.updates[0]["last_checked_at"], datetime)


def test_run_fetch_cycle_rss_200_persists_validators_and_processes_items(monkeypatch) -> None:
    feed = (
        '<rss version="2.0"><channel><title>AI</title><item><title>AI model release</title>'
        "<link>https://example.com/news/ai-model-release</link>"
        "<pubDate>Mon, 23 Feb 2026 12:00:00 GMT</pubDate></item></channel></rss>"
    )
    requests = _feed_request(monkeypatch, httpx.Response(200, content=feed.encode(), headers={
        "ETag": '"etag-new"', "Last-Modified": "Mon, 23 Feb 2026 12:05:00 GMT",
    }))

    class _StatefulSourceRepo(_SourceRepo):
        fetch_state: ClassVar[dict[str, object | None]] = OLD_VALIDATORS

    summary = _run(
        monkeypatch, [_rss("rss_stateful", "https://example.com/stateful.xml")],
        source_repo=_StatefulSourceRepo,
        fetch_rss=rss_module.fetch_rss,
    )
    source_repo = _StatefulSourceRepo.last

    assert requests[0]["if_none_match"] == '"etag-old"'
    assert requests[0]["if_modified_since"] == "Sun, 22 Feb 2026 10:00:00 GMT"
    assert summary.not_modified_sources == 0
    assert summary.fetched == 1
    assert summary.new == 1
    assert _ArticleRepo.last.inserted_urls() == ["https://example.com/news/ai-model-release"]
    assert [(row["etag"], row["last_modified"], row["last_status_code"])
            for row in source_repo.updates] == [
        ('"etag-new"', "Mon, 23 Feb 2026 12:05:00 GMT", 200),
    ]
    assert isinstance(source_repo.updates[0]["last_checked_at"], datetime)


def _rss_result(
    items: list[Article], status_code: int = 200, *, etag: str | None = None,
    last_modified: str | None = None,
) -> list[Article]:
    wrapped: list[Article] = _with_rss_metadata(items, RssFetchResult(
        items=items, not_modified=status_code == 304, status_code=status_code, etag=etag,
        last_modified=last_modified,
    ))
    return wrapped


class _NoInsertArticleRepo(_ArticleRepo):
    def insert_article(self, **row):
        pytest.fail("a not-modified source must not insert articles")


def test_run_fetch_cycle_uses_rss_validators_and_handles_not_modified(monkeypatch) -> None:
    rss_calls: list[dict[str, object]] = []

    class _StatefulSourceRepo(_SourceRepo):
        fetch_state: ClassVar[dict[str, object | None]] = OLD_VALIDATORS

    def fetch_rss(source_key: str, url: str, *_args, **kwargs):
        rss_calls.append({"source_key": source_key, "url": url,
                          "if_none_match": kwargs.get("if_none_match"),
                          "if_modified_since": kwargs.get("if_modified_since")})
        return _rss_result([], 304, etag='"etag-new"',
                           last_modified="Mon, 23 Feb 2026 11:00:00 GMT")

    summary = _run(
        monkeypatch, [_rss("rss_stateful", "https://example.com/stateful.xml")],
        source_repo=_StatefulSourceRepo, article_repo=_NoInsertArticleRepo, fetch_rss=fetch_rss,
    )
    repo = _StatefulSourceRepo.last

    assert rss_calls == [{
        "source_key": "rss_stateful", "url": "https://example.com/stateful.xml",
        "if_none_match": '"etag-old"', "if_modified_since": "Sun, 22 Feb 2026 10:00:00 GMT",
    }]
    assert summary.not_modified_sources == 1
    assert summary.fetched == 0
    assert summary.new == 0
    assert summary.duplicates == 0
    assert repo.get_calls == [_SourceRepo.source_id("rss_stateful")]
    assert len(repo.updates) == 1
    assert repo.updates[0]["source_id"] == _SourceRepo.source_id("rss_stateful")
    assert repo.updates[0]["etag"] == '"etag-new"'
    assert repo.updates[0]["last_modified"] == "Mon, 23 Feb 2026 11:00:00 GMT"
    assert repo.updates[0]["last_status_code"] == 304
    assert isinstance(repo.updates[0]["last_checked_at"], datetime)


def test_run_fetch_cycle_default_rss_path_persists_304_metadata_from_wrapper(monkeypatch) -> None:
    wrapper_calls: list[dict[str, object]] = []

    class _StatefulSourceRepo(_SourceRepo):
        fetch_state: ClassVar[dict[str, object | None]] = OLD_VALIDATORS

    def fetch_rss_with_metadata(source_key: str, url: str, *_args, **kwargs):
        wrapper_calls.append({"source_key": source_key, "url": url,
                              "if_none_match": kwargs.get("if_none_match"),
                              "if_modified_since": kwargs.get("if_modified_since")})
        return RssFetchResult(items=[], not_modified=True, status_code=304, etag='"etag-304"',
                              last_modified="Mon, 23 Feb 2026 11:00:00 GMT")

    monkeypatch.setattr("app.ingest.rss.fetch_rss_with_metadata", fetch_rss_with_metadata)
    summary = _run(
        monkeypatch,
        [_rss("rss_stateful_default_path", "https://example.com/stateful-default.xml")],
        source_repo=_StatefulSourceRepo, article_repo=_NoInsertArticleRepo,
        fetch_rss=rss_module.fetch_rss,
    )
    repo = _StatefulSourceRepo.last

    assert wrapper_calls == [{
        "source_key": "rss_stateful_default_path",
        "url": "https://example.com/stateful-default.xml",
        "if_none_match": '"etag-old"', "if_modified_since": "Sun, 22 Feb 2026 10:00:00 GMT",
    }]
    assert summary.not_modified_sources == 1
    assert summary.fetched == 0
    assert summary.new == 0
    assert summary.duplicates == 0
    assert repo.get_calls == [_SourceRepo.source_id("rss_stateful_default_path")]
    assert [(row["etag"], row["last_modified"], row["last_status_code"])
            for row in repo.updates] == [
        ('"etag-304"', "Mon, 23 Feb 2026 11:00:00 GMT", 304),
    ]
    assert isinstance(repo.updates[0]["last_checked_at"], datetime)


def test_run_fetch_cycle_persists_rss_fetch_state_metadata_for_200(monkeypatch) -> None:
    rss_calls: list[dict[str, object]] = []

    def fetch_rss(source_key: str, url: str, *_args, **kwargs):
        rss_calls.append({"source_key": source_key, "url": url,
                          "if_none_match": kwargs.get("if_none_match"),
                          "if_modified_since": kwargs.get("if_modified_since")})
        return _rss_result(
            [_item(source_key, "https://example.com/fresh-rss-item", "Fresh RSS Item",
                   published_at=datetime(2026, 2, 23, 12, tzinfo=UTC))],
            200, etag='"etag-200"', last_modified="Mon, 23 Feb 2026 12:00:00 GMT",
        )

    summary = _run(
        monkeypatch, [_rss("rss_stateful_200", "https://example.com/stateful-200.xml")],
        fetch_rss=fetch_rss,
    )
    source_repo = _SourceRepo.last

    assert rss_calls == [{
        "source_key": "rss_stateful_200", "url": "https://example.com/stateful-200.xml",
        "if_none_match": None, "if_modified_since": None,
    }]
    assert _ArticleRepo.last.inserted_urls() == ["https://example.com/fresh-rss-item"]
    assert summary.fetched == 1
    assert summary.new == 1
    assert summary.not_modified_sources == 0
    assert source_repo.get_calls == [_SourceRepo.source_id("rss_stateful_200")]
    assert [(row["etag"], row["last_modified"], row["last_status_code"])
            for row in source_repo.updates] == [
        ('"etag-200"', "Mon, 23 Feb 2026 12:00:00 GMT", 200),
    ]
    assert isinstance(source_repo.updates[0]["last_checked_at"], datetime)


def test_run_fetch_cycle_rss_conditional_disabled_sends_no_validators(monkeypatch) -> None:
    rss_calls: list[tuple[object, object]] = []

    class _StatefulSourceRepo(_SourceRepo):
        fetch_state: ClassVar[dict[str, object | None]] = OLD_VALIDATORS

    def fetch_rss(*_args, **kwargs):
        rss_calls.append((kwargs.get("if_none_match"), kwargs.get("if_modified_since")))
        return _rss_result([], 200, etag='"etag-new"',
                           last_modified="Mon, 23 Feb 2026 10:00:00 GMT")

    summary = _run(
        monkeypatch, [_rss("rss_stateful", "https://example.com/stateful.xml")],
        settings=_settings(fetch_conditional_rss_enabled=False, fetch_emit_source_metrics=False),
        source_repo=_StatefulSourceRepo, fetch_rss=fetch_rss,
    )

    assert summary.errors == 0
    assert rss_calls == [(None, None)]
    assert [(row["etag"], row["last_modified"], row["last_status_code"])
            for row in _StatefulSourceRepo.last.updates] == [
        ('"etag-new"', "Mon, 23 Feb 2026 10:00:00 GMT", 200),
    ]


def test_run_fetch_cycle_html_304_uses_validators_and_skips_processing(monkeypatch) -> None:
    logger = _Logger()
    html_calls: list[dict[str, object]] = []

    class _StatefulSourceRepo(_SourceRepo):
        fetch_state: ClassVar[dict[str, object | None]] = {
            **OLD_VALIDATORS, "etag": '"html-etag-old"',
        }

    def fetch_html_links_with_metadata(_source, *_args, **kwargs):
        html_calls.append({"if_none_match": kwargs.get("if_none_match"),
                           "if_modified_since": kwargs.get("if_modified_since")})
        return HtmlListPageResult(links=[], not_modified=True, status_code=304,
                                  etag='"html-etag-new"',
                                  last_modified="Mon, 23 Feb 2026 12:00:00 GMT")

    summary = _run(
        monkeypatch, [_html("html_stateful")],
        settings=_settings(html_known_streak_stop=20, html_max_links_per_source=10,
                           fetch_conditional_html_list_enabled=True),
        source_repo=_StatefulSourceRepo, article_repo=_NoInsertArticleRepo, logger=logger,
        fetch_html_links_with_metadata=fetch_html_links_with_metadata,
    )
    repo = _StatefulSourceRepo.last

    assert html_calls == [{
        "if_none_match": '"html-etag-old"', "if_modified_since": "Sun, 22 Feb 2026 10:00:00 GMT",
    }]
    assert summary.not_modified_sources == 1
    assert summary.fetched == 0
    assert summary.new == 0
    assert logger.payload("source_fetch_finished", "html_stateful")["not_modified"] is True
    assert repo.get_calls == [_SourceRepo.source_id("html_stateful")]
    assert [(row["etag"], row["last_modified"], row["last_status_code"])
            for row in repo.updates] == [
        ('"html-etag-new"', "Mon, 23 Feb 2026 12:00:00 GMT", 304),
    ]
    assert isinstance(repo.updates[0]["last_checked_at"], datetime)


def test_run_fetch_cycle_html_conditional_disabled_uses_normal_two_stage_path(monkeypatch) -> None:
    class _StatefulSourceRepo(_SourceRepo):
        fetch_state: ClassVar[dict[str, object | None]] = {
            **OLD_VALIDATORS, "etag": '"html-etag-old"',
        }

    summary = _run(
        monkeypatch, [_html("html_stateful_disabled")],
        settings=_settings(html_known_streak_stop=20, html_max_links_per_source=10,
                           fetch_conditional_html_list_enabled=False),
        source_repo=_StatefulSourceRepo,
        fetch_html_links=_links("https://example.com/item-1"),
        fetch_html_article=_articles("html_stateful_disabled", title="Fetched item",
                                     content="content"),
    )

    assert _StatefulSourceRepo.last.updates == []
    assert summary.not_modified_sources == 0
    assert summary.fetched == 1
    assert summary.new == 1
    assert _ArticleRepo.last.inserted_urls() == ["https://example.com/item-1"]


def test_run_fetch_cycle_html_two_stage_skips_known_links_and_respects_max_links(
    monkeypatch,
) -> None:
    links = _links(
        "https://example.com/item-1",  # known, no article download
        "https://example.com/item-2",
        "https://example.com/item-3",
        "https://example.com/item-4",  # beyond html_max_links_per_source
    )
    articles = _articles("html_two_stage", content="content")

    class _KnownArticleRepo(_ArticleRepo):
        known: ClassVar[set[str]] = {"h:https://example.com/item-1"}

    summary = _run(
        monkeypatch, [_html("html_two_stage")],
        settings=_settings(html_known_streak_stop=50, html_max_links_per_source=3),
        article_repo=_KnownArticleRepo, fetch_html_links=links, fetch_html_article=articles,
    )

    assert links.calls == [1]
    assert articles.calls == ["https://example.com/item-2", "https://example.com/item-3"]
    assert _KnownArticleRepo.last.inserted_urls() == articles.calls
    assert summary.errors == 0
    assert summary.new == 2
    assert summary.skipped_known_html_links == 1
    assert summary.early_stop_hits == 0


def test_run_fetch_cycle_html_two_stage_stops_after_known_streak(monkeypatch) -> None:
    logger = _Logger()
    links = _links("https://example.com/item-1", "https://example.com/item-2",
                   "https://example.com/item-3")
    articles = _articles("html_known_streak")

    class _KnownArticleRepo(_ArticleRepo):
        known: ClassVar[set[str]] = {
            "h:https://example.com/item-1", "h:https://example.com/item-2",
        }

    summary = _run(
        monkeypatch, [_html("html_known_streak")],
        settings=_settings(html_known_streak_stop=2, html_max_links_per_source=20),
        article_repo=_KnownArticleRepo, logger=logger,
        fetch_html_links=links, fetch_html_article=articles,
    )

    assert links.calls == [1]
    assert not articles.calls
    assert _KnownArticleRepo.last.inserts == []
    assert summary.errors == 0
    assert summary.skipped_known_html_links == 2
    assert summary.early_stop_hits == 1
    source_finished_payload = logger.payload("source_fetch_finished", "html_known_streak")
    assert source_finished_payload["skipped_known_items"] == 2
    assert source_finished_payload["early_stop_hit"] is True


def test_run_fetch_cycle_html_two_stage_skips_known_links_before_article_fetch_future(
    monkeypatch,
) -> None:
    articles = _articles("html_future_two_stage", title="New item", content="content")

    class _KnownArticleRepo(_ArticleRepo):
        known: ClassVar[set[str]] = {"h:https://example.com/known"}

    summary = _run(
        monkeypatch, [_html("html_future_two_stage")],
        settings=_settings(html_known_streak_stop=50, html_max_links_per_source=10),
        article_repo=_KnownArticleRepo,
        fetch_html_links=_links("https://example.com/known", "https://example.com/new"),
        fetch_html_article=articles,
    )

    assert _KnownArticleRepo.last.known_batches == [
        ["h:https://example.com/known", "h:https://example.com/new"],
    ]
    assert articles.calls == ["https://example.com/new"]
    assert _KnownArticleRepo.last.inserted_urls() == ["https://example.com/new"]
    assert summary.skipped_known_html_links == 1


def test_run_fetch_cycle_html_two_stage_checks_known_links_in_one_query(
    monkeypatch,
) -> None:
    articles = _articles("html_two_stage_batch", title="Fetched item", content="content")

    class _KnownArticleRepo(_ArticleRepo):
        known: ClassVar[set[str]] = {"h:https://example.com/item-1"}

    summary = _run(
        monkeypatch, [_html("html_two_stage_batch")],
        settings=_settings(html_known_streak_stop=50, html_max_links_per_source=3),
        article_repo=_KnownArticleRepo,
        fetch_html_links=_links(*(f"https://example.com/item-{i}" for i in range(1, 5))),
        fetch_html_article=articles,
    )
    repo = _KnownArticleRepo.last

    assert repo.known_batches == [[f"h:https://example.com/item-{i}" for i in range(1, 4)]]
    assert repo.exists_calls == []
    assert articles.calls == ["https://example.com/item-2", "https://example.com/item-3"]
    assert repo.inserted_urls() == articles.calls
    assert summary.new == 2
    assert summary.skipped_known_html_links == 1


def test_run_fetch_cycle_uses_batch_article_upsert_when_enabled(monkeypatch) -> None:
    rss_items = [_item("rss_batch", "https://example.com/one", "One"),
                 _item("rss_batch", "https://example.com/two", "Two")]

    class _BatchArticleRepo(_ArticleRepo):
        def upsert_articles_batch(self, rows: list[dict[str, Any]]) -> tuple[int, int]:
            super().upsert_articles_batch(rows)
            return 1, 1

        def insert_article(self, **row):
            pytest.fail("insert_article must not be used when batch upsert is enabled")

    summary = _run(
        monkeypatch, [_rss("rss_batch")], settings=_settings(article_batch_upsert_enabled=True),
        article_repo=_BatchArticleRepo, fetch_rss=lambda *_args, **_kwargs: _rss_result(rss_items),
    )

    assert _BatchArticleRepo.last.batches == [
        ["h:https://example.com/one", "h:https://example.com/two"],
    ]
    assert summary.fetched == 2
    assert summary.new == 1
    assert summary.duplicates == 1


def test_run_fetch_cycle_batch_upsert_does_not_advance_rss_known_streak_for_in_run_duplicates(
    monkeypatch,
) -> None:
    rss_items = [
        _item("rss_batch_streak", "https://example.com/one", "One"),
        _item("rss_batch_streak", "https://example.com/one", "One again"),
        _item("rss_batch_streak", "https://example.com/two", "Two"),
    ]

    class _BatchArticleRepo(_ArticleRepo):
        def insert_article(self, **row):
            pytest.fail("insert_article must not be used when batch upsert is enabled")

    summary = _run(
        monkeypatch, [_rss("rss_batch_streak")],
        settings=_settings(rss_known_streak_stop=1, article_batch_upsert_enabled=True),
        article_repo=_BatchArticleRepo, fetch_rss=lambda *_args, **_kwargs: _rss_result(rss_items),
    )
    repo = _BatchArticleRepo.last

    assert repo.batches == [["h:https://example.com/one", "h:https://example.com/two"]]
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

    summary = _run(
        monkeypatch, [_rss("rss_weekly_publish")], session=session,
        datetime=_FrozenDateTime, WeeklyAnalyticsRepo=_WeeklyAnalyticsRepo,
        fetch_rss=lambda *_args, **_kwargs: _rss_result([]),
    )

    assert summary.fetched == 0
    assert summary.new == 0
    assert summary.duplicates == 0
    assert summary.errors == 0
    assert publish_calls == [date(2026, 3, 8)]
