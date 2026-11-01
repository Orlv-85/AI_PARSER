"""Grounding checks of the bulletin writer's sentences (spec 018, item 3).

Pure. Behavior, limits and tests: src/app/core/bulletin/writer.md ("Grounding").
"""
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from app.core.bulletin.phrases import never_word
from app.core.daily.signals_brief import (
    MARKUP,
    NON_ENGLISH,
    NUMBER,
    STARTERS,
    WORD,
    grounding_error,
    norm,
)

SENTENCE_MIN_CHARS = 20
SENTENCE_MAX_CHARS = 420
QUOTE_MAX_WORDS = 12  # ER-9: short quotes only
COPY_RUN_WORDS = 10  # ER-9: a run this long that also stands in the original is copying
WRITER_STARTERS = STARTERS | frozenset("""However Still Yet Last Next Most Many Some Such These
Those Their His Her He She They We What When Where Who How Why If So Then Now Here There No Not
Only Per Since Until While Within Without Between Among During Before Early Late Earlier Later
Given Using Under Despite Although Because Instead Reportedly Officials Experts Users Companies
People""".split())
QUOTED = re.compile(r'"([^"]+)"')
TOKEN = re.compile(r"\w+")
THE_ADMINISTRATION = re.compile(r"\b[Tt]he Administration\b")
THOUSANDS = re.compile(r"\d{1,3}(?:[.,]\d{3})+")

_CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya", "і": "i",
    "ї": "yi", "є": "ye", "ґ": "g"}
TRANSLIT = {ord(low): latin for low, latin in _CYRILLIC.items()}
TRANSLIT.update({ord(low.upper()): latin.capitalize() for low, latin in _CYRILLIC.items()})


def fold(text: str) -> str:
    """Normalised text with Cyrillic transliterated and accents removed; case is kept."""
    value = norm(text).translate(TRANSLIT)
    value = unicodedata.normalize("NFKD", value)
    return "".join(c for c in value if not unicodedata.combining(c))


def canon_number(value: str) -> str:
    """Thousand separators removed, a decimal comma written as a point, `%` dropped."""
    value = value.rstrip("%")
    if THOUSANDS.fullmatch(value):
        return re.sub(r"[.,]", "", value)
    return value.replace(",", ".")


@dataclass(frozen=True)
class _Evidence:
    numbers: frozenset[str]
    words: frozenset[str]
    text: str
    grams: frozenset[tuple[str, ...]]


def _grams(words: list[str]) -> frozenset[tuple[str, ...]]:
    return frozenset(tuple(words[i:i + COPY_RUN_WORDS])
                     for i in range(len(words) - COPY_RUN_WORDS + 1))


def _words(text: str) -> frozenset[str]:
    """Whole words of the evidence, and the parts of hyphenated or dotted ones."""
    found = set(WORD.findall(text))
    for word in list(found):
        found.update(part for part in re.split(r"[-.+]", word) if part)
    return frozenset(found)


@lru_cache(maxsize=256)
def _evidence(raw: str) -> _Evidence:
    folded = fold(raw)
    text = folded.casefold()
    return _Evidence(
        numbers=frozenset(canon_number(n) for n in NUMBER.findall(folded)),
        words=_words(text), text=text,
        grams=_grams(TOKEN.findall(text)))


def _quote_error(text: str, evidence: _Evidence) -> str | None:
    for quote in QUOTED.findall(text):
        if len(quote.split()) > QUOTE_MAX_WORDS:
            return "long_quote"
        if re.sub(r"\s+", " ", quote).strip().casefold() not in evidence.text:
            return "quote_not_found"
    return None


def _copies(text: str, evidence: _Evidence) -> bool:
    words = TOKEN.findall(QUOTED.sub(" ", text).casefold())
    return bool(_grams(words) & evidence.grams)


def sentence_error(text: str, evidence: str, *, copy: bool = False,
                   min_chars: int = SENTENCE_MIN_CHARS,
                   max_chars: int = SENTENCE_MAX_CHARS) -> str | None:
    """Drop code of the first failing check of a model text against the `evidence` it was given,
    or None. Checks, in order: length, markup, English only, never-list, quotes, copying (when
    `copy`), numbers, names."""
    if not min_chars <= len(text.strip()) <= max_chars:
        return "length"
    if MARKUP.search(text):
        return "markup"
    if NON_ENGLISH.search(text):
        return "non_english"
    if never_word(text) or THE_ADMINISTRATION.search(text):
        return "never_list"
    proof = _evidence(evidence)
    folded = fold(text)
    code = _quote_error(folded, proof)
    if code is None and copy and _copies(folded, proof):
        code = "too_close"
    return code or grounding_error(folded, set(proof.numbers), "", starters=WRITER_STARTERS,
                                   canon=canon_number, words=proof.words)
