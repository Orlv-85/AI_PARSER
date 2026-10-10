# pylint: disable=redefined-outer-name,protected-access
import json
import logging
from datetime import UTC, date, datetime, timedelta
from importlib import import_module

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.config.sources import SourceConfig
from app.core.models import Article as InputArticle
from app.core.weekly_analytics import calculate
from app.core.weekly_audit import audit
from app.storage.models_sql import (
    Article,
    Base,
    WeeklyAnalyticsStoredReport,
    WeeklyCoverageAttempt,
    WeeklyJob,
    WeeklySnapshot,
    WeeklySourceVersion,
)
from app.storage.repos import WeeklyAnalyticsRepo
from app.storage.weekly import (
    WeeklyStore,
    publisher_group,
    record_attempt,
    record_observation,
    register_source,
)


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'weekly.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    engine.dispose()


def settings(**changes) -> Settings:
    return Settings(_env_file=None, weekly_v2_enabled=True, **changes)


def make_payload(report_date: date) -> dict:
    result = dict(calculate(report_date, [], [], [], now=datetime.now(UTC)))
    result["taxonomy_version"] = "test-1"
    return result


def publish(store: WeeklyStore, target: date) -> dict:
    job_id = store.enqueue(target, settings())
    store.session.commit()
    claim = store.claim(900)
    assert claim is not None
    claimed_id, token = claim
    assert claimed_id == job_id
    job = store.session.get(WeeklyJob, job_id)
    packet = json.loads(job.input_payload)
    payload = make_payload(target)
    store.publish(job_id, token, payload, packet)
    return payload


def test_migration_preserves_legacy_and_schema_matches(tmp_path, monkeypatch) -> None:
    target = tmp_path / "migrated.db"
    monkeypatch.setenv("AINEWS_DATABASE_URL", f"sqlite:///{target}")
    config = Config("alembic.ini")
    command.upgrade(config, "c9e71b82a640")
    engine = create_engine(f"sqlite:///{target}")
    with Session(engine) as value:
        value.add(WeeklyAnalyticsStoredReport(
            report_date=date(2026, 10, 4), date_from=date(2026, 9, 28),
            date_to=date(2026, 10, 4), summary="Original legacy"))
        value.commit()
    command.upgrade(config, "head")
    with Session(engine) as value:
        report = WeeklyAnalyticsRepo(value).get_weekly_report(report_date=date(2026, 10, 4))
        assert report.summary == "Original legacy"
        assert value.scalar(select(func.count(WeeklyJob.id))) == 0
    engine.dispose()


def test_observation_provenance_keeps_alias_dates_unknown_and_raw_duplicates(session) -> None:
    now = datetime.now(UTC)
    item = InputArticle(source_key="test", title="One announcement", url="https://example.com/a",
                        published_at=now, summary="Actual source text")
    record_observation(session, 1, item)
    record_observation(session, 1, item)
    record_observation(session, 2, item.model_copy(
        update={"published_at": now - timedelta(days=7)}))
    record_observation(session, 3, item.model_copy(update={"published_at": None}))
    session.commit()
    packet = WeeklyStore(session).freeze_input(now.date(), settings())
    assert len(packet["observations"]) == 2
    assert len({r["published_at"] for r in packet["observations"]}) == 2
    assert packet["quality_counters"]["invalid_dates"] == 1
    assert packet["history_complete"] is False


def test_complete_read_over_two_hundred_and_safety_cap_explicit(session) -> None:
    now = datetime.now(UTC)
    for i in range(250):
        record_observation(session, 1, InputArticle(
            source_key="test", title=f"Unranked {i}", url=f"https://example.com/{i}",
            published_at=now - timedelta(days=1), summary="AI event evidence"))
    session.commit()
    packet = WeeklyStore(session).freeze_input(now.date(), settings())
    assert len(packet["observations"]) == 250
    assert packet["input_complete"] is True
    truncated = WeeklyStore(session).freeze_input(now.date(), settings(weekly_input_safety_cap=200))
    assert truncated["input_complete"] is False
    assert truncated["quality_counters"]["safety_cap_excluded"] == 50


