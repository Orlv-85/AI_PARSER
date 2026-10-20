from contextlib import contextmanager
from datetime import UTC, datetime
from logging import getLogger
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.config.settings import Settings
from app.config.sources import SourceConfig
from app.core.jev import JevAssessment
from app.core.models import Article
from app.core.pipeline import run_fetch_cycle
from app.ingest.html import HtmlListPageResult
from app.ingest.rss import RssFetchResult, RssItemList, _with_rss_metadata
from app.storage.models_sql import Article as StoredArticle
from app.storage.models_sql import Base, Source, WeeklyCoverageAttempt
from app.storage.repos import ArticleRepo


def _rss_items(
    items: list[Article], *, etag: str | None = None, coverage_complete: bool = True,
) -> RssItemList:
    return _with_rss_metadata(items, RssFetchResult(
        items=items, not_modified=False, status_code=200, etag=etag, last_modified=None,
        coverage_complete=coverage_complete,
    ))


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("source_type", ["rss", "html"])
def test_source_savepoint_recovers_after_database_error(
    monkeypatch, tmp_path, caplog, batch, source_type,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path}/isolation.db")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TRIGGER reject_article BEFORE INSERT ON articles "
            "WHEN NEW.title = 'Invalid' BEGIN SELECT RAISE(ABORT, 'invalid article'); END"
        ))
    sessions = sessionmaker(bind=engine, autoflush=False)
    configs = [
        SourceConfig(
            id=key, name=key, type=source_type, url=f"https://example.com/{key}",
            html={} if source_type == "html" else None,
        )
        for key in ("before", "broken", "after")
    ]
    now = datetime(2026, 10, 4, 12, tzinfo=UTC)
    articles = {
        key: [Article(
            source_key=key, title="AI update", url=f"https://example.com/{key}/1",
            published_at=now,
        )]
        for key in ("before", "broken", "after")
    }
    articles["broken"].append(Article(
        source_key="broken", title="Invalid", url="https://example.com/broken/2",
        published_at=now,
    ))

    def collect(**_kwargs):
        results = {}
        for index, config in enumerate(configs):
            items = articles[config.id]
            if source_type == "html":
                results[index] = HtmlListPageResult(
                    links=[str(item.url) for item in items], etag="new-validator",
                )
            else:
                results[index] = _rss_items(items, etag="new-validator")
        return results, 0

    def fetch_article(*, source, url, **_kwargs):
        return next(item for item in articles[source.id] if str(item.url) == url)

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", sessions)
    monkeypatch.setattr("app.core.pipeline._collect_fetched_items", collect)
    monkeypatch.setattr("app.core.pipeline.fetch_html_article", fetch_article)
    settings = Settings(
        article_batch_upsert_enabled=batch, respect_robots_txt=False,
        rss_known_streak_stop=0,
    )
    logger = getLogger("persistence-isolation")

    summary = run_fetch_cycle(settings=settings, logger=logger)

    assert summary.errors == 1
    assert summary.new == 2
    assert summary.duplicates == 0
    with sessions() as session:
        assert set(session.scalars(select(StoredArticle.url))) == {
            "https://example.com/before/1", "https://example.com/after/1",
        }
        sources = {source.source_key: source for source in session.scalars(select(Source))}
        assert sources["before"].etag == "new-validator"
        assert sources["after"].etag == "new-validator"
        assert sources["broken"].etag is None
        assert sources["broken"].last_checked_at is None
    failure = next(record for record in caplog.records if record.msg == "source_persist_failed")
    assert failure.args["source_id"] == "broken"
    assert failure.args["stage"] == "persist"

    articles["broken"][1] = articles["broken"][1].model_copy(update={"title": "Recovered"})
    recovered = run_fetch_cycle(settings=settings, logger=logger)
    assert recovered.errors == 0
    assert recovered.new == 2
    assert recovered.duplicates == 2
    with sessions() as session:
        assert len(list(session.scalars(select(StoredArticle)))) == 4
        source = session.scalar(select(Source).where(Source.source_key == "broken"))
        assert source is not None
        assert source.etag == "new-validator"


