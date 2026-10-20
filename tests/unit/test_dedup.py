from app.core.dedup import hamming_distance, simhash64


def test_simhash_close_for_near_duplicate_titles() -> None:
    left = simhash64("OpenAI releases a new frontier reasoning model")
    right = simhash64("OpenAI releases new frontier reasoning model")
    assert hamming_distance(left, right) <= 10

