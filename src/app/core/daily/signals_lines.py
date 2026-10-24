"""Daily AI Signals: one-liner of a New item (see signals.md)."""
import re
from collections.abc import Iterable

from app.core.daily.signals_brief import cut, norm

# One-liners (007 plan "One-liners"): sentence split, abbreviations, launch / "is a" verbs.
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")


ABBREVIATION = re.compile(r"(?:\b[A-Z]\.|\b(?:Inc|Corp|Ltd|Co|Mr|Ms|Dr|vs|St|No|U\.S|e\.g|i\.e|"
                          r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.)$")


WHAT_VERB = re.compile(r"\b(launch\w*|releas\w*|introduc\w*|announc\w*|unveil\w*|debut\w*|"
                       r"open-sourc\w*|formed|founded|(?<!-)built|"
                       r"(?:is|are) (?:an?|the|its|their) )",
                       re.IGNORECASE)


SHORT_QUOTE_WORDS = 8


ONE_LINER_MIN_WORDS = 3  # words besides the item name; fewer says nothing ("llm-echo 0.5")


def sentences(text: str) -> list[str]:
    parts: list[str] = []
    buffer = ""
    for piece in SENTENCE_END.split(norm(text)):
        buffer = f"{buffer} {piece}".strip()
        if not ABBREVIATION.search(buffer):
            parts.append(buffer)
            buffer = ""
    if buffer:
        parts.append(buffer)
    return parts


def name_key(text: str) -> str:
    return re.sub(r"[\s.\-_]+", " ", norm(text).casefold()).strip()


def one_liner(name: str, quote: str | None, summaries: Iterable[str],
              limit: int = 140) -> tuple[str | None, str | None]:
    """(line, source) for a New item: a digest-summary sentence that names the item and says what
    it is or that it launched; a naming sentence when the novelty quote is a short fragment; else
    the novelty quote (`quote`, rendered in quotation marks). Never generated; (None, None) when
    the line would only repeat the name."""
    line, source = _one_liner(name, quote, summaries, limit)
    if len(name_key(line).replace(name_key(name), " ").split()) < ONE_LINER_MIN_WORDS:
        return None, None
    return line, source


def _one_liner(name: str, quote: str | None, summaries: Iterable[str],
               limit: int) -> tuple[str, str]:
    key = name_key(name)
    named = [s for text in summaries for s in sentences(text) if key in name_key(s)]
    for sentence in named:
        if WHAT_VERB.search(sentence):
            return cut(sentence, limit), "summary"
    text = norm(quote)
    if named and len(text.split()) < SHORT_QUOTE_WORDS:
        return cut(named[0], limit), "summary"
    return cut(text, limit), "quote"
