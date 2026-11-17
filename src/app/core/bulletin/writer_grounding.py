"""Grounding checks of the bulletin writer's sentences (spec 018, item 3).

Pure. Behavior, limits and tests: src/app/core/bulletin/writer.md ("Grounding").
"""
import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.bulletin.phrases import never_word
from app.core.daily.signals_brief import (
    MARKUP,
    NON_ENGLISH,
    NUMBER,
    STARTERS,
    WORD,
    NameRules,
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
# Common nouns that open an English headline or sentence about a story in another language, where
# the article text cannot hold the English word.
HEADLINE_OPENERS = frozenset("""Survey Surveys Study Studies Report Reports Expert
Court Judge Scientists Regulators Workers Students Teachers Schools Former Commentary Critics
Analysts Hundreds Thousands Dozens""".split())
# The subject of every story: other languages write it differently (IA, KI, ИИ).
SUBJECT_WORDS = frozenset({"ai"})
QUOTED = re.compile(r'"([^"]+)"')
TOKEN = re.compile(r"\w+")
CAMEL_NAME = re.compile(r"[a-z]+[A-Z]")  # "xAI", "iPhone": a name that starts lower-case
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
# Latin letters that NFKD does not split into a base letter and an accent.
TRANSLIT.update({ord(c): latin for c, latin in {"đ": "d", "Đ": "D", "ß": "ss", "ł": "l",
                                                 "Ł": "L", "ø": "o", "Ø": "O"}.items()})
_GREEK = {
    "α": "a", "β": "v", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "i", "θ": "th", "ι": "i",
    "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x", "ο": "o", "π": "p", "ρ": "r", "σ": "s",
    "ς": "s", "τ": "t", "υ": "y", "φ": "f", "χ": "ch", "ψ": "ps", "ω": "o"}
GREEK = {ord(low): latin for low, latin in _GREEK.items()}
GREEK.update({ord(low.upper()): latin.capitalize() for low, latin in _GREEK.items() if low != "ς"})

NAME_FORMS_PATH = Path(__file__).with_name("name_forms.json")
FORM_MIN_CHARS = 3  # a Latin form without `*`
PREFIX_MIN_CHARS = 4  # a Latin form with `*`, before the star
SCRIPT_FORM_MIN_CHARS = 2  # a form that stays non-Latin after folding (Chinese, Arabic)
CYRILLIC_OR_GREEK = re.compile(r"[\u0370-\u03ff\u0400-\u04ff]")  # these fold to Latin
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")  # no spaces between words


def fold(text: str) -> str:
    """Normalised text with Cyrillic and Greek transliterated and accents removed; case is kept."""
    value = unicodedata.normalize("NFKD", norm(text).translate(TRANSLIT))
    return "".join(c for c in value if not unicodedata.combining(c)).translate(GREEK)


def _form_pattern(key: str, form: object) -> re.Pattern[str]:
    """Pattern of one form of a name in the folded, casefolded evidence; ValueError if invalid."""
    if not isinstance(form, str):
        raise ValueError(f"name forms: {key!r}: form {form!r} is not a string")
    folded = fold(form).casefold().strip()
    stem = folded.removesuffix("*")
    if "*" in stem:
        raise ValueError(f"name forms: {key!r}: form {form!r} has a star before its end")
    if CJK.search(stem):
        if len(stem) < SCRIPT_FORM_MIN_CHARS:
            raise ValueError(f"name forms: {key!r}: form {form!r} is too short")
        return re.compile(re.escape(stem))
    prefix = folded.endswith("*")
    least = FORM_MIN_CHARS if stem.isascii() else SCRIPT_FORM_MIN_CHARS
    if len(stem) < (PREFIX_MIN_CHARS if prefix else least):
        raise ValueError(f"name forms: {key!r}: form {form!r} is too short")
    body = r"\s+".join(re.escape(part) for part in stem.split())
    return re.compile(rf"(?<!\w){body}" + ("" if prefix else r"(?!\w)"))


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    found: dict[str, object] = {}
    for key, value in pairs:
        if key in found:
            raise ValueError(f"name forms: duplicate key {key!r}")
        found[key] = value
    return found


@lru_cache(maxsize=4)
def load_name_forms(path: Path) -> dict[str, tuple[re.Pattern[str], ...]]:
    """The name-forms table: lower-case English name word -> patterns of its forms in other
    languages. A malformed table raises ValueError (tests catch it, not production)."""
    table = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)
    for key, forms in table.items():
        if key != key.casefold() or not key or len(key.split()) != 1:
            raise ValueError(f"name forms: key {key!r} must be one lower-case word")
        if not isinstance(forms, list) or not forms:
            raise ValueError(f"name forms: {key!r} has no forms")
    return {key: tuple(_form_pattern(key, form) for form in forms)
            for key, forms in table.items()}


def _name_words(raw: str, text: str) -> frozenset[str]:
    """Table keys with a form in the folded `text`, and adjacent words of `raw` joined when they
    are accented Latin ("Hà Nội" gives "hanoi"; "met a" and Russian "и ран" give nothing)."""
    keys = (key for key, patterns in load_name_forms(NAME_FORMS_PATH).items()
            if any(pattern.search(text) for pattern in patterns))
    tokens = TOKEN.findall(raw)
    joined = (fold(a + b).casefold() for a, b in zip(tokens, tokens[1:], strict=False)
              if not (a + b).isascii() and not CYRILLIC_OR_GREEK.search(a + b))
    return frozenset(keys) | frozenset(joined)


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
        words=_words(text) | _name_words(raw, text), text=text,
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


def _form_error(text: str, min_chars: int, max_chars: int) -> str | None:
    """Drop code of the checks that need no evidence: length, markup, English only, never-list."""
    if not min_chars <= len(text.strip()) <= max_chars:
        return "length"
    if MARKUP.search(text):
        return "markup"
    if NON_ENGLISH.search(text):
        return "non_english"
    if never_word(text) or THE_ADMINISTRATION.search(text):
        return "never_list"
    return None


def _camel_error(text: str, words: frozenset[str]) -> str | None:
    """`unsupported_name` for a lower-case-first name ("xAI") that the evidence words lack;
    `grounding_error` skips such words."""
    for word in WORD.findall(text):
        if CAMEL_NAME.match(word) and re.sub(r"'s$", "", word).casefold() not in words:
            return "unsupported_name"
    return None


def _evidence_error(text: str, evidence: str, copy: bool) -> str | None:
    """Drop code of the checks against the evidence: quotes, copying (`copy`), numbers, names."""
    proof = _evidence(evidence)
    folded = fold(text)
    code = _quote_error(folded, proof)
    if code is None and copy and _copies(folded, proof):
        code = "too_close"
    words = proof.words | SUBJECT_WORDS
    return (code or grounding_error(
        folded, set(proof.numbers), "",
        NameRules(WRITER_STARTERS | HEADLINE_OPENERS, canon_number, words))
        or _camel_error(folded, words))


def sentence_error(text: str, evidence: str, *, copy: bool = False,
                   min_chars: int = SENTENCE_MIN_CHARS,
                   max_chars: int = SENTENCE_MAX_CHARS) -> str | None:
    """Drop code of the first failing check of a model text against the `evidence` it was given,
    or None. Checks, in order: length, markup, English only, never-list, quotes, copying (when
    `copy`), numbers, names."""
    return _form_error(text, min_chars, max_chars) or _evidence_error(text, evidence, copy)