@pytest.mark.parametrize("batch", [False, True])
def test_article_storage_bounds_long_titles_in_both_insert_modes(tmp_path, batch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path}/titles.db")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    title = "AI headline " * 100
    row = {
        "source_id": None, "title": title, "url": "https://example.com/story",
        "url_canonical": "https://example.com/story", "url_canonical_hash": "title-test",
        "published_at": datetime.now(UTC), "ai_relevance_score": 0.5,
        "freshness_score": 0.5, "rank_score": 0.5,
    }
    with sessions() as session:
        repo = ArticleRepo(session)
        if batch:
            assert repo.upsert_articles_batch([row]) == (1, 0)
        else:
            _, is_new = repo.insert_article(**row)
            assert is_new
        session.commit()
    with sessions() as session:
        stored = session.scalar(select(StoredArticle))
        assert stored is not None
        assert stored.title == title[:512]
    assert row["title"] == title


NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)


def _sqlite_run(monkeypatch, tmp_path, configs, *, collect=None, fetch_article=None):
    engine = create_engine(f"sqlite:///{tmp_path}/run.db")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", sessions)
    if collect is not None:
        monkeypatch.setattr("app.core.pipeline._collect_fetched_items", collect)
    if fetch_article is not None:
        monkeypatch.setattr("app.core.pipeline.fetch_html_article", fetch_article)
    return sessions


def _settings(**overrides) -> Settings:
    values = {
        "_env_file": None, "respect_robots_txt": False, "rss_known_streak_stop": 0,
        "rss_extract_full_text": False, "weekly_v2_enabled": False,
        "article_batch_upsert_enabled": False,
    }
    values.update(overrides)
    return Settings(**values)


def _attempts(sessions) -> dict[str, tuple[str, bool]]:
    with sessions() as session:
        keys = {source.id: source.source_key for source in session.scalars(select(Source))}
        return {
            keys[attempt.source_id]: (attempt.outcome, attempt.complete)
            for attempt in session.scalars(select(WeeklyCoverageAttempt))
        }


def _rss_entry(index: int, *, link: bool = True) -> str:
    link_tag = f"<link>https://example.com/news/ai-model-{index}</link>" if link else ""
    return (f"<item><title>AI model release {index}</title>{link_tag}"
            "<pubDate>Sun, 04 Oct 2026 12:00:00 GMT</pubDate></item>")


def test_rss_skipped_entry_or_malformed_feed_marks_coverage_incomplete(monkeypatch, tmp_path):
    feeds = {
        "complete": f"<rss version=\"2.0\"><channel><title>AI</title>{_rss_entry(1)}"
                    "</channel></rss>",
        "skipped": f"<rss version=\"2.0\"><channel><title>AI</title>{_rss_entry(2)}"
                   f"{_rss_entry(3, link=False)}</channel></rss>",
        "malformed": f"<rss version=\"2.0\"><channel><title>AI</title>{_rss_entry(4)}"
                     "</channel>",
    }
    configs = [
        SourceConfig(id=key, name=key, type="rss", url=f"https://example.com/{key}.xml")
        for key in feeds
    ]

    def request(_self, *, source_id, url, **_kwargs):
        return httpx.Response(200, content=feeds[source_id].encode(),
                              request=httpx.Request("GET", url))

    monkeypatch.setattr("app.ingest.fetcher.Fetcher.request", request)
    sessions = _sqlite_run(monkeypatch, tmp_path, configs)

    summary = run_fetch_cycle(settings=_settings(), logger=getLogger("coverage"))

    assert summary.errors == 0
    assert summary.new == 3
    assert _attempts(sessions) == {
        "complete": ("success", True),
        "skipped": ("parser_failure", False),
        "malformed": ("parser_failure", False),
    }


