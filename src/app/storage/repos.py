import logging
import re
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, cast

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.storage.models_sql import (
    Article,
    WeeklyAnalyticsStoredItem,
    WeeklyAnalyticsStoredReport,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class WeeklyAnalyticsItem:
    title: str
    summary: str
    url: str
    details: dict[str, Any] = dataclass_field(default_factory=dict)


@dataclass(slots=True)
class WeeklyAnalyticsReport:  # pylint: disable=too-many-instance-attributes
    report_date: date
    date_from: date
    date_to: date
    summary: str
    new: list[WeeklyAnalyticsItem]
    trending_up: list[WeeklyAnalyticsItem]
    trending_down: list[WeeklyAnalyticsItem]
    metadata: dict[str, Any] = dataclass_field(default_factory=dict)


@dataclass(slots=True)
class WeeklyAnalyticsReportIndexEntry:
    report_date: date
    date_from: date
    date_to: date
    summary: str
    created_at: datetime


class WeeklyAnalyticsRepo:
    _TITLE_MAX_LEN = 512
    _URL_MAX_LEN = 2048
    _TOPIC_STOPWORDS = frozenset(
        {
            "a",
            "an",
            "and",
            "are",
            "as",
            "at",
            "by",
            "for",
            "from",
            "how",
            "in",
            "into",
            "is",
            "new",
            "of",
            "on",
            "or",
            "that",
            "the",
            "this",
            "to",
            "what",
            "week",
            "weeks",
            "with",
            "story",
            "stories",
            "recent",
            "prior",
            "trending",
            "trend",
            "latest",
            "up",
            "down",
        }
    )
    _TOPIC_TOKEN_MAX = 6
    _TOPIC_MATCH_MIN_OVERLAP = 0.5
    _TOPIC_MATCH_MIN_COMMON_TOKENS = 2

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_weekly_report(self, *, report_date: date) -> WeeklyAnalyticsReport:
        stored_report = self._get_stored_report(report_date=report_date)
        if stored_report is not None:
            return self._hydrate_stored_report(stored_report)

        return self._generate_report(report_date=report_date)

    def get_latest_report_date(self) -> date | None:
        stmt = (
            select(WeeklyAnalyticsStoredReport.report_date)
            .order_by(WeeklyAnalyticsStoredReport.report_date.desc())
            .limit(1)
        )
        value = self.session.execute(stmt).scalar_one_or_none()
        if value is None or isinstance(value, date):
            return value
        raise TypeError(f"Expected date or None for report_date, got {type(value)!r}")

    def list_stored_reports(self, *, limit: int = 52) -> list[WeeklyAnalyticsReportIndexEntry]:
        stmt: Select[tuple[WeeklyAnalyticsStoredReport]] = (
            select(WeeklyAnalyticsStoredReport)
            .order_by(WeeklyAnalyticsStoredReport.report_date.desc())
            .limit(limit)
        )
        rows = self.session.execute(stmt).scalars().all()
        entries = [
            WeeklyAnalyticsReportIndexEntry(
                report_date=row.report_date,
                date_from=row.date_from,
                date_to=row.date_to,
                summary=row.summary,
                created_at=row.created_at,
            )
            for row in rows
        ]
        return entries[:limit]

    def save_weekly_report(
        self,
        *,
        report_date: date,
        date_from: date | None = None,
        date_to: date | None = None,
        summary: str | None = None,
        new: list[dict[str, str] | WeeklyAnalyticsItem] | None = None,
        trending_up: list[dict[str, str] | WeeklyAnalyticsItem] | None = None,
        trending_down: list[dict[str, str] | WeeklyAnalyticsItem] | None = None,
    ) -> WeeklyAnalyticsReport:
        should_generate = any(
            value is None
            for value in (date_from, date_to, summary, new, trending_up, trending_down)
        )
        report = (
            self._generate_report(report_date=report_date)
            if should_generate
            else WeeklyAnalyticsReport(
                report_date=report_date,
                date_from=(date_from if date_from is not None else report_date - timedelta(days=6)),
                date_to=(date_to if date_to is not None else report_date),
                summary=(summary or "").strip(),
                new=self._coerce_items(new or []),
                trending_up=self._coerce_items(trending_up or []),
                trending_down=self._coerce_items(trending_down or []),
            )
        )

        with self.session.begin_nested():
            existing = self._get_stored_report(report_date=report.report_date)
            if existing is not None:
                self.session.delete(existing)
                self.session.flush()

            stored_report = WeeklyAnalyticsStoredReport(
                report_date=report.report_date,
                date_from=report.date_from,
                date_to=report.date_to,
                summary=report.summary,
            )
            for section_name, items in (
                ("new", report.new),
                ("trending_up", report.trending_up),
                ("trending_down", report.trending_down),
            ):
                for position, item in enumerate(items):
                    stored_report.items.append(
                        WeeklyAnalyticsStoredItem(
                            section_name=section_name,
                            title=item.title,
                            summary=item.summary,
                            url=item.url,
                            position=position,
                        )
                    )
            self.session.add(stored_report)
            self.session.flush()

        return report

    def _generate_report(self, *, report_date: date) -> WeeklyAnalyticsReport:
        date_to = report_date
        date_from = report_date - timedelta(days=6)
        prior_date_to = date_from - timedelta(days=1)
        prior_date_from = prior_date_to - timedelta(days=6)

        recent_rows = self._list_articles(date_from=date_from, date_to=date_to)
        prior_rows = self._list_articles(date_from=prior_date_from, date_to=prior_date_to)
        fallback_report = self._build_fallback_report(
            report_date=report_date,
            date_from=date_from,
            date_to=date_to,
            recent_rows=recent_rows,
            prior_rows=prior_rows,
        )
        return fallback_report

    def _get_stored_report(self, *, report_date: date) -> WeeklyAnalyticsStoredReport | None:
        stmt: Select[tuple[WeeklyAnalyticsStoredReport]] = (
            select(WeeklyAnalyticsStoredReport)
            .where(WeeklyAnalyticsStoredReport.report_date == report_date)
            .options(selectinload(WeeklyAnalyticsStoredReport.items))
        )
        return self.session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def _hydrate_stored_report(
        stored_report: WeeklyAnalyticsStoredReport,
    ) -> WeeklyAnalyticsReport:
        sections: dict[str, list[WeeklyAnalyticsItem]] = {
            "new": [],
            "trending_up": [],
            "trending_down": [],
        }
        for item in stored_report.items:
            if item.section_name not in sections:
                continue
            sections[item.section_name].append(
                WeeklyAnalyticsItem(
                    title=item.title,
                    summary=item.summary,
                    url=item.url,
                )
            )

        return WeeklyAnalyticsReport(
            report_date=stored_report.report_date,
            date_from=stored_report.date_from,
            date_to=stored_report.date_to,
            summary=stored_report.summary,
            new=sections["new"],
            trending_up=sections["trending_up"],
            trending_down=sections["trending_down"],
        )

    def _build_fallback_report(
        self,
        *,
        report_date: date,
        date_from: date,
        date_to: date,
        recent_rows: list[Article],
        prior_rows: list[Article],
    ) -> WeeklyAnalyticsReport:
        section_rows = self._build_section_rows(recent_rows=recent_rows, prior_rows=prior_rows)
        return WeeklyAnalyticsReport(
            report_date=report_date,
            date_from=date_from,
            date_to=date_to,
            summary=self._build_summary(
                date_from=date_from,
                date_to=date_to,
                recent_rows=recent_rows,
                prior_rows=prior_rows,
            ),
            new=self._to_items(section_rows["new"], sort_key="published_at"),
            trending_up=self._to_items(section_rows["trending_up"], sort_key="rank_score"),
            trending_down=self._to_items(section_rows["trending_down"], sort_key="rank_score"),
        )

    def _list_articles(
        self,
        *,
        date_from: date,
        date_to: date,
        limit: int = 5,
    ) -> list[Article]:
        start_at = datetime.combine(date_from, time.min, tzinfo=UTC)
        end_at = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
        stmt: Select[tuple[Article]] = (
            select(Article)
            .where(Article.published_at >= start_at)
            .where(Article.published_at < end_at)
            .order_by(Article.rank_score.desc(), Article.published_at.desc().nulls_last())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    @staticmethod
    def _to_items(
        rows: list[Article],
        *,
        sort_key: str,
        limit: int = 10,
        reverse: bool = True,
    ) -> list[WeeklyAnalyticsItem]:
        if sort_key == "published_at":
            ordered = sorted(rows, key=lambda row: row.published_at or row.discovered_at,
                             reverse=reverse)
        else:
            ordered = sorted(
                rows,
                key=lambda row: (row.rank_score, row.published_at or row.discovered_at),
                reverse=reverse,
            )
        return [
            WeeklyAnalyticsItem(
                title=row.title,
                summary=(row.summary or row.content or "No summary available.").strip(),
                url=row.url,
            )
            for row in ordered[:limit]
        ]

    @classmethod
    def _build_section_rows(
        cls,
        *,
        recent_rows: list[Article],
        prior_rows: list[Article],
    ) -> dict[str, list[Article]]:
        recent_topics = cls._group_topics_by_title(recent_rows)
        prior_topics = cls._group_topics_by_title(prior_rows)

        new_rows: list[Article] = []
        trending_up_rows: list[Article] = []
        matched_prior_keys: set[str] = set()
        for _, recent_topic in recent_topics.items():
            prior_key = cls._find_best_topic_match(
                recent_tokens=recent_topic["tokens"],
                prior_topics=prior_topics,
                excluded_keys=matched_prior_keys,
            )
            if prior_key is None:
                new_rows.append(recent_topic["recent"])
                continue
            matched_prior_keys.add(prior_key)
            if recent_topic["recent"].rank_score > prior_topics[prior_key]["recent"].rank_score:
                trending_up_rows.append(recent_topic["recent"])

        trending_down_rows: list[Article] = []
        for prior_key, prior_topic in prior_topics.items():
            if prior_key not in matched_prior_keys:
                trending_down_rows.append(prior_topic["recent"])

        return {
            "new": new_rows,
            "trending_up": trending_up_rows,
            "trending_down": trending_down_rows,
        }

    @staticmethod
    def _normalize_topic_token(token: str) -> str:
        normalized = token.lower().strip()
        if len(normalized) <= 2:
            return normalized
        for suffix in ("ing", "ed", "es", "s"):
            if normalized.endswith(suffix) and len(normalized) > len(suffix) + 2:
                normalized = normalized[: -len(suffix)]
                break
        return normalized

    @classmethod
    def _topic_tokens_from_title(cls, title: str) -> list[str]:
        words = re.findall(r"[a-z0-9]+", title.lower())
        tokens: list[str] = []
        seen: set[str] = set()
        for raw in words:
            token = cls._normalize_topic_token(raw)
            if (
                not token
                or token in cls._TOPIC_STOPWORDS
                or (len(token) <= 2 and not token.isdigit())
                or token in seen
            ):
                continue
            seen.add(token)
            tokens.append(token)
            if len(tokens) >= cls._TOPIC_TOKEN_MAX:
                break
        if tokens:
            return tokens
        fallback = " ".join(words).strip() or title.lower().strip()
        return [fallback]

    @classmethod
    def _topic_overlap_score(
        cls,
        left_tokens: set[str],
        right_tokens: set[str],
    ) -> tuple[int, float]:
        if not left_tokens or not right_tokens:
            return (0, 0.0)
        common_count = len(left_tokens & right_tokens)
        smaller_len = float(min(len(left_tokens), len(right_tokens)))
        return (common_count, common_count / smaller_len)

    @classmethod
    def _find_best_topic_match(
        cls,
        *,
        recent_tokens: set[str],
        prior_topics: dict[str, dict[str, Any]],
        excluded_keys: set[str],
    ) -> str | None:
        best_key: str | None = None
        best_common = 0
        best_ratio = 0.0
        for prior_key, prior_topic in prior_topics.items():
            if prior_key in excluded_keys:
                continue
            common_count, overlap_ratio = cls._topic_overlap_score(
                recent_tokens,
                cast(set[str], prior_topic["tokens"]),
            )
            if (
                common_count < cls._TOPIC_MATCH_MIN_COMMON_TOKENS
                or overlap_ratio < cls._TOPIC_MATCH_MIN_OVERLAP
            ):
                continue
            if (common_count, overlap_ratio) > (best_common, best_ratio):
                best_key = prior_key
                best_common = common_count
                best_ratio = overlap_ratio
        return best_key

    @classmethod
    def _group_topics_by_title(cls, rows: list[Article]) -> dict[str, dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            tokens = set(cls._topic_tokens_from_title(row.title))
            topic_key = " ".join(sorted(tokens))
            existing = grouped.get(topic_key)
            if existing is None:
                grouped[topic_key] = {"recent": row, "tokens": tokens}
                continue
            current = existing["recent"]
            if (row.rank_score, row.published_at or row.discovered_at) > (
                current.rank_score, current.published_at or current.discovered_at
            ):
                existing["recent"] = row
        return grouped

    @staticmethod
    def _build_summary(
        *,
        date_from: date,
        date_to: date,
        recent_rows: list[Article],
        prior_rows: list[Article],
    ) -> str:
        recent_count = len(recent_rows)
        prior_count = len(prior_rows)
        if recent_count == 0:
            return (
                f"No AI news signals between {date_from.isoformat()} "
                f"and {date_to.isoformat()}."
            )
        delta = recent_count - prior_count
        if delta > 0:
            trend = "Momentum increased versus the previous week."
        elif delta < 0:
            trend = "Momentum cooled versus the previous week."
        else:
            trend = "Momentum held steady versus the previous week."
        return (
            f"Weekly summary for {date_from.isoformat()} to {date_to.isoformat()}: "
            f"{recent_count} notable AI stories surfaced. {trend} "
            f"Current attention centers on {recent_rows[0].title}."
        )

    @staticmethod
    def _coerce_items(
        raw_items: list[dict[str, str] | WeeklyAnalyticsItem],
    ) -> list[WeeklyAnalyticsItem]:
        items: list[WeeklyAnalyticsItem] = []
        for raw_item in raw_items:
            if isinstance(raw_item, WeeklyAnalyticsItem):
                items.append(
                    WeeklyAnalyticsItem(
                        title=raw_item.title.strip()[:WeeklyAnalyticsRepo._TITLE_MAX_LEN],
                        summary=raw_item.summary.strip(),
                        url=raw_item.url.strip()[:WeeklyAnalyticsRepo._URL_MAX_LEN],
                    )
                )
                continue
            items.append(
                WeeklyAnalyticsItem(
                    title=str(raw_item["title"]).strip()[:WeeklyAnalyticsRepo._TITLE_MAX_LEN],
                    summary=str(raw_item["summary"]).strip(),
                    url=str(raw_item["url"]).strip()[:WeeklyAnalyticsRepo._URL_MAX_LEN],
                )
            )
        return items
