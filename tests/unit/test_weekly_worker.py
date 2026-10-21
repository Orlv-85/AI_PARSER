import json
from dataclasses import asdict
from datetime import UTC, date, datetime

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.core.weekly.analytics import DEFAULT_THRESHOLDS
from app.core.weekly.enrichment import WeeklyEnricher
from app.core.weekly.topics import TAXONOMY_VERSION, topic_registry
from app.core.weekly.worker import build_snapshot, drain
from app.storage.models_sql import Base, WeeklyJob, WeeklyTopicVersion
from app.storage.weekly import WeeklyStore, encoded


def packet() -> dict:
    return {"report_date": "2026-10-04", "data_cutoff": "2026-10-05T00:00:00+00:00",
            "observations": [], "coverage": [], "topics": topic_registry(),
            "taxonomy_version": TAXONOMY_VERSION, "input_complete": True,
            "included_ids": [], "thresholds": asdict(DEFAULT_THRESHOLDS),
            "quality_counters": {}, "provider_configuration": {}}


def test_jev_outage_produces_explicit_quality_without_false_labels() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    data = packet()
    data["observations"] = [{"id": "1", "title": "AI coding agent", "canonical_hash": "1",
                             "published_at": "2026-10-01T00:00:00+00:00",
                             "publisher": "example.com",
                             "url": "https://example.com/1", "summary": "Software development"}]
    with Session(engine) as session, httpx.Client(transport=httpx.MockTransport(
        lambda _: httpx.Response(401))) as client:
        service = WeeklyEnricher(Settings(_env_file=None, jev_api_key="invalid"),
                                  WeeklyStore(session), client, data["topics"], TAXONOMY_VERSION)
        result = build_snapshot(data, service)
        assert result["status"] == "insufficient_data"
        assert result["assignments"][0]["topic_id"] is None
        assert not any(result[s] for s in ("new", "trending_up", "trending_down"))


def test_new_taxonomy_reclassifies_all_thirty_five_days(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    data = packet()
    data["observations"] = [
        {"id": str(i), "title": "Previously unseen subject", "canonical_hash": str(i),
         "published_at": day, "publisher": "example.com", "url": f"https://example.com/{i}"}
        for i, day in enumerate(("2026-10-01T00:00:00+00:00", "2026-09-01T00:00:00+00:00"))]
    candidate = {"id": "new-topic", "label": "New topic", "definition": "A distinct topic",
                 "exclusions": "Existing topics", "aliases": [], "parent_category": "Applications"}
    classified: list[tuple[str, str]] = []

    def classify(self, row):
        classified.append((row["id"], self.taxonomy_version))
        return {"topic_id": candidate["id"] if self.taxonomy_version != TAXONOMY_VERSION else None,
                "eligible": True, "possible_topics": [], "classification_complete": True}

    monkeypatch.setattr(WeeklyEnricher, "classify", classify)
    monkeypatch.setattr(WeeklyEnricher, "propose_topic", lambda *args: candidate)
    monkeypatch.setattr(WeeklyEnricher, "cluster", lambda _, rows: (
        [{**r, "event_id": r["id"]} for r in rows], True))
    with Session(engine) as session, httpx.Client() as client:
        service = WeeklyEnricher(Settings(_env_file=None), WeeklyStore(session), client,
                                  data["topics"], TAXONOMY_VERSION)
        result = build_snapshot(data, service)
        assert len(classified) == 4
        reassigned = [r["id"] for r in result["assignments"] if r["topic_id"] == "new-topic"]
        assert reassigned == ["0", "1"]
        assert result["topic_registry"][-1]["id"] == "new-topic"
        assert session.scalars(select(WeeklyTopicVersion)).all()
        assert not result["new"]


def test_worker_budget_resumption_reuses_same_frozen_input(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'worker.db'}")
    Base.metadata.create_all(engine)
    data = packet()
    data["observations"] = [
        {"id": str(i), "title": f"Software engineering agent event {i}",
         "canonical_hash": str(i), "published_at": "2026-10-01T00:00:00+00:00",
         "publisher": "example.com", "url": f"https://example.com/{i}"}
        for i in range(2)]
    requests = []

    def handler(request):
        requests.append(request)
        body = json.loads(request.content)
        if "same_event" in body["questions"]:
            return httpx.Response(200, json={"answers": {"same_event": {"noul": 0.05}}})
        return httpx.Response(200, json={"answers": {"relevant": {"noul": 0.95},
                                                   "topic": {"choice": "coding-agents",
                                                             "confidence": 0.95}}})

    real_client = httpx.Client
    monkeypatch.setattr("app.core.weekly.worker.httpx.Client", lambda **_: real_client(
        transport=httpx.MockTransport(handler)))
    with Session(engine) as session:
        session.add(WeeklyJob(id="job", report_date=date(2026, 10, 4), methodology_version="v2",
                              input_fingerprint="job", input_payload=encoded(data),
                              status="pending",
                              attempts=0, created_at=datetime.now(UTC)))
        session.commit()
        config = Settings(_env_file=None, weekly_v2_enabled=True, jev_api_key="key",
                          weekly_jev_decision_budget=1)
        first = drain(WeeklyStore(session), config)
        assert first[0]["status"] == "retry"
        assert len(requests) == 1
        second = drain(WeeklyStore(session), config)
        assert second[0]["status"] == "retry"
        assert len(requests) == 2
        third = drain(WeeklyStore(session), config)
        assert third[0]["status"] == "insufficient_data"
        assert len(requests) == 3
        job = session.get(WeeklyJob, "job")
        assert job is not None and job.status == "complete"
