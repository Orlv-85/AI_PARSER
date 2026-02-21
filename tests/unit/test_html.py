from pathlib import Path

from app.ingest.html import extract_article_text, extract_links_from_html


def test_extract_links_from_html_uses_selectors_and_deduplicates() -> None:
    html_content = Path("tests/fixtures/html/list_page.html").read_text(encoding="utf-8")
    links = extract_links_from_html(
        html_content=html_content,
        base_url="https://example.com",
        list_selector="main.news-list",
        link_selector="a",
    )

    assert links == [
        "https://example.com/news/post-1",
        "https://example.com/news/post-2",
    ]


def test_extract_article_text_returns_plain_text() -> None:
    html_content = Path("tests/fixtures/html/article_page.html").read_text(encoding="utf-8")
    text = extract_article_text(
        html_content=html_content,
        url="https://example.com/news/post-1",
        strategy="readability",
    )

    assert text is not None
    assert "AI Safety Update" in text
    assert "frontier models" in text

