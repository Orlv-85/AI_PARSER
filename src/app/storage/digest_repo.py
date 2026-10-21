from datetime import date
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.storage.models_sql import NewsDigestGroup, NewsDigestItem, NewsDigestReport


class NewsDigestRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save_digest(
        self,
        *,
        report_date: date,
        groups: list[dict[str, Any]],
    ) -> NewsDigestReport:
        with self.session.begin_nested():
            existing = self.get_digest(report_date=report_date)
            if existing is not None:
                self.session.delete(existing)
                self.session.flush()

            report = NewsDigestReport(report_date=report_date)
            for group_index, group_data in enumerate(groups):
                group = NewsDigestGroup(
                    title=str(group_data["title"]),
                    position=group_index,
                )
                for item_index, item_data in enumerate(group_data.get("items", [])):
                    group.items.append(
                        NewsDigestItem(
                            title=str(item_data["title"]),
                            summary=str(item_data["summary"]),
                            url=str(item_data["url"]),
                            position=item_index,
                        )
                    )
                report.groups.append(group)

            self.session.add(report)
            self.session.flush()
            return report

    def get_digest(self, *, report_date: date) -> NewsDigestReport | None:
        stmt: Select[tuple[NewsDigestReport]] = (
            select(NewsDigestReport)
            .options(
                selectinload(NewsDigestReport.groups).selectinload(NewsDigestGroup.items)
            )
            .where(NewsDigestReport.report_date == report_date)
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()
