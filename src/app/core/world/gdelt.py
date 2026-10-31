"""GDELT 2.0 GKG reader for the world stream (spec 018, item 5, step W2); no database.

One file at a time is streamed into an anonymous temporary file, read line by line and deleted.
Behavior and tests: src/app/core/world/world.md.
"""
import html
import io
import re
import tempfile
import time
import zipfile
import zlib
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import IO

import httpx

from app.core.world.filter import filter_title, url_host
from app.ingest.fetcher import DEFAULT_USER_AGENT

GDELT_BASE_URL = "https://data.gdeltproject.org/gdeltv2/"
KIND_GKG = "gkg"
KIND_TRANSLATION = "translation"
KINDS = (KIND_GKG, KIND_TRANSLATION)
STAMP_MINUTES = (0, 15, 30, 45)
FILES_PER_KIND = 96
DOWNLOAD_TRIES = 3
RETRY_DELAY_SECONDS = 30.0
PAUSE_SECONDS = 1.0
MAX_MISSING_FILES_OK = 8
STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
LANGUAGE_UNKNOWN = "unknown"
MAX_CONSECUTIVE_MISSING = 12
# GKG 2.1 columns (0-based) used by the reader.
COL_DATE = 1
COL_DOMAIN = 3
COL_URL = 4
COL_THEMES = 7
COL_TRANSLATION = 25
COL_EXTRAS = 26
MIN_COLUMNS = 27
# Country code domains that are used as generic names; not a country hint.
GENERIC_CC_TLDS = frozenset({"ai", "io", "tv", "me", "co", "fm", "ly", "cc", "to", "gg"})

_TITLE_RE = re.compile(r"<PAGE_TITLE>(.*?)</PAGE_TITLE>", re.DOTALL)
_LANG_RE = re.compile(r"srclc:([a-z]{3})")
_ZIP_MAGIC = b"PK\x03\x04"


@dataclass(frozen=True)
class GkgRow:  # pylint: disable=too-many-instance-attributes
    url: str
    title: str
    source_domain: str
    language: str
    themes: str
    date: str


@dataclass(frozen=True)
class Candidate:  # pylint: disable=too-many-instance-attributes
    url: str
    title: str
    source_domain: str
    language: str
    tld_hint: str | None
    published_stamp: str
    gdelt_file: str
    translation: bool
    match: str


@dataclass
class DayStats:  # pylint: disable=too-many-instance-attributes
    files_expected: int = 0
    files_read: int = 0
    files_missing: int = 0
    rows: int = 0
    bad_rows: int = 0
    matched: int = 0
    kept: int = 0
    drops: Counter[str] = field(default_factory=Counter)
    stopped_early: bool = False

    @property
    def status(self) -> str:
        return STATUS_OK if self.files_missing <= MAX_MISSING_FILES_OK else STATUS_PARTIAL

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "files_expected": self.files_expected,
            "stopped_early": self.stopped_early,
            "files_read": self.files_read,
            "files_missing": self.files_missing,
            "rows": self.rows,
            "bad_rows": self.bad_rows,
            "matched": self.matched,
            "kept": self.kept,
            "drops": dict(sorted(self.drops.items())),
        }


def day_file_names(day: date, kind: str = KIND_GKG) -> list[str]:
    """The 96 file names of a UTC day, one per 15 minutes."""
    suffix = ".translation.gkg.csv.zip" if kind == KIND_TRANSLATION else ".gkg.csv.zip"
    if kind not in KINDS:
        raise ValueError(f"unknown GDELT file kind: {kind}")
    return [
        f"{day:%Y%m%d}{hour:02d}{minute:02d}00{suffix}"
        for hour in range(24)
        for minute in STAMP_MINUTES
    ]


def parse_gkg_line(line: str) -> GkgRow | None:
    """Parse one GKG 2.1 line; None for a line without a url or a title."""
    cols = line.rstrip("\r\n").split("\t")
    if len(cols) < MIN_COLUMNS:
        return None
    url = cols[COL_URL].strip()
    found = _TITLE_RE.search(cols[COL_EXTRAS])
    title = html.unescape(found.group(1)).strip() if found else ""
    if not url.startswith(("http://", "https://")) or not title:
        return None
    lang = _LANG_RE.search(cols[COL_TRANSLATION])
    return GkgRow(
        url=url,
        title=title,
        source_domain=cols[COL_DOMAIN].strip().lower(),
        language=lang.group(1) if lang else LANGUAGE_UNKNOWN,
        themes=cols[COL_THEMES],
        date=cols[COL_DATE].strip(),
    )


def tld_hint(host: str) -> str | None:
    last = host.rsplit(".", 1)[-1]
    if len(last) == 2 and last.isalpha() and last not in GENERIC_CC_TLDS:
        return last
    return None


def make_client() -> httpx.Client:
    """Client with the bot user agent; GDELT files are small, the timeout covers a slow stream."""
    return httpx.Client(
        timeout=httpx.Timeout(60.0, connect=15.0),
        headers={"User-Agent": DEFAULT_USER_AGENT},
        follow_redirects=True,
    )


def _download(client: httpx.Client, url: str, target: IO[bytes]) -> bool:
    """Stream one URL into `target`; False on any HTTP or transport failure."""
    try:
        with client.stream("GET", url) as response:
            if response.status_code != 200:
                return False
            for chunk in response.iter_bytes():
                target.write(chunk)
    except httpx.HTTPError:
        return False
    return True


