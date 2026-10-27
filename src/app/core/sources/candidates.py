# pylint: disable=too-many-lines
"""Source candidate parsing and overlap grouping."""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.canonicalize import canonicalize_url

_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\((https?://[^\s)]+)\)", re.IGNORECASE)

_PLAIN_URL_RE = re.compile(r"https?://[^\s<>\])]+", re.IGNORECASE)

_TRACKING_PARAM_PREFIXES = ("utm_",)

_TRACKING_PARAM_NAMES = {"gclid", "fbclid", "mc_cid", "mc_eid", "ref", "ref_src"}

_TOPIC_SEGMENTS = {"tag", "tags", "topic", "topics", "category", "categories", "section"}

_ROOT_SEGMENTS = {"", "blog", "news", "articles", "feed"}

_REVIEW_REASON_SAME_HOST_PATH_PREFIX = "same_host_path_prefix"

_REVIEW_REASON_SAME_HOST_TOPIC_VARIANT = "same_host_topic_variant"

_REVIEW_REASON_SAME_HOST_FAMILY = "same_host_family"

_REVIEW_REASON_PRIORITIES = {
    _REVIEW_REASON_SAME_HOST_PATH_PREFIX: 3,
    _REVIEW_REASON_SAME_HOST_TOPIC_VARIANT: 2,
    _REVIEW_REASON_SAME_HOST_FAMILY: 1,
}

@dataclass(frozen=True, slots=True)
class NormalizedSourceCandidate:
    raw_input: str
    normalized_url: str
    candidate_type: str

@dataclass(frozen=True, slots=True)
class CandidateOverlapGroup:
    candidate_ids: list[int]
    reason: str
    preferred_candidate_id: int
    candidate_urls: list[str] | None = None
    preferred_url: str | None = None

def extract_candidate_urls(raw_text: str) -> list[str]:
    records = _json_source_records(raw_text)
    if records is not None:
        return [str(record["url"]) for record in records]
    matches: list[tuple[int, str]] = []
    consumed_ranges: list[tuple[int, int]] = []

    for match in _MARKDOWN_LINK_RE.finditer(raw_text):
        matches.append((match.start(1), match.group(1)))
        consumed_ranges.append((match.start(), match.end()))

    cursor = 0
    for start, end in consumed_ranges:
        matches.extend(_extract_plain_urls(raw_text[cursor:start], offset=cursor))
        cursor = end
    matches.extend(_extract_plain_urls(raw_text[cursor:], offset=cursor))

    matches.sort(key=lambda item: item[0])
    return [url for _, url in matches]

def _json_source_records(raw_text: str) -> list[dict[str, str]] | None:
    text = raw_text.strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    if not text.startswith(("{", "[")):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        if text.startswith("[") and not re.match(r'\[\s*[\{"\]]', text):
            return None
        raise ValueError("Invalid JSON: upload an array or an object with a sources array") from exc
    records = payload.get("sources") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("JSON must contain a sources array")
    if len(records) > 200 or len(text.encode("utf-8")) > 1_000_000:
        raise ValueError("Source JSON is limited to 200 records and 1 MB")
    result: list[dict[str, str]] = []
    for record in records:
        if isinstance(record, str):
            record = {"url": record}
        if not isinstance(record, dict) or not isinstance(record.get("url"), str):
            raise ValueError("Each source record needs a string url")
        if len(record["url"]) > 2048:
            raise ValueError("Source URLs must be at most 2048 characters")
        result.append({
            key: str(record[key])[:limit]
            for key, limit in (("url", 2048), ("name", 128), ("description", 500), ("type", 16))
            if key in record and isinstance(record[key], str)
        })
    return result

def normalize_candidate_url(raw_url: str) -> str:
    candidate = raw_url.strip()
    parts = urlsplit(candidate)
    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()

    if scheme not in {"http", "https"} or not hostname:
        raise ValueError("invalid source candidate URL")
    if _is_search_wrapper(hostname=hostname, path=parts.path, query=parts.query):
        raise ValueError("search wrapper URLs are not valid source candidates")

    netloc = hostname
    if parts.port is not None and parts.port != _default_port(scheme):
        netloc = f"{netloc}:{parts.port}"

    path = re.sub(r"/{2,}", "/", parts.path or "")
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    if path == "/":
        path = ""

    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith(_TRACKING_PARAM_PREFIXES)
        and key.lower() not in _TRACKING_PARAM_NAMES
    ]
    query = urlencode(filtered_query, doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))

