from datetime import UTC, datetime

import pytest

from app.config.sources import SourceConfig, load_sources
from app.core.canonicalize import canonicalize_url
from app.core.dedup import simhash64
from app.core.models import Article
from app.core.scoring import ai_relevance_score, freshness_score, rank_score


def test_load_sources_empty_file_returns_empty_list(tmp_path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text("", encoding="utf-8")
    assert load_sources(path) == []


def test_load_sources_rejects_scalar_root(tmp_path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text("42", encoding="utf-8")
    with pytest.raises(ValueError, match="must contain either"):
        load_sources(path)


def test_source_id_is_lowercased_and_invalid_chars_fail() -> None:
    config = SourceConfig(id="UPPER_OK", name="X", type="rss", url="https://example.com/feed")
    assert config.id == "upper_ok"

    with pytest.raises(ValueError, match="only a-z"):
        SourceConfig(id="bad.id", name="X", type="rss", url="https://example.com/feed")


def test_canonicalize_handles_scheme_less_and_non_default_port() -> None:
    assert canonicalize_url(" example.com/path/?ref=x ") == "https:///example.com/path"
    assert canonicalize_url("https://example.com:8443/path") == "https://example.com:8443/path"
    assert canonicalize_url("https://example.com") == "https://example.com/"


def test_simhash_empty_content_is_zero() -> None:
    assert simhash64("") == 0


def test_freshness_and_rank_edge_cases() -> None:
    assert freshness_score(None) == 0.0

    naive = datetime(2026, 2, 21, 12, 0)
    now = datetime(2026, 2, 21, 12, 0, tzinfo=UTC)
    assert freshness_score(naive, now=now, half_life_hours=0.1) == 1.0
    assert 0.0 < freshness_score(now, half_life_hours=24.0) <= 1.0

    score = rank_score(relevance=2.0, freshness=-1.0, source_weight=5.0, alias_count=99)
    assert score == 0.5

    zeroed = rank_score(relevance=-1.0, freshness=-1.0, source_weight=-1.0, alias_count=0)
    assert zeroed == 0.0


def test_ai_relevance_uses_content_weight() -> None:
    article = Article(
        source_key="s",
        title="General update",
        url="https://example.com",
        content="Inference and reasoning improvements",
    )
    assert ai_relevance_score(article) > 0.0


def test_ai_relevance_skips_keywords_in_stop_words(monkeypatch) -> None:
    from app.core import scoring

    monkeypatch.setitem(scoring.AI_KEYWORDS, "zzstop", 1.0)
    monkeypatch.setattr(scoring, "STOP_WORDS", scoring.STOP_WORDS | {"zzstop"})
    article = Article(source_key="s", title="zzstop", url="https://example.com")
    assert ai_relevance_score(article) == 0.0
