# pylint: disable=redefined-outer-name,unused-argument
import json
import logging.config
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from importlib import import_module
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.dialects.postgresql import dialect as postgres_dialect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from typer.testing import CliRunner

from app.cli import main as cli_main
from app.config.settings import Settings
from app.core.bulletin.builder import Candidate, DayInput, build_bulletin
from app.core.bulletin.phrases import load_phrases
from app.core.bulletin.world_change import WORLD_CHANGE_VERSION, WorldChange
from app.core.bulletin.writer import WRITER_MODEL, WRITER_VERSION
from app.core.canonicalize import canonical_url_hash
from app.storage.bulletin_store import BULLETIN_STORE_VERSION, BulletinRepo
from app.storage.digest_repo import NewsDigestRepo
from app.storage.models_sql import Article, Base, BulletinRow, DailySignalReport
from app.storage.world_change import WorldChangeRepo

DAY = date(2026, 10, 30)
PREVIOUS = "c9f3a7e15b28"
HEAD = "d2a6f8b03c19"
NUMBERS = {"assessed": 1, "digest_articles": 1}


@pytest.fixture
def maker():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def bulletin(day=DAY):
    candidate = Candidate("https://example.com/a", "AI changes the work", "Example", "changed",
                          0.9, "Work", "organisation", 0.0, "event", article_id=17)
    data = DayInput(day, "ready", False, 1, 0, 0, None, (candidate,), 1)
    return build_bulletin(data, load_phrases()).bulletin


def seed_day(maker, status="ready"):
    with maker() as session:
        url = "https://example.com/a"
        article = Article(title="AI changes the work", url=url, url_canonical=url,
                          url_canonical_hash=canonical_url_hash(url))
        session.add(article)
        session.flush()
        WorldChangeRepo(session).save(
            article, WorldChange("changed", 0.9, "Work", 0.8, "organisation", 0.8, 0.0),
            version=WORLD_CHANGE_VERSION, model="fake")
        NewsDigestRepo(session).save_digest(report_date=DAY, groups=[{"title": "G", "items": [
            {"title": article.title, "summary": "s", "url": url}]}])
        payload = {"status": status, "quiet": False, "coverage": {"items": 1},
                   "event_counts": [], "top_stories": []}
        session.add(DailySignalReport(
            report_date=DAY, methodology_version="m", extraction_version="e", status=status,
            payload_hash="h", thresholds="{}", payload=json.dumps(payload), coverage="{}"))
        session.commit()


@pytest.mark.parametrize("writer", [None, {"version": WRITER_VERSION, "model": "fake",
                                         "reason": None, "cost_usd": 0.001}])
def test_save_and_get_ready_day(maker, writer):
    built = bulletin()
    numbers = {**NUMBERS, **({"writer": writer} if writer else {})}
    with maker() as session:
        assert BulletinRepo(session).save(DAY, bulletin=built, numbers=numbers)
        session.commit()
    with maker() as session:
        row = BulletinRepo(session).get(DAY)
        assert row.day == DAY and row.status == "ready" and row.reason is None
        assert row.payload == built.as_dict() and row.numbers == numbers
        assert row.payload["key_results"][0]["article_ids"] == [17]
        expected = {"bulletin": BULLETIN_STORE_VERSION, "world_change": WORLD_CHANGE_VERSION}
        if writer:
            expected["writer"] = WRITER_VERSION
        assert row.versions == expected
        assert row.generated_at.tzinfo == UTC
        assert row.telegram_message_id is None


def test_save_replaces_the_day(maker):
    with maker() as session:
        repo = BulletinRepo(session)
        repo.save(DAY, bulletin=bulletin(), numbers=NUMBERS)
        loaded = repo.get(DAY)
        first_time = loaded.generated_at
        session.commit()
        changed = bulletin()
        changed.headline = "CHANGED HEADLINE"
        assert repo.save(DAY, bulletin=changed, numbers={"assessed": 2, "digest_articles": 3})
        assert repo.get(DAY) is loaded
        assert loaded.payload == changed.as_dict()
        assert loaded.numbers == {"assessed": 2, "digest_articles": 3}
        session.commit()
        row = repo.get(DAY)
        assert row.payload == changed.as_dict() and row.numbers["assessed"] == 2
        assert row.generated_at >= first_time
        assert session.scalar(select(func.count()).select_from(BulletinRow)) == 1


