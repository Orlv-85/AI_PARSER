"""Article reads of the news API: each opens its own session and writes nothing."""

from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.storage.article_repo import ArticleDailyStats, ArticleRepo
from app.storage.models_sql import Article

type ArticleRow = tuple[Article, str | None, str | None]


def news_rows(session_factory: Callable[[], Session], **filters: Any) -> list[ArticleRow]:
    """Articles with source key and name for the list and the export."""
    with session_factory() as session:
        rows: list[ArticleRow] = ArticleRepo(session).list_for_view(**filters)
        return rows


def agent_rows(session_factory: Callable[[], Session], **filters: Any) -> list[ArticleRow]:
    """Articles with source key and name for the daily links feed."""
    with session_factory() as session:
        rows: list[ArticleRow] = ArticleRepo(session).list_for_agent(**filters)
        return rows


def agent_article(session_factory: Callable[[], Session], article_id: int) -> ArticleRow | None:
    """One article with source key and name; None when it does not exist."""
    with session_factory() as session:
        row: ArticleRow | None = ArticleRepo(session).get_article_for_agent(article_id=article_id)
        return row


def daily_stats(session_factory: Callable[[], Session], date_from: date, date_to: date
                ) -> list[ArticleDailyStats]:
    """Article and fetch counts per day of the range."""
    with session_factory() as session:
        stats: list[ArticleDailyStats] = ArticleRepo(session).daily_stats(
            date_from=date_from, date_to=date_to)
        return stats


def top_articles(session_factory: Callable[[], Session], *, hours: int, limit: int,
                 min_ai_relevance: float) -> list[Article]:
    """Top ranked articles of the window (CLI `top`)."""
    with session_factory() as session:
        rows: list[Article] = ArticleRepo(session).query_top(
            hours=hours, limit=limit, min_ai_relevance=min_ai_relevance)
        return rows


def search_articles(session_factory: Callable[[], Session], *, query: str, days: int
                    ) -> list[Article]:
    """Articles matching `query` (CLI `search`)."""
    with session_factory() as session:
        rows: list[Article] = ArticleRepo(session).search(query=query, days=days)
        return rows
