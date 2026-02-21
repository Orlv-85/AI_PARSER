from app.core.canonicalize import canonical_url_hash, canonicalize_url
from app.core.dedup import DedupCandidate, find_duplicate, hamming_distance, simhash64
from app.core.models import Article
from app.core.scoring import ai_relevance_score, freshness_score, rank_score

__all__ = [
    "Article",
    "DedupCandidate",
    "canonical_url_hash",
    "canonicalize_url",
    "find_duplicate",
    "freshness_score",
    "hamming_distance",
    "rank_score",
    "simhash64",
    "ai_relevance_score",
]
