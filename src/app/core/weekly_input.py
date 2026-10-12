"""Current article evidence, independent of historical ingestion observations."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from types import SimpleNamespace

from app.core.admission import bounded_evidence, evidence_hash
from app.ingest.date_evidence import date_candidate, resolve_dates


def source_fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def parsed(value) -> dict:
    try:
        result = json.loads(value) if isinstance(value, str) else value
    except ValueError:
        return {}
    return result if isinstance(result, dict) else {}


def instant(value) -> datetime | None:
    if not value:
        return None
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    return result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)


def publication(article: dict, periods: list) -> dict:
    provenance = parsed(article.get("date_provenance"))
    status = article.get("publication_status", "legacy_unverified")
    selected = (provenance.get("published") or {}).get("selected") or {}
    precision = article.get("publication_precision") or ""
    if status != "confirmed":
        return {"date_reason": status, "window_index": None}
    if "normalized" in precision:
        raw = resolve_dates([c for c in provenance.get("candidates", [])
                             if not c.get("precision_origin")], "published")
        literal = provenance.get("published_literal")
        if raw["status"] == "unknown" and literal:
            try:
                feed_stamp = parsedate_to_datetime(literal)
                if feed_stamp.tzinfo:
                    raw = resolve_dates([date_candidate(feed_stamp.isoformat(), kind="published",
                        source="feed_literal", locator="published_literal")], "published")
            except (ValueError, TypeError):
                pass
        if raw["status"] != "confirmed":
            return {"date_reason": "normalized_precision_unverified", "window_index": None}
        selected = raw["selected"]
    stamp = instant(selected.get("utc"))
    stored = instant(article.get("published_at"))
    if stamp and stored and "normalized" not in precision and stamp != stored:
        return {"date_reason": "evidence_mismatch", "window_index": None}
    if stamp is None and not selected and precision in {"second", "minute", "timestamp"}:
        stamp = stored
    if stamp:
        index = next((i for i, (a, b) in enumerate(periods) if a <= stamp < b), None)
        return {"published_at": stamp.isoformat(), "publication_precision":
                selected.get("precision") or precision, "window_index": index,
                "date_reason": "confirmed" if index is not None else "outside_scope"}
    literal = selected.get("value") or article.get("publication_day")
    if not literal:
        return {"date_reason": "unknown", "window_index": None}
    value = datetime.fromisoformat(str(literal)).replace(tzinfo=UTC)
    low = value - timedelta(hours=14)
    high = value + timedelta(hours=12)
    if selected.get("precision", "day") == "day":
        high += timedelta(days=1)
    index = next((i for i, (a, b) in enumerate(periods) if a <= low and high <= b), None)
    possible = [i for i, (a, b) in enumerate(periods) if low < b and high > a]
    return {"published_at": None, "calendar_date": str(literal)[:10],
            "publication_precision": selected.get("precision", "day"),
            "publication_interval": {"start": low.isoformat(), "end": high.isoformat()},
            "window_index": index, "possible_windows": possible,
            "date_reason": "week_safe_calendar" if index is not None else (
                "ambiguous_week_boundary" if possible else "outside_scope")}


def compatible_admission(article: dict, decisions: list[dict]) -> list[dict]:
    """Require exact admitted evidence; an old acceptance on changed text is insufficient."""
    refs = []
    for row in decisions:
        candidate = parsed(row.get("payload")).get("candidate")
        if (row.get("decision") != "accept" or row.get("provider_status") != "ok"
                or not isinstance(candidate, dict) or row.get("source_id") != article["source_id"]
                or row.get("url_canonical_hash") != article["url_canonical_hash"]):
            continue
        if (evidence_hash(bounded_evidence(SimpleNamespace(**candidate))) == row["evidence_hash"]
                and all((candidate.get(k) or "") == (article.get(k) or "")
                        for k in ("title", "summary", "content"))):
            refs.append({"kind": "admission_ledger", "key": row["key"]})
    proof = parsed(article.get("enrichment_provenance"))
    state = f"Title: {article['title'][:1024]}\nContent: {(article.get('content') or '')[:16000]}"
    if (proof.get("admission_source_hash") == source_fingerprint(state)
            and (proof.get("admission_assessment") or {}).get("admission_choice")
            == "accepted_ai_editorial"):
        refs.append({"kind": "article_admission_proof", "source_hash": source_fingerprint(state)})
    return refs
