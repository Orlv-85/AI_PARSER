"""Read-only export for historical replay and manual semantic review."""

import json
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select

from app.core.weekly_analytics import METHODOLOGY_VERSION
from app.storage.models_sql import (
    WeeklyAnalyticsStoredReport,
    WeeklyDecision,
    WeeklyPublication,
    WeeklySnapshot,
)
from app.storage.weekly import WeeklyStore


def audit(store: WeeklyStore, report_date: date, weeks: int = 8) -> dict[str, Any]:
    comparisons = []
    assignment_buckets: dict[tuple, list[dict]] = defaultdict(list)
    event_pairs: list[dict] = []
    job_ids = set()
    for i in range(weeks):
        target = report_date - timedelta(days=7 * i)
        row = store.session.scalar(select(WeeklySnapshot).join(
            WeeklyPublication, WeeklyPublication.snapshot_id == WeeklySnapshot.id,
        ).where(WeeklyPublication.report_date == target))
        legacy = store.session.scalar(select(WeeklyAnalyticsStoredReport).where(
            WeeklyAnalyticsStoredReport.report_date == target))
        payload = json.loads(row.payload) if row else None
        if row:
            job_ids.add(row.id)
        sections = ("new", "trending_up", "trending_down")
        comparisons.append({
            "report_date": str(target), "snapshot_id": row.id if row else None,
            "legacy_counts": {s: sum(item.section_name == s for item in legacy.items)
                              for s in sections} if legacy else None,
            "v2_counts": {s: len(payload[s]) for s in sections} if payload else None,
            "status": payload["status"] if payload else "missing",
            "quality": payload.get("quality", {}) if payload else {},
            "section_status": payload.get("section_status", {}) if payload else {},
            "displayed_topics": [item for s in sections for item in payload[s][:5]]
                                if payload else [],
            "all_topic_metrics": [item for s in (*sections, "other_signals")
                                  for item in payload.get(s, [])] if payload else [],
        })
        if payload is None:
            continue
        events: dict[str, list[dict]] = defaultdict(list)
        for assignment in payload.get("assignments", []):
            multilingual = not assignment["title"].isascii()
            bucket = (assignment.get("topic_id"), multilingual, assignment.get("eligible"))
            assignment_buckets[bucket].append({
                "snapshot_id": row.id, "article_id": assignment["id"],
                "title": assignment["title"], "text": (assignment.get("summary") or
                                                        assignment.get("content") or "")[:4000],
                "url": assignment["url"], "publisher": assignment["publisher"],
                "published_at": assignment["published_at"],
                "accepted_topic": assignment.get("topic_id"), "multilingual": multilingual,
                "expected_topic": None, "review_notes": None,
            })
            events[assignment["event_id"]].append(assignment)
        for event_id, members in sorted(events.items()):
            if len(members) >= 2 and len(event_pairs) < 50:
                event_pairs.append({"snapshot_id": row.id, "event_id": event_id,
                                    "a": members[0], "b": members[1],
                                    "expected_same_event": None, "review_notes": None})
    samples: list[dict] = []
    buckets = list(assignment_buckets.values())
    while any(buckets) and len(samples) < 200:
        for stratum in buckets:
            if stratum and len(samples) < 200:
                samples.append(stratum.pop(0))
    usage = [json.loads(row.payload) for row in store.session.scalars(
        select(WeeklyDecision).where(WeeklyDecision.task == "worker_usage").order_by(
            WeeklyDecision.created_at, WeeklyDecision.key)).all()]
    return {"methodology_version": METHODOLOGY_VERSION, "comparisons": comparisons,
            "ready_weeks": sum(row["status"] == "ready" for row in comparisons),
            "assignment_review_sample": samples, "event_pair_review_sample": event_pairs,
            "worker_usage": [row for row in usage if row["job_id"] in job_ids],
            "release_evaluation_complete": False,
            "release_note": "Manual precision and missed-signal review, separate tuning/evaluation "
                            "weeks, and proven coverage are required before enabling v2."}
