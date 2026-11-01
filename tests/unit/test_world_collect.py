"""World collect job (spec 018 item 5, W4); see src/app/core/world/world.md."""
import io
import json
import zipfile
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner

from app.cli import main as cli_main
from app.core.world.gdelt import (
    DOWNLOAD_TRIES,
    MAX_CONSECUTIVE_MISSING,
    MAX_MISSING_FILES_OK,
    Candidate,
    day_file_names,
)
from app.core.world_collect import collect_day, yesterday_utc
from app.storage.models_sql import Base, WorldCandidate, WorldFile
from app.storage.world import FILE_DONE, FILE_MISSING, WORLD_RETENTION_DAYS, WorldRepo

DAY = date(2026, 10, 30)
NAMES = day_file_names(DAY)


def gkg_line(title, url):
    cols = [""] * 27
    cols[0:5] = ["20261030000000-1", "20261030000000", "1", "example.org", url]
    cols[7] = "EDUCATION"
    cols[26] = f"<PAGE_TITLE>{title}</PAGE_TITLE>"
    return "\t".join(cols) + "\n"


def zipped(text):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("x.gkg.csv", text.encode("utf-8"))
    return buffer.getvalue()


def file_for(index, rows=1):
    """A file with `rows` unique AI titles and one other title."""
    text = "".join(gkg_line(f"AI story {index}-{n}", f"https://example.org/{index}/{n}")
                   for n in range(rows))
    return zipped(text + gkg_line("Town fair opens", f"https://example.org/fair/{index}"))


def candidate_for(url):
    return Candidate(url=url, title="AI story old", source_domain="example.org", language="eng",
                     tld_hint=None, published_stamp="20260101000000",
                     gdelt_file="20260101000000.gkg.csv.zip", translation=False, match="strong")


def client_for(files, calls=None, on_request=None):
    def handler(request):
        name = request.url.path.rsplit("/", 1)[-1]
        if calls is not None:
            calls.append(name)
        if on_request is not None:
            on_request(name)
        if name in files:
            return httpx.Response(200, content=files[name])
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture(name="engine")
def engine_fixture(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'world.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def run(engine, files, tmp_path, calls=None, on_request=None, **kwargs):
    with Session(engine) as session, client_for(files, calls, on_request) as client:
        return collect_day(session, DAY, client=client, tmp_dir=tmp_path, pause=0,
                           retry_delay=0, sleep=lambda _s: None, **kwargs)


def test_collect_resumes_without_reprocessing_files(engine, tmp_path):
    files = {NAMES[i]: file_for(i) for i in range(3)}
    first = run(engine, files, tmp_path, max_files=3)
    assert (first.files, first.skipped, first.missing, first.new) == (3, 0, 0, 3)
    calls = []
    second = run(engine, files, tmp_path, calls, max_files=3)
    assert not calls
    assert (second.files, second.skipped, second.new, second.repeats) == (0, 3, 0, 0)
    calls = []
    third = run(engine, {**files, NAMES[3]: file_for(3)}, tmp_path, calls, max_files=4)
    assert calls == [NAMES[3]]
    assert (third.files, third.skipped, third.new) == (1, 3, 1)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(WorldCandidate)) == 4
        assert session.scalar(select(func.count()).select_from(WorldFile)) == 4


def test_collect_commits_per_file(engine, tmp_path):
    seen = {}

    def on_request(name):
        # A second connection sees only what was committed.
        with Session(engine) as other:
            seen[name] = other.scalar(select(func.count()).select_from(WorldCandidate))

    files = {NAMES[i]: file_for(i, rows=2) for i in range(3)}
    run(engine, files, tmp_path, on_request=on_request, max_files=3)
    assert [seen[NAMES[i]] for i in range(3)] == [0, 2, 4]


def test_collect_crash_keeps_finished_files(engine, tmp_path):
    files = {NAMES[0]: file_for(0), NAMES[1]: file_for(1)}

    def explode(name):
        if name == NAMES[1]:
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        run(engine, files, tmp_path, on_request=explode, max_files=2)
    with Session(engine) as session:
        assert WorldRepo(session).done_files(DAY) == {(NAMES[0][:14], "gkg")}


def test_collect_missing_file_is_recorded_and_retried(engine, tmp_path):
    first = run(engine, {NAMES[0]: file_for(0)}, tmp_path, max_files=2)
    assert (first.files, first.missing, first.partial) == (1, 1, False)
    with Session(engine) as session:
        row = session.get(WorldFile, (NAMES[1][:14], "gkg"))
        assert row.state == FILE_MISSING and row.error
    calls = []
    second = run(engine, {NAMES[0]: file_for(0), NAMES[1]: file_for(1)}, tmp_path, calls,
                 max_files=2)
    assert calls == [NAMES[1]]
    assert (second.files, second.skipped, second.missing) == (1, 1, 0)
    with Session(engine) as session:
        assert session.get(WorldFile, (NAMES[1][:14], "gkg")).state == FILE_DONE


def test_collect_stops_after_consecutive_missing(engine, tmp_path):
    calls = []
    summary = run(engine, {}, tmp_path, calls, max_files=30)
    assert summary.missing == 30 and summary.partial
    assert len(calls) == MAX_CONSECUTIVE_MISSING * DOWNLOAD_TRIES
    with Session(engine) as session:
        recorded = session.scalar(select(func.count()).select_from(WorldFile))
    assert recorded == MAX_CONSECUTIVE_MISSING


@pytest.mark.parametrize("missing,partial", [(MAX_MISSING_FILES_OK, False),
                                             (MAX_MISSING_FILES_OK + 1, True)])