def test_legacy_dates_are_quality_counters_not_verified_publication(session) -> None:
    now = datetime.now(UTC)
    session.add(Article(title="Legacy", url="https://example.com/legacy",
                        url_canonical="https://example.com/legacy", url_canonical_hash="legacy",
                        published_at=now, discovered_at=now))
    session.commit()
    packet = WeeklyStore(session).freeze_input(now.date(), settings())
    assert packet["quality_counters"]["legacy_unverified_dates"] == 1
    assert packet["observations"][0]["publication_provenance"] == "legacy_unverified"
    assert not packet["history_complete"]


def test_coverage_recorded_for_empty_304_failures_and_truncation(session) -> None:
    now = datetime.now(UTC).replace(hour=0, minute=0) - timedelta(days=1)
    config = SourceConfig(id="test", name="Test", type="rss", url="https://example.com/feed",
                          fetch_interval_minutes=360)
    key = register_source(session, 1, config, settings(), now - timedelta(days=40))
    for i, outcome in enumerate(("empty", "not_modified", "fetch_failure", "success")):
        record_attempt(session, run_id=str(i), source_id=1, version_id=key, interval=360,
                       outcome=outcome, complete=i != 3, now=now + timedelta(hours=i * 6))
    session.commit()
    packet = WeeklyStore(session).freeze_input(now.date(), settings())
    assert session.scalar(select(func.count(WeeklyCoverageAttempt.id))) == 4
    assert packet["coverage"][0]["expected"] == 4
    assert packet["coverage"][0]["successful"] == 3
    assert packet["coverage"][0]["complete"] is False
    assert session.scalar(select(func.count(WeeklySourceVersion.id))) == 1


def test_duplicate_attempts_do_not_hide_missed_schedule_slots(session) -> None:
    now = datetime.now(UTC).replace(hour=0, minute=0)
    config = SourceConfig(id="test", name="Test", type="rss", url="https://example.com/feed",
                          fetch_interval_minutes=360)
    key = register_source(session, 1, config, settings(), now - timedelta(days=40))
    for i in range(20):
        record_attempt(session, run_id=f"repeat-{i}", source_id=1, version_id=key, interval=360,
                       outcome="success", complete=True, now=now)
    session.commit()
    packet = WeeklyStore(session).freeze_input(now.date(), settings())
    assert packet["coverage"][0]["successful"] == 1
    assert packet["coverage"][0]["expected"] == 4


def test_unchanged_inputs_reuse_job_and_cached_outputs(session) -> None:
    store = WeeklyStore(session)
    target = date(2026, 10, 4)
    first = store.enqueue(target, settings())
    session.commit()
    assert store.enqueue(target, settings()) == first
    store.save_decision("cached", "jev", {"topic": "coding"})
    assert store.decision("cached") == {"topic": "coding"}
    assert session.scalar(select(func.count(WeeklyJob.id))) == 1


def test_lease_prevents_parallel_claim_and_can_resume_after_expiry(session) -> None:
    store = WeeklyStore(session)
    job_id = store.enqueue(date(2026, 10, 4), settings())
    session.commit()
    claim = store.claim(900)
    assert claim is not None
    assert store.claim(900) is None
    row = session.get(WeeklyJob, job_id)
    row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    resumed = store.claim(900)
    assert resumed is not None and resumed[1] != claim[1]
    with pytest.raises(ValueError, match="lease expired"):
        store.publish(job_id, claim[1], make_payload(row.report_date),
                      json.loads(row.input_payload))


def test_atomic_revisions_preserve_legacy_and_block_legacy_overwrite(session) -> None:
    target = date(2026, 10, 4)
    repo = WeeklyAnalyticsRepo(session)
    repo.save_weekly_report(report_date=target, date_from=target - timedelta(days=6),
                            date_to=target,
                            summary="Legacy original", new=[], trending_up=[], trending_down=[])
    session.commit()
    store = WeeklyStore(session)
    first = publish(store, target)
    assert first["revision"] == 1
    with pytest.raises(ValueError, match="cannot be overwritten"):
        repo.save_weekly_report(report_date=target, summary="Unverified client metrics")
    session.rollback()
    assert store.published(target)["snapshot_id"] == first["snapshot_id"]
    record_observation(session, 1, InputArticle(source_key="test", title="Later discovered AI",
                                               url="https://example.com/new",
                                               published_at=datetime(2026, 10, 4, tzinfo=UTC)))
    session.commit()
    second = publish(store, target)
    assert second["revision"] == 2
    assert session.scalar(select(func.count(WeeklySnapshot.id))) == 2
    assert repo._get_stored_report(report_date=target).summary == "Legacy original"