def _html_configs(*keys: str) -> list[SourceConfig]:
    return [
        SourceConfig(id=key, name=key, type="html", url=f"https://example.com/{key}", html={})
        for key in keys
    ]


def _html_links(links_by_source: dict[str, list[str]]):
    def collect(*, enabled_sources, **_kwargs):
        return {
            index: HtmlListPageResult(links=links_by_source[config.id])
            for index, config, *_ in enabled_sources
        }, 0
    return collect


def _dated_article(*, source, url, **_kwargs):
    return Article(source_key=source.id, title="AI update", url=url, published_at=NOW,
                   content="AI is central.")


def test_html_link_cap_marks_coverage_incomplete(monkeypatch, tmp_path):
    links = {
        "capped": [f"https://example.com/capped/story-{i}" for i in range(3)],
        "within": [f"https://example.com/within/story-{i}" for i in range(2)],
    }
    sessions = _sqlite_run(
        monkeypatch, tmp_path, _html_configs("capped", "within"),
        collect=_html_links(links), fetch_article=_dated_article,
    )

    summary = run_fetch_cycle(
        settings=_settings(html_max_links_per_source=2), logger=getLogger("coverage"),
    )

    assert summary.new == 4
    assert _attempts(sessions) == {
        "capped": ("parser_failure", False),
        "within": ("success", True),
    }


def test_failed_or_unparsable_html_article_marks_coverage_incomplete(monkeypatch, tmp_path):
    links = {
        key: [f"https://example.com/{key}/story-1", f"https://example.com/{key}/story-2"]
        for key in ("ok", "raises", "unparsable")
    }

    def fetch_article(*, source, url, **kwargs):
        if url.endswith("story-1") and source.id == "raises":
            raise httpx.ReadTimeout("offline")
        if url.endswith("story-1") and source.id == "unparsable":
            return None
        return _dated_article(source=source, url=url, **kwargs)

    sessions = _sqlite_run(
        monkeypatch, tmp_path, _html_configs(*links),
        collect=_html_links(links), fetch_article=fetch_article,
    )

    summary = run_fetch_cycle(settings=_settings(), logger=getLogger("coverage"))

    assert summary.errors == 0
    assert summary.new == 4
    assert _attempts(sessions) == {
        "ok": ("success", True),
        "raises": ("parser_failure", False),
        "unparsable": ("parser_failure", False),
    }


def test_coverage_attempt_records_fetch_persist_and_parser_failures(monkeypatch, tmp_path):
    configs = [
        SourceConfig(id=key, name=key, type="rss", url=f"https://example.com/{key}.xml")
        for key in ("ok", "fetch", "persist", "parser")
    ]
    items = {
        key: [Article(source_key=key, title="AI update" if key != "persist" else "Invalid",
                      url=f"https://example.com/{key}/1", published_at=NOW)]
        for key in ("ok", "persist", "parser")
    }

    def collect(*, enabled_sources, **_kwargs):
        results = {}
        for index, config, *_ in enabled_sources:
            if config.id in items:
                results[index] = _rss_items(
                    items[config.id], coverage_complete=config.id != "parser",
                )
        return results, 1

    sessions = _sqlite_run(monkeypatch, tmp_path, configs, collect=collect)
    with sessions() as session:
        session.execute(text(
            "CREATE TRIGGER reject_article BEFORE INSERT ON articles "
            "WHEN NEW.title = 'Invalid' BEGIN SELECT RAISE(ABORT, 'invalid article'); END"
        ))
        session.commit()

    summary = run_fetch_cycle(settings=_settings(), logger=getLogger("coverage"))

    assert summary.errors == 2
    attempts = _attempts(sessions)
    assert {key: outcome for key, (outcome, _) in attempts.items()} == {
        "ok": "success", "fetch": "fetch_failure",
        "persist": "persist_failure", "parser": "parser_failure",
    }
    assert attempts["ok"][1] is True
    assert attempts["fetch"][1] is True
    assert attempts["persist"][1] is False
    assert attempts["parser"][1] is False


