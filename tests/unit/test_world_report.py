"""World first days report (spec 018 item 5, W7); see src/app/core/world/world.md."""
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session
from test_world_screen import (  # pylint: disable=import-error
    cand,
    force,
    make_assessor,
    seed,
    usage_handler,
)
from typer.testing import CliRunner

from app.cli import main as cli_main
from app.core.bulletin.world_change import WORLD_CHANGE_VERSION
from app.core.world_report import build_report
from app.storage.models_sql import Base, WorldCandidate, WorldChangeAssessment
from app.storage.provider_journal import PilotJournal
from app.storage.world import (
    STATE_ASSESSED,
    STATE_FAILED,
    STATE_NEW,
    STATE_NO_TEXT,
    STATE_SCREENED_IN,
    STATE_SCREENED_OUT,
    STATE_TEXT_READY,
)

DAY = date(2026, 10, 30)


@pytest.fixture(name="engine")
def engine_fixture(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'world.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session


def answer(item, change="changed", area="Work"):
    return WorldChangeAssessment(
        url_canonical_hash=item.url_canonical_hash, world_change=change,
        world_change_confidence=0.9, area=area, area_confidence=0.8, actor="organisation",
        actor_confidence=0.7, harm_to_people=0.05, question_version=WORLD_CHANGE_VERSION,
        model="jev-m", assessed_at=datetime(2026, 11, 1, tzinfo=UTC))


def test_world_report_counts_the_window(session, tmp_path):
    same = "Same story about AI"
    seed(session, cand(1, title=same, domain="a.org"), cand(2, title=same, domain="b.org"),
         cand(3, title="Out story"), cand(4, title="No text story"), cand(5, title="Ready story"),
         cand(6, title="Failed story"), cand(7, title="New story"),
         cand(8, title="Old day story", day="20261020"))
    force(session, "Out story", STATE_SCREENED_OUT, 0.1)
    for item in session.scalars(select(WorldCandidate).where(WorldCandidate.title == same)):
        item.state, item.screen_confidence = STATE_SCREENED_IN, 0.9
    session.commit()
    force(session, "No text story", STATE_NO_TEXT, 0.8, last_error="text: paywall")
    force(session, "Ready story", STATE_TEXT_READY, 0.8)
    force(session, "Failed story", STATE_FAILED, None, last_error="screen: jev_failed")
    report = build_report(session, DAY, journal_root=tmp_path / "data/world")
    assert report["date"] == "2026-10-30"
    assert report["window"] == ["2026-10-29", "2026-10-30"]
    assert report["candidates"] == 7 and report["clusters"] == 6  # old day is outside the window
    assert report["states"] == {
        STATE_SCREENED_IN: 2, STATE_SCREENED_OUT: 1, STATE_NO_TEXT: 1, STATE_TEXT_READY: 1,
        STATE_FAILED: 1, STATE_NEW: 1}
    assert (report["screened_in"], report["screened_out"]) == (4, 1)
    assert (report["text_ready"], report["no_text"], report["failed"]) == (1, 1, 1)
    assert report["no_text_reasons"] == {"paywall": 1}
    assert (report["assessed"], report["world_change"], report["sample"]) == (0, {}, [])


def test_world_report_world_change_counts_and_sample(session, tmp_path):
    seed(session, *(cand(n, title=f"Assessed story {n:02d}") for n in range(1, 26)),
         cand(30, title="Other version story"))
    for n in range(1, 26):
        item = force(session, f"Assessed story {n:02d}", STATE_ASSESSED, 0.9, priority=float(n))
        session.add(answer(item, change="changed" if n % 5 else "no_change"))
    other = force(session, "Other version story", STATE_ASSESSED, 0.9, priority=99.0)
    stale = answer(other)
    stale.question_version = "world-change-0"
    session.add(stale)
    session.commit()
    report = build_report(session, DAY, journal_root=tmp_path / "data/world")
    assert report["assessed"] == 26
    assert report["world_change"] == {"changed": 20, "no_change": 5}
    sample = report["sample"]
    assert len(sample) == 20
    assert [s["title"] for s in sample[:2]] == ["Assessed story 25", "Assessed story 24"]
    assert "Other version story" not in {s["title"] for s in sample}
    assert sample[0] == {
        "title": "Assessed story 25", "domain": "site25.example.org", "world_change": "no_change",
        "area": "Work", "actor": "organisation", "harm_to_people": 0.05}


def make_journal(root: Path, day: str, tokens: int):
    folder = root / day
    folder.mkdir(parents=True)
    path = folder / "journal-world-stream-1.sqlite3"
    journal = PilotJournal(path, {"v": 1}, {"total": "0.1", "jev": "0.099", "deepseek": "0.001"})
    try:
        with make_assessor(usage_handler(tokens=tokens), journal).client as client:
            journal.call("jev", {"model": "m", "state": day, "questions": {}}, client, "k")
    finally:
        journal.close()
    return path


def test_world_report_cost_reads_journal_read_only(session, tmp_path):
    root = tmp_path / "data/world"
    path = make_journal(root, "2026-10-31", 1000)
    before = path.read_bytes()
    report = build_report(session, DAY, journal_root=root)
    assert report["cost"]["2026-10-30"] is None  # no journal that day: nothing is created
    assert not (root / "2026-10-30").exists()
    day = report["cost"]["2026-10-31"]
    assert day["calls"] == 1
    assert day["committed_usd"] == pytest.approx(0.000042)
    assert day["priced_usd"] == pytest.approx(0.000042)
    assert path.read_bytes() == before


def test_world_report_writes_nothing(engine, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with Session(engine) as session:
        seed(session, cand(1, title="One story"))
        force(session, "One story", STATE_SCREENED_IN, 0.9)
    created = []
    monkeypatch.setattr(cli_main, "create_all", lambda: created.append(1))
    monkeypatch.setattr(cli_main, "SessionLocal", lambda: Session(engine))
    tables = set(inspect(engine).get_table_names())
    before = sorted(path.name for path in tmp_path.iterdir())
    result = CliRunner().invoke(cli_main.app, ["world", "report", "--date", "2026-10-30"])
    assert result.exit_code == 0, result.output
    assert not created and set(inspect(engine).get_table_names()) == tables
    assert sorted(path.name for path in tmp_path.iterdir()) == before


def test_cli_world_report_prints_json(engine, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with Session(engine) as session:
        seed(session, cand(1, title="One story"))
        item = force(session, "One story", STATE_ASSESSED, 0.9)
        session.add(answer(item))
        session.commit()
    make_journal(tmp_path / "data/world", "2026-10-31", 1000)
    monkeypatch.setattr(cli_main, "SessionLocal", lambda: Session(engine))
    result = CliRunner().invoke(cli_main.app, ["world", "report", "--date", "2026-10-30"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert (report["candidates"], report["assessed"]) == (1, 1)
    assert report["cost"]["2026-10-31"]["calls"] == 1
    assert report["sample"][0]["title"] == "One story"
    bad = CliRunner().invoke(cli_main.app, ["world", "report", "--date", "yesterday"])
    assert bad.exit_code != 0
