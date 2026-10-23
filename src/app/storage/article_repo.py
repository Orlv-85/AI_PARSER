from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, cast

from sqlalchemy import Select, case, delete, desc, func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.categories import CATEGORY_ORDER
from app.storage.models_sql import Article, ArticleAlias, FetchRun, Source


def _publication_since(moment: datetime):
    return or_(Article.published_at >= moment,
               Article.published_at.is_(None) & (Article.publication_day >= moment.date()))


def _publication_before(moment: datetime):
    return or_(Article.published_at < moment,
               Article.published_at.is_(None) & (Article.publication_day < moment.date()))


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
        """Delete rows past the cutoff; archives them first in the same transaction (016)."""
        # Local import: app.storage/__init__ imports this module, and capture imports app.storage.
        from app.core.archive.capture import archive_articles  # pylint: disable=import-outside-toplevel
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        old_article_ids = select(Article.id).where(_publication_before(cutoff))

        deleted_aliases_stmt = select(ArticleAlias.id).where(
            ArticleAlias.article_id.in_(old_article_ids)
        )
        deleted_aliases = len(self.session.scalars(deleted_aliases_stmt).all())
        old_articles = list(
            self.session.scalars(select(Article).where(_publication_before(cutoff))))
        deleted_articles = len(old_articles)
        archive_articles(self.session, old_articles)

        self.session.execute(delete(ArticleAlias).where(ArticleAlias.article_id.in_(old_article_ids)))
        # The archived rows are loaded; "fetch" avoids evaluating the cutoff on naive SQLite values.
        self.session.execute(delete(Article).where(_publication_before(cutoff))
                             .execution_options(synchronize_session="fetch"))
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
