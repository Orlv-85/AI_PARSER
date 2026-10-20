import re
from hashlib import sha1

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(value: str) -> list[str]:
    words = _TOKEN_RE.findall(value.lower())
    normalized_words: list[str] = []
    for word in words:
        if len(word) > 3 and word.endswith("s"):
            normalized_words.append(word[:-1])
        else:
            normalized_words.append(word)

    bigrams = [
        f"{normalized_words[idx]}_{normalized_words[idx + 1]}"
        for idx in range(len(normalized_words) - 1)
    ]
    return normalized_words + bigrams


def simhash64(value: str) -> int:
    tokens = _tokenize(value)
    if not tokens:
        return 0

    bit_weights = [0] * 64
    for token in tokens:
        token_hash = int.from_bytes(sha1(token.encode("utf-8")).digest()[:8], byteorder="big")
        for bit in range(64):
            bit_weights[bit] += 1 if token_hash & (1 << bit) else -1

    result = 0
    for bit, weight in enumerate(bit_weights):
        if weight >= 0:
            result |= 1 << bit
    return result


def hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()