def test_save_compiles_for_postgres():
    compiled = []

    def execute(statement, **kwargs):
        query = statement.compile(dialect=postgres_dialect())
        compiled.append(str(query))
        assert query.params["day"] == DAY
        return object()

    session = SimpleNamespace(flush=lambda: None, scalar=execute,
                              get_bind=lambda: SimpleNamespace(dialect=postgres_dialect()))
    assert BulletinRepo(session).save(DAY, bulletin=bulletin(), numbers=NUMBERS) is True
    assert len(compiled) == 1
    assert "ON CONFLICT (day) DO UPDATE SET" in compiled[0]
    assert "WHERE bulletins.telegram_message_id IS NULL" in compiled[0]


def test_posted_day_is_never_replaced(maker, caplog):
    with maker() as session:
        repo = BulletinRepo(session)
        repo.save(DAY, bulletin=bulletin(), numbers=NUMBERS)
        row = repo.get(DAY)
        row.telegram_message_id = 2**40
        session.commit()
        before = (row.payload, row.numbers, row.versions, row.generated_at)
        with caplog.at_level(logging.INFO, logger="ai_news"):
            assert repo.save(DAY, bulletin=None, reason="signals_partial", numbers={}) is False
        session.commit()
        session.expire_all()
        row = repo.get(DAY)
        assert (row.payload, row.numbers, row.versions, row.generated_at) == before
        assert row.status == "ready" and row.reason is None
        assert row.telegram_message_id == 2**40
        assert "bulletin_stored" in caplog.text


def test_refused_save_refreshes_the_session(maker):
    with maker() as session:
        BulletinRepo(session).save(DAY, bulletin=bulletin(), numbers=NUMBERS)
        session.commit()
    with maker() as session_a:
        repo = BulletinRepo(session_a)
        loaded = repo.get(DAY)
        old_payload = loaded.payload
        assert loaded.telegram_message_id is None
        with maker() as session_b:
            BulletinRepo(session_b).get(DAY).telegram_message_id = 42
            session_b.commit()
        changed = bulletin()
        changed.headline = "A DIFFERENT HEADLINE"
        assert repo.save(DAY, bulletin=changed, numbers={}) is False
        stored = repo.get(DAY)
        assert stored is loaded
        assert stored.telegram_message_id == 42
        assert stored.payload == old_payload


def test_skipped_day_is_stored_with_reason(maker):
    with maker() as session:
        repo = BulletinRepo(session)
        repo.save(DAY, bulletin=bulletin(), numbers=NUMBERS)
        assert repo.save(DAY, bulletin=None, reason="signals_partial", numbers=NUMBERS)
        session.commit()
        row = repo.get(DAY)
        assert row.status == "skipped" and row.reason == "signals_partial"
        assert row.payload == {} and row.numbers == NUMBERS
        assert row.versions == {"bulletin": BULLETIN_STORE_VERSION,
                                "world_change": WORLD_CHANGE_VERSION}


def test_latest_ready_skips_skipped_days(maker):
    with maker() as session:
        repo = BulletinRepo(session)
        assert repo.latest_ready() is None and repo.get(DAY) is None
        repo.save(DAY, bulletin=bulletin(), numbers=NUMBERS)
        repo.save(DAY + timedelta(days=1), bulletin=None, reason="no_assessments", numbers={})
        repo.save(DAY - timedelta(days=1), bulletin=bulletin(DAY - timedelta(days=1)), numbers={})
        session.commit()
        assert repo.latest_ready().day == DAY


@pytest.fixture
def cli(maker, monkeypatch):
    monkeypatch.setattr(cli_main, "SessionLocal", maker)
    monkeypatch.setattr(cli_main, "create_all", lambda: Base.metadata.create_all(maker.kw["bind"]))
    monkeypatch.setattr(cli_main, "get_settings", lambda: Settings(_env_file=None))

    def no_writer(*args, **kwargs):
        pytest.fail("A build without --write must not open the writer")

    monkeypatch.setattr(cli_main, "open_writer", no_writer)
    return lambda *args: CliRunner().invoke(
        cli_main.app, ["bulletin", "build", "--date", DAY.isoformat(), *args])


def test_cli_build_stores_the_day(maker, cli):
    seed_day(maker)
    result = cli("--json")
    assert result.exit_code == 0, result.output
    printed = json.loads(result.stdout)
    with maker() as session:
        row = BulletinRepo(session).get(DAY)
        assert row.status == "ready" and row.numbers == NUMBERS
        assert row.payload == {k: v for k, v in printed.items() if k not in NUMBERS}
        assert session.scalar(select(func.count()).select_from(BulletinRow)) == 1
    assert "bulletin_stored" in result.stderr
    event = next(json.loads(line) for line in result.stderr.splitlines()
                 if json.loads(line)["message"] == "bulletin_stored")
    assert event["date"] == DAY.isoformat() and event["status"] == "ready"
    assert event["refused"] is False and "replaced" not in event
    repeated = cli("--json")
    assert repeated.exit_code == 0 and repeated.stdout == result.stdout
    assert '"refused": false' in repeated.stderr and '"replaced"' not in repeated.stderr


