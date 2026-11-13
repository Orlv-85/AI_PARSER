import os
from datetime import date
from importlib import import_module
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.core.bulletin.builder import Candidate, DayInput, build_bulletin
from app.core.bulletin.phrases import load_phrases
from app.storage.bulletin_store import BulletinRepo

POSTGRES_TEST_URL = os.getenv("AINEWS_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_URL, reason="AINEWS_TEST_POSTGRES_URL is not set")


def test_bulletin_store_postgres() -> None:
    schema = "bulletins_" + uuid4().hex
    admin = create_engine(str(POSTGRES_TEST_URL), future=True)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(str(POSTGRES_TEST_URL), future=True,
                           connect_args={"options": "-csearch_path=" + schema})
    try:
        migration = import_module(
            "app.storage.migrations.versions.d2a6f8b03c19_add_bulletins")
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
        assert "bulletins" in inspect(engine).get_table_names()
        maker = sessionmaker(bind=engine, expire_on_commit=False)
        day = date(2026, 10, 30)
        candidate = Candidate("https://example.com/a", "AI changes the work", "Example", "changed",
                              0.9, "Work", "organisation", 0.0, "event", article_id=17)
        data = DayInput(day, "ready", False, 1, 0, 0, None, (candidate,), 1)
        built = build_bulletin(data, load_phrases()).bulletin
        assert built is not None
        numbers = {"assessed": 1, "digest_articles": 1}
        with maker() as session:
            repo = BulletinRepo(session)
            assert repo.save(day, bulletin=built, numbers=numbers) is True
            session.commit()
            row = repo.get(day)
            assert row is not None
            assert row.payload["key_results"][0]["article_ids"] == [17]
            built.headline = "A CHANGED HEADLINE"
            assert repo.save(day, bulletin=built, numbers=numbers) is True
            session.commit()
            row = repo.get(day)
            assert row is not None
            assert row.payload == built.as_dict()
            row.telegram_message_id = 42
            session.commit()
            assert repo.save(day, bulletin=None, reason="signals_partial", numbers={}) is False
            session.commit()
            row = repo.get(day)
            assert row is not None
            assert (row.payload, row.telegram_message_id) == (built.as_dict(), 42)
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
