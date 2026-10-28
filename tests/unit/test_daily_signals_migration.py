import logging.config

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.storage.models_sql import Article, Base

SIGNAL_TABLES = {"article_signals", "daily_signal_scope", "signal_mentions", "ai_entities",
                 "ai_entity_overrides", "daily_signal_reports", "daily_signal_briefs"}


def schema(url, table):
    engine = create_engine(url)
    inspector = inspect(engine)
    columns = {c["name"]: (str(c["type"]), c["nullable"]) for c in inspector.get_columns(table)}
    indexes = {(i["name"], tuple(i["column_names"]), bool(i["unique"]))
               for i in inspector.get_indexes(table)}
    uniques = {tuple(u["column_names"]) for u in inspector.get_unique_constraints(table)}
    fks = {(tuple(f["constrained_columns"]), f["referred_table"],
            (f.get("options") or {}).get("ondelete")) for f in inspector.get_foreign_keys(table)}
    engine.dispose()
    return columns, indexes, uniques, fks


def article():
    # Digest tables have no migration (create_all only); keep a pre-feature row in articles.
    return Article(title="Kept", url="https://x.com/a", url_canonical="https://x.com/a",
                   url_canonical_hash="h" * 64, published_at=None)


def upgrade(monkeypatch, path, revision="head"):
    monkeypatch.setenv("AINEWS_DATABASE_URL", f"sqlite:///{path}")
    # alembic env.py calls logging.config.fileConfig, which disables existing loggers and
    # breaks caplog in later tests (docs/troubleshooting.md: alembic-env-disables-loggers).
    monkeypatch.setattr(logging.config, "fileConfig", lambda *args, **kwargs: None)
    config = Config("alembic.ini")
    command.upgrade(config, revision)
    return config


def test_upgrade_from_previous_head_matches_models(tmp_path, monkeypatch):
    migrated = tmp_path / "migrated.db"
    upgrade(monkeypatch, migrated, "a42b750d0c44")
    engine = create_engine(f"sqlite:///{migrated}")
    with Session(engine) as session:
        session.add(article())
        session.commit()
    upgrade(monkeypatch, migrated)
    created = tmp_path / "created.db"
    model_engine = create_engine(f"sqlite:///{created}")
    Base.metadata.create_all(model_engine)
    model_engine.dispose()
    assert SIGNAL_TABLES <= set(inspect(engine).get_table_names())
    for table in SIGNAL_TABLES:
        assert schema(f"sqlite:///{migrated}", table) == \
            schema(f"sqlite:///{created}", table), table
    _, _, _, fks = schema(f"sqlite:///{migrated}", "article_signals")
    assert fks == {(("article_id",), "articles", "CASCADE")}
    _, _, _, fks = schema(f"sqlite:///{migrated}", "daily_signal_scope")
    assert fks == {(("article_id",), "articles", "CASCADE")}
    assert schema(f"sqlite:///{migrated}", "signal_mentions")[3] == set()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM articles")).scalar() == 1
    engine.dispose()


def test_upgrade_after_create_all_and_downgrade_keeps_existing_tables(tmp_path, monkeypatch):
    path = tmp_path / "both.db"
    config = upgrade(monkeypatch, path, "a42b750d0c44")
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(article())
        session.commit()
    command.upgrade(config, "head")
    assert SIGNAL_TABLES <= set(inspect(engine).get_table_names())
    command.downgrade(config, "a42b750d0c44")
    tables = set(inspect(engine).get_table_names())
    assert not SIGNAL_TABLES & tables
    assert {"articles", "sources"} <= tables
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM articles")).scalar() == 1
    command.upgrade(config, "head")
    assert SIGNAL_TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()


def test_briefs_table_upgrade_downgrade_without_article_fk(tmp_path, monkeypatch):
    path = tmp_path / "briefs.db"
    config = upgrade(monkeypatch, path, "b6d1f0a7c3e5")
    engine = create_engine(f"sqlite:///{path}")
    assert "daily_signal_briefs" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    columns, indexes, _, fks = schema(f"sqlite:///{path}", "daily_signal_briefs")
    assert fks == set()
    assert ("ix_daily_signal_briefs_report_date", ("report_date",), True) in indexes
    assert set(columns) == {"id", "report_date", "brief_version", "model", "input_hash",
                            "status", "reason", "payload", "created_at", "updated_at"}
    command.downgrade(config, "b6d1f0a7c3e5")
    tables = set(inspect(engine).get_table_names())
    assert "daily_signal_briefs" not in tables
    assert SIGNAL_TABLES - {"daily_signal_briefs"} <= tables
    engine.dispose()


ARCHIVE_TABLES = {"archive_documents", "archive_texts"}


def test_article_archive_migration_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "archive.db"
    config = upgrade(monkeypatch, path, "c3a8e5d27f14")
    engine = create_engine(f"sqlite:///{path}")
    with Session(engine) as session:
        session.add(article())
        session.commit()
    assert not ARCHIVE_TABLES & set(inspect(engine).get_table_names())
    command.upgrade(config, "head")
    created = tmp_path / "created.db"
    model_engine = create_engine(f"sqlite:///{created}")
    Base.metadata.create_all(model_engine)
    model_engine.dispose()
    for table in ARCHIVE_TABLES:
        assert schema(f"sqlite:///{path}", table) == schema(f"sqlite:///{created}", table), table
    assert schema(f"sqlite:///{path}", "archive_documents")[3] == set()
    assert schema(f"sqlite:///{path}", "archive_texts")[3] == {
        (("document_id",), "archive_documents", None)}
    command.downgrade(config, "c3a8e5d27f14")
    assert not ARCHIVE_TABLES & set(inspect(engine).get_table_names())
    command.upgrade(config, "head")
    assert ARCHIVE_TABLES <= set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM articles")).scalar() == 1
    engine.dispose()
