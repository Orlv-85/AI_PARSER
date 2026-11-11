"""Article reads of the news API: each opens its own session and writes nothing."""

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.storage.article_repo import ArticleRepo
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
