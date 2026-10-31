import logging.config

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.storage.models_sql import Article, Base

PERIOD_TABLES = {"period_signal_reports", "period_signal_briefs"}
PREVIOUS_HEAD = "e7b4c2a9d150"
PERIOD_REVISION = "f4a9c1d27b83"
DROP_REVISION = "a7d3e5b18c94"
HEAD = "b8e2d4f61a07"


def schema(url, table):
    engine = create_engine(url)
    inspector = inspect(engine)
    columns = {c["name"]: (str(c["type"]), c["nullable"]) for c in inspector.get_columns(table)}
    indexes = {(i["name"], tuple(i["column_names"]), bool(i["unique"]))
               for i in inspector.get_indexes(table)}
    uniques = {tuple(u["column_names"]) for u in inspector.get_unique_constraints(table)}
    fks = {tuple(f["constrained_columns"]) for f in inspector.get_foreign_keys(table)}
    engine.dispose()
    return columns, indexes, uniques, fks


def upgrade(monkeypatch, path, revision="head"):
    monkeypatch.setenv("AINEWS_DATABASE_URL", f"sqlite:///{path}")
    # env.py calls fileConfig, which disables loggers (docs/troubleshooting.md).
    monkeypatch.setattr(logging.config, "fileConfig", lambda *args, **kwargs: None)
    config = Config("alembic.ini")
    command.upgrade(config, revision)
    return config


def test_single_head_and_chain():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert script.get_heads() == [HEAD]
    assert script.get_revision(PERIOD_REVISION).down_revision == PREVIOUS_HEAD
    assert script.get_revision(DROP_REVISION).down_revision == PERIOD_REVISION
    assert script.get_revision(HEAD).down_revision == DROP_REVISION


def test_upgrade_matches_models_and_downgrade_drops_only_period_tables(tmp_path, monkeypatch):
    path = tmp_path / "migrated.db"
    config = upgrade(monkeypatch, path, PREVIOUS_HEAD)
    engine = create_engine(f"sqlite:///{path}")
    with Session(engine) as session:
        session.add(Article(title="Kept", url="https://x.com/a", url_canonical="https://x.com/a",
                            url_canonical_hash="h" * 64, published_at=None))
        session.commit()
    assert not PERIOD_TABLES & set(inspect(engine).get_table_names())
    command.upgrade(config, "head")
    created = tmp_path / "created.db"
    model_engine = create_engine(f"sqlite:///{created}")
    Base.metadata.create_all(model_engine)
    model_engine.dispose()
    for table in PERIOD_TABLES:
        assert schema(f"sqlite:///{path}", table) == schema(f"sqlite:///{created}", table), table
        assert schema(f"sqlite:///{path}", table)[3] == set()  # no foreign keys
        assert ("period_kind", "period_start") in schema(f"sqlite:///{path}", table)[2]
    command.downgrade(config, PREVIOUS_HEAD)
    tables = set(inspect(engine).get_table_names())
    assert not PERIOD_TABLES & tables
    assert {"articles", "archive_documents", "daily_signal_reports"} <= tables
    command.upgrade(config, "head")
    assert PERIOD_TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()


def test_upgrade_after_create_all_keeps_existing_tables(tmp_path, monkeypatch):
    path = tmp_path / "both.db"
    config = upgrade(monkeypatch, path, PREVIOUS_HEAD)
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    command.upgrade(config, "head")
    assert PERIOD_TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()
