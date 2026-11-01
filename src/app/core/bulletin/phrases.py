"""Phrase library of the bulletin: loader and checks (spec 018, item 2).

Behavior and tests: src/app/core/bulletin/builder.md. The data is `phrases.json`.
"""
import json
import re
from functools import lru_cache
from pathlib import Path
from string import Formatter
from typing import Any, cast

from app.core.bulletin.world_change import AREA_CRITERIA

PHRASES_PATH = Path(__file__).with_name("phrases.json")
DAY_TYPES = ("ordinary", "busy", "quiet")
LABELS = ("masthead", "byline", "key_results", "cooperation", "incidents", "among", "full_report")
REACTION_KINDS = ("limit", "ai_issue", "ai_issue_with_fix")
UNITS = ("model", "product")
SLOTS = {"openings": {"weekday"}, "launches": {"models", "products"}, "items": {"items"}}

# ER-4 and voice.md "Never"; matched as whole words, any case.
NEVER_RE = re.compile(
    r"\b(government|citizens?|comrades?|glory|party|regime|leaders?|decrees?|flags?|emblems?"
    r"|anthems?)\b|\bAdministration\s+(released|launched)\b", re.IGNORECASE)


class PhraseError(ValueError):
    """The phrase library is malformed or has a forbidden word."""


def never_word(text: str) -> str | None:
    found = NEVER_RE.search(text)
    return found.group(0) if found else None


def _texts(value: Any, where: str, slots: set[str]) -> list[str]:
    if not isinstance(value, list) or not value:
        raise PhraseError(f"{where}: a non-empty list of phrases is required")
    for phrase in value:
        if not isinstance(phrase, str) or not phrase.strip():
            raise PhraseError(f"{where}: phrases must be non-empty strings")
        used = {name for _, name, _, _ in Formatter().parse(phrase) if name}
        if not used <= slots:
            raise PhraseError(f"{where}: unknown slot in {phrase!r}")
    return cast(list[str], value)


def _walk(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        return [text for item in node for text in _walk(item)]
    if isinstance(node, dict):
        return [text for item in node.values() for text in _walk(item)]
    return []


def _validate_numbers(numbers: dict[str, Any]) -> None:
    _texts(numbers.get("launches"), "numbers.launches", SLOTS["launches"])
    _texts(numbers.get("items"), "numbers.items", SLOTS["items"])
    units = numbers.get("units", {})
    if set(units) != set(UNITS) or not all(
            isinstance(v, list) and len(v) == 2 and all(isinstance(x, str) and x for x in v)
            for v in units.values()):
        raise PhraseError("numbers.units needs [singular, plural] for model and product")


def validate_phrases(data: dict[str, Any]) -> None:
    """Raise PhraseError unless the library has every slot filled with clean phrases."""
    for key in ("openings", "numbers", "rubrics", "reactions", "closings", "cut", "labels"):
        if key not in data:
            raise PhraseError(f"missing key: {key}")
    if not isinstance(data.get("version"), str):
        raise PhraseError("version must be a string")
    if set(data["labels"]) != set(LABELS) or not all(
            isinstance(v, str) and v for v in data["labels"].values()):
        raise PhraseError("labels must be exactly " + ", ".join(LABELS))
    if set(data["openings"]) != set(DAY_TYPES):
        raise PhraseError("openings must cover " + ", ".join(DAY_TYPES))
    for name, phrases in data["openings"].items():
        _texts(phrases, f"openings.{name}", SLOTS["openings"])
    _validate_numbers(data["numbers"])
    _texts(data["rubrics"], "rubrics", set())
    _texts(data["closings"], "closings", set())
    reactions = data["reactions"]
    for kind in REACTION_KINDS:
        _texts(reactions.get(kind), f"reactions.{kind}", set())
    for area, phrases in reactions.get("by_area", {}).items():
        if area not in AREA_CRITERIA:
            raise PhraseError(f"reactions.by_area: unknown area {area}")
        _texts(phrases, f"reactions.by_area.{area}", set())
    cut = data["cut"]
    if not (isinstance(cut.get("marker"), str) and cut["marker"]
            and isinstance(cut.get("footnote"), str) and cut["footnote"]):
        raise PhraseError("cut needs a marker and a footnote")
    for phrase in _walk(data):
        word = never_word(phrase)
        if word:
            raise PhraseError(f"forbidden word {word!r} in {phrase!r}")


@lru_cache(maxsize=1)
def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_phrases(data)
    return cast(dict[str, Any], data)


def load_phrases(path: Path = PHRASES_PATH) -> dict[str, Any]:
    """The validated library; the file is read once per path."""
    return _load(path)