def test_failed_regeneration_retains_published_revision(session) -> None:
    store = WeeklyStore(session)
    first = publish(store, date(2026, 10, 4))
    job_id = store.enqueue(date(2026, 9, 27), settings())
    session.commit()
    claim = store.claim(900)
    assert claim is not None
    store.retry(job_id, claim[1], "provider_failure")
    assert store.published(date(2026, 10, 4))["snapshot_id"] == first["snapshot_id"]


def test_api_reads_snapshot_without_provider_calls_and_rejects_old_publisher(
    session, monkeypatch
) -> None:
    monkeypatch.setenv("AINEWS_WEEKLY_V2_ENABLED", "true")
    get_settings.cache_clear()
    module = import_module("app.web.app")
    store = WeeklyStore(session)
    payload = publish(store, date(2026, 10, 4))
    # Returning the same session lets TestClient inspect the isolated database.
    monkeypatch.setattr(module, "SessionLocal", lambda: session)
    monkeypatch.setattr(module, "create_all", lambda: None)
    client = TestClient(module.create_app())
    response = client.get("/api/news/weekly-analytics?date=2026-10-04")
    assert response.status_code == 200
    assert response.json()["snapshot_id"] == payload["snapshot_id"]
    assert response.json()["quality"]["reason"] == "coverage_unknown"
    manual = {"report_date": "2026-10-04", "date_from": "2026-09-28", "date_to": "2026-10-04",
              "summary": "Legacy publisher", "new": [], "trending_up": [], "trending_down": []}
    assert client.post("/api/news/weekly-analytics", json=manual).status_code == 409
    missing = client.get("/api/news/weekly-analytics?date=2026-09-27")
    assert missing.json()["status"] == "insufficient_data"
    assert missing.json()["new"] == []
    get_settings.cache_clear()


def test_monday_v2_trigger_only_enqueues(session, monkeypatch) -> None:
    module = import_module("app.core.pipeline")
    monkeypatch.setattr(module, "_weekly_report_date_to_publish", lambda _: date(2026, 10, 4))
    module._publish_weekly_analytics_if_due(
        session=session, logger=logging.getLogger("weekly-test"), run_id="test",
        settings=settings())
    session.commit()
    assert session.scalar(select(func.count(WeeklyJob.id))) == 1
    assert session.scalar(select(func.count(WeeklySnapshot.id))) == 0


def test_publisher_overrides_collapse_owned_domains() -> None:
    overrides = {"example.co.uk": "owner", "second.com": "owner"}
    assert publisher_group("https://feed.example.co.uk/rss", overrides) == "owner"
    assert publisher_group("https://second.com/rss", overrides) == "owner"


def test_audit_reports_missing_history_without_certifying_precision(session) -> None:
    store = WeeklyStore(session)
    payload = publish(store, date(2026, 10, 4))
    result = audit(store, date(2026, 10, 4))
    assert len(result["comparisons"]) == 8
    assert result["comparisons"][0]["snapshot_id"] == payload["snapshot_id"]
    assert result["comparisons"][1]["status"] == "missing"
    assert result["ready_weeks"] == 0
    assert result["release_evaluation_complete"] is False


def test_accepted_emerging_topic_keeps_identity_in_subsequent_frozen_jobs(session) -> None:
    store = WeeklyStore(session)
    candidate = {"id": "emerging-stable", "label": "Distinct subject", "definition": "Definition",
                 "exclusions": "Other topics", "aliases": [],
                 "parent_category": "Business & Product"}
    store.save_taxonomy([candidate], "accepted-1")
    first = store.freeze_input(date(2026, 10, 4), settings())
    second = store.freeze_input(date(2026, 10, 11), settings())
    assert first["topics"][-1] == candidate
    assert second["topics"][-1] == candidate
    assert first["taxonomy_version"] == second["taxonomy_version"]
