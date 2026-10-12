"""One service for scheduled jobs and ingestion-triggered weekly analytics."""

import json
import logging
import time
from datetime import date, datetime
from typing import Any

import httpx

from app.config.settings import Settings
from app.core.weekly_analytics import Observation, Thresholds, calculate
from app.core.weekly_enrichment import BudgetExhausted, WeeklyEnricher, clean_text
from app.core.weekly_narrative import explain
from app.storage.models_sql import WeeklyJob
from app.storage.weekly import WeeklyStore, fingerprint, hydrate_coverage
from app.web.models import WeeklyAnalyticsResponse


def _classify(packet: dict, enricher: WeeklyEnricher) -> list[dict]:
    classified = []
    for row in packet["observations"]:
        assessment = enricher.classify(row)
        if row.get("publication_provenance") == "legacy_unverified":
            assessment["eligible"] = False
        classified.append({**row, **assessment})
    return classified


def build_snapshot(packet: dict, enricher: WeeklyEnricher) -> dict[str, Any]:
    classified = _classify(packet, enricher)
    clustered, events_complete = enricher.cluster(classified)
    candidate = enricher.propose_topic(clustered) if events_complete else None
    if candidate is not None:
        packet["topics"] = [*packet["topics"], candidate]
        packet["taxonomy_version"] = "topics-" + fingerprint(packet["topics"])[:24]
        enricher.topics = packet["topics"]
        enricher.taxonomy_version = packet["taxonomy_version"]
        enricher.store.save_taxonomy(packet["topics"], packet["taxonomy_version"])
        # Reclassify the entire 35-day frozen input, including every historical week.
        clustered, events_complete = enricher.cluster(_classify(packet, enricher))
    observations = [Observation(
        id=row["id"], event_id=row["event_id"], publisher=row["publisher"],
        published_at=(datetime.fromisoformat(row["published_at"])
                      if row.get("published_at") else None), topic_id=row["topic_id"],
        title=row["title"], url=row["url"], article_id=row.get("article_id"),
        excerpt=clean_text(row.get("summary") or row.get("content") or row["title"])[:2000],
        eligible=row["eligible"], possible_topics=tuple(row["possible_topics"]),
        calendar_date=row.get("calendar_date"),
        publication_precision=row.get("publication_precision"),
        publication_interval=row.get("publication_interval"),
    ) for row in clustered]
    payload = calculate(date.fromisoformat(packet["report_date"]), observations,
                        hydrate_coverage(packet["coverage"]), packet["topics"],
                        now=datetime.fromisoformat(packet["data_cutoff"]),
                        history_complete=packet.get("history_complete", True),
                        thresholds=Thresholds(**packet.get("thresholds", {})),
                        input_complete=packet["input_complete"] and events_complete)
    payload["quality"].update(packet["quality_counters"])
    payload["quality"]["events_complete"] = events_complete
    payload["quality"]["admission_unresolved"] = sum(
        bool(row.get("admission_required")) and row.get("admission_state") not in {
            "accepted_compatible", "rejected"} for row in clustered)
    payload["quality"]["provider_calls"] = dict(enricher.calls)
    payload["quality"]["provider_tokens"] = dict(enricher.tokens)
    # All accepted assignments/event IDs and all candidates are retained for replay.
    payload["input_fingerprint"] = packet.get("job_id")
    payload["assignments"] = clustered
    payload["event_ambiguities"] = enricher.event_ambiguities
    payload["topic_registry"] = packet["topics"]
    payload["included_observation_ids"] = packet["included_ids"]
    payload["excluded_observations"] = packet.get("excluded_observations", [])
    payload["unassigned_articles"] = packet.get("unassigned_articles", [])
    selected = [item for section in ("new", "trending_up", "trending_down")
                for item in payload[section][:5]]
    selected += sorted((item for item in payload["other_signals"] if item["evidence"]),
                       key=lambda item: (-item["event_count_current"], item["topic_id"]))[:8]
    modes = []
    definitions = {t["id"]: t for t in packet["topics"]}
    for item in selected:
        modes.append(explain(item, enricher, definitions[item["topic_id"]]))
    if modes and any(modes):
        payload["narrative_mode"] = "deepseek" if all(modes) else "mixed"
    payload["quality"]["provider_calls"] = dict(enricher.calls)
    payload["quality"]["provider_tokens"] = dict(enricher.tokens)
    return dict(payload)


def drain(store: WeeklyStore, settings: Settings, *, max_jobs: int = 1) -> list[dict]:
    results = []
    calls: Any = None
    started = None
    with httpx.Client(limits=httpx.Limits(max_connections=settings.weekly_provider_concurrency,
                                         max_keepalive_connections=4)) as client:
        for _ in range(max_jobs):
            claim = store.claim(settings.weekly_wall_seconds)
            if claim is None:
                break
            job_id, token = claim
            job = store.session.get(WeeklyJob, job_id)
            if job is None:
                continue
            packet = json.loads(job.input_payload)
            packet["job_id"] = job_id
            frozen_settings = settings.model_copy(update=packet["provider_configuration"])
            enricher = WeeklyEnricher(frozen_settings, store, client, packet["topics"],
                                      packet["taxonomy_version"])
            if calls is not None:
                enricher.calls = calls
                enricher.started = started
            calls, started = enricher.calls, enricher.started
            try:
                payload = build_snapshot(packet, enricher)
                WeeklyAnalyticsResponse.model_validate(payload)
                store.publish(job_id, token, payload, packet)
                results.append({"job_id": job_id, "status": payload["status"],
                                "revision": payload["revision"], "calls": dict(enricher.calls)})
            except BudgetExhausted:
                store.retry(job_id, token, "provider_budget_exhausted")
                results.append({"job_id": job_id, "status": "retry", "calls": dict(enricher.calls)})
                break
            except Exception as exc:
                store.retry(job_id, token, type(exc).__name__)
                results.append({"job_id": job_id, "status": "retry",
                                "error_type": type(exc).__name__})
                break
            finally:
                usage = {"job_id": job_id, "calls": dict(enricher.calls),
                         "tokens": dict(enricher.tokens),
                         "failed_providers": sorted(enricher.failed),
                         "elapsed_seconds": time.monotonic() - enricher.started}
                store.save_decision(fingerprint(["worker_usage", job_id, token]),
                                    "worker_usage", usage)
                logging.getLogger("ai_news.weekly").info(
                    "weekly_worker_usage", extra={"event_fields": usage})
    return results