class GkgFile:
    """An open GKG file: iterate its lines, `close()` removes the temporary file.

    `corrupt` is set when the zip stream breaks while it is read.
    """

    def __init__(self, target: IO[bytes]) -> None:
        self.corrupt = False
        self._target = target
        self._archive: zipfile.ZipFile | None = None
        self._text: io.TextIOWrapper | None = None
        try:
            self._open()
        except BaseException:
            self.close()
            raise

    def _open(self) -> None:
        self._target.seek(0)
        head = self._target.read(2048)
        self._target.seek(0)
        if head.startswith(_ZIP_MAGIC):
            self._archive = zipfile.ZipFile(self._target)  # pylint: disable=consider-using-with
            members = self._archive.namelist()
            if not members:
                raise zipfile.BadZipFile("empty archive")
            raw = self._archive.open(members[0])  # pylint: disable=consider-using-with
            self._text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
        elif b"\t" in head and not head.lstrip().startswith(b"<"):
            self._text = io.TextIOWrapper(
                self._target, encoding="utf-8", errors="replace", newline="\n"
            )
        else:
            raise zipfile.BadZipFile("not a GKG file")

    def __iter__(self) -> Iterator[str]:
        if self._text is None:
            return
        try:
            yield from self._text
        except (zipfile.BadZipFile, zlib.error, EOFError, OSError):
            self.corrupt = True

    def close(self) -> None:
        for resource in (self._text, self._archive, self._target):
            if resource is not None:
                resource.close()


def fetch_file(
    client: httpx.Client,
    name: str,
    *,
    tmp_dir: Path | None = None,
    retry_delay: float = RETRY_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    base_url: str = GDELT_BASE_URL,
) -> GkgFile | None:
    """Download a GKG file (zip or plain), check it and return it open, or None when missing.

    A truncated or broken zip, an HTML body or a failed download is a failed attempt. The caller
    closes the result; the temporary file is removed then.
    """
    for attempt in range(DOWNLOAD_TRIES):
        if attempt:
            sleep(retry_delay)
        target = tempfile.TemporaryFile(dir=tmp_dir)  # pylint: disable=consider-using-with
        try:
            if _download(client, base_url + name, target):
                return GkgFile(target)
        except (zipfile.BadZipFile, zlib.error, EOFError):
            pass
        except BaseException:
            target.close()
            raise
        target.close()
    return None


def scan_day(  # pylint: disable=too-many-arguments,too-many-locals
    day: date,
    *,
    client: httpx.Client,
    stats: DayStats,
    own_domains: frozenset[str] = frozenset(),
    kinds: tuple[str, ...] = KINDS,
    max_files: int | None = None,
    tmp_dir: Path | None = None,
    pause: float = PAUSE_SECONDS,
    retry_delay: float = RETRY_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    base_url: str = GDELT_BASE_URL,
) -> Iterator[Candidate]:
    """Read the files of a UTC day one at a time and yield the rows kept by the filter.

    `stats` is filled while the iterator is consumed. Nothing is stored.
    """
    names = [(kind, name) for kind in kinds for name in day_file_names(day, kind)]
    if max_files is not None:
        names = names[:max_files]
    stats.files_expected = len(names)
    consecutive_missing = 0
    for index, (kind, name) in enumerate(names):
        if consecutive_missing >= MAX_CONSECUTIVE_MISSING:
            stats.stopped_early = True
            stats.files_missing += len(names) - index
            return
        if index:
            sleep(pause)
        gfile = fetch_file(
            client, name, tmp_dir=tmp_dir, retry_delay=retry_delay, sleep=sleep, base_url=base_url
        )
        if gfile is None:
            stats.files_missing += 1
            consecutive_missing += 1
            continue
        rows_before, bad_before = stats.rows, stats.bad_rows
        try:
            yield from _scan_lines(gfile, name, kind == KIND_TRANSLATION, stats, own_domains)
        finally:
            gfile.close()
        all_bad = stats.rows == rows_before and stats.bad_rows > bad_before
        if gfile.corrupt or all_bad:
            stats.files_missing += 1
            consecutive_missing += 1
        else:
            stats.files_read += 1
            consecutive_missing = 0


def _scan_lines(
    lines: Iterable[str],
    name: str,
    translation: bool,
    stats: DayStats,
    own_domains: frozenset[str],
) -> Iterator[Candidate]:
    for line in lines:
        if not line.strip():
            continue
        row = parse_gkg_line(line)
        if row is None:
            stats.bad_rows += 1
            continue
        stats.rows += 1
        result = filter_title(
            title=row.title, url=row.url, themes=row.themes, own_domains=own_domains
        )
        if result.match is not None:
            stats.matched += 1
        if not result.kept:
            if result.match is not None and result.reason:
                stats.drops[result.reason] += 1
            continue
        stats.kept += 1
        domain = row.source_domain or url_host(row.url)
        yield Candidate(
            url=row.url,
            title=row.title,
            source_domain=domain,
            language=row.language,
            tld_hint=tld_hint(url_host(row.url)),
            published_stamp=row.date,
            gdelt_file=name,
            translation=translation,
            match=result.match or "",
        )
