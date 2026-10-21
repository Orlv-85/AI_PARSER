# pylint: disable=too-many-lines
import json
import logging
import re
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlsplit

from sqlalchemy import Select, case, delete, desc, func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, selectinload

from app.config.settings import get_settings
from app.config.sources import SourceConfig
from app.core.categories import CATEGORY_ORDER
from app.core.weekly.analytics import SECTION_STATES, empty_section
from app.storage.models_sql import (
    Article,
    ArticleAlias,
    FetchRun,
    NewsDigestGroup,
    NewsDigestItem,
    NewsDigestReport,
    Source,
    SourceCandidate,
    SourceImportBatch,
    WeeklyAnalyticsStoredItem,
    WeeklyAnalyticsStoredReport,
    WeeklyPublication,
    WeeklySnapshot,
)
from app.storage.weekly import WeeklyStore

if TYPE_CHECKING:
    from app.core.sources.onboarding import CandidateOverlapGroup


_LOGGER = logging.getLogger(__name__)


def _publication_since(moment: datetime):
    return or_(Article.published_at >= moment,
               Article.published_at.is_(None) & (Article.publication_day >= moment.date()))


def _publication_before(moment: datetime):
    return or_(Article.published_at < moment,
               Article.published_at.is_(None) & (Article.publication_day < moment.date()))


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


@dataclass(slots=True)
class ArticleDailyStats:  # pylint: disable=too-many-instance-attributes
    stat_date: date
    published_count: int
    discovered_count: int
    fetch_run_count: int
    fetched_count: int
    new_count: int
    duplicate_count: int
    error_count: int


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


