"""World collect job (spec 018 item 5, W4); see src/app/core/world/world.md."""
import io
import json
import zipfile
from datetime import UTC, date, datetime

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
    day_file_names,
)
from app.core.world_collect import collect_day, yesterday_utc
from app.storage.models_sql import Base, WorldCandidate, WorldFile
from app.storage.world import FILE_DONE, FILE_MISSING, WorldRepo

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