def test_undated_item_marks_coverage_incomplete(monkeypatch, tmp_path):
    configs = [
        SourceConfig(id=key, name=key, type="rss", url=f"https://example.com/{key}.xml")
        for key in ("rss_dated", "rss_undated", "rss_updated_only")
    ] + _html_configs("html_dated", "html_undated")
    rss_items = {
        "rss_dated": Article(source_key="rss_dated", title="AI update",
                             url="https://example.com/rss_dated/1", published_at=NOW),
        "rss_undated": Article(source_key="rss_undated", title="AI update",
                               url="https://example.com/rss_undated/1", published_at=None),
        "rss_updated_only": Article(
            source_key="rss_updated_only", title="AI update",
            url="https://example.com/rss_updated_only/1", published_at=None,
            publication_evidence_at=NOW, publication_date_kind="updated",
        ),
    }

    def collect(*, enabled_sources, **_kwargs):
        return {
            index: _rss_items([rss_items[config.id]]) if config.type == "rss"
            else HtmlListPageResult(links=[f"https://example.com/{config.id}/story-1"])
            for index, config, *_ in enabled_sources
        }, 0

    def fetch_article(*, source, url, **kwargs):
        if source.id == "html_undated":
            return Article(source_key=source.id, title="AI update", url=url, published_at=None,
                           content="AI is central.")
        return _dated_article(source=source, url=url, **kwargs)

    sessions = _sqlite_run(monkeypatch, tmp_path, configs, collect=collect,
                           fetch_article=fetch_article)

    summary = run_fetch_cycle(settings=_settings(), logger=getLogger("coverage"))

    assert (summary.errors, summary.new) == (0, 5)
    assert _attempts(sessions) == {
        "rss_dated": ("success", True),
        "rss_undated": ("parser_failure", False),
        "rss_updated_only": ("parser_failure", False),
        "html_dated": ("success", True),
        "html_undated": ("parser_failure", False),
    }


def test_two_urls_of_one_story_become_two_articles(monkeypatch, tmp_path):
    configs = [SourceConfig(id="feed", name="feed", type="rss", url="https://example.com/feed")]
    story = {"title": "OpenAI releases a new model", "summary": "Same story text.",
             "content": "OpenAI released a new AI model today.", "published_at": NOW}
    items = [
        Article(source_key="feed", url="https://example.com/news/openai-model", **story),
        Article(source_key="feed", url="https://example.com/blog/openai-model", **story),
    ]
    sessions = _sqlite_run(
        monkeypatch, tmp_path, configs,
        collect=lambda **_kwargs: ({0: _rss_items(items)}, 0),
    )

    first = run_fetch_cycle(settings=_settings(), logger=getLogger("identity"))
    second = run_fetch_cycle(settings=_settings(), logger=getLogger("identity"))

    assert (first.new, first.duplicates) == (2, 0)
    assert (second.new, second.duplicates) == (0, 2)
    with sessions() as session:
        assert sorted(session.scalars(select(StoredArticle.url))) == [
            "https://example.com/blog/openai-model", "https://example.com/news/openai-model",
        ]


