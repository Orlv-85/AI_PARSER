"""GDELT GKG reader (spec 018 item 5, W2); see src/app/core/world/world.md."""
# ruff: noqa: E501
import io
import json
import tracemalloc
import zipfile
from datetime import date
from pathlib import Path

import httpx
from typer.testing import CliRunner

from app.cli import main as cli_main
from app.core.world.gdelt import (
    DOWNLOAD_TRIES,
    FILES_PER_KIND,
    KIND_GKG,
    KIND_TRANSLATION,
    MAX_MISSING_FILES_OK,
    STATUS_OK,
    STATUS_PARTIAL,
    DayStats,
    day_file_names,
    parse_gkg_line,
    scan_day,
)

DAY = date(2026, 10, 30)
FIRST = "20261030000000.gkg.csv.zip"
SECOND = "20261030001500.gkg.csv.zip"
T_FIRST = "20261030000000.translation.gkg.csv.zip"


def gkg_line(title: str, url: str, *, domain: str = "example.org", lang: str = "",
             themes: str = "EDUCATION", extras: bool = True, columns: int = 27) -> str:
    cols = [""] * columns
    cols[0:5] = ["20261030000000-1", "20261030000000", "1", domain, url][:min(columns, 5)]
    if columns > 7:
        cols[7] = themes
    if columns > 25:
        cols[25] = f"srclc:{lang};eng:GT" if lang else ""
    if columns > 26 and extras:
        cols[26] = f"<PAGE_LINKS>x</PAGE_LINKS><PAGE_TITLE>{title}</PAGE_TITLE>"
    return "\t".join(cols) + "\n"


