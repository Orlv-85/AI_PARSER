# pylint: disable=too-many-lines
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlsplit

import httpx
from sqlalchemy import Select, delete, desc, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, selectinload

from app.config.sources import SourceConfig
from app.storage.models_sql import (
    Article,
    ArticleAlias,
    NewsDigestGroup,
    NewsDigestItem,
    NewsDigestReport,
    Source,
    SourceCandidate,
    SourceImportBatch,
)

if TYPE_CHECKING:
    from app.core.source_onboarding import CandidateOverlapGroup


_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class WeeklyAnalyticsItem:
    title: str
    summary: str
    url: str


@dataclass(slots=True)
class WeeklyAnalyticsReport:
    report_date: date
    date_from: date
    date_to: date
    summary: str
    new: list[WeeklyAnalyticsItem]
    trending_up: list[WeeklyAnalyticsItem]
    trending_down: list[WeeklyAnalyticsItem]


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

    def get_source_fetch_state(self, source_id: int) -> dict[str, object | None]:
        return self.get_fetch_state(source_id=source_id)

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

    def update_source_fetch_state(
        self,
        source_id: int,
        *,
        etag: str | None,
        last_modified: str | None,
        last_checked_at: datetime,
        last_status_code: int | None,
    ) -> None:
        self.update_fetch_state(
            source_id=source_id,
            etag=etag,
            last_modified=last_modified,
            last_checked_at=last_checked_at,
            last_status_code=last_status_code,
        )

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


class ArticleRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def exists_by_canonical_hash(self, canonical_hash: str) -> bool:
        stmt: Select[tuple[Article]] = (
            select(Article)
            .where(Article.url_canonical_hash == canonical_hash)
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def existing_canonical_hashes(self, canonical_hashes: list[str]) -> set[str]:
        if not canonical_hashes:
            return set()
        stmt = select(Article.url_canonical_hash).where(
            Article.url_canonical_hash.in_(canonical_hashes)
        )
        rows = self.session.execute(stmt).scalars().all()
        return {str(value) for value in rows}

    def upsert_articles_batch(self, rows: list[dict[str, Any]]) -> tuple[int, int]:
        if not rows:
            return 0, 0

        normalized_by_hash: dict[str, dict[str, Any]] = {}
        input_duplicates = 0
        for row in rows:
            canonical_hash = str(row["url_canonical_hash"])
            if canonical_hash in normalized_by_hash:
                input_duplicates += 1
                existing_row = normalized_by_hash[canonical_hash]
                existing_row["ai_relevance_score"] = row["ai_relevance_score"]
                existing_row["freshness_score"] = row["freshness_score"]
                existing_row["rank_score"] = row["rank_score"]
                continue
            normalized_by_hash[canonical_hash] = dict(row)

        normalized_rows = list(normalized_by_hash.values())
        canonical_hashes = list(normalized_by_hash)
        existing_before = self.existing_canonical_hashes(canonical_hashes)
        new_count = sum(
            1 for canonical_hash in canonical_hashes if canonical_hash not in existing_before
        )
        duplicate_count = (len(canonical_hashes) - new_count) + input_duplicates

        bind = self.session.get_bind()
        dialect_name = bind.dialect.name if bind is not None else ""
        if dialect_name in {"postgresql", "sqlite"}:
            insert_factory = postgresql_insert if dialect_name == "postgresql" else sqlite_insert
            stmt = insert_factory(Article).values(normalized_rows)
            excluded = stmt.excluded
            stmt = stmt.on_conflict_do_update(
                index_elements=[Article.url_canonical_hash],
                set_={
                    "ai_relevance_score": excluded.ai_relevance_score,
                    "freshness_score": excluded.freshness_score,
                    "rank_score": excluded.rank_score,
                },
            )
            self.session.execute(stmt)
            self.session.flush()
            return new_count, duplicate_count

        actual_new = 0
        actual_duplicates = 0
        for row in normalized_rows:
            _, is_new = self.insert_article(**row)
            if is_new:
                actual_new += 1
            else:
                actual_duplicates += 1
        actual_duplicates += input_duplicates
        return actual_new, actual_duplicates

    def insert_article(
        self,
        *,
        source_id: int | None,
        title: str,
        url: str,
        url_canonical: str,
        url_canonical_hash: str,
        published_at: datetime,
        summary: str | None = None,
        content: str | None = None,
        ai_relevance_score: float = 0.0,
        freshness_score: float = 0.0,
        rank_score: float = 0.0,
    ) -> tuple[Article, bool]:
        existing_stmt: Select[tuple[Article]] = select(Article).where(
            Article.url_canonical_hash == url_canonical_hash
        )
        existing = self.session.execute(existing_stmt).scalar_one_or_none()
        if existing is not None:
            existing.ai_relevance_score = ai_relevance_score
            existing.freshness_score = freshness_score
            existing.rank_score = rank_score
            return existing, False

        article = Article(
            source_id=source_id,
            title=title,
            summary=summary,
            content=content,
            url=url,
            url_canonical=url_canonical,
            url_canonical_hash=url_canonical_hash,
            published_at=published_at,
            discovered_at=datetime.now(UTC),
            ai_relevance_score=ai_relevance_score,
            freshness_score=freshness_score,
            rank_score=rank_score,
        )
        self.session.add(article)
        self.session.flush()
        return article, True

    def add_alias(
        self,
        *,
        article_id: int,
        source_id: int,
        url: str,
        discovered_at: datetime | None = None,
    ) -> ArticleAlias:
        alias = ArticleAlias(
            article_id=article_id,
            source_id=source_id,
            url=url,
            discovered_at=discovered_at or datetime.now(UTC),
        )
        self.session.add(alias)
        self.session.flush()
        return alias

    def merge_alias(
        self,
        *,
        existing_article_id: int,
        source_id: int,
        url: str,
        discovered_at: datetime | None = None,
    ) -> ArticleAlias:
        return self.add_alias(
            article_id=existing_article_id,
            source_id=source_id,
            url=url,
            discovered_at=discovered_at,
        )

    def query_top(
        self,
        *,
        hours: int = 24,
        limit: int = 30,
        min_ai_relevance: float = 0.0,
    ) -> list[Article]:
        window_start = datetime.now(UTC) - timedelta(hours=hours)
        stmt: Select[tuple[Article]] = (
            select(Article)
            .where(Article.published_at >= window_start)
            .where(Article.ai_relevance_score >= min_ai_relevance)
            .order_by(Article.rank_score.desc(), Article.published_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def search(self, *, query: str, days: int = 7, limit: int = 100) -> list[Article]:
        window_start = datetime.now(UTC) - timedelta(days=days)
        ilike = f"%{query}%"
        stmt: Select[tuple[Article]] = (
            select(Article)
            .where(Article.published_at >= window_start)
            .where(
                Article.title.ilike(ilike)
                | Article.summary.ilike(ilike)
                | Article.content.ilike(ilike)
            )
            .order_by(Article.published_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def list_for_view(
        self,
        *,
        hours: int | None,
        limit: int,
        query: str | None,
        days: int,
        sort: str,
        min_ai_relevance: float = 0.0,
        date_from: date | None = None,
        date_to: date | None = None,
        include_content: bool = False,
    ) -> list[tuple[Article, str | None, str | None]]:
        del include_content
        base_stmt = (
            select(Article, Source.source_key, Source.name)
            .outerjoin(Source, Article.source_id == Source.id)
            .where(Article.ai_relevance_score >= min_ai_relevance)
            .limit(limit)
        )
        has_date_range = date_from is not None or date_to is not None
        if has_date_range:
            if date_from is not None:
                start_at = datetime.combine(date_from, time.min, tzinfo=UTC)
                base_stmt = base_stmt.where(Article.published_at >= start_at)
            if date_to is not None:
                end_at = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
                base_stmt = base_stmt.where(Article.published_at < end_at)
        if query:
            if not has_date_range:
                window_start = datetime.now(UTC) - timedelta(days=days)
                base_stmt = base_stmt.where(Article.published_at >= window_start)
            ilike = f"%{query}%"
            base_stmt = base_stmt.where(
                Article.title.ilike(ilike)
                | Article.summary.ilike(ilike)
                | Article.content.ilike(ilike)
            )
            if sort == "published":
                base_stmt = base_stmt.order_by(
                    Article.published_at.desc(),
                    desc(Article.rank_score),
                )
            else:
                base_stmt = base_stmt.order_by(
                    Article.rank_score.desc(),
                    Article.published_at.desc(),
                )
        else:
            if not has_date_range:
                effective_hours = 24 if hours is None else hours
                window_start = datetime.now(UTC) - timedelta(hours=effective_hours)
                base_stmt = base_stmt.where(Article.published_at >= window_start)
            if sort == "published":
                base_stmt = base_stmt.order_by(
                    Article.published_at.desc(),
                    desc(Article.rank_score),
                )
            else:
                base_stmt = base_stmt.order_by(
                    Article.rank_score.desc(),
                    Article.published_at.desc(),
                )
        return [
            (row[0], row[1], row[2])
            for row in self.session.execute(base_stmt).all()
        ]

    def list_for_agent(
        self,
        *,
        hours: int | None,
        limit: int,
        query: str | None,
        days: int,
        sort: str,
        min_ai_relevance: float = 0.0,
        date_from: date | None = None,
        date_to: date | None = None,
        include_content: bool = False,
    ) -> list[tuple[Article, str | None, str | None]]:
        kwargs: dict[str, Any] = {
            "hours": hours,
            "limit": limit,
            "query": query,
            "days": days,
            "sort": sort,
            "min_ai_relevance": min_ai_relevance,
        }
        if date_from is not None:
            kwargs["date_from"] = date_from
        if date_to is not None:
            kwargs["date_to"] = date_to
        if include_content:
            kwargs["include_content"] = include_content
        return self.list_for_view(**cast(Any, kwargs))

    def get_article_for_agent(
        self, *, article_id: int
    ) -> tuple[Article, str | None, str | None] | None:
        stmt = (
            select(Article, Source.source_key, Source.name)
            .outerjoin(Source, Article.source_id == Source.id)
            .where(Article.id == article_id)
        )
        row = self.session.execute(stmt).one_or_none()
        if row is None:
            return None
        return row[0], row[1], row[2]

    def count_older_than(self, *, older_than_days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        stmt = select(Article.id).where(Article.published_at < cutoff)
        return len(self.session.scalars(stmt).all())

    def prune_older_than(self, *, older_than_days: int) -> tuple[int, int]:
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        old_article_ids = select(Article.id).where(Article.published_at < cutoff)

        deleted_aliases_stmt = select(ArticleAlias.id).where(
            ArticleAlias.article_id.in_(old_article_ids)
        )
        deleted_aliases = len(self.session.scalars(deleted_aliases_stmt).all())
        deleted_articles = self.count_older_than(older_than_days=older_than_days)

        self.session.execute(delete(ArticleAlias).where(ArticleAlias.article_id.in_(old_article_ids)))
        self.session.execute(delete(Article).where(Article.published_at < cutoff))
        return deleted_articles, deleted_aliases


class WeeklyAnalyticsRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_weekly_report(self, *, report_date: date) -> WeeklyAnalyticsReport:
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
        if not recent_rows:
            return fallback_report

        try:
            payload = self._generate_antigravity_report(
                report_date=report_date,
                date_from=date_from,
                date_to=date_to,
                recent_rows=recent_rows,
                prior_rows=prior_rows,
            )
            return self._build_report_from_payload(
                report_date=report_date,
                date_from=date_from,
                date_to=date_to,
                payload=payload,
            )
        except TimeoutError as exc:
            _LOGGER.warning("weekly_analytics_antigravity_timeout: %s", exc)
        except (ValueError, httpx.HTTPError) as exc:
            _LOGGER.warning("weekly_analytics_antigravity_fallback: %s", exc)

        return fallback_report

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
            .order_by(Article.rank_score.desc(), Article.published_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    @staticmethod
    def _to_items(
        rows: list[Article],
        *,
        sort_key: str,
        limit: int = 3,
        reverse: bool = True,
    ) -> list[WeeklyAnalyticsItem]:
        if sort_key == "published_at":
            ordered = sorted(rows, key=lambda row: row.published_at, reverse=reverse)
        else:
            ordered = sorted(
                rows,
                key=lambda row: (row.rank_score, row.published_at),
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

        new_rows = [
            topic["recent"]
            for title, topic in recent_topics.items()
            if title not in prior_topics
        ]
        trending_up_rows = [
            topic["recent"]
            for title, topic in recent_topics.items()
            if title in prior_topics
            and topic["recent"].rank_score > prior_topics[title]["recent"].rank_score
        ]
        trending_down_rows = []
        for title, topic in prior_topics.items():
            recent_topic = recent_topics.get(title)
            if recent_topic is None:
                trending_down_rows.append(topic["recent"])
                continue
            if recent_topic["recent"].rank_score < topic["recent"].rank_score:
                trending_down_rows.append(topic["recent"])

        return {
            "new": new_rows,
            "trending_up": trending_up_rows,
            "trending_down": trending_down_rows,
        }

    @staticmethod
    def _group_topics_by_title(rows: list[Article]) -> dict[str, dict[str, Article]]:
        grouped: dict[str, dict[str, Article]] = {}
        for row in rows:
            existing = grouped.get(row.title)
            if existing is None:
                grouped[row.title] = {"recent": row}
                continue
            current = existing["recent"]
            if (row.rank_score, row.published_at) > (current.rank_score, current.published_at):
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
                f"Antigravity found no AI news signals between {date_from.isoformat()} "
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
            f"Antigravity summary for {date_from.isoformat()} to {date_to.isoformat()}: "
            f"{recent_count} notable AI stories surfaced. {trend} "
            f"Current attention centers on {recent_rows[0].title}."
        )

    def _generate_antigravity_report(
        self,
        *,
        report_date: date,
        date_from: date,
        date_to: date,
        recent_rows: list[Article],
        prior_rows: list[Article],
    ) -> dict[str, object]:
        api_url = os.getenv("AINEWS_ANTIGRAVITY_API_URL", "").strip()
        if not api_url:
            raise ValueError("AINEWS_ANTIGRAVITY_API_URL is not configured")

        request_payload = {
            "report_date": report_date.isoformat(),
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "instructions": (
                "Return JSON with keys summary, new, trending_up, trending_down. "
                "Each section list item must include title, summary, url."
            ),
            "recent_articles": self._serialize_articles(recent_rows),
            "prior_articles": self._serialize_articles(prior_rows),
        }
        headers = {"Content-Type": "application/json"}
        api_key = os.getenv("AINEWS_ANTIGRAVITY_API_KEY", "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        timeout_seconds = self._get_antigravity_timeout_seconds()
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            response = client.post(api_url, json=request_payload, headers=headers)
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError("Antigravity response must be a JSON object")
        return cast(dict[str, object], payload)

    @staticmethod
    def _serialize_articles(rows: list[Article]) -> list[dict[str, object]]:
        return [
            {
                "title": row.title,
                "summary": (row.summary or row.content or "No summary available.").strip(),
                "url": row.url,
                "published_at": row.published_at.isoformat(),
                "rank_score": row.rank_score,
            }
            for row in rows
        ]

    @staticmethod
    def _get_antigravity_timeout_seconds() -> float:
        raw_value = os.getenv("AINEWS_ANTIGRAVITY_TIMEOUT_SECONDS", "60").strip()
        try:
            timeout_seconds = float(raw_value)
        except ValueError as exc:
            raise ValueError("AINEWS_ANTIGRAVITY_TIMEOUT_SECONDS must be numeric") from exc
        if timeout_seconds <= 0:
            raise ValueError("AINEWS_ANTIGRAVITY_TIMEOUT_SECONDS must be greater than 0")
        return min(timeout_seconds, 60.0)

    def _build_report_from_payload(
        self,
        *,
        report_date: date,
        date_from: date,
        date_to: date,
        payload: dict[str, object],
    ) -> WeeklyAnalyticsReport:
        summary = payload.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("Antigravity response must include a non-empty summary")

        return WeeklyAnalyticsReport(
            report_date=report_date,
            date_from=date_from,
            date_to=date_to,
            summary=summary.strip(),
            new=self._validate_payload_items(payload.get("new"), section_name="new"),
            trending_up=self._validate_payload_items(
                payload.get("trending_up"),
                section_name="trending_up",
            ),
            trending_down=self._validate_payload_items(
                payload.get("trending_down"),
                section_name="trending_down",
            ),
        )

    @staticmethod
    def _validate_payload_items(
        raw_items: object,
        *,
        section_name: str,
    ) -> list[WeeklyAnalyticsItem]:
        if not isinstance(raw_items, list):
            raise ValueError(f"Antigravity response section {section_name} must be a list")

        items: list[WeeklyAnalyticsItem] = []
        for index, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                raise ValueError(
                    f"Antigravity response item {section_name}[{index}] must be an object"
                )
            title = raw_item.get("title")
            summary = raw_item.get("summary")
            url = raw_item.get("url")
            if not isinstance(title, str) or not title.strip():
                raise ValueError(
                    f"Antigravity response item {section_name}[{index}] is missing title"
                )
            if not isinstance(summary, str) or not summary.strip():
                raise ValueError(
                    f"Antigravity response item {section_name}[{index}] is missing summary"
                )
            if not isinstance(url, str) or not url.strip():
                raise ValueError(
                    f"Antigravity response item {section_name}[{index}] is missing url"
                )
            items.append(
                WeeklyAnalyticsItem(
                    title=title.strip(),
                    summary=summary.strip(),
                    url=url.strip(),
                )
            )
        return items


class SourceImportBatchRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_import_batch(
        self,
        *,
        raw_text: str,
        parsed_count: int = 0,
        accepted_count: int = 0,
        rejected_count: int = 0,
    ) -> SourceImportBatch:
        return self.create_batch(
            raw_text=raw_text,
            parsed_count=parsed_count,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
        )

    def create_batch(
        self,
        *,
        raw_text: str,
        parsed_count: int = 0,
        accepted_count: int = 0,
        rejected_count: int = 0,
    ) -> SourceImportBatch:
        batch = SourceImportBatch(
            raw_text=raw_text,
            parsed_count=parsed_count,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
        )
        self.session.add(batch)
        self.session.flush()
        return batch

    def update_counts(
        self,
        *,
        batch: SourceImportBatch,
        parsed_count: int,
        accepted_count: int,
        rejected_count: int,
    ) -> SourceImportBatch:
        batch.parsed_count = parsed_count
        batch.accepted_count = accepted_count
        batch.rejected_count = rejected_count
        self.session.flush()
        return batch

    def get_batch(self, batch_id: int) -> SourceImportBatch | None:
        return self.session.get(SourceImportBatch, batch_id)


class SourceCandidateRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_draft_candidate(
        self,
        *,
        raw_input: str,
        normalized_url: str,
        batch_id: int | None = None,
        candidate_type: str = "unknown",
    ) -> tuple[SourceCandidate, bool]:
        stmt: Select[tuple[SourceCandidate]] = select(SourceCandidate).where(
            SourceCandidate.normalized_url == normalized_url
        )
        existing = self.session.execute(stmt).scalar_one_or_none()
        if existing is not None:
            return existing, False

        candidate = SourceCandidate(
            batch_id=batch_id,
            raw_input=raw_input,
            normalized_url=normalized_url,
            candidate_type=candidate_type,
        )
        self.session.add(candidate)
        self.session.flush()
        return candidate, True

    def create_draft_candidates(
        self,
        *,
        batch_id: int | None,
        candidates: list[object],
    ) -> tuple[list[SourceCandidate], int]:
        rows: list[SourceCandidate] = []
        accepted_count = 0
        for candidate_data in candidates:
            raw_input = self._read_candidate_value(candidate_data, "raw_input")
            normalized_url = self._read_candidate_value(candidate_data, "normalized_url")
            candidate_type = self._read_candidate_value(
                candidate_data,
                "candidate_type",
                default="unknown",
            )
            candidate, created = self.create_draft_candidate(
                raw_input=raw_input,
                normalized_url=normalized_url,
                batch_id=batch_id,
                candidate_type=candidate_type,
            )
            if created:
                rows.append(candidate)
                accepted_count += 1
        return rows, accepted_count

    def insert_normalized_draft_candidates(
        self,
        *,
        batch_id: int | None,
        candidates: list[object],
    ) -> tuple[list[SourceCandidate], int]:
        return self.create_draft_candidates(batch_id=batch_id, candidates=candidates)

    @staticmethod
    def _read_candidate_value(
        candidate_data: object,
        field_name: str,
        *,
        default: str | None = None,
    ) -> str:
        if isinstance(candidate_data, dict):
            value = candidate_data.get(field_name, default)
        else:
            value = getattr(candidate_data, field_name, default)
        if value is None:
            raise ValueError(f"candidate field is required: {field_name}")
        return str(value)

    def get_candidate(self, candidate_id: int) -> SourceCandidate | None:
        return self.session.get(SourceCandidate, candidate_id)

    def list_candidates(
        self,
        *,
        batch_id: int | None = None,
        candidate_ids: list[int] | None = None,
        status: str | None = None,
        validation_status: str | None = None,
    ) -> list[SourceCandidate]:
        stmt: Select[tuple[SourceCandidate]] = select(SourceCandidate)
        if batch_id is not None:
            stmt = stmt.where(SourceCandidate.batch_id == batch_id)
        if candidate_ids:
            stmt = stmt.where(SourceCandidate.id.in_(candidate_ids))
        if status is not None:
            stmt = stmt.where(SourceCandidate.status == status)
        if validation_status is not None:
            stmt = stmt.where(SourceCandidate.validation_status == validation_status)
        stmt = stmt.order_by(SourceCandidate.id.asc())
        return list(self.session.scalars(stmt).all())

    def find_by_normalized_url(self, normalized_url: str) -> SourceCandidate | None:
        stmt: Select[tuple[SourceCandidate]] = (
            select(SourceCandidate).where(SourceCandidate.normalized_url == normalized_url).limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def record_validation_result(
        self,
        *,
        candidate_id: int,
        result: object,
    ) -> SourceCandidate:
        candidate = self.get_candidate(candidate_id)
        if candidate is None:
            raise ValueError(f"source candidate not found: {candidate_id}")

        status = self._read_candidate_value(result, "status")
        detected_type = self._read_optional_value(result, "detected_type")
        validation_error = self._read_optional_value(result, "validation_error")
        candidate.validation_status = status
        candidate.validation_detected_type = detected_type
        candidate.validation_error = validation_error
        if detected_type:
            candidate.candidate_type = detected_type
        candidate.validation_details = self._build_validation_details(result)
        candidate.validated_at = datetime.now(UTC)
        self.session.flush()
        return candidate

    def update_candidate(
        self,
        *,
        candidate_id: int,
        raw_input: str | None = None,
        normalized_url: str | None = None,
        candidate_type: str | None = None,
    ) -> SourceCandidate:
        candidate = self.get_candidate(candidate_id)
        if candidate is None:
            raise ValueError(f"source candidate not found: {candidate_id}")

        if normalized_url is not None and normalized_url != candidate.normalized_url:
            existing = self.find_by_normalized_url(normalized_url)
            if existing is not None and existing.id != candidate_id:
                raise ValueError("normalized URL already exists for another candidate")
            candidate.normalized_url = normalized_url
        if raw_input is not None:
            candidate.raw_input = raw_input
        if candidate_type is not None:
            candidate.candidate_type = candidate_type
        self.session.flush()
        return candidate

    def save_review_update(self, candidate: object) -> SourceCandidate:
        candidate_id = int(self._read_candidate_value(candidate, "id"))
        stored = self.get_candidate(candidate_id)
        if stored is None:
            raise ValueError(f"source candidate not found: {candidate_id}")
        for field_name in (
            "status",
            "review_note",
            "duplicate_of_candidate_id",
            "approved_source_id",
            "raw_input",
            "normalized_url",
            "candidate_type",
            "validation_status",
        ):
            if isinstance(candidate, dict):
                if field_name not in candidate:
                    continue
                value = candidate.get(field_name)
            else:
                if not hasattr(candidate, field_name):
                    continue
                value = getattr(candidate, field_name)
            setattr(stored, field_name, value)
        self.session.flush()
        return stored

    def find_overlap_groups(
        self,
        *,
        batch_id: int | None = None,
        candidate_ids: list[int] | None = None,
    ) -> list[CandidateOverlapGroup]:
        from app.core.source_onboarding import (  # pylint: disable=import-outside-toplevel
            group_candidate_overlaps,
        )

        candidates = self.list_candidates(batch_id=batch_id, candidate_ids=candidate_ids)
        return cast("list[CandidateOverlapGroup]", group_candidate_overlaps(candidates))

    def summarize_batch(self, *, batch_id: int | None) -> dict[str, int]:
        candidates = self.list_candidates(batch_id=batch_id)
        summary = {
            "batch_id": 0 if batch_id is None else batch_id,
            "total_candidates": len(candidates),
            "draft_count": 0,
            "validated_count": 0,
            "approved_count": 0,
            "rejected_count": 0,
            "duplicate_count": 0,
            "pending_review_count": 0,
            "rejected_review_count": 0,
        }
        for candidate in candidates:
            if candidate.status == "draft":
                summary["draft_count"] += 1
            if candidate.validation_status == "validated":
                summary["validated_count"] += 1
            if candidate.status == "approved":
                summary["approved_count"] += 1
            if candidate.status == "rejected":
                summary["rejected_count"] += 1
                summary["rejected_review_count"] += 1
            if candidate.status == "duplicate":
                summary["duplicate_count"] += 1
            if candidate.status in {"draft", "validated"}:
                summary["pending_review_count"] += 1
        return summary

    @staticmethod
    def _build_validation_details(result: object) -> str | None:
        details: dict[str, object] = {}
        for field_name in ("entry_count", "link_count", "sample_links"):
            if isinstance(result, dict):
                value = result.get(field_name)
            else:
                value = getattr(result, field_name, None)
            if value is None:
                continue
            details[field_name] = value
        if not details:
            return None
        return json.dumps(details, ensure_ascii=True, sort_keys=True)

    @staticmethod
    def _read_optional_value(candidate_data: object, field_name: str) -> str | None:
        if isinstance(candidate_data, dict):
            value = candidate_data.get(field_name)
        else:
            value = getattr(candidate_data, field_name, None)
        if value is None:
            return None
        return str(value)


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