def test_per_row_duplicate_updates_scores_and_category_only(monkeypatch, tmp_path):
    configs = [SourceConfig(id="feed", name="feed", type="rss", url="https://example.com/feed")]
    original = Article(source_key="feed", title="AI update", url="https://example.com/ai-update",
                       summary="First summary", content="First text.", published_at=NOW)
    changed = Article(
        source_key="feed", title="Changed title",
        url="https://example.com/ai-update?utm_source=feed", summary="New summary",
        content="New text.", published_at=datetime(2026, 10, 5, 12, tzinfo=UTC),
    )
    batch = {"items": [original]}
    assessments = {
        "AI update": JevAssessment(0.2, "AI Coding", 0.9),
        "Changed title": JevAssessment(0.95, "AI Applications", 0.8),
    }

    @contextmanager
    def scorer(*_args):
        yield SimpleNamespace(classify=lambda item: assessments[item.title])

    monkeypatch.setattr("app.core.pipeline.jev_relevance_scorer", scorer)
    sessions = _sqlite_run(
        monkeypatch, tmp_path, configs,
        collect=lambda **_kwargs: ({0: _rss_items(batch["items"])}, 0),
    )
    settings = _settings(article_batch_upsert_enabled=False)

    assert run_fetch_cycle(settings=settings, logger=getLogger("duplicate")).new == 1
    with sessions() as session:
        before = session.scalar(select(StoredArticle))
        assert before is not None
        first_rank = before.rank_score
    batch["items"] = [changed]
    second = run_fetch_cycle(settings=settings, logger=getLogger("duplicate"))

    assert (second.new, second.duplicates) == (0, 1)
    with sessions() as session:
        stored = session.scalar(select(StoredArticle))
        assert stored is not None
        assert stored.ai_relevance_score == 0.95
        assert stored.rank_score != first_rank
        assert (stored.category, stored.category_confidence) == ("AI Applications", 0.8)
        assert stored.title == "AI update"
        assert stored.url == "https://example.com/ai-update"
        assert (stored.summary, stored.content) == ("First summary", "First text.")
        assert stored.published_at.replace(tzinfo=UTC) == NOW


@pytest.mark.parametrize("stage", ["load_sources", "create_all", "register_source"])
def test_error_outside_source_loop_aborts_without_commit(monkeypatch, tmp_path, stage):
    configs = [SourceConfig(id="feed", name="feed", type="rss", url="https://example.com/feed")]
    sessions = _sqlite_run(
        monkeypatch, tmp_path, configs,
        collect=lambda **_kwargs: pytest.fail("A broken run must not fetch sources"),
    )

    def broken(*_args, **_kwargs):
        raise RuntimeError(f"broken {stage}")

    monkeypatch.setattr(f"app.core.pipeline.{stage}", broken)

    with pytest.raises(RuntimeError, match=f"broken {stage}"):
        run_fetch_cycle(settings=_settings(), logger=getLogger("abort"))

    with sessions() as session:
        assert not list(session.scalars(select(Source)))
        assert not list(session.scalars(select(WeeklyCoverageAttempt)))


def test_html_fetch_cycle_skips_failed_article_only(monkeypatch, tmp_path):
    base = "https://example.com/site"
    pages = {
        base: '<main><a href="/site/news-1">one</a><a href="/site/news-2">two</a>'
              '<a href="/site/news-3">three</a></main>',
        f"{base}/news-1": "<html><body><h1>Headline</h1><p>content</p></body></html>",
        f"{base}/news-3": "<html><body><p>no h1</p></body></html>",
    }

    def request(_self, *, source_id, url, **_kwargs):
        assert source_id == "site"
        if url not in pages:
            raise RuntimeError("fetch_failed")
        return httpx.Response(200, text=pages[url], request=httpx.Request("GET", url))

    monkeypatch.setattr("app.ingest.fetcher.Fetcher.request", request)
    monkeypatch.setattr("app.ingest.html.extract_article_text", lambda **_kwargs: "parsed")
    sessions = _sqlite_run(monkeypatch, tmp_path, _html_configs("site"))

    summary = run_fetch_cycle(settings=_settings(), logger=getLogger("html-failure"))

    assert (summary.errors, summary.new) == (0, 2)
    with sessions() as session:
        assert sorted(session.scalars(select(StoredArticle.title))) == [
            "Headline", f"{base}/news-3",
        ]
    assert _attempts(sessions) == {"site": ("parser_failure", False)}
