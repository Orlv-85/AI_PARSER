"""News list, export, daily links feed and article detail.

The article route is a separate router: `/api/news/{article_id}` must be registered after every
fixed `/api/news/<name>` path of the other routers.
"""

import json
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.categories import READABLE_CATEGORIES
from app.usecases.news_reads import (
    ArticleRow,
    ViewFilter,
    agent_article,
    agent_rows,
    news_rows,
)
from app.web.models import DigestLinkFeedItem, NewsArticleDetail, NewsItem
from app.web.routes import WebDeps
from app.web.routes.common import _http_errors


def _article_category_metadata(article: object) -> dict[str, Any]:
    category = getattr(article, "category", None)
    result: dict[str, Any] = {}
    if isinstance(category, str) and category in READABLE_CATEGORIES:
        result.update(category=category,
                      category_confidence=getattr(article, "category_confidence", None))
    for name in ("publication_status", "publication_precision", "publication_day",
                 "modified_at", "material_type"):
        value = getattr(article, name, None)
        if value is not None:
            result[name] = value
    try:
        products = getattr(article, "compared_products", None)
        if products is not None:
            result["compared_products"] = json.loads(products)
        raw_dates = getattr(article, "date_provenance", None)
        if raw_dates is not None:
            dates = json.loads(raw_dates)
            literal = (dates.get("published", {}).get("selected") or {}).get("literal")
            if literal is not None:
                result["publication_literal"] = literal
    except (TypeError, ValueError, AttributeError):
        pass
    return result


class _NewsWindow(BaseModel):
    hours: int = Field(24, ge=1, le=720)
    limit: int = Field(30, ge=1, le=200)
    min_ai_relevance: float = Field(0.2, ge=0.0, le=1.0)
    query: str | None = None
    days: int = Field(7, ge=1, le=365)
    sort: str = Field("rank", pattern="^(rank|published|category)$")
    category: str | None = None


class NewsQuery(_NewsWindow):
    """Query of `/api/news`; field order is the order of the OpenAPI parameters."""

    date_from: date | None = None
    date_to: date | None = None


class NewsExportQuery(_NewsWindow):
    """Query of `/api/news/export`: `include_content` sits before the date range."""

    include_content: bool = False
    date_from: date | None = None
    date_to: date | None = None


def _view(news: NewsQuery | NewsExportQuery) -> ViewFilter:
    """`list_for_view` filter: a date range replaces the `hours` window."""
    has_date_range = news.date_from is not None or news.date_to is not None
    return ViewFilter(
        hours=None if has_date_range else news.hours, days=news.days, sort=news.sort,
        query=news.query, min_ai_relevance=news.min_ai_relevance,
        date_from=news.date_from, date_to=news.date_to, category=news.category,
    )


class LinksQuery(BaseModel):
    """Query of `/api/news/links`."""

    target_date: date = Field(alias="date")
    limit: int = Field(30, ge=1, le=200)
    offset: int = Field(0, ge=0)
    min_ai_relevance: float = Field(0.2, ge=0.0, le=1.0)
    include_content: bool = False


def _link_item(article: Any, source_key: str | None, source_name: str | None,
               include_content: bool) -> DigestLinkFeedItem:
    rank = ({"rank_score": article.rank_score}
            if include_content and hasattr(article, "rank_score") else {})
    content = ({"summary": article.summary,
                "content": article.content[:12000] if article.content else None}
               if include_content else {})
    return DigestLinkFeedItem(
        article_id=article.id,
        title=article.title,
        published_at=article.published_at,
        url=article.url,
        url_canonical=article.url_canonical,
        source_id=article.source_id,
        source_key=source_key,
        source_name=source_name,
        **_article_category_metadata(article),
        **rank,
        **content,
    )


def _news_rows(deps: WebDeps, news: NewsQuery | NewsExportQuery) -> list[ArticleRow]:
    with _http_errors():
        deps.create_all()
        rows: list[ArticleRow] = news_rows(deps.SessionLocal, _view(news), limit=news.limit)
        return rows


