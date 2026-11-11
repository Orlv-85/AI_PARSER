"""Counter persistence, migration and read-only CLI."""
# pylint: disable=redefined-outer-name,import-error,unused-import
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from importlib import import_module
from unittest.mock import Mock

import pytest
import test_web_bulletin_page as bulletin_helpers
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner

maker = bulletin_helpers.maker


def test_cli_page_views_prints_json(maker, monkeypatch):
    cli = import_module("app.cli.main")
    deps = import_module("app.cli.deps")
    monkeypatch.setattr(deps, "SessionLocal", maker)
    monkeypatch.setattr(deps, "create_all", lambda: (_ for _ in ()).throw(AssertionError("write")))
    today = datetime.now(UTC).date()
    with maker() as session:
        session.execute(text("INSERT INTO page_views (day, route, count) VALUES "
                             "(:today, '/', 3), (:today, '/daily', 7), (:edge, '/', 2), "
                             "(:old, '/', 99), (:future, '/', 100)"),
                        {"today": today, "edge": today - timedelta(days=13),
                         "old": today - timedelta(days=14), "future": today + timedelta(days=1)})
        session.commit()
    runner = CliRunner()
    result = runner.invoke(cli.app, ["page-views"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {str(today): {"/": 3, "/daily": 7},
                                       str(today - timedelta(days=13)): {"/": 2}}
    result = runner.invoke(cli.app, ["page-views", "--days", "1"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {str(today): {"/": 3, "/daily": 7}}
    assert runner.invoke(cli.app, ["page-views", "--days", "0"]).exit_code == 2
    with maker() as session:
        assert session.scalar(text("SELECT SUM(count) FROM page_views")) == 211


def test_page_views_empty_cli(maker, monkeypatch):
    cli = import_module("app.cli.main")
    deps = import_module("app.cli.deps")
    monkeypatch.setattr(deps, "SessionLocal", maker)
    result = CliRunner().invoke(cli.app, ["page-views"])
    assert result.exit_code == 0 and json.loads(result.output) == {}


def test_page_views_sqlite_atomic_increment(tmp_path):
    repo = import_module("app.storage.page_views").PageViewRepo
    engine = create_engine(f"sqlite:///{tmp_path}/counter.db")
    import_module("app.storage.models_sql").Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    day = date(2026, 11, 6)
    def increment(_):
        with factory() as session:
            repo(session).increment(day, "/")
            session.commit()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(increment, range(24)))
    with factory() as session:
        assert repo(session).totals(day, day) == {str(day): {"/": 24}}
    engine.dispose()


def test_page_views_increment_compiles_for_postgres():
    repo = import_module("app.storage.page_views").PageViewRepo
    session = Mock(spec=Session)
    session.get_bind.return_value.dialect.name = "postgresql"
    day = date(2026, 11, 6)
    repo(session).increment(day, "/daily")
    statement = session.execute.call_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "ON CONFLICT (day, route) DO UPDATE SET count = (page_views.count +" in str(compiled)
    assert compiled.params["day"] == day
    assert compiled.params["route"] == "/daily"
    assert compiled.params["count"] == 1


@pytest.mark.parametrize("dialect", ["postgresql", "sqlite"])
def test_page_views_transaction_timeouts(dialect):
    repo = import_module("app.storage.page_views").PageViewRepo
    session = Mock(spec=Session)
    session.get_bind.return_value.dialect.name = dialect
    repo(session).increment(date(2026, 11, 6), "/")
    statements = [call.args[0] for call in session.execute.call_args_list]
    expected = (["SET LOCAL lock_timeout = '1s'", "SET LOCAL statement_timeout = '2s'"]
                if dialect == "postgresql" else [])
    assert [str(statement) for statement in statements[:-1]] == expected
    assert str(statements[-1]).startswith("INSERT INTO page_views")


def test_page_views_migration(tmp_path):
    migration = import_module("app.storage.migrations.versions.a6b0180c0001_add_page_views")
    engine = create_engine(f"sqlite:///{tmp_path}/migration.db")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()
            assert [c["name"] for c in inspect(connection).get_columns("page_views")] == [
                "day", "route", "count"]
            assert inspect(connection).get_pk_constraint("page_views")["constrained_columns"] == [
                "day", "route"]
            assert not any(c["nullable"] for c in inspect(connection).get_columns("page_views"))
            connection.execute(text("INSERT INTO page_views VALUES ('2026-11-06', '/', 2)"))
            migration.upgrade()
            assert connection.scalar(text("SELECT count FROM page_views")) == 2
            migration.downgrade()
            migration.downgrade()
            assert "page_views" not in inspect(connection).get_table_names()
    engine.dispose()
