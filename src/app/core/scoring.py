import math
import re
from datetime import UTC, datetime

from app.core.models import Article

AI_KEYWORDS: dict[str, float] = {
    "ai": 1.0,
    "agent": 0.8,
    "artificial intelligence": 1.0,
    "benchmark": 0.5,
    "foundation model": 1.0,
    "gpt": 1.0,
    "inference": 0.8,
    "llm": 1.0,
    "multimodal": 0.9,
    "neural": 0.7,
    "reasoning": 0.8,
    "safety": 0.5,
    "transformer": 0.8,
}

STOP_WORDS = {
    "air",
    "aid",
    "aim",
    "rail",
    "said",
}


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip().lower()


def _contains_keyword(text: str, keyword: str) -> bool:
    # Avoid substring false positives like "paid" matching "ai".
    pattern = rf"(?<!\w){re.escape(keyword)}(?!\w)"
    return re.search(pattern, text) is not None


def ai_relevance_score(article: Article) -> float:
    title = _normalize(article.title)
    summary = _normalize(article.summary)
    content = _normalize(article.content)

    score = 0.0
    title_or_summary_hit = False
    for keyword, weight in AI_KEYWORDS.items():
        if keyword in STOP_WORDS:
            continue
        if _contains_keyword(title, keyword):
            score += weight * 1.0
            title_or_summary_hit = True
        if _contains_keyword(summary, keyword):
            score += weight * 0.6
            title_or_summary_hit = True
        if _contains_keyword(content, keyword):
            # Content is noisy (boilerplate/navigation text), keep it as a weak signal.
            score += weight * (0.15 if title_or_summary_hit else 0.03)

    return min(score / 5.0, 1.0)


def freshness_score(
    published_at: datetime | None,
    *,
    now: datetime | None = None,
    half_life_hours: float = 24.0,
) -> float:
    if published_at is None:
        return 0.0
    if now is None:
        now = datetime.now(UTC)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)

    age_seconds = max((now - published_at).total_seconds(), 0.0)
    half_life_seconds = max(half_life_hours, 1.0) * 3600.0
    return math.exp(-math.log(2) * age_seconds / half_life_seconds)


def rank_score(
    *,
    relevance: float,
    freshness: float,
    source_weight: float,
    alias_count: int = 0,
) -> float:
    bounded_relevance = min(max(relevance, 0.0), 1.0)
    bounded_freshness = min(max(freshness, 0.0), 1.0)
    bounded_source_weight = min(max(source_weight, 0.0), 1.0)
    alias_bonus = min(alias_count, 10) * 0.01
    return min(
        1.0,
        0.6 * bounded_freshness
        + 0.3 * bounded_relevance
        + 0.1 * bounded_source_weight
        + alias_bonus,
    )
