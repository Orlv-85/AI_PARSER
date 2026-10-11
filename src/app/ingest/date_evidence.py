"""Literal publication/modification evidence without discovery-time substitution."""
import json
import re
from datetime import UTC, date, datetime
from typing import Any

from lxml import html as lxml_html

from app.core.canonicalize import canonicalize_url

DATE_EVIDENCE_VERSION = "page-dates-1"
_ARTICLE_TYPES = {"Article", "NewsArticle", "BlogPosting", "TechArticle", "ScholarlyArticle"}
_FIELDS = {"datePublished": "published", "dateModified": "modified"}
_META = {"article:published_time": "published", "datepublished": "published",
         "article:modified_time": "modified", "datemodified": "modified"}


def date_candidate(literal: str, *, kind: str, source: str, locator: str) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "literal": literal, "kind": kind, "source": source, "locator": locator,
        "value": None, "utc": None, "precision": None, "timezone": None,
        "valid": False,
    }
    value = literal.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            candidate.update(value=date.fromisoformat(value).isoformat(), precision="day")
        elif re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", value):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            precision = "second" if re.search(r":\d{2}:\d{2}", value) else "minute"
            candidate.update(value=parsed.isoformat(), precision=precision)
            if parsed.utcoffset() is not None:
                candidate.update(timezone=str(parsed.utcoffset()),
                                 utc=parsed.astimezone(UTC).isoformat())
        else:
            return candidate
    except ValueError:
        return candidate
    candidate["valid"] = True
    return candidate


def _objects(value: Any):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _objects(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _objects(nested)


def _is_article(node: dict[str, Any]) -> bool:
    kinds = node.get("@type", [])
    kinds = [kinds] if isinstance(kinds, str) else kinds
    return isinstance(kinds, list) and any(
        isinstance(kind, str) and kind.rsplit("/", 1)[-1] in _ARTICLE_TYPES for kind in kinds)


def _page_matches(node: dict[str, Any], url: str) -> bool:
    page = node.get("mainEntityOfPage", node.get("url"))
    if isinstance(page, dict):
        page = page.get("@id", page.get("url"))
    if not isinstance(page, str) or not page.startswith(("http://", "https://")):
        return True
    return bool(canonicalize_url(page) == canonicalize_url(url))


def resolve_dates(candidates: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    valid = [c for c in candidates if c["kind"] == kind and c["valid"]]
    if not valid:
        return {"status": "unknown", "selected": None}
    for left in valid:
        for right in valid:
            if left["precision"] == "day" or right["precision"] == "day":
                equal = left["value"][:10] == right["value"][:10]
            elif left["utc"] and right["utc"]:
                precision = 16 if "minute" in (left["precision"], right["precision"]) else 19
                equal = left["utc"][:precision] == right["utc"][:precision]
            elif bool(left["utc"]) != bool(right["utc"]):
                equal = left["value"][:16] == right["value"][:16]
            else:
                equal = left["value"] == right["value"]
            if not equal:
                return {"status": "conflict", "selected": None}
    selected = max(valid, key=lambda c: (bool(c["utc"]), c["precision"] != "day"))
    return {"status": "confirmed", "selected": selected}


def extract_date_evidence(  # pylint: disable=too-many-branches
    page_html: str, url: str,
) -> dict[str, Any]:
    """Read metadata before scripts are stripped; keep unknowns and conflicts explicit."""
    result: dict[str, Any] = {"version": DATE_EVIDENCE_VERSION, "candidates": [],
                              "literal_labels": [], "invalid_jsonld": 0}
    if not page_html.strip():
        return {**result, "published": resolve_dates([], "published"),
                "modified": resolve_dates([], "modified")}
    tree = lxml_html.fromstring(page_html)
    candidates = result["candidates"]
    for index, script in enumerate(tree.xpath('//script[@type="application/ld+json"]')):
        try:
            data = json.loads(script.text or "")
        except (ValueError, TypeError):
            result["invalid_jsonld"] += 1
            continue
        for item in _objects(data):
            if not _is_article(item) or not _page_matches(item, url):
                continue
            for field, kind in _FIELDS.items():
                if isinstance(item.get(field), str):
                    candidates.append(date_candidate(
                        item[field], kind=kind, source="jsonld",
                        locator=f"script[{index}].{field}"))
    for index, node in enumerate(tree.xpath('//meta[@property or @name]')):
        name = (node.get("property") or node.get("name") or "").lower()
        if name in _META and node.get("content"):
            candidates.append(date_candidate(node.get("content"), kind=_META[name],
                                             source="meta", locator=f"meta[{index}].{name}"))
    for index, node in enumerate(tree.xpath('//*[@itemprop]')):
        if any(parent.tag in {"nav", "footer"} for parent in node.iterancestors()):
            continue
        for field in (node.get("itemprop") or "").split():
            if field in _FIELDS:
                literal = node.get("content") or node.get("datetime") or node.text_content().strip()
                candidates.append(date_candidate(literal, kind=_FIELDS[field], source="microdata",
                                                 locator=f"itemprop[{index}].{field}"))
    # Visible labels are evidence for later literal parsing, never a guessed publication.
    for node in tree.xpath('//article//time | //main//time | //header//time'):
        if any(parent.tag in {"nav", "footer"} for parent in node.iterancestors()):
            continue
        parent = node.getparent()
        label = " ".join(parent.text_content().split())[:500] if parent is not None else ""
        result["literal_labels"].append({"datetime": node.get("datetime"),
                                         "text": node.text_content().strip(), "context": label})
    result["published"] = resolve_dates(candidates, "published")
    result["modified"] = resolve_dates(candidates, "modified")
    return result
