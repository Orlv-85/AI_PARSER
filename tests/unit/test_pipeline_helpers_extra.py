from __future__ import annotations

# pylint: disable=protected-access
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import app.core.pipeline as pipeline_module
from app.config.sources import SourceConfig
from app.core.models import Article
from app.core.pipeline import (
    _fetch_result_items,
    _fetch_source_items,
    _persist_fetch_state_if_present,
    _process_html_links_two_stage,
    _profiled_source_groups,
    _source_group_max_workers,
    _source_repo_update_fetch_state,
    _upsert_article_rows,
)
from app.ingest.html import HtmlListPageResult


class _Logger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def info(self, event: str, payload: dict[str, object]) -> None:
        self.events.append((event, payload))

    def error(self, event: str, payload: dict[str, object]) -> None:
        self.events.append((event, payload))


def _html_source() -> SourceConfig:
    return SourceConfig(
        id="html_source",
        name="HTML Source",
        type="html",
        url="https://example.com/news",
        html={
            "list_selector": "main",
            "link_selector": "a",
            "article_selector": "article",
            "extraction_strategy": "readability",
        },
    )


def _settings(**overrides):
    base = {
        "request_timeout_seconds": 1.0,
        "max_retries": 0,
        "per_source_min_interval_seconds": 0.0,
        "rss_extract_full_text": False,
        "rss_full_text_max_items_per_source": 0,
        "html_known_streak_stop": 2,
        "html_max_links_per_source": 5,
        "concurrency_limit": 4,
        "fetch_conditional_html_list_enabled": False,
        "fetch_conditional_rss_enabled": False,
        "fetch_execution_profile": "balanced",
        "fetch_http_max_connections": 20,
        "fetch_http_max_keepalive_connections": 10,
        "fetch_emit_source_metrics": True,
        "article_batch_upsert_enabled": False,
        "rss_full_text_concurrency_limit": 0,
        "sources_path": "sources.yaml",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_fetch_source_items_html_list_and_conditional_paths(monkeypatch) -> None:
    logger = _Logger()
    html_config = _html_source()

    monkeypatch.setattr(
        "app.core.pipeline.fetch_html_links",
        lambda *_args, **_kwargs: ["https://example.com/news/1"],
    )
    two_stage = _fetch_source_items(
        config=html_config,
        db_source_id=1,
        fetch_state=None,
        enable_fetch_state=False,
        settings=_settings(),
        logger=logger,
        run_id="run-3",
        full_text_semaphore=None,
    )
    assert isinstance(two_stage, HtmlListPageResult)
    assert two_stage.links == ["https://example.com/news/1"]

    monkeypatch.setattr(
        "app.core.pipeline.fetch_html_links_with_metadata",
        lambda *_args, **_kwargs: HtmlListPageResult(
            links=["https://example.com/news/2"],
            status_code=200,
            etag='"etag"',
            last_modified="Mon, 01 Jan 2024 00:00:00 GMT",
        ),
    )
    conditional = _fetch_source_items(
        config=html_config,
        db_source_id=1,
        fetch_state={"etag": '"etag"', "last_modified": "Mon, 01 Jan 2024 00:00:00 GMT"},
        enable_fetch_state=True,
        settings=_settings(fetch_conditional_html_list_enabled=True),
        logger=logger,
        run_id="run-4",
        full_text_semaphore=None,
    )
    assert isinstance(conditional, HtmlListPageResult)
    assert conditional.links == ["https://example.com/news/2"]
    assert conditional.etag == '"etag"'


def test_fetch_source_items_html_conditional_default_path(monkeypatch) -> None:
    logger = _Logger()
    html_config = _html_source()
    monkeypatch.setattr(
        "app.core.pipeline.fetch_html_links",
        lambda *_args, **_kwargs: pytest.fail("conditional HTML must use the metadata fetch"),
    )
    monkeypatch.setattr(
        "app.core.pipeline.fetch_html_links_with_metadata",
        lambda *_args, **_kwargs: HtmlListPageResult(
            links=["https://example.com/news/3"],
            status_code=200,
            etag='"etag-3"',
            last_modified="Wed, 03 Jan 2024 00:00:00 GMT",
        ),
    )

    conditional = _fetch_source_items(
        config=html_config,
        db_source_id=1,
        fetch_state={"etag": '"etag-old"', "last_modified": "Tue, 02 Jan 2024 00:00:00 GMT"},
        enable_fetch_state=True,
        settings=_settings(fetch_conditional_html_list_enabled=True),
        logger=logger,
        run_id="run-5",
        full_text_semaphore=None,
    )

    assert isinstance(conditional, HtmlListPageResult)
    assert conditional.links == ["https://example.com/news/3"]
    assert conditional.etag == '"etag-3"'


def test_fetch_source_items_html_two_stage_default_nonconditional_path(monkeypatch) -> None:
    logger = _Logger()
    html_config = _html_source()

    def _fake_fetch_html_links(*_args, **_kwargs):
        return ["https://example.com/news/4"]

    monkeypatch.setattr("app.core.pipeline.fetch_html_links", _fake_fetch_html_links)

    result = _fetch_source_items(
        config=html_config,
        db_source_id=1,
        fetch_state=None,
        enable_fetch_state=False,
        settings=_settings(fetch_conditional_html_list_enabled=True),
        logger=logger,
        run_id="run-6",
        full_text_semaphore=None,
    )

    assert isinstance(result, HtmlListPageResult)
    assert result.links == ["https://example.com/news/4"]

    captured: list[dict[str, object]] = []

    def _fake_fetch_html_links_with_metadata(*_args, **kwargs):
        captured.append(kwargs)
        return HtmlListPageResult(links=[], status_code=304, not_modified=True)

    monkeypatch.setattr(
        "app.core.pipeline.fetch_html_links_with_metadata",
        _fake_fetch_html_links_with_metadata,
    )

    _fetch_source_items(
        config=html_config,
        db_source_id=1,
        fetch_state=None,
        enable_fetch_state=True,
        settings=_settings(fetch_conditional_html_list_enabled=True),
        logger=logger,
        run_id="run-7",
        full_text_semaphore=None,
    )

    assert captured
    assert captured[0]["if_none_match"] is None
    assert captured[0]["if_modified_since"] is None


class _SpyFetcher:
    instances: list[_SpyFetcher] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.closed = False
        _SpyFetcher.instances.append(self)

    def close(self) -> None:
        self.closed = True


def test_fetch_source_items_closes_fetcher_after_success_and_error(monkeypatch) -> None:
    _SpyFetcher.instances = []
    monkeypatch.setattr("app.core.pipeline.Fetcher", _SpyFetcher)
    seen_fetchers: list[object] = []

    def _fetch_links_ok(*_args, fetcher, **_kwargs):
        seen_fetchers.append(fetcher)
        assert not fetcher.closed
        return ["https://example.com/news/item"]

    def _fetch_links_fails(*_args, fetcher, **_kwargs):
        seen_fetchers.append(fetcher)
        raise RuntimeError("fetch_failed")

    def _fetch(run_id: str):
        return _fetch_source_items(
            config=_html_source(),
            db_source_id=1,
            fetch_state=None,
            enable_fetch_state=False,
            settings=_settings(),
            logger=_Logger(),
            run_id=run_id,
            full_text_semaphore=None,
        )

    monkeypatch.setattr("app.core.pipeline.fetch_html_links", _fetch_links_ok)
    assert _fetch("run-ok").links == ["https://example.com/news/item"]

    monkeypatch.setattr("app.core.pipeline.fetch_html_links", _fetch_links_fails)
    with pytest.raises(RuntimeError, match="fetch_failed"):
        _fetch("run-error")

    assert seen_fetchers == _SpyFetcher.instances
    assert [fetcher.closed for fetcher in _SpyFetcher.instances] == [True, True]


def test_process_html_links_two_stage_closes_fetcher_when_placeholder_loop_raises(
    monkeypatch,
) -> None:
    _SpyFetcher.instances = []
    monkeypatch.setattr("app.core.pipeline.Fetcher", _SpyFetcher)

    def _upsert_pending_fails(*_args, **_kwargs):
        raise RuntimeError("placeholder write failed")

    def _fetch_html_article_unexpected(**_kwargs):
        raise AssertionError("article stage must not run")

    monkeypatch.setattr("app.core.pipeline.upsert_pending", _upsert_pending_fails)
    monkeypatch.setattr("app.core.pipeline.fetch_html_article", _fetch_html_article_unexpected)

    class _Repo:
        session = object()

        @staticmethod
        def existing_canonical_hashes(_hashes):
            return set()

    with pytest.raises(RuntimeError, match="placeholder write failed"):
        _process_html_links_two_stage(
            links=["https://example.com/news/new"],
            config=_html_source(),
            db_source_id=1,
            article_repo=_Repo(),
            settings=_settings(
                jev_model="model",
                semantic_admission_policy_version="policy",
                semantic_admission_prompt_version="prompt",
            ),
            admission_state=pipeline_module.AdmissionState(enabled=True),
        )

    assert len(_SpyFetcher.instances) == 1
    assert _SpyFetcher.instances[0].closed is True


def test_profile_helpers_and_misc_pipeline_helpers() -> None:
    html_config = _html_source()
    rss_config = SourceConfig(
        id="rss_source",
        name="RSS",
        type="rss",
        url="https://example.com/feed",
    )
    enabled_sources = [
        (0, rss_config, 1, None, True),
        (1, html_config, 2, None, True),
    ]

    grouped = _profiled_source_groups(enabled_sources, _settings(fetch_execution_profile="invalid"))
    assert grouped == [enabled_sources]

    assert _source_group_max_workers([], _settings()) == 1
    assert (
        _source_group_max_workers(
            [(0, rss_config, 1, None, True), (1, html_config, 2, None, True)],
            _settings(),
        )
        == 2
    )

    assert _fetch_result_items(object()) == []
    assert (
        _upsert_article_rows(
            article_repo=SimpleNamespace(),
            rows=[],
            prefer_batch=False,
        )
        == (0, 0)
    )

    inserted: list[dict[str, object]] = []

    def _insert_article(**row):
        inserted.append(row)
        return SimpleNamespace(), row["title"] == "new"

    article_repo = SimpleNamespace(insert_article=_insert_article)
    result = _upsert_article_rows(
        article_repo=article_repo,
        rows=[
            {"title": "new"},
            {"title": "dup"},
        ],
        prefer_batch=False,
    )
    assert result == (1, 1)
    assert len(inserted) == 2

    assert _source_repo_update_fetch_state(
        SimpleNamespace(),
        source_id=1,
        etag=None,
        last_modified=None,
        last_status_code=None,
        last_checked_at=datetime.now(UTC),
    ) is False


def test_process_html_links_two_stage_covers_non_batch_edge_paths(monkeypatch) -> None:
    links = [
        "https://example.com/known",
        "https://example.com/error",
        "https://example.com/none",
        "https://example.com/dup",
    ]
    article_by_url = {
        "https://example.com/dup": Article(
            source_key="html_source",
            title="Title",
            url="https://example.com/dup",
            published_at=datetime(2026, 2, 28, tzinfo=UTC),
        )
    }

    class _Repo:
        @staticmethod
        def exists_by_canonical_hash(canonical_hash: str) -> bool:
            return canonical_hash == "known"

        @staticmethod
        def insert_article(**_row):
            return SimpleNamespace(), False

    class _FakeFetcher:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.closed = False

        def close(self) -> None:
            self.closed = True

    def _canonical_hash(url: str) -> str:
        return url.rsplit("/", maxsplit=1)[-1]

    def _fake_fetch_html_article(*, url: str, **_kwargs):
        if url.endswith("/error"):
            raise RuntimeError("boom")
        if url.endswith("/none"):
            return None
        return article_by_url[url]

    monkeypatch.setattr("app.core.pipeline.Fetcher", _FakeFetcher)
    monkeypatch.setattr("app.core.pipeline.canonicalize_url", lambda url: url)
    monkeypatch.setattr("app.core.pipeline.canonical_url_hash", _canonical_hash)
    monkeypatch.setattr("app.core.pipeline.fetch_html_article", _fake_fetch_html_article)
    monkeypatch.setattr("app.core.pipeline.ai_relevance_score", lambda _item: 0.5)
    monkeypatch.setattr("app.core.pipeline.freshness_score", lambda _published: 0.5)
    monkeypatch.setattr("app.core.pipeline.rank_score", lambda **_kwargs: 1.0)

    fetched, new_count, duplicates, skipped, early_stop = _process_html_links_two_stage(
        links=links,
        config=_html_source(),
        db_source_id=1,
        article_repo=_Repo(),
        settings=_settings(html_max_links_per_source=-1, article_batch_upsert_enabled=False),
    )

    assert fetched == 1
    assert new_count == 0
    assert duplicates == 2
    assert skipped == 1
    assert early_stop is False


def test_process_html_links_two_stage_batch_mode(monkeypatch) -> None:
    class _Repo:
        @staticmethod
        def existing_canonical_hashes(_hashes: list[str]) -> set[str]:
            return set()

        @staticmethod
        def upsert_articles_batch(rows: list[dict[str, object]]) -> tuple[int, int]:
            assert len(rows) == 2
            return 2, 1

    class _FakeFetcher:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def close(self) -> None:
            return None

    def _fake_fetch_html_article(*, url: str, **_kwargs):
        return Article(
            source_key="html_source",
            title=url.rsplit("/", maxsplit=1)[-1],
            url=url,
            published_at=datetime(2026, 2, 28, tzinfo=UTC),
        )

    monkeypatch.setattr("app.core.pipeline.Fetcher", _FakeFetcher)
    monkeypatch.setattr("app.core.pipeline.fetch_html_article", _fake_fetch_html_article)
    monkeypatch.setattr("app.core.pipeline.ai_relevance_score", lambda _item: 0.5)
    monkeypatch.setattr("app.core.pipeline.freshness_score", lambda _published: 0.5)
    monkeypatch.setattr("app.core.pipeline.rank_score", lambda **_kwargs: 1.0)

    fetched, new_count, duplicates, skipped, early_stop = _process_html_links_two_stage(
        links=["https://example.com/one", "https://example.com/two"],
        config=_html_source(),
        db_source_id=1,
        article_repo=_Repo(),
        settings=_settings(article_batch_upsert_enabled=True),
    )

    assert fetched == 2
    assert new_count == 2
    assert duplicates == 1
    assert skipped == 0
    assert early_stop is False


def test_process_html_links_two_stage_without_known_hash_helpers(monkeypatch) -> None:
    class _Repo:
        @staticmethod
        def insert_article(**_row):
            return SimpleNamespace(), True

    class _FakeFetcher:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def close(self) -> None:
            return None

    monkeypatch.setattr("app.core.pipeline.Fetcher", _FakeFetcher)
    monkeypatch.setattr(
        "app.core.pipeline.fetch_html_article",
        lambda **kwargs: Article(
            source_key="html_source",
            title="Solo",
            url=kwargs["url"],
            published_at=datetime(2026, 2, 28, tzinfo=UTC),
        ),
    )
    monkeypatch.setattr("app.core.pipeline.ai_relevance_score", lambda _item: 0.5)
    monkeypatch.setattr("app.core.pipeline.freshness_score", lambda _published: 0.5)
    monkeypatch.setattr("app.core.pipeline.rank_score", lambda **_kwargs: 1.0)

    fetched, new_count, duplicates, skipped, early_stop = _process_html_links_two_stage(
        links=["https://example.com/solo"],
        config=_html_source(),
        db_source_id=1,
        article_repo=_Repo(),
        settings=_settings(article_batch_upsert_enabled=False),
    )

    assert fetched == 1
    assert new_count == 1
    assert duplicates == 0
    assert skipped == 0
    assert early_stop is False


def test_persist_fetch_state_if_present_skips_results_without_metadata() -> None:
    assert (
        _persist_fetch_state_if_present(
            source_repo=SimpleNamespace(),
            db_source_id=1,
            result=HtmlListPageResult(links=["https://example.com/news/1"]),
        )
        is None
    )