def candidate_url_key(raw_url: str) -> str:
    """Key for "is this source already known": the pipeline's canonical URL on top of the
    onboarding cleanup, https, no ``www.``. Not stored; ``normalized_url`` stays unchanged."""
    parts = urlsplit(canonicalize_url(normalize_candidate_url(raw_url)))
    host = (parts.hostname or "").removeprefix("www.")
    netloc = host if parts.port in {None, 80, 443} else f"{host}:{parts.port}"
    return str(urlunsplit(("https", netloc, parts.path, parts.query, "")))

def parse_source_candidates(raw_text: str) -> tuple[list[NormalizedSourceCandidate], int, int]:
    records = _json_source_records(raw_text)
    extracted_urls = extract_candidate_urls(raw_text)
    normalized_candidates: list[NormalizedSourceCandidate] = []
    seen_urls: set[str] = set()
    rejected_count = 0

    for index, raw_url in enumerate(extracted_urls):
        try:
            normalized_url = normalize_candidate_url(raw_url)
        except ValueError:
            rejected_count += 1
            continue

        if normalized_url in seen_urls:
            rejected_count += 1
            continue

        seen_urls.add(normalized_url)
        record = records[index] if records is not None else None
        declared_type = record.get("type", "").lower() if record else ""
        candidate_type = "rss" if declared_type == "atom" else declared_type
        normalized_candidates.append(
            NormalizedSourceCandidate(
                raw_input=json.dumps(record, ensure_ascii=True) if record else raw_url,
                normalized_url=normalized_url,
                candidate_type=(
                    candidate_type if candidate_type in {"rss", "html"}
                    else _infer_candidate_type(normalized_url)
                ),
            )
        )

    return normalized_candidates, len(extracted_urls), rejected_count

def group_candidate_overlaps(  # pylint: disable=too-many-branches
    candidates: Sequence[object],
) -> list[CandidateOverlapGroup]:
    grouped_by_host: dict[str, list[object]] = {}
    for candidate in candidates:
        normalized_url = _candidate_value(candidate, "normalized_url")
        hostname = (urlsplit(normalized_url).hostname or "").lower()
        if not hostname:
            continue
        grouped_by_host.setdefault(hostname, []).append(candidate)

    groups: list[CandidateOverlapGroup] = []
    for host_candidates in grouped_by_host.values():
        if len(host_candidates) < 2:
            continue
        overlaps_by_id: dict[int, set[int]] = {}
        reasons_by_pair: dict[frozenset[int], str] = {}
        for index, left in enumerate(host_candidates):
            left_id = int(_candidate_value(left, "id"))
            for right in host_candidates[index + 1 :]:
                reason = _overlap_reason(left, right)
                if reason is None:
                    continue
                right_id = int(_candidate_value(right, "id"))
                overlaps_by_id.setdefault(left_id, set()).add(right_id)
                overlaps_by_id.setdefault(right_id, set()).add(left_id)
                pair_key = frozenset({left_id, right_id})
                reasons_by_pair[pair_key] = _prefer_reason(reasons_by_pair.get(pair_key), reason)
        if len(overlaps_by_id) < 2:
            continue

        candidate_by_id = {
            int(_candidate_value(candidate, "id")): candidate for candidate in host_candidates
        }
        visited: set[int] = set()
        for candidate_id in sorted(overlaps_by_id):
            if candidate_id in visited:
                continue
            component_ids: set[int] = set()
            pending = [candidate_id]
            strongest_reason: str | None = None
            while pending:
                current_id = pending.pop()
                if current_id in visited:
                    continue
                visited.add(current_id)
                component_ids.add(current_id)
                for neighbor_id in overlaps_by_id.get(current_id, ()):
                    pair_key = frozenset({current_id, neighbor_id})
                    strongest_reason = _prefer_reason(
                        strongest_reason,
                        reasons_by_pair.get(pair_key, "same_host_family"),
                    )
                    if neighbor_id not in visited:
                        pending.append(neighbor_id)
            # Defensive guard: graph construction should make this unreachable.
            if len(component_ids) < 2:  # pragma: no cover
                continue

            members = [candidate_by_id[member_id] for member_id in sorted(component_ids)]
            preferred_candidate_id = int(_candidate_value(_pick_preferred_candidate(members), "id"))
            groups.append(
                CandidateOverlapGroup(
                    candidate_ids=sorted(component_ids),
                    reason=strongest_reason or "same_host_family",
                    preferred_candidate_id=preferred_candidate_id,
                    candidate_urls=[
                        _candidate_value(candidate_by_id[member_id], "normalized_url")
                        for member_id in sorted(component_ids)
                    ],
                    preferred_url=_candidate_value(
                        candidate_by_id[preferred_candidate_id],
                        "normalized_url",
                    ),
                )
            )
    return groups

