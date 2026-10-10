import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.config.sources import SourceConfig
from app.core.models import Article
from app.core.pipeline import (
    _managed_source_to_config,
    _process_fetched_source_items,
    _process_html_links_two_stage,
)
from app.ingest.html import (
    _build_html_article,
    extract_links_from_html,
    fetch_html,
    fetch_html_article,
)
from app.ingest.page_filter import html_exclusion_reason, url_exclusion_reason
from app.ingest.rss import RssFetchResult, fetch_rss, parse_rss
from app.storage.models_sql import Article as StoredArticle
from app.storage.models_sql import Base
from app.storage.repos import ArticleRepo, SourceRepo

BAD_URLS = [
    "https://kobiton.com/about-kobiton",
    "https://www.qualitestgroup.com/about-us",
    "https://www.qualitestgroup.com/about-us/leadership-team",
    "https://www.qualitestgroup.com/about-us/board-of-directors",
    "https://autify.com/about",
    "https://autify.com/genesis",
    "https://www.qodo.ai/about",
    "https://example.com/en/careers/",
    "https://example.com/contact?utm_source=blog",
    "https://example.com/blog/category/ai",
    "https://example.com/insights/blog",
]


def _source(kind="html") -> SourceConfig:
    return SourceConfig(id="example", name="Example", type=kind,
                        url="https://example.com/blog", html={} if kind == "html" else None)


@pytest.mark.parametrize("url", BAD_URLS)
def test_known_non_news_never_downloads_or_extracts(url, monkeypatch) -> None:
    def forbidden(**_kwargs):
        pytest.fail("Rejected page was downloaded or extracted")
    monkeypatch.setattr("app.ingest.html.extract_article_text", forbidden)
    fetcher = SimpleNamespace(fetch_text=forbidden)
    assert fetch_html_article(source=_source(), url=url, fetcher=fetcher) is None
    assert _build_html_article(source=_source(), url=url, article_html="<h1>AI</h1>") is None


@pytest.mark.parametrize("parser", ["lxml", "selectolax"])
def test_list_stage_skips_navigation_but_keeps_editorial_links(parser) -> None:
    content = """<html><body><nav><a href='/genesis'>Product</a></nav>
    <div role='navigation'><a href='/platform/tools'>Tools</a></div>
    <main><a href='/about'>About</a><a href='/blog'>Blog</a>
    <a href='/blog/introducing-genesis'>Release</a>
    <a href='/blog/introducing-genesis'>Duplicate</a>
    <a href='/research/team-agents'>Research</a><a href='/news/contact-model'>News</a></main>
    <footer><a href='/misc'>Misc</a></footer></body></html>"""
    assert extract_links_from_html(html_content=content, base_url="https://example.com/blog",
                                   list_selector=None, link_selector=None, parser=parser) == [
        "https://example.com/blog/introducing-genesis", "https://example.com/research/team-agents",
        "https://example.com/news/contact-model",
    ]


def test_landing_classification_uses_body_and_preserves_article_evidence(monkeypatch) -> None:
    landing = "<h1>Testing Platform</h1><main><h2>Features</h2><a>Request a Demo</a></main>"
    assert html_exclusion_reason("https://example.com/platform/tools", landing)
    monkeypatch.setattr("app.ingest.html.extract_article_text",
                        lambda **_kwargs: pytest.fail("Landing text extraction was attempted"))
    assert _build_html_article(source=_source(), url="https://example.com/products/tools",
                               article_html=landing) is None
    for url in ("https://example.com/blog/new-platform", "https://example.com/research/ai",
                "https://example.com/introducing-platform"):
        page = '<script type="application/ld+json">' + json.dumps(
            {"@graph": [{"@type": "BlogPosting"}]}) + "</script>" + landing
        assert html_exclusion_reason(url, page) is None
    assert html_exclusion_reason("https://example.com/products/release", (
        '<meta property="og:type" content="article">' + landing)) is None


@pytest.mark.parametrize("url", ["https://example.com/blog/about-ai-teams",
                                  "https://example.com/news/product-release",
                                  "https://example.com/ai", "https://example.com/team-research"])
def test_url_words_are_not_substring_bans(url) -> None:
    assert url_exclusion_reason(url) is None


