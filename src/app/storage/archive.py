"""Storage for the private article archive (spec 016); behavior in core/archive/capture.md."""
import hashlib
import json
from collections.abc import Collection, Sequence
from datetime import UTC, date, datetime

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.orm import Session

from app.storage.models_sql import ArchiveDocument, ArchiveText

STATE_PENDING = "pending"
STATE_ARCHIVED = "archived"
STATE_FAILED = "failed"
STATE_GAVE_UP = "gave_up"
WORLD_SOURCE_KEY = "world"  # marks documents the world stream made; the nightly job skips them


def _not_world() -> ColumnElement[bool]:
    clause: ColumnElement[bool] = (
        ArchiveDocument.source_key.is_(None) | (ArchiveDocument.source_key != WORLD_SOURCE_KEY))
    return clause


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ArchiveRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_document(  # pylint: disable=too-many-arguments
            self, *, url_canonical_hash: str, url: str, url_canonical: str,
            source_key: str | None, host: str, title: str, published_at: datetime | None,
            publication_day: date | None, publication_status: str | None, article_id: int | None,
            first_seen_at: datetime | None) -> ArchiveDocument:
        """Create the document of a canonical hash or refresh its latest metadata; the first
        `first_seen_at` is kept."""
        now = datetime.now(UTC)
        document = self.session.scalar(select(ArchiveDocument).where(
            ArchiveDocument.url_canonical_hash == url_canonical_hash))
        if document is None:
            document = ArchiveDocument(url_canonical_hash=url_canonical_hash,
                                       first_seen_at=first_seen_at or now, state=STATE_PENDING,
                                       attempts=0, created_at=now)
            self.session.add(document)
        document.url = url
        document.url_canonical = url_canonical
        document.source_key = source_key
        document.host = host
        document.title = title
        document.published_at = published_at
        document.publication_day = publication_day
        document.publication_status = publication_status
        document.article_id = article_id
        document.updated_at = now
        self.session.flush()
        return document

    def add_version(  # pylint: disable=too-many-arguments
            self, document: ArchiveDocument, *, text: str, origin: str, extraction_version: str,
            final_url: str | None = None, http_status: int | None = None,
            issues: Sequence[str] = ()) -> ArchiveText | None:
        """Append a text version unless the document already has this exact text."""
        digest = text_sha256(text)
        exists = self.session.scalar(select(ArchiveText.id).where(
            ArchiveText.document_id == document.id, ArchiveText.text_sha256 == digest))
        if exists is not None:
            return None
        now = datetime.now(UTC)
        version = ArchiveText(document_id=document.id, text=text, text_chars=len(text),
                              text_sha256=digest, origin=origin,
                              extraction_version=extraction_version, final_url=final_url,
                              http_status=http_status, issues=json.dumps(list(issues)),
                              captured_at=now)
        self.session.add(version)
        document.state = STATE_ARCHIVED
        document.updated_at = now
        self.session.flush()
        return version

    def purge(self, *, url: str | None = None, source_key: str | None = None,
              host: str | None = None, apply: bool = False) -> tuple[int, int]:
        """Documents and versions selected by exactly one of url, source key or host; deleted only
        with `apply`. Returns (documents, versions)."""
        conditions = [condition for value, condition in (
            (url, (ArchiveDocument.url == url) | (ArchiveDocument.url_canonical == url)),
            (source_key, ArchiveDocument.source_key == source_key),
            (host, ArchiveDocument.host == (host or "").lower().removeprefix("www.")),
        ) if value]
        if len(conditions) != 1:
            raise ValueError("purge needs exactly one of url, source_key, host")
        ids = select(ArchiveDocument.id).where(conditions[0])
        documents = int(self.session.scalar(
            select(func.count()).select_from(ArchiveDocument).where(conditions[0])) or 0)
        versions = int(self.session.scalar(
            select(func.count()).select_from(ArchiveText).where(
                ArchiveText.document_id.in_(ids))) or 0)
        if apply:
            self.session.execute(delete(ArchiveText).where(ArchiveText.document_id.in_(ids)))
            self.session.execute(delete(ArchiveDocument).where(conditions[0]))
        return documents, versions

    def state_counts(self) -> dict[str, int]:
        rows = self.session.execute(select(ArchiveDocument.state, func.count())
                                    .where(_not_world())
                                    .group_by(ArchiveDocument.state)).all()
        return {str(state): int(count) for state, count in rows}

    def version_count(self) -> int:
        return int(self.session.scalar(select(func.count()).select_from(ArchiveText)) or 0)

    def size_bytes(self) -> int:
        """Table size on PostgreSQL; summed text length on other databases."""
        if self.session.get_bind().dialect.name == "postgresql":
            return int(self.session.scalar(select(
                func.pg_total_relation_size("archive_documents")
                + func.pg_total_relation_size("archive_texts"))) or 0)
        return int(self.session.scalar(select(func.coalesce(
            func.sum(func.length(ArchiveText.text)), 0))) or 0)

    def window_states(self, since: datetime | None) -> list[tuple[datetime, str]]:
        """(first_seen_at, state) of documents first seen at or after `since` (all when None)."""
        stmt = select(ArchiveDocument.first_seen_at, ArchiveDocument.state).where(
            _not_world())
        if since is not None:
            stmt = stmt.where(ArchiveDocument.first_seen_at >= since)
        return [(seen, str(state)) for seen, state in self.session.execute(stmt).all()]

    def new_versions_since(self, since: datetime) -> dict[str, int]:
        rows = self.session.execute(select(ArchiveText.origin, func.count())
                                    .where(ArchiveText.captured_at >= since)
                                    .group_by(ArchiveText.origin)).all()
        return {str(origin): int(count) for origin, count in rows}

    def hosts_without_text(self, limit: int) -> list[tuple[str, int]]:
        rows = self.session.execute(
            select(ArchiveDocument.host, func.count().label("n"))
            .where(ArchiveDocument.state != STATE_ARCHIVED, _not_world())
            .group_by(ArchiveDocument.host)
            .order_by(func.count().desc(), ArchiveDocument.host).limit(limit)).all()
        return [(str(host), int(count)) for host, count in rows]

    def due(self, since: datetime | None, now: datetime,
            ids: Collection[int] | None = None) -> list[ArchiveDocument]:
        """Documents without text that may be downloaded now, newest first: pending ones first
        seen since `since` (all when None) and failed ones of any age; only `ids` when given."""
        stmt = (select(ArchiveDocument)
                .where(ArchiveDocument.state.in_((STATE_PENDING, STATE_FAILED)),
                       ArchiveDocument.next_attempt_at.is_(None)
                       | (ArchiveDocument.next_attempt_at <= now))
                .order_by(ArchiveDocument.first_seen_at.desc(), ArchiveDocument.id.desc()))
        if since is not None:
            # Documents already in the retry schedule stay due after the window (FR-010).
            stmt = stmt.where((ArchiveDocument.first_seen_at >= since)
                              | (ArchiveDocument.state == STATE_FAILED))
        if ids is None:
            stmt = stmt.where(_not_world())
        else:
            stmt = stmt.where(ArchiveDocument.id.in_(list(ids)))
        return list(self.session.scalars(stmt))

    def record_attempt(self, document: ArchiveDocument, *, issue: str | None, gave_up: bool,
                       next_attempt_at: datetime | None) -> None:
        """Count one download attempt; a success comes with `add_version` (issue None)."""
        document.attempts = (document.attempts or 0) + 1
        document.last_issue = issue
        document.next_attempt_at = next_attempt_at
        if issue is not None:
            document.state = STATE_GAVE_UP if gave_up else STATE_FAILED
        document.updated_at = datetime.now(UTC)
        self.session.flush()
