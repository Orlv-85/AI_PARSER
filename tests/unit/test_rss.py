from pathlib import Path

from app.ingest.rss import parse_rss


def test_parse_rss_maps_entries_to_article_model() -> None:
    fixture = Path("tests/fixtures/rss/sample_feed.xml").read_bytes()

    items = parse_rss(source_key="sample_feed", content=fixture)

    assert len(items) == 2
    assert items[0].source_key == "sample_feed"
    assert items[0].title == "New AI model release"
    assert str(items[0].url) == "https://example.com/posts/model-release"
    assert items[0].published_at is not None

