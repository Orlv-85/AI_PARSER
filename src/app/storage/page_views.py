"""Anonymous daily route totals; behavior and decisions: src/app/web/pages.md."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.storage.models_sql import PageView

PAGE_VIEWS_DEFAULT_DAYS = 14


class PageViewRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def increment(self, day: date, route: str) -> None:
        """One atomic statement; the caller owns the transaction."""
        dialect = self.session.get_bind().dialect.name
        insert = pg_insert if dialect == "postgresql" else sqlite_insert
        statement = insert(PageView).values(day=day, route=route, count=1)
        self.session.execute(statement.on_conflict_do_update(
            index_elements=[PageView.day, PageView.route], set_={"count": PageView.count + 1}))

    def totals(self, start: date, end: date) -> dict[str, dict[str, int]]:
        rows = self.session.scalars(select(PageView).where(
            PageView.day >= start, PageView.day <= end).order_by(PageView.day, PageView.route))
        result: dict[str, dict[str, int]] = {}
        for row in rows:
            result.setdefault(row.day.isoformat(), {})[row.route] = row.count
        return result