def _news_items(rows: list[ArticleRow]) -> list[NewsItem]:
    return [_news_item(*row) for row in rows]


def _news_item(article: Any, source_key: str | None, source_name: str | None) -> NewsItem:
    return NewsItem(
        title=article.title,
        published_at=article.published_at,
        rank_score=article.rank_score,
        url_canonical=article.url_canonical,
        source_id=article.source_id,
        source_key=source_key,
        source_name=source_name,
        **_article_category_metadata(article),
    )


def _export_item(article: Any, source_key: str | None, source_name: str | None,
                 include_content: bool) -> dict[str, object | None]:
    item: dict[str, object | None] = {
        "article_id": article.id,
        "title": article.title,
        "published_at": article.published_at,
        "rank_score": article.rank_score,
        "url_canonical": article.url_canonical,
        "source_id": article.source_id,
        "source_key": source_key,
        "source_name": source_name,
    }
    if include_content:
        item["summary"] = article.summary
        item["content"] = article.content
        item["url"] = article.url
    item.update(_article_category_metadata(article))
    return item


def _export_response(rows: list[ArticleRow], include_content: bool) -> JSONResponse:
    payload = [_export_item(article, source_key, source_name, include_content)
               for article, source_key, source_name in rows]
    filename = datetime.now(UTC).strftime("news-export-%Y%m%dT%H%M%SZ.json")
    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _links_response(deps: WebDeps, links: LinksQuery, include_content: bool
                    ) -> list[DigestLinkFeedItem]:
    view = ViewFilter(hours=None, days=1, sort="published",
                      min_ai_relevance=links.min_ai_relevance,
                      date_from=links.target_date, date_to=links.target_date)
    with _http_errors():
        deps.create_all()
        rows = agent_rows(deps.SessionLocal, view, limit=links.limit, offset=links.offset)
    return [_link_item(article, source_key, source_name, include_content)
            for article, source_key, source_name in rows]


def _article_response(deps: WebDeps, article_id: int) -> NewsArticleDetail:
    with _http_errors():
        deps.create_all()
        row = agent_article(deps.SessionLocal, article_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")

    article, source_key, source_name = row
    return NewsArticleDetail(
        article_id=article.id,
        title=article.title,
        summary=article.summary,
        content=article.content,
        published_at=article.published_at,
        rank_score=article.rank_score,
        url=article.url,
        url_canonical=article.url_canonical,
        source_id=article.source_id,
        source_key=source_key,
        source_name=source_name,
        **_article_category_metadata(article),
    )


def build_news_router(deps: WebDeps) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/news", response_model=list[NewsItem], response_model_exclude_unset=True,
    )
    def list_news(news: Annotated[NewsQuery, Query()]) -> list[NewsItem]:
        return _news_items(_news_rows(deps, news))

    @router.get("/api/news/export")
    def export_news(news: Annotated[NewsExportQuery, Query()]) -> JSONResponse:
        return _export_response(_news_rows(deps, news), news.include_content)

    @router.get(
        "/api/news/links",
        response_model=list[DigestLinkFeedItem],
        response_model_exclude_unset=True,
    )
    def list_news_links(links: Annotated[LinksQuery, Query()], request: Request
                        ) -> list[DigestLinkFeedItem]:
        # Without a session or the publish token the content fields are left out (set by
        # the auth middleware); the answer is otherwise the same, so old clients keep working.
        return _links_response(
            deps, links,
            links.include_content and getattr(request.state, "full_text_allowed", False),
        )

    return router


def build_news_article_router(deps: WebDeps) -> APIRouter:
    router = APIRouter()

    @router.get("/api/news/{article_id}", response_model=NewsArticleDetail)
    def get_news_article(article_id: int) -> NewsArticleDetail:
        return _article_response(deps, article_id)

    return router
