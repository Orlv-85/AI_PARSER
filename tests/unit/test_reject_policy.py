import pytest

from app.core.ingestion.reject_policy import cleanup_verdict
from app.core.jev import JevAssessment


def article(**overrides):
    return {"id": 1, "url": "https://example.com/about", "url_canonical":
            "https://example.com/about", "url_canonical_hash": "hash", "source_id": None,
            "title": "About us", "summary": None, "content": "Company history " * 30,
            "published_at": None, "rank_score": 0, **overrides}


@pytest.mark.parametrize("choice,confidence,score,url,body,outcome", [
    ("accepted_ai_editorial", 0.7, 0.99, "/news", "AI news", "kept"),
    ("accepted_ai_editorial", None, 0.9, "/research", "AI research", "kept"),
    ("accepted_ai_editorial", 0.99, 1, "/tutorial", "AI evergreen guide", "kept"),
    ("non_editorial", 0.99, 0.5, "/about", "Company", "rejected"),
    ("non_editorial", 0.99, 0.4, "/products/tool",
     "Features and pricing. Request a demo", "rejected"),
    ("non_ai", 0.99, 0.01, "/football", "Football results " * 30, "rejected"),
    ("non_ai", 0.99, 0.5, "/topic", "AI mentioned " * 30, "unresolved"),
    ("non_ai", 0.94, 0.01, "/topic", "Football results " * 30, "unresolved"),
    ("non_ai", None, 0.01, "/topic", "Football results " * 30, "unresolved"),
    ("non_ai", 0.99, 0.01, "/topic", "Short snippet", "unresolved"),
    ("non_editorial", 0.99, 0.1, "/blog/article", "Article " * 30, "unresolved"),
    ("insufficient_evidence", 0.99, 0.01, "/about", "Unknown", "unresolved"),
])
def test_conservative_policy(  # pylint: disable=too-many-positional-arguments
    choice, confidence, score, url, body, outcome,
):
    row = article(url="https://example.com" + url, title="Topic", content=body)
    verdict = cleanup_verdict(row, JevAssessment(score, admission_choice=choice,
                                                admission_confidence=confidence))
    assert verdict["outcome"] == outcome
