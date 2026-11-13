"""Phrase library of the bulletin: loader and checks (spec 018, item 2).

Behavior and tests: src/app/core/bulletin/builder.md. The data is `phrases.json`.
"""
import json
import re
from functools import lru_cache
from pathlib import Path
from string import Formatter
from typing import NotRequired, TypedDict, cast

from app.core.bulletin.world_change import AREA_CRITERIA

PHRASES_PATH = Path(__file__).with_name("phrases.json")
DAY_TYPES = ("ordinary", "busy", "quiet")
LABELS = ("masthead", "byline", "key_results", "cooperation", "incidents", "among", "full_report")
REACTION_KINDS = ("limit", "ai_issue", "ai_issue_with_fix")
UNITS = ("model", "product")
REQUIRED_KEYS = ("openings", "numbers", "rubrics", "reactions", "closings", "cut", "labels")
SLOTS = {"openings": {"weekday"}, "launches": {"models", "products"}, "items": {"items"}}

# ER-4 and voice.md "Never"; matched as whole words, any case.
NEVER_RE = re.compile(
    r"\b(government|citizens?|comrades?|glory|party|regime|leaders?|decrees?|flags?|emblems?"
    r"|anthems?)\b|\bAdministration\s+(released|launched)\b", re.IGNORECASE)


class PhraseError(ValueError):
    """The phrase library is malformed or has a forbidden word."""


class Numbers(TypedDict):
    launches: list[str]
    items: list[str]
    units: dict[str, list[str]]  # unit -> [singular, plural]


class Reactions(TypedDict):
    limit: list[str]
    ai_issue: list[str]
    ai_issue_with_fix: list[str]
    by_area: NotRequired[dict[str, list[str]]]


class Cut(TypedDict):
    marker: str
    footnote: str


class PhraseLibrary(TypedDict):
    """The library after `validate_phrases`; extra keys may be present and are not read."""

    version: str
    labels: dict[str, str]
    openings: dict[str, list[str]]
    numbers: Numbers
    rubrics: list[str]
    reactions: Reactions
    closings: list[str]
    cut: Cut


def never_word(text: str) -> str | None:
    found = NEVER_RE.search(text)
    return found.group(0) if found else None


def _texts(value: object, where: str, slots: set[str]) -> list[str]:
    if not isinstance(value, list) or not value:
        raise PhraseError(f"{where}: a non-empty list of phrases is required")
    for phrase in value:
        if not isinstance(phrase, str) or not phrase.strip():
            raise PhraseError(f"{where}: phrases must be non-empty strings")
        used = {name for _, name, _, _ in Formatter().parse(phrase) if name}
        if not used <= slots:
            raise PhraseError(f"{where}: unknown slot in {phrase!r}")
    return cast(list[str], value)


def _walk(node: object) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        return [text for item in node for text in _walk(item)]
    if isinstance(node, dict):
        return [text for item in node.values() for text in _walk(item)]
    return []


def _section(data: dict[str, object], key: str) -> dict[str, object]:
    value = data[key]
    if not isinstance(value, dict):
        raise PhraseError(f"{key} must be an object")
    return value


def _validate_numbers(numbers: dict[str, object]) -> None:
    _texts(numbers.get("launches"), "numbers.launches", SLOTS["launches"])
    _texts(numbers.get("items"), "numbers.items", SLOTS["items"])
    units = numbers.get("units", {})
    if not isinstance(units, dict) or set(units) != set(UNITS) or not all(
            isinstance(v, list) and len(v) == 2 and all(isinstance(x, str) and x for x in v)
            for v in units.values()):
        raise PhraseError("numbers.units needs [singular, plural] for model and product")


def _filled(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _validate_top(data: dict[str, object]) -> None:
    for key in REQUIRED_KEYS:
        if key not in data:
            raise PhraseError(f"missing key: {key}")
    if not isinstance(data.get("version"), str):
        raise PhraseError("version must be a string")


def _validate_labels(labels: dict[str, object]) -> None:
    if set(labels) != set(LABELS) or not all(_filled(v) for v in labels.values()):
        raise PhraseError("labels must be exactly " + ", ".join(LABELS))


def _validate_openings(openings: dict[str, object]) -> None:
    if set(openings) != set(DAY_TYPES):
        raise PhraseError("openings must cover " + ", ".join(DAY_TYPES))
    for name, phrases in openings.items():
        _texts(phrases, f"openings.{name}", SLOTS["openings"])


def _validate_reactions(reactions: dict[str, object]) -> None:
    for kind in REACTION_KINDS:
        _texts(reactions.get(kind), f"reactions.{kind}", set())
    by_area = reactions.get("by_area", {})
    if not isinstance(by_area, dict):
        raise PhraseError("reactions.by_area must be an object")
    for area, phrases in by_area.items():
        if area not in AREA_CRITERIA:
            raise PhraseError(f"reactions.by_area: unknown area {area}")
        _texts(phrases, f"reactions.by_area.{area}", set())


def _validate_cut(cut: dict[str, object]) -> None:
    if not (_filled(cut.get("marker")) and _filled(cut.get("footnote"))):
        raise PhraseError("cut needs a marker and a footnote")


def _validate_never_list(data: dict[str, object]) -> None:
    for phrase in _walk(data):
        word = never_word(phrase)
        if word:
            raise PhraseError(f"forbidden word {word!r} in {phrase!r}")


def validate_phrases(data: dict[str, object]) -> None:
    """Raise PhraseError unless the library has every slot filled with clean phrases.

    Checks run in this order; the first failing one names the error."""
    _validate_top(data)
    _validate_labels(_section(data, "labels"))
    _validate_openings(_section(data, "openings"))
    _validate_numbers(_section(data, "numbers"))
    _texts(data["rubrics"], "rubrics", set())
    _texts(data["closings"], "closings", set())
    _validate_reactions(_section(data, "reactions"))
    _validate_cut(_section(data, "cut"))
    _validate_never_list(data)


@lru_cache(maxsize=1)
def _load(path: Path) -> PhraseLibrary:
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_phrases(data)
    return cast(PhraseLibrary, data)


def load_phrases(path: Path = PHRASES_PATH) -> PhraseLibrary:
    """The validated library; the file is read once per path."""
    return _load(path)
