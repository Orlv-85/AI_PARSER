"""Storage for the world news stream (spec 018, item 5); behavior in core/world/world.md.

Never reads or writes articles or digest tables (FR-016).
"""
import re
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.canonicalize import canonical_url_hash
from app.core.world.gdelt import Candidate
from app.storage.models_sql import WorldCandidate, WorldFile

WORLD_RETENTION_DAYS = 30
CLUSTER_KEY_CHARS = 60
HASH_CHUNK = 500

STATE_NEW = "new"
STATE_SCREENED_OUT = "screened_out"
STATE_SCREENED_IN = "screened_in"
STATE_TEXT_READY = "text_ready"
STATE_NO_TEXT = "no_text"
STATE_ASSESSED = "assessed"
STATE_FAILED = "failed"
TRANSITIONS: dict[str, frozenset[str]] = {
    STATE_NEW: frozenset({STATE_SCREENED_OUT, STATE_SCREENED_IN, STATE_FAILED}),
    STATE_SCREENED_IN: frozenset({STATE_TEXT_READY, STATE_NO_TEXT, STATE_FAILED}),
    STATE_TEXT_READY: frozenset({STATE_ASSESSED, STATE_FAILED}),
    STATE_FAILED: frozenset({STATE_NEW, STATE_SCREENED_IN, STATE_TEXT_READY}),
    STATE_SCREENED_OUT: frozenset(),
    STATE_NO_TEXT: frozenset(),
    STATE_ASSESSED: frozenset(),
}
FILE_DONE = "done"
FILE_MISSING = "missing"
FILE_STATES = frozenset({FILE_DONE, FILE_MISSING})

_NON_WORD_RE = re.compile(r"[\W_]+")


class InvalidTransition(ValueError):
    """A candidate state change that is not in TRANSITIONS."""


def cluster_key(title: str) -> str:
    """Story key: first characters of the title, lower case, runs of non-word chars as one space."""
    return _NON_WORD_RE.sub(" ", title.casefold()).strip()[:CLUSTER_KEY_CHARS]


def _stamp_time(stamp: str) -> datetime | None:
    try:
        return datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


class WorldRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_candidates(self, candidates: Iterable[Candidate],
                          *, now: datetime | None = None) -> tuple[int, int]:
        """Insert candidates with a new canonical hash in state `new`; a known hash is left as it
        is. Returns (new, repeats)."""
        now = now or datetime.now(UTC)
        by_hash: dict[str, Candidate] = {}
        repeats = 0
        for candidate in candidates:
            digest = canonical_url_hash(candidate.url)
            if digest in by_hash:
                repeats += 1
            else:
                by_hash[digest] = candidate
        known: set[str] = set()
        hashes = list(by_hash)
        for start in range(0, len(hashes), HASH_CHUNK):
            known.update(self.session.scalars(select(WorldCandidate.url_canonical_hash).where(
                WorldCandidate.url_canonical_hash.in_(hashes[start:start + HASH_CHUNK]))))
        created = 0
        for digest, candidate in by_hash.items():
            if digest in known:
                repeats += 1
                continue
            self.session.add(WorldCandidate(
                url_canonical_hash=digest, url=candidate.url[:2048], title=candidate.title[:512],
                source_domain=candidate.source_domain[:255], language=candidate.language[:16],
                country_hint=candidate.tld_hint,
                published_at=_stamp_time(candidate.published_stamp), first_seen_at=now,
                gdelt_file=candidate.gdelt_file[:64],
                match_kind=candidate.match, cluster_key=cluster_key(candidate.title),
                state=STATE_NEW, attempts=0, created_at=now, updated_at=now))
            created += 1
        self.session.flush()
        return created, repeats

    def get(self, url_hash: str) -> WorldCandidate | None:
        return self.session.scalar(select(WorldCandidate).where(
            WorldCandidate.url_canonical_hash == url_hash))

    def candidates_in_state(self, state: str, *, limit: int | None = None) -> list[WorldCandidate]:
        """Candidates of a state, oldest first."""
        query = select(WorldCandidate).where(WorldCandidate.state == state).order_by(
            WorldCandidate.first_seen_at, WorldCandidate.id)
        if limit is not None:
            query = query.limit(limit)
        return list(self.session.scalars(query))

    def transition(self, candidate: WorldCandidate, state: str, *, error: str | None = None,
                   screen_confidence: float | None = None,
                   priority: float | None = None) -> WorldCandidate:
        """Move a candidate to `state` if TRANSITIONS allows it; `failed` counts an attempt."""
        if state not in TRANSITIONS.get(candidate.state, frozenset()):
            raise InvalidTransition(f"{candidate.state} -> {state}")
        candidate.state = state
        if state == STATE_FAILED:
            candidate.attempts += 1
            candidate.last_error = (error or "")[:255] or None
        else:
            candidate.last_error = None
        if screen_confidence is not None:
            candidate.screen_confidence = screen_confidence
        if priority is not None:
            candidate.priority = priority
        candidate.updated_at = datetime.now(UTC)
        self.session.flush()
        return candidate

    def record_file(self, stamp: str, kind: str, state: str, *, rows: int = 0, matched: int = 0,
                    error: str | None = None) -> WorldFile:
        """Store the state of one GDELT file, replacing an earlier row of the same file."""
        if state not in FILE_STATES:
            raise ValueError(f"unknown file state: {state}")
        row = self.session.get(WorldFile, (stamp, kind))
        if row is None:
            row = WorldFile(stamp=stamp, kind=kind)
            self.session.add(row)
        row.state = state
        row.rows = rows
        row.matched = matched
        row.error = (error or "")[:255] or None
        row.updated_at = datetime.now(UTC)
        self.session.flush()
        return row

    def done_files(self, day: date) -> set[tuple[str, str]]:
        """(stamp, kind) of the files of a UTC day that are done."""
        rows = self.session.execute(select(WorldFile.stamp, WorldFile.kind).where(
            WorldFile.state == FILE_DONE, WorldFile.stamp.like(f"{day:%Y%m%d}%")))
        return {(row[0], row[1]) for row in rows}

    def prune(self, *, now: datetime | None = None,
              days: int = WORLD_RETENTION_DAYS) -> tuple[int, int]:
        """Delete candidates first seen and file rows updated before the retention limit.
        Returns (candidates, files)."""
        cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
        candidates = self.session.execute(delete(WorldCandidate).where(
            WorldCandidate.first_seen_at < cutoff))
        files = self.session.execute(delete(WorldFile).where(WorldFile.updated_at < cutoff))
        self.session.flush()
        return (int(getattr(candidates, "rowcount", 0) or 0),
                int(getattr(files, "rowcount", 0) or 0))