def zipped(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("x.gkg.csv", text.encode("utf-8"))
    return buffer.getvalue()


def client_for(files: dict[str, bytes], calls: list[str] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        if calls is not None:
            calls.append(name)
        if name in files:
            return httpx.Response(200, content=files[name])
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def run_scan(files: dict[str, bytes], tmp_path: Path, **kwargs: object):
    stats = DayStats()
    with client_for(files) as client:
        found = list(
            scan_day(DAY, client=client, stats=stats, tmp_dir=tmp_path, pause=0,
                     retry_delay=0, sleep=lambda _s: None, **kwargs)  # type: ignore[arg-type]
        )
    return found, stats


def test_day_file_names_cover_96_stamps() -> None:
    names = day_file_names(DAY, KIND_GKG)
    assert len(names) == FILES_PER_KIND == 96
    assert names[0] == "20261030000000.gkg.csv.zip"
    assert names[1] == "20261030001500.gkg.csv.zip"
    assert names[-1] == "20261030234500.gkg.csv.zip"
    assert len(set(names)) == 96
    translated = day_file_names(DAY, KIND_TRANSLATION)
    assert translated[0] == "20261030000000.translation.gkg.csv.zip"
    assert len(translated) == 96


def test_gkg_row_parse_title_and_lang() -> None:
    row = parse_gkg_line(
        gkg_line("Les d&#233;put&#233;s &amp; l&apos;IA", "https://exemple.fr/a", domain="Exemple.fr",
                 lang="fra")
    )
    assert row is not None
    assert row.title == "Les députés & l'IA"
    assert row.url == "https://exemple.fr/a"
    assert row.source_domain == "exemple.fr"
    assert row.language == "fra"
    assert row.themes == "EDUCATION"
    assert row.date == "20261030000000"
    english = parse_gkg_line(gkg_line("AI in class", "https://example.org/b"))
    assert english is not None and english.language == "eng"


def test_gkg_malformed_row_is_counted_and_skipped(tmp_path: Path) -> None:
    text = (
        gkg_line("AI in class", "https://example.org/a")
        + "too\tfew\tcolumns\n"
        + gkg_line("No url", "not-a-url")
        + gkg_line("", "https://example.org/c", extras=False)
        + "\n"
        + gkg_line("Teachers use AI", "https://example.org/d")
    )
    found, stats = run_scan({FIRST: zipped(text)}, tmp_path, kinds=(KIND_GKG,), max_files=1)
    assert [c.url for c in found] == ["https://example.org/a", "https://example.org/d"]
    assert stats.bad_rows == 3
    assert stats.rows == 2


def test_scan_reads_zip_and_plain_files(tmp_path: Path) -> None:
    files = {
        FIRST: zipped(gkg_line("AI in class", "https://example.org/zip")),
        SECOND: gkg_line("Teachers use AI", "https://example.org/plain").encode("utf-8"),
        T_FIRST: zipped(gkg_line("Inteligencia artificial en la escuela", "https://escuela.es/t",
                                 lang="spa")),
    }
    found, stats = run_scan(files, tmp_path, max_files=FILES_PER_KIND + 1)
    by_url = {c.url: c for c in found}
    assert set(by_url) == {"https://example.org/zip", "https://example.org/plain", "https://escuela.es/t"}
    assert by_url["https://escuela.es/t"].translation
    assert by_url["https://escuela.es/t"].language == "spa"
    assert by_url["https://escuela.es/t"].tld_hint == "es"
    assert not by_url["https://example.org/zip"].translation
    assert by_url["https://example.org/zip"].gdelt_file == FIRST
    assert stats.files_read == 3 and stats.kept == 3


def test_missing_file_counts_as_missing(tmp_path: Path) -> None:
    calls: list[str] = []
    stats = DayStats()
    files = {FIRST: zipped(gkg_line("AI in class", "https://example.org/a"))}
    with client_for(files, calls) as client:
        found = list(scan_day(DAY, client=client, stats=stats, kinds=(KIND_GKG,), max_files=2,
                              tmp_dir=tmp_path, pause=0, retry_delay=0, sleep=lambda _s: None))
    assert len(found) == 1
    assert stats.files_read == 1 and stats.files_missing == 1
    assert calls.count(SECOND) == DOWNLOAD_TRIES
    assert not list(tmp_path.iterdir())


def test_download_retries_then_succeeds(tmp_path: Path) -> None:
    attempts: list[int] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(503)
        if len(attempts) == 2:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, content=zipped(gkg_line("AI in class", "https://example.org/a")))

    stats = DayStats()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        found = list(scan_day(DAY, client=client, stats=stats, kinds=(KIND_GKG,), max_files=1,
                              tmp_dir=tmp_path, retry_delay=30, sleep=sleeps.append))
    assert len(found) == 1 and stats.files_missing == 0
    assert len(attempts) == 3
    assert sleeps == [30, 30]


def test_day_status_partial_above_missing_limit(tmp_path: Path) -> None:
    _found, stats = run_scan({}, tmp_path, kinds=(KIND_GKG,), max_files=MAX_MISSING_FILES_OK)
    assert stats.files_missing == MAX_MISSING_FILES_OK and stats.status == STATUS_OK
    _found, stats = run_scan({}, tmp_path, kinds=(KIND_GKG,), max_files=MAX_MISSING_FILES_OK + 1)
    assert stats.status == STATUS_PARTIAL


def test_scan_counts_rows_and_drop_reasons(tmp_path: Path) -> None:
    text = (
        gkg_line("AI in class", "https://example.org/a")
        + gkg_line("Weather today", "https://example.org/b")
        + gkg_line("Nasdaq falls on AI worries", "https://example.org/c")
        + gkg_line("AI teaches kids", "https://econotimes.com/d")
        + gkg_line("AI in school", "https://example.org/e", themes="ECON_STOCKMARKET")
        + gkg_line("Anthropic opens an office", "https://example.org/f")
    )
    found, stats = run_scan(
        {FIRST: zipped(text)}, tmp_path, kinds=(KIND_GKG,), max_files=1,
        own_domains=frozenset({"example.net"}),
    )
    assert [c.url for c in found] == ["https://example.org/a"]
    assert stats.rows == 6 and stats.matched == 5 and stats.kept == 1
    assert dict(stats.drops) == {
        "finance_title": 1, "finance_domain": 1, "finance_theme": 1, "weak_not_ai": 1,
    }


def test_scan_leaves_no_file_on_disk(tmp_path: Path) -> None:
    files = {FIRST: zipped(gkg_line("AI in class", "https://example.org/a") * 3)}
    stats = DayStats()
    with client_for(files) as client:
        iterator = scan_day(DAY, client=client, stats=stats, kinds=(KIND_GKG,), max_files=1,
                            tmp_dir=tmp_path, pause=0)
        first = next(iterator)
        assert first.url == "https://example.org/a"
        iterator.close()  # early stop
    assert not list(tmp_path.rglob("*"))
    found, _stats = run_scan(files, tmp_path, kinds=(KIND_GKG,), max_files=2)
    assert len(found) == 3
    assert not list(tmp_path.rglob("*"))


def test_scan_memory_is_bounded(tmp_path: Path) -> None:
    rows = 40_000
    text = "".join(
        gkg_line(
            ("AI in class %d" if index % 500 == 0 else "Local news item number %d about the town") % index,
            f"https://example.org/story/{index}",
            themes="EDUCATION;TAX_FNCACT;" + "X" * 150,
        )
        for index in range(rows)
    )
    payload = zipped(text)
    assert len(text) > 10_000_000
    stats = DayStats()
    kept = 0
    with client_for({FIRST: payload}) as client:
        tracemalloc.start()
        try:
            for _candidate in scan_day(DAY, client=client, stats=stats, kinds=(KIND_GKG,),
                                       max_files=1, tmp_dir=tmp_path, pause=0):
                kept += 1
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
    assert stats.rows == rows and kept == rows // 500
    assert peak < 1_000_000, peak
    assert not list(tmp_path.rglob("*"))


def test_cli_world_scan_prints_counts(monkeypatch) -> None:
    files = {FIRST: zipped(gkg_line("AI in class", "https://example.org/a"))}
    monkeypatch.setattr(cli_main, "make_client", lambda: client_for(files))
    result = CliRunner().invoke(
        cli_main.app, ["world", "scan", "--date", "2026-10-30", "--max-files", "1"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output.strip().splitlines()[-1])
    assert data["kept"] == 1 and data["files_read"] == 1 and data["files_missing"] == 0
    assert data["status"] == "ok"
    bad = CliRunner().invoke(cli_main.app, ["world", "scan", "--date", "nope"])
    assert bad.exit_code != 0
