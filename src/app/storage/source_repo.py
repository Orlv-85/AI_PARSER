import json
import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config.sources import SourceConfig
from app.storage.models_sql import Source


class SourceRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_source(self, source_config: SourceConfig) -> Source:
        source_values = {
            "source_key": source_config.id,
            "name": source_config.name,
            "type": source_config.type,
            "url": str(source_config.url),
            "enabled": source_config.enabled,
            "fetch_interval_minutes": source_config.fetch_interval_minutes,
            "source_weight": source_config.source_weight,
            "created_at": datetime.now(UTC),
        }

        bind = self.session.get_bind()
        dialect_name = bind.dialect.name if bind is not None else ""
        if dialect_name in {"postgresql", "sqlite"}:
            insert_factory = postgresql_insert if dialect_name == "postgresql" else sqlite_insert
            upsert_stmt = insert_factory(Source).values(source_values)
            upsert_stmt = upsert_stmt.on_conflict_do_update(
                index_elements=[Source.source_key],
                set_={
                    "name": upsert_stmt.excluded.name,
                    "type": upsert_stmt.excluded.type,
                    "url": upsert_stmt.excluded.url,
                    "enabled": upsert_stmt.excluded.enabled,
                    "fetch_interval_minutes": upsert_stmt.excluded.fetch_interval_minutes,
                    "source_weight": upsert_stmt.excluded.source_weight,
                },
            )
            self.session.execute(upsert_stmt)
            self.session.flush()
            refresh_stmt: Select[tuple[Source]] = (
                select(Source)
                .where(Source.source_key == source_config.id)
                .execution_options(populate_existing=True)
            )
            return self.session.execute(refresh_stmt).scalar_one()

        stmt: Select[tuple[Source]] = select(Source).where(Source.source_key == source_config.id)
        source = self.session.execute(stmt).scalar_one_or_none()
        if source is None:
            source = Source(source_key=source_config.id)
            self.session.add(source)

        source.name = source_config.name
        source.type = source_config.type
        source.url = str(source_config.url)
        source.enabled = source_config.enabled
        source.fetch_interval_minutes = source_config.fetch_interval_minutes
        source.source_weight = source_config.source_weight

        self.session.flush()
        return source

    def list_enabled_sources(self) -> list[Source]:
        stmt: Select[tuple[Source]] = select(Source).where(Source.enabled.is_(True))
        return list(self.session.scalars(stmt).all())

    def disable_source(self, source_id: int) -> Source:
        source = self.session.get(Source, source_id)
        if source is None:
            raise ValueError(f"source not found: {source_id}")
        source.enabled = False
        self.session.flush()
        return source

    def create_from_candidate(self, candidate: object) -> Source:
        approved_source_id = self._read_int_value(candidate, "approved_source_id")
        if approved_source_id is not None:
            approved_source = self.session.get(Source, approved_source_id)
            if approved_source is not None:
                approved_source.enabled = True
                approved_source.type = self._source_type_for_candidate(
                    candidate,
                    default=approved_source.type,
                )
                approved_source.url = self._read_object_value(candidate, "normalized_url")
                approved_source.name = self._source_name_for_candidate(
                    candidate,
                    default=approved_source.name,
                )
                self.session.flush()
                return approved_source

        source_url = self._read_object_value(candidate, "normalized_url")
        existing_stmt: Select[tuple[Source]] = (
            select(Source).where(Source.url == source_url).limit(1)
        )
        existing = self.session.execute(existing_stmt).scalar_one_or_none()
        if existing is not None:
            existing.enabled = True
            existing.type = self._source_type_for_candidate(
                candidate,
                default=existing.type,
            )
            existing.name = self._source_name_for_candidate(candidate, default=existing.name)
            self.session.flush()
            return existing

        source_key = self._allocate_source_key(candidate)
        source = Source(
            source_key=source_key,
            name=self._source_name_for_candidate(candidate),
            type=self._source_type_for_candidate(candidate, default="html"),
            url=source_url,
            enabled=True,
            fetch_interval_minutes=30,
            source_weight=1.0,
        )
        self.session.add(source)
        self.session.flush()
        return source

    def get_fetch_state(self, *, source_id: int) -> dict[str, object | None]:
        source = self.session.get(Source, source_id)
        if source is None:
            raise ValueError(f"source not found: {source_id}")
        last_checked_at = source.last_checked_at
        if last_checked_at is not None and last_checked_at.tzinfo is None:
            last_checked_at = last_checked_at.replace(tzinfo=UTC)
        return {
            "etag": source.etag,
            "last_modified": source.last_modified,
            "last_checked_at": last_checked_at,
            "last_status_code": source.last_status_code,
        }

    def update_fetch_state(
        self,
        *,
        source_id: int,
        etag: str | None,
        last_modified: str | None,
        last_checked_at: datetime,
        last_status_code: int | None,
    ) -> None:
        source = self.session.get(Source, source_id)
        if source is None:
            raise ValueError(f"source not found: {source_id}")
        source.etag = etag
        source.last_modified = last_modified
        source.last_checked_at = last_checked_at
        source.last_status_code = last_status_code
        self.session.flush()

    @staticmethod
    def _read_object_value(
        candidate: object,
        field_name: str,
        *,
        default: str | None = None,
    ) -> str:
        if isinstance(candidate, dict):
            value = candidate.get(field_name, default)
        else:
            value = getattr(candidate, field_name, default)
        if value is None:
            raise ValueError(f"candidate field is required: {field_name}")
        return str(value)

    def _allocate_source_key(self, candidate: object) -> str:
        base_key = self._source_key_for_candidate(candidate)
        suffix = 1
        candidate_key = base_key
        while self.session.execute(
            select(Source.id).where(Source.source_key == candidate_key).limit(1)
        ).scalar_one_or_none() is not None:
            suffix += 1
            candidate_key = f"{base_key[:59]}-{suffix}"
        return candidate_key

    def _source_key_for_candidate(self, candidate: object) -> str:
        source_url = self._read_object_value(candidate, "normalized_url")
        parts = urlsplit(source_url)
        host = (parts.hostname or "source").lower()
        host_token = re.sub(r"[^a-z0-9]+", "-", host).strip("-")
        path = re.sub(r"[^a-z0-9]+", "-", (parts.path or "").lower()).strip("-")
        key = "-".join(token for token in (host_token, path or None) if token)
        return (key or "source-candidate")[:64]

    def _source_name_for_candidate(self, candidate: object, *, default: str | None = None) -> str:
        raw_input = getattr(candidate, "raw_input", "")
        if isinstance(raw_input, str) and raw_input.startswith("{"):
            try:
                metadata = json.loads(raw_input)
                if isinstance(metadata, dict) and isinstance(metadata.get("name"), str):
                    name = metadata["name"].strip()[:128]
                    if name:
                        return str(name)
            except ValueError:
                pass
        source_url = self._read_object_value(candidate, "normalized_url")
        host = (urlsplit(source_url).hostname or "").lower()
        if host:
            return host
        if default is not None:
            return default
        return source_url

    def _source_type_for_candidate(self, candidate: object, *, default: str) -> str:
        candidate_type = self._read_object_value(
            candidate,
            "candidate_type",
            default=default,
        ).lower()
        if candidate_type == "unknown":
            candidate_type = self._read_object_value(
                candidate,
                "validation_detected_type",
                default=default,
            ).lower()
        return candidate_type or default

    @staticmethod
    def _read_int_value(candidate: object, field_name: str) -> int | None:
        if isinstance(candidate, dict):
            value = candidate.get(field_name)
        else:
            value = getattr(candidate, field_name, None)
        if value is None:
            return None
        return int(value)
