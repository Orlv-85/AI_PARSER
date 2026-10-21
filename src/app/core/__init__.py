from app.core.canonicalize import canonical_url_hash, canonicalize_url
from app.core.ingestion.dedup import hamming_distance, simhash64
from app.core.ingestion.scoring import ai_relevance_score, freshness_score, rank_score
from app.core.models import Article

__all__ = [
    "Article",
    "canonical_url_hash",
    "canonicalize_url",
    "freshness_score",
    "hamming_distance",
    "rank_score",
    "simhash64",
    "ai_relevance_score",
]
