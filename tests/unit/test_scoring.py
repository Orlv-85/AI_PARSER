from datetime import UTC, datetime, timedelta

import pytest

from app.core.ingestion.scoring import ai_relevance_score, freshness_score, rank_score
from app.core.models import Article


def test_ai_relevance_higher_for_ai_keywords() -> None:
    ai_article = Article(
        source_key="a",
        title="OpenAI releases new multimodal GPT model",
        url="https://example.com/a",
        summary="Frontier model reasoning and inference updates.",
    )
    generic_article = Article(
        source_key="b",
        title="Quarterly corporate update",
        url="https://example.com/b",
        summary="General business and finance results.",
    )

    assert ai_relevance_score(ai_article) > ai_relevance_score(generic_article)


def test_freshness_decay_uses_half_life() -> None:
    now = datetime(2026, 2, 21, 12, 0, tzinfo=UTC)
    twenty_four_hours_ago = now - timedelta(hours=24)
    score = freshness_score(twenty_four_hours_ago, now=now, half_life_hours=24)
    assert 0.49 <= score <= 0.51


def test_rank_score_combines_signal_weights() -> None:
    score = rank_score(relevance=0.8, freshness=0.9, source_weight=0.7)
    assert score == pytest.approx(0.6 * 0.9 + 0.3 * 0.8 + 0.1 * 0.7)


def test_ai_keyword_uses_word_boundary() -> None:
    article = Article(
        source_key="c",
        title="Paid leave policy update",
        url="https://example.com/c",
        summary="General HR news.",
    )
    assert ai_relevance_score(article) == 0.0
