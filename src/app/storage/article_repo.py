from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, cast

from sqlalchemy import Select, case, delete, desc, func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.categories import CATEGORY_ORDER
from app.storage.models_sql import Article, ArticleAlias, FetchRun, Source

_ROW_SCORES = ("ai_relevance_score", "freshness_score", "rank_score")


@dataclass(frozen=True)
class ViewFilter:  # pylint: disable=too-many-instance-attributes
    """Which articles a list shows: a `hours` window, or `days` with a date range; text; order."""

    hours: int | None
    days: int
    sort: str
    query: str | None = None
    min_ai_relevance: float = 0.0
    date_from: date | None = None
    date_to: date | None = None
    category: str | None = None


def _publication_since(moment: datetime):
    return or_(Article.published_at >= moment,
               Article.published_at.is_(None) & (Article.publication_day >= moment.date()))


def _publication_before(moment: datetime):
    return or_(Article.published_at < moment,
               Article.published_at.is_(None) & (Article.publication_day < moment.date()))


def _text_match(query: str):
    ilike = f"%{query}%"
    return (Article.title.ilike(ilike)
            | Article.summary.ilike(ilike)
            | Article.content.ilike(ilike))


def _view_window(*, hours: int | None, days: int, query: str | None,
                 date_from: date | None, date_to: date | None) -> list:
    """An explicit date range wins; otherwise a search looks back `days`, a listing `hours`."""
    if date_from is None and date_to is None:
        span = timedelta(days=days) if query else timedelta(hours=24 if hours is None else hours)
        return [_publication_since(datetime.now(UTC) - span)]
    conditions = []
    if date_from is not None:
        conditions.append(_publication_since(datetime.combine(date_from, time.min, tzinfo=UTC)))
    if date_to is not None:
        end_at = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
        conditions.append(_publication_before(end_at))
    return conditions


def _view_order(sort: str) -> tuple:
    if sort == "category":
        return (
            case(
                {name: index for index, name in enumerate(CATEGORY_ORDER)},
                value=Article.category, else_=len(CATEGORY_ORDER),
            ),
            Article.rank_score.desc(),
            Article.published_at.desc().nulls_last(),
        )
    if sort == "published":
        return Article.published_at.desc().nulls_last(), desc(Article.rank_score)
    return Article.rank_score.desc(), Article.published_at.desc().nulls_last()


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
        stmt: Select[Article] = (
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

    def upsert_articles_batch(self, rows: list[dict[str, Any]]) -> tuple[int, int]:  # pylint: disable=too-many-locals
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
            _, is_new = self.insert_article(row)
            if is_new:
                actual_new += 1
            else:
                actual_duplicates += 1
        actual_duplicates += input_duplicates
        return actual_new, actual_duplicates

    def insert_article(self, row: Mapping[str, Any]) -> tuple[Article, bool]:
        """Insert `row` (`Article` columns) as a new article, or refresh the scores and category
        of the article stored under its canonical hash; returns (article, is_new)."""
        existing_stmt: Select[Article] = select(Article).where(
            Article.url_canonical_hash == row["url_canonical_hash"]
        )
        existing = self.session.execute(existing_stmt).scalar_one_or_none()
        scores = {name: row.get(name, 0.0) for name in _ROW_SCORES}
        if existing is not None:
            for name, value in scores.items():
                setattr(existing, name, value)
            if row.get("category") is not None:
                existing.category = row["category"]
                existing.category_confidence = row.get("category_confidence")
            return existing, False

        article = Article(**{**row, **scores, "title": row["title"][:self._TITLE_MAX_LEN],
                             "discovered_at": datetime.now(UTC)})
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
        stmt: Select[Article] = (
            select(Article)
            .where(_publication_since(window_start))
            .where(Article.ai_relevance_score >= min_ai_relevance)
            .order_by(Article.rank_score.desc(), Article.published_at.desc().nulls_last())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def search(self, *, query: str, days: int = 7, limit: int = 100) -> list[Article]:
        window_start = datetime.now(UTC) - timedelta(days=days)
        stmt: Select[Article] = (
            select(Article)
            .where(_publication_since(window_start))
            .where(_text_match(query))
            .order_by(Article.published_at.desc().nulls_last())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def list_for_view(
        self, view: ViewFilter, *, limit: int, offset: int = 0,
    ) -> list[tuple[Article, str | None, str | None]]:
        base_stmt = (
            select(Article, Source.source_key, Source.name)
            .outerjoin(Source, Article.source_id == Source.id)
            .where(Article.ai_relevance_score >= view.min_ai_relevance)
        )
        if view.category is not None:
            base_stmt = base_stmt.where(Article.category == view.category)
        base_stmt = base_stmt.where(*_view_window(
            hours=view.hours, days=view.days, query=view.query, date_from=view.date_from,
            date_to=view.date_to))
        if view.query:
            base_stmt = base_stmt.where(_text_match(view.query))
        base_stmt = base_stmt.order_by(*_view_order(view.sort)).limit(limit).offset(offset)
        return [
            (row[0], row[1], row[2])
            for row in self.session.execute(base_stmt).all()
        ]

    def list_for_agent(
        self, view: ViewFilter, *, limit: int, offset: int = 0,
    ) -> list[tuple[Article, str | None, str | None]]:
        return self.list_for_view(view, limit=limit, offset=offset)

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

    def prune_older_than(self, *, older_than_days: int,
                         archive: Callable[[list[Article]], object]) -> tuple[int, int]:
        """Delete rows past the cutoff; `archive` gets them first, in the same transaction (016)."""
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        old_article_ids = select(Article.id).where(_publication_before(cutoff))

        deleted_aliases_stmt = select(ArticleAlias.id).where(
            ArticleAlias.article_id.in_(old_article_ids)
        )
        deleted_aliases = len(self.session.scalars(deleted_aliases_stmt).all())
        old_articles = list(
            self.session.scalars(select(Article).where(_publication_before(cutoff))))
        deleted_articles = len(old_articles)
        archive(old_articles)

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
            # The >= / <= filters drop rows without a publication_day.
            key = cast(date, day)
            published_counts[key] = published_counts.get(key, 0) + int(count)
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
