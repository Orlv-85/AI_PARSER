"""Concurrent increments against an isolated PostgreSQL schema."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from importlib import import_module
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

POSTGRES_TEST_URL = os.getenv("AINEWS_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_URL, reason="AINEWS_TEST_POSTGRES_URL is not set")


def test_page_views_postgres_atomic_increment():
    repo = import_module("app.storage.page_views").PageViewRepo
    schema = "page_views_" + uuid4().hex
    admin = create_engine(str(POSTGRES_TEST_URL))
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(str(POSTGRES_TEST_URL),
                           connect_args={"options": "-csearch_path=" + schema})
    try:
        migration = import_module("app.storage.migrations.versions.a6b0180c0001_add_page_views")
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
        maker = sessionmaker(bind=engine)
        day = date(2026, 11, 6)
        def increment(_):
            with maker() as session:
                repo(session).increment(day, "/")
                session.commit()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(increment, range(24)))
        with maker() as session:
            assert repo(session).totals(day, day) == {str(day): {"/": 24}}
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