class ArticleRepo:
    _TITLE_MAX_LEN = 512

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
                if row.get("category") is not None:
                    existing_row["category"] = row["category"]
                    existing_row["category_confidence"] = row.get("category_confidence")
                continue
            normalized_by_hash[canonical_hash] = dict(row)
            normalized_by_hash[canonical_hash]["title"] = str(row["title"])[:self._TITLE_MAX_LEN]
            normalized_by_hash[canonical_hash].setdefault("category", None)
            normalized_by_hash[canonical_hash].setdefault("category_confidence", None)
            normalized_by_hash[canonical_hash].setdefault("material_type", None)
            normalized_by_hash[canonical_hash].setdefault("enrichment_provenance", None)

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
                    "category": func.coalesce(excluded.category, Article.category),
                    "category_confidence": case(
                        (excluded.category.is_not(None), excluded.category_confidence),
                        else_=Article.category_confidence,
                    ),
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
        published_at: datetime | None,
        summary: str | None = None,
        content: str | None = None,
        ai_relevance_score: float = 0.0,
        freshness_score: float = 0.0,
        rank_score: float = 0.0,
        category: str | None = None,
        category_confidence: float | None = None,
        **evidence_fields: Any,
    ) -> tuple[Article, bool]:
        existing_stmt: Select[tuple[Article]] = select(Article).where(
            Article.url_canonical_hash == url_canonical_hash
        )
        existing = self.session.execute(existing_stmt).scalar_one_or_none()
        if existing is not None:
            existing.ai_relevance_score = ai_relevance_score
            existing.freshness_score = freshness_score
            existing.rank_score = rank_score
            if category is not None:
                existing.category = category
                existing.category_confidence = category_confidence
            return existing, False

        article = Article(
            source_id=source_id,
            title=title[:self._TITLE_MAX_LEN],
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
            category=category,
            category_confidence=category_confidence,
            **evidence_fields,
        )
        self.session.add(article)
        self.session.flush()
        return article, True

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
            .where(_publication_since(window_start))
            .where(Article.ai_relevance_score >= min_ai_relevance)
            .order_by(Article.rank_score.desc(), Article.published_at.desc().nulls_last())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def search(self, *, query: str, days: int = 7, limit: int = 100) -> list[Article]:
        window_start = datetime.now(UTC) - timedelta(days=days)
        ilike = f"%{query}%"
        stmt: Select[tuple[Article]] = (
            select(Article)
            .where(_publication_since(window_start))
            .where(
                Article.title.ilike(ilike)
                | Article.summary.ilike(ilike)
                | Article.content.ilike(ilike)
            )
            .order_by(Article.published_at.desc().nulls_last())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def list_for_view(  # pylint: disable=too-many-branches
        self,
        *,
        hours: int | None,
        limit: int,
        offset: int = 0,
        query: str | None,
        days: int,
        sort: str,
        min_ai_relevance: float = 0.0,
        date_from: date | None = None,
        date_to: date | None = None,
        include_content: bool = False,
        category: str | None = None,
    ) -> list[tuple[Article, str | None, str | None]]:
        del include_content
        base_stmt = (
            select(Article, Source.source_key, Source.name)
            .outerjoin(Source, Article.source_id == Source.id)
            .where(Article.ai_relevance_score >= min_ai_relevance)
        )
        has_date_range = date_from is not None or date_to is not None
        if category is not None:
            base_stmt = base_stmt.where(Article.category == category)
        if has_date_range:
            if date_from is not None:
                start_at = datetime.combine(date_from, time.min, tzinfo=UTC)
                base_stmt = base_stmt.where(_publication_since(start_at))
            if date_to is not None:
                end_at = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
                base_stmt = base_stmt.where(_publication_before(end_at))
        if query:
            if not has_date_range:
                window_start = datetime.now(UTC) - timedelta(days=days)
                base_stmt = base_stmt.where(_publication_since(window_start))
            ilike = f"%{query}%"
            base_stmt = base_stmt.where(
                Article.title.ilike(ilike)
                | Article.summary.ilike(ilike)
                | Article.content.ilike(ilike)
            )
            if sort == "published":
                base_stmt = base_stmt.order_by(
                    Article.published_at.desc().nulls_last(),
                    desc(Article.rank_score),
                )
            else:
                base_stmt = base_stmt.order_by(
                    Article.rank_score.desc(),
                    Article.published_at.desc().nulls_last(),
                )
        else:
            if not has_date_range:
                effective_hours = 24 if hours is None else hours
                window_start = datetime.now(UTC) - timedelta(hours=effective_hours)
                base_stmt = base_stmt.where(_publication_since(window_start))
            if sort == "published":
                base_stmt = base_stmt.order_by(
                    Article.published_at.desc().nulls_last(),
                    desc(Article.rank_score),
                )
            else:
                base_stmt = base_stmt.order_by(
                    Article.rank_score.desc(),
                    Article.published_at.desc().nulls_last(),
                )
        if sort == "category":
            base_stmt = base_stmt.order_by(None).order_by(
                case(
                    {name: index for index, name in enumerate(CATEGORY_ORDER)},
                    value=Article.category, else_=len(CATEGORY_ORDER),
                ),
                Article.rank_score.desc(),
                Article.published_at.desc().nulls_last(),
            )
        base_stmt = base_stmt.limit(limit).offset(offset)
        return [
            (row[0], row[1], row[2])
            for row in self.session.execute(base_stmt).all()
        ]

    def list_for_agent(
        self,
        *,
        hours: int | None,
        limit: int,
        offset: int = 0,
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
            "offset": offset,
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
        stmt = select(Article.id).where(_publication_before(cutoff))
        return len(self.session.scalars(stmt).all())

    def prune_older_than(self, *, older_than_days: int) -> tuple[int, int]:
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        old_article_ids = select(Article.id).where(_publication_before(cutoff))

        deleted_aliases_stmt = select(ArticleAlias.id).where(
            ArticleAlias.article_id.in_(old_article_ids)
        )
        deleted_aliases = len(self.session.scalars(deleted_aliases_stmt).all())
        deleted_articles = self.count_older_than(older_than_days=older_than_days)

        self.session.execute(delete(ArticleAlias).where(ArticleAlias.article_id.in_(old_article_ids)))
        self.session.execute(delete(Article).where(_publication_before(cutoff)))
        return deleted_articles, deleted_aliases

    def daily_stats(self, *, date_from: date, date_to: date) -> list[ArticleDailyStats]:
        start_at = datetime.combine(date_from, time.min, tzinfo=UTC)
        end_at = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)

        published_counts = self._daily_article_counts(
            field=Article.published_at,
            start_at=start_at,
            end_at=end_at,
        )
        day_counts = self.session.execute(
            select(Article.publication_day, func.count(Article.id))
            .where(Article.published_at.is_(None))
            .where(Article.publication_day >= date_from)
            .where(Article.publication_day <= date_to)
            .group_by(Article.publication_day)
        ).all()
        for day, count in day_counts:
            published_counts[day] = published_counts.get(day, 0) + int(count)
        discovered_counts = self._daily_article_counts(
            field=Article.discovered_at,
            start_at=start_at,
            end_at=end_at,
        )
        fetch_stats = self._daily_fetch_stats(start_at=start_at, end_at=end_at)

        result: list[ArticleDailyStats] = []
        current = date_from
        while current <= date_to:
            fetch_row = fetch_stats.get(current, {})
            result.append(
                ArticleDailyStats(
                    stat_date=current,
                    published_count=published_counts.get(current, 0),
                    discovered_count=discovered_counts.get(current, 0),
                    fetch_run_count=fetch_row.get("fetch_run_count", 0),
                    fetched_count=fetch_row.get("fetched_count", 0),
                    new_count=fetch_row.get("new_count", 0),
                    duplicate_count=fetch_row.get("duplicate_count", 0),
                    error_count=fetch_row.get("error_count", 0),
                )
            )
            current += timedelta(days=1)
        return result

    def _daily_article_counts(  # pylint: disable=not-callable
        self,
        *,
        field: Any,
        start_at: datetime,
        end_at: datetime,
    ) -> dict[date, int]:
        day_expr = func.date(field)
        stmt = (
            select(day_expr, func.count(Article.id))
            .where(field >= start_at)
            .where(field < end_at)
            .group_by(day_expr)
        )
        return {
            self._coerce_stat_date(row[0]): int(row[1] or 0)
            for row in self.session.execute(stmt).all()
        }

    def _daily_fetch_stats(  # pylint: disable=not-callable
        self,
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> dict[date, dict[str, int]]:
        day_expr = func.date(FetchRun.started_at)
        stmt = (
            select(
                day_expr,
                func.count(FetchRun.id),
                func.coalesce(func.sum(FetchRun.fetched_count), 0),
                func.coalesce(func.sum(FetchRun.new_count), 0),
                func.coalesce(func.sum(FetchRun.duplicate_count), 0),
                func.coalesce(func.sum(FetchRun.error_count), 0),
            )
            .where(FetchRun.started_at >= start_at)
            .where(FetchRun.started_at < end_at)
            .group_by(day_expr)
        )
        return {
            self._coerce_stat_date(row[0]): {
                "fetch_run_count": int(row[1] or 0),
                "fetched_count": int(row[2] or 0),
                "new_count": int(row[3] or 0),
                "duplicate_count": int(row[4] or 0),
                "error_count": int(row[5] or 0),
            }
            for row in self.session.execute(stmt).all()
        }

    @staticmethod
    def _coerce_stat_date(value: object) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return date.fromisoformat(value[:10])
        raise TypeError(f"Expected date-like daily stat value, got {type(value)!r}")


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
        if get_settings().weekly_v2_enabled:
            payload = WeeklyStore(self.session).published(report_date)
            if payload is not None:
                return self._hydrate_v2(payload)
            stored_report = self._get_stored_report(report_date=report_date)
            if stored_report is not None:
                return self._hydrate_stored_report(stored_report)
            return WeeklyAnalyticsReport(
                report_date, report_date - timedelta(days=6), report_date,
                "Weekly attention analytics are awaiting a verified snapshot.", [], [], [],
                metadata={"status": "insufficient_data", "quality": {"reason": "coverage_unknown"},
                          "section_status": {s: empty_section(s, "coverage_unknown")
                                             for s in SECTION_STATES}},
            )
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
        if get_settings().weekly_v2_enabled:
            latest = self.session.scalar(select(func.max(WeeklyPublication.report_date)).where(
                WeeklyPublication.snapshot_id.is_not(None)))
            if latest is not None:
                value = max(value, latest) if value else latest
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
        if get_settings().weekly_v2_enabled:
            snapshots = self.session.scalars(select(WeeklySnapshot).join(
                WeeklyPublication, WeeklyPublication.snapshot_id == WeeklySnapshot.id,
            ).order_by(WeeklySnapshot.report_date.desc()).limit(limit)).all()
            by_date = {entry.report_date: entry for entry in entries}
            for snapshot in snapshots:
                payload = json.loads(snapshot.payload)
                by_date[snapshot.report_date] = WeeklyAnalyticsReportIndexEntry(
                    snapshot.report_date, date.fromisoformat(payload["date_from"]),
                    snapshot.report_date, payload["summary"], snapshot.generated_at)
            entries = sorted(by_date.values(), key=lambda entry: entry.report_date, reverse=True)
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
            store = WeeklyStore(self.session)
            store.lock_date(report_date)
            if store.published(report_date) is not None:
                raise ValueError(
                    "A verified weekly revision cannot be overwritten by a legacy report")
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

    @staticmethod
    def _hydrate_v2(payload: dict) -> WeeklyAnalyticsReport:
        def items(section: str) -> list[WeeklyAnalyticsItem]:
            return [WeeklyAnalyticsItem(
                title=row["title"], summary=row["summary"], url=row["url"],
                details={k: v for k, v in row.items() if k not in {"title", "summary", "url"}},
            ) for row in payload[section][:5]]

        return WeeklyAnalyticsReport(
            report_date=date.fromisoformat(payload["report_date"]),
            date_from=date.fromisoformat(payload["date_from"]),
            date_to=date.fromisoformat(payload["date_to"]), summary=payload["summary"],
            new=items("new"), trending_up=items("trending_up"),
            trending_down=items("trending_down"),
            metadata={k: v for k, v in payload.items() if k not in {
                "report_date", "date_from", "date_to", "summary", "new", "trending_up",
                "trending_down", "assignments", "included_observation_ids", "input_fingerprint",
                "topic_registry", "event_ambiguities", "excluded_observations",
            }},
        )

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
        from app.core.sources.onboarding import (  # pylint: disable=import-outside-toplevel
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
