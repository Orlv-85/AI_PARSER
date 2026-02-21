from app.core.dedup import DedupCandidate, find_duplicate, hamming_distance, simhash64


def test_simhash_close_for_near_duplicate_titles() -> None:
    left = simhash64("OpenAI releases a new frontier reasoning model")
    right = simhash64("OpenAI releases new frontier reasoning model")
    assert hamming_distance(left, right) <= 10


def test_find_duplicate_returns_matching_article_id() -> None:
    existing = simhash64("Anthropic introduces constitutional model updates")
    duplicate_id = find_duplicate(
        content="Anthropic introduces constitutional model update",
        candidates=[DedupCandidate(article_id=42, simhash=existing)],
        threshold=10,
    )
    assert duplicate_id == 42


def test_find_duplicate_returns_none_for_distant_content() -> None:
    candidates = [
        DedupCandidate(article_id=7, simhash=simhash64("GPU market analysis and pricing"))
    ]
    duplicate_id = find_duplicate(
        content="OpenAI announces new multimodal API capabilities",
        candidates=candidates,
        threshold=4,
    )
    assert duplicate_id is None
