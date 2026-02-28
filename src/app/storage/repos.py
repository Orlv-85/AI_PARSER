from datetime import UTC, date, datetime, time, timedelta
from typing import Any, cast

from sqlalchemy import Select, delete, desc, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config.sources import SourceConfig
from app.storage.models_sql import Article, ArticleAlias, Source


class SourceRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_source(self, source_config: SourceConfig) -> Source:
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
