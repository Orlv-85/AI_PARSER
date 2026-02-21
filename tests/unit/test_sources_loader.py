import pytest

from app.config.sources import load_sources


def test_load_sources_from_mapping(tmp_path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
sources:
  - id: source_1
    name: Source 1
    type: rss
    url: https://example.com/feed.xml
    enabled: true
    fetch_interval_minutes: 15
    source_weight: 0.8
  - id: source_2
    name: Source 2
    type: html
    url: https://example.com/news
    html:
      list_selector: main
      link_selector: a
      article_selector: article
      extraction_strategy: trafilatura
""".strip(),
        encoding="utf-8",
    )

    sources = load_sources(path)

    assert len(sources) == 2
    assert sources[0].id == "source_1"
    assert sources[1].type == "html"


def test_load_sources_applies_defaults_and_parser_options(tmp_path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
version: 1
defaults:
  language: en
  enabled: true
  fetch_interval_minutes: 60
  respect_robots: true
  source_weight: 1.0
sources:
  - id: anthropic_news
    name: Anthropic Newsroom
    type: html
    url: https://www.anthropic.com/news
    parser_options:
      list_mode: generic
      article_mode: readability
      respect_robots: true
""".strip(),
        encoding="utf-8",
    )

    sources = load_sources(path)

    assert len(sources) == 1
    assert sources[0].language == "en"
    assert sources[0].fetch_interval_minutes == 60
    assert sources[0].respect_robots is True
    assert sources[0].parser_options is not None
    assert sources[0].parser_options.article_mode == "readability"


def test_load_sources_rejects_html_without_options(tmp_path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
- id: bad_html
  name: Bad HTML
  type: html
  url: https://example.com/news
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid sources configuration"):
        load_sources(path)
