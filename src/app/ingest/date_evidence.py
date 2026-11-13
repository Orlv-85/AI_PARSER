"""Literal publication/modification evidence without discovery-time substitution."""
import json
import re
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Literal, TypedDict

from lxml import html as lxml_html
from lxml.html import HtmlElement

from app.core.canonicalize import canonicalize_url

DATE_EVIDENCE_VERSION = "page-dates-1"
_ARTICLE_TYPES = {"Article", "NewsArticle", "BlogPosting", "TechArticle", "ScholarlyArticle"}
_FIELDS = {"datePublished": "published", "dateModified": "modified"}
_META = {"article:published_time": "published", "datepublished": "published",
         "article:modified_time": "modified", "datemodified": "modified"}


class DateCandidate(TypedDict):
    literal: str
    kind: str
    source: str
    locator: str
    value: str | None
    utc: str | None
    precision: str | None
    timezone: str | None
    valid: bool


class DateResolution(TypedDict):
    status: Literal["unknown", "conflict", "confirmed"]
    selected: DateCandidate | None


class TimeLabel(TypedDict):
    datetime: str | None
    text: str
    context: str


class DateEvidence(TypedDict):
    version: str
    candidates: list[DateCandidate]
    literal_labels: list[TimeLabel]
    invalid_jsonld: int
    published: DateResolution
    modified: DateResolution


def date_candidate(literal: str, *, kind: str, source: str, locator: str) -> DateCandidate:
    candidate: DateCandidate = {
        "literal": literal, "kind": kind, "source": source, "locator": locator,
        "value": None, "utc": None, "precision": None, "timezone": None,
        "valid": False,
    }
    value = literal.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            candidate.update({"value": date.fromisoformat(value).isoformat(), "precision": "day"})
        elif re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", value):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            precision = "second" if re.search(r":\d{2}:\d{2}", value) else "minute"
            candidate.update({"value": parsed.isoformat(), "precision": precision})
            if parsed.utcoffset() is not None:
                candidate.update({"timezone": str(parsed.utcoffset()),
                                  "utc": parsed.astimezone(UTC).isoformat()})
        else:
            return candidate
    except ValueError:
        return candidate
    candidate["valid"] = True
    return candidate


def _objects(value: object) -> Iterator[dict[str, object]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _objects(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _objects(nested)


def _is_article(node: dict[str, object]) -> bool:
    kinds = node.get("@type", [])
    kinds = [kinds] if isinstance(kinds, str) else kinds
    return isinstance(kinds, list) and any(
        isinstance(kind, str) and kind.rsplit("/", 1)[-1] in _ARTICLE_TYPES for kind in kinds)


def _page_matches(node: dict[str, object], url: str) -> bool:
    page = node.get("mainEntityOfPage", node.get("url"))
    if isinstance(page, dict):
        page = page.get("@id", page.get("url"))
    if not isinstance(page, str) or not page.startswith(("http://", "https://")):
        return True
    return bool(canonicalize_url(page) == canonicalize_url(url))


def _same_date(left: DateCandidate, right: DateCandidate) -> bool:
    # A valid candidate always has a value; utc is set only when the literal has an offset.
    left_value, right_value = left["value"] or "", right["value"] or ""
    left_utc, right_utc = left["utc"] or "", right["utc"] or ""
    if left["precision"] == "day" or right["precision"] == "day":
        return left_value[:10] == right_value[:10]
    if left_utc and right_utc:
        precision = 16 if "minute" in (left["precision"], right["precision"]) else 19
        return left_utc[:precision] == right_utc[:precision]
    if bool(left_utc) != bool(right_utc):
        return left_value[:16] == right_value[:16]
    return left_value == right_value


def resolve_dates(candidates: list[DateCandidate], kind: str) -> DateResolution:
    valid = [c for c in candidates if c["kind"] == kind and c["valid"]]
    if not valid:
        return {"status": "unknown", "selected": None}
    if not all(_same_date(left, right) for left in valid for right in valid):
        return {"status": "conflict", "selected": None}
    selected = max(valid, key=lambda c: (bool(c["utc"]), c["precision"] != "day"))
    return {"status": "confirmed", "selected": selected}


def _in_chrome(node: HtmlElement) -> bool:
    return any(parent.tag in {"nav", "footer"} for parent in node.iterancestors())


def _jsonld_candidates(tree: HtmlElement, url: str) -> tuple[list[DateCandidate], int]:
    """(article date candidates, count of unparsable JSON-LD scripts)."""
    candidates: list[DateCandidate] = []
    invalid = 0
    for index, script in enumerate(tree.xpath('//script[@type="application/ld+json"]')):
        try:
            data = json.loads(script.text or "")
        except (ValueError, TypeError):
            invalid += 1
            continue
        for item in _objects(data):
            if not (_is_article(item) and _page_matches(item, url)):
                continue
            for field, kind in _FIELDS.items():
                if isinstance(literal := item.get(field), str):
                    candidates.append(date_candidate(literal, kind=kind, source="jsonld",
                                                     locator=f"script[{index}].{field}"))
    return candidates, invalid


def _meta_candidates(tree: HtmlElement) -> list[DateCandidate]:
    candidates = []
    for index, node in enumerate(tree.xpath('//meta[@property or @name]')):
        name = (node.get("property") or node.get("name") or "").lower()
        if name in _META and node.get("content"):
            candidates.append(date_candidate(node.get("content"), kind=_META[name],
                                             source="meta", locator=f"meta[{index}].{name}"))
    return candidates


def _microdata_candidates(tree: HtmlElement) -> list[DateCandidate]:
    candidates = []
    for index, node in enumerate(tree.xpath('//*[@itemprop]')):
        if _in_chrome(node):
            continue
        for field in (node.get("itemprop") or "").split():
            if field in _FIELDS:
                literal = node.get("content") or node.get("datetime") or node.text_content().strip()
                candidates.append(date_candidate(literal, kind=_FIELDS[field], source="microdata",
                                                 locator=f"itemprop[{index}].{field}"))
    return candidates


def _time_labels(tree: HtmlElement) -> list[TimeLabel]:
    """Visible labels are evidence for later literal parsing, never a guessed publication."""
    labels: list[TimeLabel] = []
    for node in tree.xpath('//article//time | //main//time | //header//time'):
        if _in_chrome(node):
            continue
        parent = node.getparent()
        label = " ".join(parent.text_content().split())[:500] if parent is not None else ""
        labels.append({"datetime": node.get("datetime"),
                       "text": node.text_content().strip(), "context": label})
    return labels


def extract_date_evidence(page_html: str, url: str) -> DateEvidence:
    """Read metadata before scripts are stripped; keep unknowns and conflicts explicit."""
    candidates: list[DateCandidate] = []
    labels: list[TimeLabel] = []
    invalid = 0
    if page_html.strip():
        tree = lxml_html.fromstring(page_html)
        candidates, invalid = _jsonld_candidates(tree, url)
        candidates += _meta_candidates(tree) + _microdata_candidates(tree)
        labels = _time_labels(tree)
    return {"version": DATE_EVIDENCE_VERSION, "candidates": candidates,
            "literal_labels": labels, "invalid_jsonld": invalid,
            "published": resolve_dates(candidates, "published"),
            "modified": resolve_dates(candidates, "modified")}
