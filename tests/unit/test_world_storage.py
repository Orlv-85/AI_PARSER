import ast
import logging.config
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session

from app.core.canonicalize import canonical_url_hash
from app.core.world.gdelt import Candidate
from app.storage.archive import ArchiveRepo
from app.storage.models_sql import (
    ArchiveDocument,
    Article,
    Base,
    WorldCandidate,
    WorldChangeAssessment,
    WorldFile,
)
from app.storage.world import (
    FILE_DONE,
    FILE_MISSING,
    HASH_CHUNK,
    STATE_ASSESSED,
    STATE_FAILED,
    STATE_NEW,
    STATE_NO_TEXT,
    STATE_SCREENED_IN,
    STATE_SCREENED_OUT,
    STATE_TEXT_READY,
    TRANSITIONS,
    WORLD_RETENTION_DAYS,
    InvalidTransition,
    WorldRepo,
    cluster_key,
)

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
NOW = datetime(2026, 11, 1, 4, 0, tzinfo=UTC)


def candidate(url="https://example.org/a?utm_source=x", title="AI tutors reach schools", **kw):
    fields = {"url": url, "title": title, "source_domain": "example.org", "language": "eng",
              "tld_hint": None, "published_stamp": "20261031001500",
              "gdelt_file": "20261031001500.gkg.csv.zip", "translation": False,
              "match": "strong"}
    fields.update(kw)
    return Candidate(**fields)


