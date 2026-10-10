import importlib
import json
import os
from datetime import date
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.storage.models_sql import WeeklyJob
from app.storage.weekly import WeeklyStore

POSTGRES_TEST_URL = os.getenv("AINEWS_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_TEST_URL, reason="AINEWS_TEST_POSTGRES_URL is not set")


def test_weekly_migrations_and_leased_snapshot_roundtrip_postgres() -> None:
    engine = create_engine(str(POSTGRES_TEST_URL))
    schema = "weekly_test_" + uuid4().hex
    with engine.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.commit()
        try:
            connection.execute(text(f'SET search_path TO "{schema}"'))
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                for revision in (
                    "d5686ed0fc60_create_initial_tables",
                    "5f3c9f6f2a11_add_source_fetch_state_columns",
                    "8b3a2d4e9f10_add_weekly_analytics_report_tables",
                    "c9e71b82a640_add_article_categories",
                    "e12a640c9b32_add_weekly_attention_snapshots",
                ):
                    importlib.import_module(f"app.storage.migrations.versions.{revision}").upgrade()
            connection.commit()
            with Session(connection) as session:
                store = WeeklyStore(session)
                config = Settings(_env_file=None)
                job_id = store.enqueue(date(2026, 10, 4), config)
                session.commit()
                assert store.enqueue(date(2026, 10, 4), config) == job_id
                session.commit()
                claim = store.claim(900)
                assert claim is not None
                assert store.claim(900) is None
                job = session.get(WeeklyJob, job_id)
                assert job is not None
                packet = json.loads(job.input_payload)
                payload = {"report_date": "2026-10-04", "date_from": "2026-09-28",
                           "date_to": "2026-10-04", "status": "insufficient_data",
                           "summary": "Test",
                           "new": [], "trending_up": [], "trending_down": []}
                store.publish(job_id, claim[1], payload, packet)
                assert store.published(date(2026, 10, 4))["revision"] == 1
        finally:
            connection.rollback()
            connection.execute(text('SET search_path TO "public"'))
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            connection.commit()
    engine.dispose()