def _normalize_candidate_type(candidate_type: str) -> str:
    normalized_candidate_type = candidate_type.strip().lower()
    if normalized_candidate_type not in {"rss", "html", "unknown"}:
        raise ValueError("candidate_type must be one of: rss, html, unknown")
    return normalized_candidate_type

def _extract_plain_urls(text: str, *, offset: int) -> list[tuple[int, str]]:
    return [
        (offset + match.start(), _strip_trailing_punctuation(match.group(0)))
        for match in _PLAIN_URL_RE.finditer(text)
    ]

def _strip_trailing_punctuation(raw_url: str) -> str:
    return raw_url.rstrip(".,;]")

def _is_search_wrapper(*, hostname: str, path: str, query: str) -> bool:
    is_google_host = hostname.startswith("google.") or hostname.startswith("www.google.")
    if not is_google_host:
        return False
    if path in {"/url", "/search"}:
        return True
    return any(key == "q" and value.startswith("http") for key, value in parse_qsl(query))

def _default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80

def _infer_candidate_type(normalized_url: str) -> str:
    lower_url = normalized_url.lower()
    if lower_url.endswith((".xml", ".rss", ".atom")) or "/feed" in lower_url:
        return "rss"
    return "html"

def _candidate_value(candidate: object, field_name: str, default: str | None = None) -> str:
    if isinstance(candidate, dict):
        value = candidate.get(field_name, default)
    else:
        value = getattr(candidate, field_name, default)
    if value is None:
        raise ValueError(f"candidate field is required: {field_name}")
    return str(value)

def _normalized_path(url: str) -> str:
    path = urlsplit(url).path or "/"
    path = re.sub(r"/{2,}", "/", path)
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return path or "/"

def _path_segments(url: str) -> list[str]:
    path = _normalized_path(url)
    if path == "/":
        return []
    return [segment for segment in path.strip("/").split("/") if segment]

def _overlap_reason(left: object, right: object) -> str | None:
    left_url = _candidate_value(left, "normalized_url")
    right_url = _candidate_value(right, "normalized_url")
    left_path = _normalized_path(left_url)
    right_path = _normalized_path(right_url)

    if _is_strict_path_prefix(left_path, right_path):
        return _REVIEW_REASON_SAME_HOST_PATH_PREFIX
    if _is_topic_path(left_path) or _is_topic_path(right_path):
        return _REVIEW_REASON_SAME_HOST_TOPIC_VARIANT
    if _is_root_family_path(left_path) or _is_root_family_path(right_path):
        return _REVIEW_REASON_SAME_HOST_FAMILY
    return None

def _is_strict_path_prefix(left_path: str, right_path: str) -> bool:
    if left_path == right_path:
        return False
    left_segments = _path_segments(left_path)
    right_segments = _path_segments(right_path)
    if not left_segments or not right_segments:
        return False
    shorter, longer = (
        (left_segments, right_segments)
        if len(left_segments) < len(right_segments)
        else (right_segments, left_segments)
    )
    return len(shorter) < len(longer) and longer[: len(shorter)] == shorter

def _is_topic_path(path: str) -> bool:
    segments = _path_segments(path)
    return any(segment.lower() in _TOPIC_SEGMENTS for segment in segments)

def _is_root_family_path(path: str) -> bool:
    segments = _path_segments(path)
    if not segments:
        return True
    return len(segments) == 1 and segments[0].lower() in _ROOT_SEGMENTS

def _prefer_reason(current_reason: str | None, new_reason: str) -> str:
    normalized_new_reason = new_reason.strip().lower()
    if current_reason is None:
        return normalized_new_reason
    normalized_current_reason = current_reason.strip().lower()
    if _REVIEW_REASON_PRIORITIES.get(normalized_new_reason, 0) > _REVIEW_REASON_PRIORITIES.get(
        normalized_current_reason,
        0,
    ):
        return normalized_new_reason
    return normalized_current_reason

def _pick_preferred_candidate(candidates: list[object]) -> object:
    return min(
        candidates,
        key=lambda candidate: (
            _is_topic_path(_normalized_path(_candidate_value(candidate, "normalized_url"))),
            len(_path_segments(_candidate_value(candidate, "normalized_url"))),
            len(_normalized_path(_candidate_value(candidate, "normalized_url"))),
            _candidate_value(candidate, "candidate_type", default="unknown") != "rss",
            int(_candidate_value(candidate, "id")),
        ),
    )
