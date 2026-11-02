"""Bulletin persistence; behavior and decisions: src/app/storage/bulletin_store.md."""
import logging
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.bulletin.builder import Bulletin
from app.core.bulletin.world_change import WORLD_CHANGE_VERSION
from app.core.bulletin.writer import WRITER_VERSION
from app.observability.logging import log_event
from app.storage.models_sql import BulletinRow

BULLETIN_STORE_VERSION = "bulletin-store-1"
_LOGGER = logging.getLogger("ai_news")


class BulletinRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, day: date) -> BulletinRow | None:
        return self.session.scalar(select(BulletinRow).where(BulletinRow.day == day))

    def latest_ready(self) -> BulletinRow | None:
        return self.session.scalar(select(BulletinRow).where(BulletinRow.status == "ready")
                                   .order_by(BulletinRow.day.desc()).limit(1))

    def save(self, day: date, *, bulletin: Bulletin | None, numbers: dict[str, Any],
             reason: str | None = None) -> bool:
        """Upsert an unposted day. The caller commits; False means a posted row refused it."""
        self.session.flush()
        versions = {"bulletin": BULLETIN_STORE_VERSION, "world_change": WORLD_CHANGE_VERSION}
        if "writer" in numbers:
            versions["writer"] = WRITER_VERSION
        values = {
            "status": "ready" if bulletin is not None else "skipped",
            "reason": None if bulletin is not None else reason,
            "payload": bulletin.as_dict() if bulletin is not None else {},
            "numbers": numbers, "versions": versions, "generated_at": datetime.now(UTC)}
        dialect = self.session.get_bind().dialect.name
        insert = pg_insert if dialect == "postgresql" else sqlite_insert
        statement = insert(BulletinRow).values(day=day, **values)
        upsert = statement.on_conflict_do_update(
            index_elements=[BulletinRow.day], set_=values,
            where=BulletinRow.telegram_message_id.is_(None)).returning(BulletinRow)
        stored = self.session.scalar(upsert, execution_options={"populate_existing": True})
        if stored is None:
            self.session.scalar(select(BulletinRow).where(BulletinRow.day == day),
                                execution_options={"populate_existing": True})
        log_event(_LOGGER, event="bulletin_stored", date=day.isoformat(), status=values["status"],
                  refused=stored is None)
        return stored is not None
