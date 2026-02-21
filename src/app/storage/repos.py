from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, delete, desc, select
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


class ArticleRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

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
        hours: int,
        limit: int,
        query: str | None,
        days: int,
        sort: str,
        min_ai_relevance: float = 0.0,
    ) -> list[tuple[Article, str | None, str | None]]:
        base_stmt = (
            select(Article, Source.source_key, Source.name)
            .outerjoin(Source, Article.source_id == Source.id)
            .where(Article.ai_relevance_score >= min_ai_relevance)
            .limit(limit)
        )
        if query:
            window_start = datetime.now(UTC) - timedelta(days=days)
            ilike = f"%{query}%"
            base_stmt = (
                base_stmt.where(Article.published_at >= window_start)
                .where(
                    Article.title.ilike(ilike)
                    | Article.summary.ilike(ilike)
                    | Article.content.ilike(ilike)
                )
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
            window_start = datetime.now(UTC) - timedelta(hours=hours)
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