@pytest.fixture(name="session")
def session_fixture(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'world.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_world_candidate_dedup_by_canonical_hash(session):
    repo = WorldRepo(session)
    batch = [candidate("https://example.org/a?utm_source=x"),
             candidate("https://EXAMPLE.org/a/"),
             candidate("https://example.org/b", title="Other story")]
    assert repo.upsert_candidates(batch, now=NOW) == (2, 1)
    assert repo.upsert_candidates([candidate("https://example.org/a?fbclid=1")], now=NOW) == (0, 1)
    rows = session.scalars(select(WorldCandidate)).all()
    assert len(rows) == 2
    assert {row.url_canonical_hash for row in rows} == {
        canonical_url_hash("https://example.org/a"), canonical_url_hash("https://example.org/b")}


def test_world_upsert_repeat_keeps_first_seen_and_state(session):
    repo = WorldRepo(session)
    repo.upsert_candidates([candidate()], now=NOW)
    row = repo.candidates_in_state(STATE_NEW)[0]
    repo.transition(row, STATE_SCREENED_IN, screen_confidence=0.9)
    repo.upsert_candidates([candidate(title="Changed title")], now=NOW + timedelta(days=1))
    row = session.scalars(select(WorldCandidate)).one()
    assert row.first_seen_at == NOW
    assert row.state == STATE_SCREENED_IN
    assert row.screen_confidence == 0.9
    assert row.title == "AI tutors reach schools"


def test_world_cluster_key_normalizes_title():
    assert cluster_key("  AI: Tutors -- reach   Schools! ") == "ai tutors reach schools"
    assert cluster_key("A" * 100) == "a" * 60
    assert cluster_key("Ai Tutors") == cluster_key("AI tutors")


def test_world_candidate_fields_from_gdelt(session):
    repo = WorldRepo(session)
    repo.upsert_candidates([
        candidate("https://example.de/a", title="T" * 700, tld_hint="de", language="deu",
                  match="weak"),
        candidate("https://example.org/b", published_stamp="bad")], now=NOW)
    first = repo.get(canonical_url_hash("https://example.de/a"))
    assert first.published_at == datetime(2026, 10, 31, 0, 15, tzinfo=UTC)
    assert (first.country_hint, first.language, first.match_kind) == ("de", "deu", "weak")
    assert len(first.title) == 512
    assert (first.state, first.attempts, first.last_error) == (STATE_NEW, 0, None)
    assert repo.get(canonical_url_hash("https://example.org/b")).published_at is None


def test_world_transitions_follow_allowed_table(session):
    repo = WorldRepo(session)
    states = set(TRANSITIONS)
    for source, allowed in TRANSITIONS.items():
        for target in states:
            repo.upsert_candidates([candidate(f"https://example.org/{source}-{target}")], now=NOW)
            row = repo.get(canonical_url_hash(f"https://example.org/{source}-{target}"))
            row.state = source
            if target in allowed:
                assert repo.transition(row, target).state == target
            else:
                with pytest.raises(InvalidTransition):
                    repo.transition(row, target)
                assert row.state == source
    assert TRANSITIONS[STATE_SCREENED_OUT] == TRANSITIONS[STATE_NO_TEXT] == \
        TRANSITIONS[STATE_ASSESSED] == frozenset()
    repo.upsert_candidates([candidate("https://example.org/path")], now=NOW)
    row = repo.candidates_in_state(STATE_NEW)[-1]
    for state in (STATE_SCREENED_IN, STATE_TEXT_READY, STATE_ASSESSED):
        repo.transition(row, state)
    assert row in repo.candidates_in_state(STATE_ASSESSED)
    assert row not in repo.candidates_in_state(STATE_NEW)


def test_world_failed_counts_attempts_and_retries(session):
    repo = WorldRepo(session)
    repo.upsert_candidates([candidate()], now=NOW)
    row = repo.candidates_in_state(STATE_NEW)[0]
    repo.transition(row, STATE_FAILED, error="e" * 400)
    assert (row.attempts, len(row.last_error)) == (1, 255)
    repo.transition(row, STATE_NEW)
    assert (row.attempts, row.last_error) == (1, None)
    repo.transition(row, STATE_FAILED, error="again")
    assert (row.attempts, row.last_error) == (2, "again")
    repo.transition(row, STATE_SCREENED_IN, priority=2.5)
    assert row.priority == 2.5


def test_world_no_text_keeps_reason(session):
    repo = WorldRepo(session)
    repo.upsert_candidates([candidate()], now=NOW)
    row = repo.candidates_in_state(STATE_NEW)[0]
    repo.transition(row, STATE_SCREENED_IN, screen_confidence=0.9)
    repo.transition(row, STATE_NO_TEXT, error="text: paywall")
    assert (row.state, row.attempts, row.last_error) == (STATE_NO_TEXT, 0, "text: paywall")


def test_world_file_states_record_and_skip_done(session):
    repo = WorldRepo(session)
    repo.record_file("20261031000000", "gkg", FILE_DONE, rows=10, matched=3)
    repo.record_file("20261031000000", "translation", FILE_MISSING, error="HTTP 404")
    repo.record_file("20261031001500", "gkg", FILE_DONE, rows=5)
    repo.record_file("20261030234500", "gkg", FILE_DONE)
    assert repo.done_files(date(2026, 10, 31)) == {
        ("20261031000000", "gkg"), ("20261031001500", "gkg")}
    repo.record_file("20261031000000", "translation", FILE_DONE, rows=7)
    again = repo.record_file("20261031000000", "gkg", FILE_MISSING, error="broken zip")
    assert (again.rows, again.error) == (0, "broken zip")
    assert repo.done_files(date(2026, 10, 31)) == {
        ("20261031000000", "translation"), ("20261031001500", "gkg")}
    assert session.scalar(select(func.count()).select_from(WorldFile)) == 4
    with pytest.raises(ValueError):
        repo.record_file("20261031003000", "gkg", "weird")


def test_world_prune_keeps_archive(session):
    repo = WorldRepo(session)
    old = NOW - timedelta(days=WORLD_RETENTION_DAYS + 1)
    repo.upsert_candidates([candidate("https://example.org/old")], now=old)
    repo.upsert_candidates([candidate("https://example.org/new")], now=NOW - timedelta(days=1))
    repo.record_file("20260930000000", "gkg", FILE_DONE)
    session.get(WorldFile, ("20260930000000", "gkg")).updated_at = old
    repo.record_file("20261031000000", "gkg", FILE_DONE)
    url = "https://example.org/old"
    ArchiveRepo(session).upsert_document(
        url_canonical_hash=canonical_url_hash(url), url=url, url_canonical=url, source_key=None,
        host="example.org", title="t", published_at=None, publication_day=None,
        publication_status=None, article_id=None, first_seen_at=old)
    session.add(WorldChangeAssessment(
        url_canonical_hash=canonical_url_hash(url), world_change="none",
        world_change_confidence=0.5, area="Work", area_confidence=0.5, actor="people",
        actor_confidence=0.5, harm_to_people=0.0, question_version="v", model="m"))
    session.flush()
    assert repo.prune(now=NOW) == (1, 1)
    assert [row.url for row in session.scalars(select(WorldCandidate))] == [
        "https://example.org/new"]
    assert session.scalar(select(func.count()).select_from(WorldFile)) == 1
    assert session.scalar(select(func.count()).select_from(ArchiveDocument)) == 1
    assert session.scalar(select(func.count()).select_from(WorldChangeAssessment)) == 1


def test_world_candidate_cuts_long_url_title_and_error(session):
    repo = WorldRepo(session)
    long_url = "https://example.org/" + "a" * 3000
    repo.upsert_candidates([candidate(url=long_url, title="t" * 700)], now=NOW)
    row = session.scalars(select(WorldCandidate)).one()
    assert len(row.url) == 2048
    assert len(row.title) == 512
    assert row.url_canonical_hash == canonical_url_hash(long_url)
    repo.transition(row, STATE_FAILED, error="e" * 400)
    assert len(row.last_error) == 255
    repo.record_file("20261031000000", "gkg", FILE_MISSING, error="x" * 400)
    assert len(session.get(WorldFile, ("20261031000000", "gkg")).error) == 255


def test_world_upsert_batches_over_hash_chunk(session):
    repo = WorldRepo(session)
    total = HASH_CHUNK * 2 + 7
    batch = [candidate(url=f"https://example.org/story-{i}") for i in range(total)]
    assert repo.upsert_candidates(batch, now=NOW) == (total, 0)
    assert repo.upsert_candidates(batch, now=NOW + timedelta(hours=1)) == (0, total)
    assert session.scalar(select(func.count()).select_from(WorldCandidate)) == total


def test_world_upsert_empty_batch(session):
    assert WorldRepo(session).upsert_candidates([], now=NOW) == (0, 0)
    assert session.scalar(select(func.count()).select_from(WorldCandidate)) == 0


def test_world_prune_cutoff_boundary(session):
    repo = WorldRepo(session)
    edge = NOW - timedelta(days=WORLD_RETENTION_DAYS)
    repo.upsert_candidates([candidate(url="https://example.org/edge")], now=edge)
    repo.upsert_candidates([candidate(url="https://example.org/old")],
                           now=edge - timedelta(seconds=1))
    assert repo.prune(now=NOW) == (1, 0)
    assert [row.url for row in session.scalars(select(WorldCandidate))] == [
        "https://example.org/edge"]


def test_world_transition_unknown_stored_state_is_invalid(session):
    repo = WorldRepo(session)
    repo.upsert_candidates([candidate()], now=NOW)
    row = session.scalars(select(WorldCandidate)).one()
    row.state = "corrupt"
    with pytest.raises(InvalidTransition):
        repo.transition(row, STATE_NEW)
    assert row.state == "corrupt"


def test_world_storage_never_touches_articles(session):
    repo = WorldRepo(session)
    repo.upsert_candidates([candidate()], now=NOW)
    repo.record_file("20261031000000", "gkg", FILE_DONE)
    repo.prune(now=NOW + timedelta(days=90))
    assert session.scalar(select(func.count()).select_from(Article)) == 0
    tree = ast.parse((SRC / "storage" / "world.py").read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
              for alias in node.names}
    assert not names & {"Article", "NewsDigestReport", "NewsDigestItem", "NewsDigestGroup"}


def _imports(path, root=SRC.parent):
    """Absolute names imported by a file; relative imports are resolved against `root`."""
    parts = list(path.relative_to(root).with_suffix("").parts)
    package = parts[:-1]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = package[:len(package) - node.level + 1] if node.level else []
            module = ".".join([*base, *([node.module] if node.module else [])])
            if module:
                yield module
                yield from (f"{module}.{alias.name}" for alias in node.names)


def test_world_tables_not_read_by_digest():
    allowed = {SRC / "storage" / "world.py", SRC / "storage" / "models_sql.py"}
    allowed |= set((SRC / "core" / "world").glob("*.py"))
    allowed.add(SRC / "cli" / "main.py")
    allowed.add(SRC / "core" / "world_collect.py")
    allowed.add(SRC / "core" / "world_screen.py")
    allowed.add(SRC / "core" / "world_text.py")
    allowed.add(SRC / "core" / "world_report.py")
    allowed.add(SRC / "storage" / "bulletin_input.py")  # the bulletin is the one reader (FR-016)
    found = []
    for path in SRC.rglob("*.py"):
        if path in allowed:
            continue
        if any(name == "app.storage.world" for name in _imports(path)):
            found.append(path.name)
        if re.search(r"\bWorld(Candidate|File)\b", path.read_text(encoding="utf-8")):
            found.append(path.name)
    assert not found
    for path in (SRC / "web").rglob("*.py"):
        assert not any(name.startswith(("app.storage.world.", "app.core.world"))
                       for name in _imports(path)), path


def test_import_scan_resolves_relative_imports(tmp_path):
    module = tmp_path / "app" / "core" / "world" / "x.py"
    module.parent.mkdir(parents=True)
    module.write_text("from ...storage import world\nfrom . import gdelt\nimport os\n")
    names = set(_imports(module, root=tmp_path))
    assert "app.storage.world" in names
    assert "app.core.world.gdelt" in names
    assert "os" in names


def test_world_core_never_imports_storage():
    found = [path.name for path in (SRC / "core" / "world").glob("*.py")
             if any(name == "app.storage" or name.startswith("app.storage.")
                    for name in _imports(path))]
    assert not found


WORLD_TABLES = {"world_candidates", "world_files"}
HEAD = "c9f3a7e15b28"
PREVIOUS = "b8e2d4f61a07"


def _schema(url, table):
    engine = create_engine(url)
    inspector = inspect(engine)
    columns = {c["name"]: (str(c["type"]), c["nullable"]) for c in inspector.get_columns(table)}
    indexes = {(i["name"], tuple(i["column_names"]), bool(i["unique"]))
               for i in inspector.get_indexes(table)}
    uniques = {tuple(u["column_names"]) for u in inspector.get_unique_constraints(table)}
    primary = tuple(inspector.get_pk_constraint(table)["constrained_columns"])
    fks = inspector.get_foreign_keys(table)
    engine.dispose()
    return columns, indexes, uniques, primary, fks


def test_world_migration_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "migrated.db"
    monkeypatch.setenv("AINEWS_DATABASE_URL", f"sqlite:///{path}")
    monkeypatch.setattr(logging.config, "fileConfig", lambda *args, **kwargs: None)
    config = Config("alembic.ini")
    command.upgrade(config, PREVIOUS)
    engine = create_engine(f"sqlite:///{path}")
    assert not WORLD_TABLES & set(inspect(engine).get_table_names())
    command.upgrade(config, "head")
    created = tmp_path / "created.db"
    model_engine = create_engine(f"sqlite:///{created}")
    Base.metadata.create_all(model_engine)
    model_engine.dispose()
    for table in WORLD_TABLES:
        assert _schema(f"sqlite:///{path}", table) == _schema(f"sqlite:///{created}", table), table
    assert _schema(f"sqlite:///{path}", "world_files")[3] == ("stamp", "kind")
    assert _schema(f"sqlite:///{path}", "world_candidates")[4] == []
    with Session(engine) as session:
        WorldRepo(session).upsert_candidates([candidate()], now=NOW)
        session.commit()
    command.upgrade(config, "head")  # idempotent
    command.downgrade(config, PREVIOUS)
    assert not WORLD_TABLES & set(inspect(engine).get_table_names())
    command.upgrade(config, "head")
    assert WORLD_TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()
