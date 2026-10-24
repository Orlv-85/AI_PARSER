from datetime import UTC, date, datetime
from types import SimpleNamespace

from app.config.sources import SourceConfig
from app.core.ingestion.pipeline.rows import _build_article_row
from app.ingest.html import fetch_html_article
from app.ingest.rss import parse_rss


def test_atom_updated_only_does_not_become_publication():
    items = parse_rss(
        "test",
        b"""<feed xmlns="http://www.w3.org/2005/Atom">
      <title>AI feed</title><id>urn:test</id><updated>2026-10-01T12:00:00Z</updated>
      <entry><id>urn:item</id><title>AI research</title>
      <link href="https://example.com/research"/><updated>2026-10-01T12:00:00Z</updated>
      </entry></feed>""",
    )
    assert len(items) == 1
    assert items[0].published_at is None
    assert items[0].modified_at == datetime(2026, 10, 1, 12, tzinfo=UTC)


def test_unknown_or_conflicting_publication_has_zero_freshness():
    source = SourceConfig(id="test", name="Test", type="rss", url="https://example.com/feed")
    for evidence in (None, {"published": {"status": "conflict", "selected": None}}):
        item = SimpleNamespace(
            title="AI research",
            url="https://example.com/research",
            published_at=None,
            date_evidence=evidence,
            summary=None,
            content=None,
        )
        row = _build_article_row(
            item=item,
            config=source,
            db_source_id=1,
            canonical=str(item.url),
            canonical_hash="a" * 64,
            assessment=None,
            admission_enabled=False,
        )
        assert row["published_at"] is None
        assert row["freshness_score"] == 0
        assert row["publication_status"] == ("conflict" if evidence else "unknown")


def test_day_precision_evidence_sets_publication_day_not_published_at():
    source = SourceConfig(id="test", name="Test", type="html", url="https://example.com/news",
                          html={})
    page = ('<html><head><meta property="article:published_time" content="2026-10-01">'
            "</head><body><h1>AI research</h1><p>AI research results.</p></body></html>")
    fetcher = SimpleNamespace(fetch_text=lambda **_kwargs: page)
    item = fetch_html_article(source=source, url="https://example.com/news/ai-research",
                              fetcher=fetcher)
    assert item is not None
    row = _build_article_row(
        item=item,
        config=source,
        db_source_id=1,
        canonical=str(item.url),
        canonical_hash="b" * 64,
        assessment=None,
        admission_enabled=False,
    )
    assert row["published_at"] is None
    assert row["publication_day"] == date(2026, 10, 1)
    assert row["publication_precision"] == "day"
    assert row["freshness_score"] == 0