def test_rss_filters_before_fulltext_and_keeps_undated_news() -> None:
    feed = b"""<rss version='2.0'><channel><title>Feed</title>
    <item><title>About</title><link>https://example.com/about</link></item>
    <item><title>Introducing Genesis</title><link>https://example.com/blog/genesis</link></item>
    </channel></rss>"""
    items = parse_rss("example", feed)
    assert len(items) == 1
    assert items[0].published_at is None


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("kind", ["rss", "html"])
def test_all_pipeline_item_paths_filter_before_models_and_preserve_dedupe(batch, kind) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source = _source(kind)
        db_source = SourceRepo(session).upsert_source(source)
        repo = ArticleRepo(session)
        items = [Article(source_key="example", title="About AI", url=BAD_URLS[0]),
                 Article(source_key="example", title="AI release", url="https://example.com/news/ai",
                         published_at=None)]
        scored = []
        def classify(item):
            scored.append(item)
        settings = Settings(article_batch_upsert_enabled=batch, rss_known_streak_stop=0)
        for _ in range(2):
            result = _process_fetched_source_items(
                items=items, config=source, db_source_id=db_source.id, article_repo=repo,
                settings=settings, relevance_scorer=SimpleNamespace(classify=classify))
        assert result[:2] == (0, 1)
        assert all(str(item.url) == "https://example.com/news/ai" for item in scored)
        assert session.scalar(select(func.count()).select_from(StoredArticle)) == 1


def test_two_stage_filters_before_limit_and_model_call(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    downloaded = []
    def fetch(**kwargs):
        downloaded.append(kwargs["url"])
        return Article(source_key="example", title="AI launch", url=kwargs["url"])
    monkeypatch.setattr("app.core.pipeline.fetch_html_article", fetch)
    with Session(engine) as session:
        source = _source()
        db_source = SourceRepo(session).upsert_source(source)
        repo = ArticleRepo(session)
        settings = Settings(html_max_links_per_source=1, html_known_streak_stop=0)
        links = [BAD_URLS[0], "https://example.com/news/new-agent"]
        assert _process_html_links_two_stage(links=links, config=source, db_source_id=db_source.id,
                                            article_repo=repo, settings=settings)[:2] == (1, 1)
        assert _process_html_links_two_stage(links=links, config=source, db_source_id=db_source.id,
                                            article_repo=repo, settings=settings)[1:4] == (0, 1, 1)
        assert downloaded == [links[1]]


def test_managed_source_selector_is_targeted() -> None:
    source = SimpleNamespace(source_key="autify-com-blog", name="Autify", type="html",
                             url="https://autify.com/blog", enabled=True,
                             fetch_interval_minutes=30, source_weight=1.0)
    config = _managed_source_to_config(source)
    assert config.html.link_selector == (
        'a[href^="/blog/"], a[href^="https://autify.com/blog/"]')


def test_positive_html_evidence_survives_pipeline_commerce_check(monkeypatch) -> None:
    monkeypatch.setattr("app.ingest.html.extract_article_text",
                        lambda **_kwargs: "Features and benefits. Request a demo")
    item = _build_html_article(source=_source(), url="https://example.com/products/new-release",
                              article_html='<meta property="og:type" content="article"><h1>AI</h1>')
    assert item is not None
    assert item.published_at is None
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        db_source = SourceRepo(session).upsert_source(_source())
        result = _process_fetched_source_items(items=[item], config=_source(),
                                              db_source_id=db_source.id,
                                              article_repo=ArticleRepo(session),
                                              settings=Settings())
        assert result[:2] == (1, 0)


def test_legacy_html_fetcher_path_filters_before_download(monkeypatch) -> None:
    calls = []
    def fetch_text(**kwargs):
        calls.append(kwargs["url"])
        if kwargs["url"] == "https://example.com/blog":
            return "<main><a href='/about'>About</a><a href='/blog/launch'>Launch</a></main>"
        return "<h1>Introducing AI testing</h1><p>A standalone news release.</p>"
    monkeypatch.setattr("app.ingest.html.extract_article_text", lambda **_kwargs: "Article body")
    items = fetch_html(_source(), fetcher=SimpleNamespace(fetch_text=fetch_text))
    assert len(items) == 1
    assert items[0].published_at is None
    assert calls == ["https://example.com/blog", "https://example.com/blog/launch"]


def test_rss_linked_landing_is_removed_before_text_extraction(monkeypatch) -> None:
    item = Article(source_key="example", title="Testing Platform",
                   url="https://example.com/products/tool")
    result = RssFetchResult(items=[item], not_modified=False, status_code=200,
                            etag=None, last_modified=None)
    monkeypatch.setattr("app.ingest.rss.fetch_rss_with_metadata", lambda **_kwargs: result)
    monkeypatch.setattr("app.ingest.rss.extract_article_text",
                        lambda **_kwargs: pytest.fail("Landing extraction was attempted"))
    fetcher = SimpleNamespace(fetch_text=lambda **_kwargs:
                              "<h1>Platform</h1><p>Features</p><a>Request a demo</a>")
    assert not fetch_rss("example", "https://example.com/feed", fetcher=fetcher,
                         extract_full_text=True)