def test_cli_build_creates_missing_table(maker, cli):
    seed_day(maker)
    BulletinRow.__table__.drop(maker.kw["bind"])
    result = cli()
    assert result.exit_code == 0, result.output
    with maker() as session:
        assert BulletinRepo(session).get(DAY).status == "ready"


def test_cli_build_stores_a_skipped_day(maker, cli):
    seed_day(maker, status="partial")
    result = cli()
    assert result.exit_code == 0 and result.stdout == ""
    with maker() as session:
        row = BulletinRepo(session).get(DAY)
        assert row.status == "skipped" and row.reason == "signals_partial"
        assert row.payload == {} and row.numbers == NUMBERS


@pytest.mark.parametrize("reason", [None, "provider_outage"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_cli_build_stores_written_day(maker, cli, monkeypatch, reason, dry_run):
    seed_day(maker)
    monkeypatch.setattr(cli_main, "get_settings",
                        lambda: Settings(_env_file=None, ds_api_key="fake-key"))
    requests = []
    note = "The work now follows a different process."

    def ask(body):
        requests.append(body)
        if reason:
            return None, reason
        content = {"headline": "AI changes the work", "stories": [{
            "id": "s1", "headline": "Work changes", "site": [note],
            "telegram": [note], "gloss": None}]}
        return {"model": WRITER_MODEL, "choices": [{"finish_reason": "stop",
                "message": {"content": json.dumps(content)}}]}, None

    @contextmanager
    def fake_writer(*args, **kwargs):
        yield SimpleNamespace(ask=ask, cost_usd=lambda: 0.001)

    monkeypatch.setattr(cli_main, "open_writer", fake_writer)
    args = ["--write", "--json", *(["--dry-run"] if dry_run else [])]
    result = cli(*args)
    assert result.exit_code == 0, result.output
    assert len(requests) == 1
    printed = json.loads(result.stdout)
    assert printed["writer"]["cost_usd"] == 0.001
    assert printed["writer"]["reason"] == reason
    story = printed["key_results"][0]
    assert story["text_origin"] == ("title" if reason else "model")
    if not reason:
        assert story["site_note"] == [note] and story["telegram_note"] == [note]
    with maker() as session:
        row = BulletinRepo(session).get(DAY)
        if dry_run:
            assert row is None
        else:
            assert row.payload == {k: v for k, v in printed.items()
                                   if k not in {*NUMBERS, "writer"}}
            assert row.numbers == {**NUMBERS, "writer": printed["writer"]}
            assert row.versions["writer"] == WRITER_VERSION


@pytest.mark.parametrize("status", ["ready", "partial"])
def test_cli_dry_run_stores_nothing(maker, cli, status):
    seed_day(maker, status=status)
    assert cli("--dry-run").exit_code == 0
    with maker() as session:
        assert session.scalar(select(func.count()).select_from(BulletinRow)) == 0


def test_cli_posted_day_exits_zero(maker, cli):
    seed_day(maker)
    with maker() as session:
        repo = BulletinRepo(session)
        repo.save(DAY, bulletin=bulletin(), numbers=NUMBERS)
        row = repo.get(DAY)
        row.telegram_message_id = 42
        before = row.generated_at
        session.commit()
    result = cli()
    assert result.exit_code == 0 and '"refused": true' in result.stderr
    with maker() as session:
        assert BulletinRepo(session).get(DAY).generated_at == before


@pytest.fixture
def client(maker, monkeypatch, tmp_path):
    web = import_module("app.web.app")
    settings = Settings(_env_file=None, database_url="sqlite://",
                        auth_username="operator", auth_password_hash="fake-hash",
                        auth_secret="0123456789abcdef0123456789abcdef")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(web, "get_settings", lambda: settings)
    monkeypatch.setattr(web, "SessionLocal", maker)
    monkeypatch.setattr(web, "create_all", lambda: None)
    with TestClient(web.create_app()) as test_client:
        yield test_client


@pytest.mark.parametrize("skipped", [False, True])
def test_api_bulletin_by_date(maker, client, skipped):
    with maker() as session:
        repo = BulletinRepo(session)
        repo.save(DAY, bulletin=None if skipped else bulletin(),
                  reason="no_assessments" if skipped else None, numbers=NUMBERS)
        row = repo.get(DAY)
        row.telegram_message_id = 123
        generated_at = row.generated_at
        session.commit()
    response = client.get(f"/api/news/bulletin?date={DAY}")
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"day", "status", "reason", "payload", "numbers", "versions",
                         "generated_at"}
    assert data["day"] == DAY.isoformat() and data["numbers"] == NUMBERS
    assert data["versions"]["bulletin"] == BULLETIN_STORE_VERSION
    assert datetime.fromisoformat(data["generated_at"]) == generated_at
    assert data["status"] == ("skipped" if skipped else "ready")
    assert data["payload"] == ({} if skipped else bulletin().as_dict())
    if not skipped:
        assert data["payload"]["key_results"][0]["article_ids"] == [17]
    assert data["reason"] == ("no_assessments" if skipped else None)


def test_api_bulletin_latest_ready(maker, client):
    with maker() as session:
        repo = BulletinRepo(session)
        repo.save(DAY, bulletin=bulletin(), numbers=NUMBERS)
        repo.save(DAY + timedelta(days=1), bulletin=None, reason="signals_partial", numbers={})
        session.commit()
    response = client.get("/api/news/bulletin")
    assert response.status_code == 200 and response.json()["day"] == DAY.isoformat()


def test_api_bulletin_404_and_400(maker, client):
    assert client.get("/api/news/bulletin").status_code == 404
    assert client.get(f"/api/news/bulletin?date={DAY}").status_code == 404
    with maker() as session:
        BulletinRepo(session).save(DAY, bulletin=None, reason="no_assessments", numbers={})
        session.commit()
    assert client.get("/api/news/bulletin").status_code == 404
    for invalid in ("bad", "2026-02-30", "20261030", "2026-W44-5", ""):
        assert client.get("/api/news/bulletin", params={"date": invalid}).status_code == 400


def test_api_bulletin_storage_failure_is_503(client, monkeypatch):
    def unavailable():
        raise SQLAlchemyError("Storage unavailable")

    web = import_module("app.web.app")
    monkeypatch.setattr(web, "SessionLocal", unavailable)
    with TestClient(web.create_app()) as failing_client:
        response = failing_client.get("/api/news/bulletin")
    assert response.status_code == 503
    assert response.json() == {"detail": "News storage is unavailable"}


def test_api_bulletin_is_public(maker, client):
    assert client.get("/api/update/settings").status_code == 401
    with maker() as session:
        BulletinRepo(session).save(DAY, bulletin=bulletin(), numbers=NUMBERS)
        session.commit()
    assert client.get("/api/news/bulletin").status_code == 200
    assert client.get(f"/api/news/bulletin?date={DAY}").status_code == 200
    assert client.head("/api/news/bulletin").status_code != 401
    assert client.post("/api/news/bulletin", json={}).status_code == 401


def _schema(engine):
    inspector = inspect(engine)
    columns = {c["name"]: (str(c["type"]), c["nullable"])
               for c in inspector.get_columns("bulletins")}
    return columns, inspector.get_pk_constraint("bulletins")["constrained_columns"]


def test_bulletins_migration_round_trip(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'bulletins.db'}"
    monkeypatch.setenv("AINEWS_DATABASE_URL", url)
    monkeypatch.setattr(logging.config, "fileConfig", lambda *args, **kwargs: None)
    config = Config("alembic.ini")
    command.upgrade(config, PREVIOUS)
    engine = create_engine(url)
    assert "bulletins" not in inspect(engine).get_table_names()
    command.upgrade(config, HEAD)
    model_engine = create_engine("sqlite://")
    Base.metadata.create_all(model_engine)
    assert _schema(engine) == _schema(model_engine)
    command.downgrade(config, PREVIOUS)
    assert "bulletins" not in inspect(engine).get_table_names()
    Base.metadata.create_all(engine)  # upgrade after create_all must preserve existing data
    with sessionmaker(bind=engine)() as session:
        BulletinRepo(session).save(DAY, bulletin=bulletin(), numbers=NUMBERS)
        session.commit()
    command.upgrade(config, HEAD)
    with sessionmaker(bind=engine)() as session:
        assert BulletinRepo(session).get(DAY).payload == bulletin().as_dict()
    command.downgrade(config, PREVIOUS)
    assert "bulletins" not in inspect(engine).get_table_names()
    engine.dispose()
    model_engine.dispose()
