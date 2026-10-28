import logging.config

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.storage.models_sql import Base

V2_TABLES = {"weekly_source_versions", "weekly_coverage_attempts", "weekly_input_observations",
             "weekly_decisions", "weekly_topic_versions", "weekly_jobs", "weekly_snapshots",
             "weekly_publications"}
KEPT = {"weekly_analytics_reports", "weekly_analytics_items"}
BEFORE = "f4a9c1d27b83"


def alembic_config(monkeypatch, path):
    monkeypatch.setenv("AINEWS_DATABASE_URL", f"sqlite:///{path}")
    monkeypatch.setattr(logging.config, "fileConfig", lambda *args, **kwargs: None)
    return Config("alembic.ini")


def test_upgrade_drops_v2_tables_and_downgrade_recreates_them_empty(tmp_path, monkeypatch):
    path = tmp_path / "drop.db"
    config = alembic_config(monkeypatch, path)
    command.upgrade(config, BEFORE)
    engine = create_engine(f"sqlite:///{path}")
    assert V2_TABLES <= set(inspect(engine).get_table_names())
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO weekly_decisions VALUES ('k', 't', '{}', "
                                "'2026-10-01 00:00:00')"))
    command.upgrade(config, "head")
    tables = set(inspect(engine).get_table_names())
    assert not V2_TABLES & tables
    assert KEPT <= tables
    command.downgrade(config, BEFORE)
    inspector = inspect(engine)
    assert V2_TABLES <= set(inspector.get_table_names())
    with engine.connect() as connection:
        for table in V2_TABLES:
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == 0
    assert inspector.get_foreign_keys("weekly_publications")[0]["referred_table"] == \
        "weekly_snapshots"
    assert {i["name"] for i in inspector.get_indexes("weekly_jobs")} == {
        "ix_weekly_jobs_report_date", "ix_weekly_jobs_status"}
    command.upgrade(config, "head")
    assert not V2_TABLES & set(inspect(engine).get_table_names())
    engine.dispose()


def test_downgrade_keeps_tables_that_already_exist(tmp_path, monkeypatch):
    path = tmp_path / "partial.db"
    config = alembic_config(monkeypatch, path)
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE weekly_jobs (id VARCHAR(64) PRIMARY KEY)"))
    command.downgrade(config, BEFORE)
    assert V2_TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()


def test_create_all_creates_no_v2_table(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    Base.metadata.create_all(engine)
    tables = set(inspect(engine).get_table_names())
    assert not V2_TABLES & tables
    assert KEPT <= tables
    engine.dispose()


def test_full_chain_from_base_to_head(tmp_path, monkeypatch):
    path = tmp_path / "chain.db"
    config = alembic_config(monkeypatch, path)
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{path}")
    tables = set(inspect(engine).get_table_names())
    assert not V2_TABLES & tables
    assert KEPT <= tables
    engine.dispose()