def test_collect_partial_day_flag(engine, tmp_path, missing, partial):
    every_name = [(kind, name) for kind in ("gkg", "translation")
                  for name in day_file_names(DAY, kind)]
    lost = {every_name[10 * i + 5][1] for i in range(missing)}
    tiny = zipped(gkg_line("AI story", "https://example.org/x"))
    files = {name: tiny for _kind, name in every_name if name not in lost}
    summary = run(engine, files, tmp_path)
    assert summary.missing == missing
    assert summary.files == 192 - missing
    assert summary.partial is partial


def test_collect_stop_counts_done_files_as_skipped(engine, tmp_path):
    with Session(engine) as session:
        repo = WorldRepo(session)
        for name in NAMES[20:23]:
            repo.record_file(name[:14], "gkg", FILE_DONE)
        session.commit()
    summary = run(engine, {}, tmp_path, max_files=30)
    assert summary.skipped == 3
    assert summary.missing == 27
    assert summary.skipped + summary.missing == 30


def test_collect_prunes_old_rows(engine, tmp_path):
    old = datetime.now(UTC) - timedelta(days=WORLD_RETENTION_DAYS + 1)
    with Session(engine) as session:
        WorldRepo(session).upsert_candidates([candidate_for("https://example.org/old")], now=old)
        session.add(WorldFile(stamp="20260101000000", kind="gkg", state=FILE_DONE, rows=0,
                              matched=0, updated_at=old))
        session.commit()
    summary = run(engine, {NAMES[0]: file_for(0)}, tmp_path, max_files=1)
    assert (summary.pruned_candidates, summary.pruned_files) == (1, 1)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(WorldCandidate)) == 1


def test_collect_summary_counts(engine, tmp_path):
    shared = gkg_line("AI story shared", "https://example.org/shared")
    files = {
        NAMES[0]: zipped(shared + gkg_line("AI story one", "https://example.org/1")
                         + gkg_line("Town fair", "https://example.org/fair")),
        NAMES[1]: zipped(shared + gkg_line("AI story two", "https://example.org/2")),
    }
    summary = run(engine, files, tmp_path, max_files=2)
    assert summary.as_dict() == {
        "day": "2026-10-30", "files": 2, "skipped": 0, "missing": 0, "partial": False,
        "rows": 5, "matched": 4, "kept": 4, "new": 3, "repeats": 1,
        "pruned_candidates": 0, "pruned_files": 0}


def test_yesterday_utc_is_previous_day():
    assert yesterday_utc(datetime(2026, 11, 1, 4, 0, tzinfo=UTC)) == date(2026, 10, 31)


def test_cli_world_collect_prints_summary(engine, monkeypatch):
    files = {NAMES[0]: file_for(0)}
    monkeypatch.setattr(cli_main, "make_client", lambda: client_for(files))
    monkeypatch.setattr(cli_main, "SessionLocal", sessionmaker(engine))
    monkeypatch.setattr(cli_main, "create_all", lambda: None)
    monkeypatch.delenv("AINEWS_WORLD_COLLECT_ENABLED", raising=False)
    result = CliRunner().invoke(
        cli_main.app, ["world", "collect", "--date", "2026-10-30", "--max-files", "1"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output.strip().splitlines()[-1])
    assert (data["files"], data["new"], data["kept"], data["partial"]) == (1, 1, 1, False)
    assert "world_collect_finished" in result.output
    bad = CliRunner().invoke(cli_main.app, ["world", "collect", "--date", "nope"])
    assert bad.exit_code != 0


def cli_collect(engine, monkeypatch, files, calls=None, args=()):
    monkeypatch.setattr(cli_main, "make_client", lambda: client_for(files, calls))
    monkeypatch.setattr(cli_main, "SessionLocal", sessionmaker(engine))
    monkeypatch.setattr(cli_main, "create_all", lambda: None)
    monkeypatch.setattr(cli_main, "yesterday_utc", lambda: DAY)
    monkeypatch.setattr("app.core.world_collect.PAUSE_SECONDS", 0)
    result = CliRunner().invoke(cli_main.app, ["world", "collect", "--max-files", "1", *args])
    assert result.exit_code == 0, result.output
    return [json.loads(line) for line in result.output.splitlines()
            if line.startswith('{"day"')]


def two_day_files():
    before = day_file_names(DAY - timedelta(days=1))
    return {NAMES[0]: file_for(0), before[0]: file_for(1)}


def test_collect_default_runs_yesterday_and_day_before(engine, monkeypatch):
    lines = cli_collect(engine, monkeypatch, two_day_files())
    assert [line["day"] for line in lines] == ["2026-10-30", "2026-10-29"]
    assert [line["new"] for line in lines] == [1, 1]
    only = cli_collect(engine, monkeypatch, two_day_files(), args=["--date", "2026-10-30"])
    assert [line["day"] for line in only] == ["2026-10-30"]


def test_collect_catch_up_recovers_missed_night(engine, monkeypatch):
    # Yesterday is already done; the night of the day before was missed and is collected now.
    with Session(engine) as session:
        WorldRepo(session).record_file(NAMES[0][:14], "gkg", FILE_DONE)
        session.commit()
    lines = cli_collect(engine, monkeypatch, two_day_files())
    assert (lines[0]["files"], lines[0]["skipped"]) == (0, 1)
    assert (lines[1]["day"], lines[1]["files"], lines[1]["new"]) == ("2026-10-29", 1, 1)


def test_collect_complete_day_downloads_nothing(engine, monkeypatch):
    cli_collect(engine, monkeypatch, two_day_files())
    calls = []
    lines = cli_collect(engine, monkeypatch, two_day_files(), calls)
    assert not calls
    assert [(line["files"], line["skipped"]) for line in lines] == [(0, 1), (0, 1)]
