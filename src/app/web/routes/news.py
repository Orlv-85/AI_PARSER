"""News list, export, daily links feed and article detail.

The article route is a separate router: `/api/news/{article_id}` must be registered after every
fixed `/api/news/<name>` path of the other routers.
"""

import json
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.categories import READABLE_CATEGORIES
from app.usecases.news_reads import agent_article, agent_rows, news_rows
from app.web.models import DigestLinkFeedItem, NewsArticleDetail, NewsItem
from app.web.routes import WebDeps

_NEWS_LINKS_DATE_QUERY = Query(alias="date")


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


def _view_filters(*, hours: int, date_from: date | None, date_to: date | None,
                  category: str | None, **filters: object) -> dict[str, object]:
    """`list_for_view` arguments: a date range replaces the `hours` window."""
    has_date_range = date_from is not None or date_to is not None
    found: dict[str, object] = {"hours": None if has_date_range else hours, **filters}
    if has_date_range:
        found.update(date_from=date_from, date_to=date_to)
    if category is not None:
        found["category"] = category
    return found


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


def build_news_router(deps: WebDeps) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/news", response_model=list[NewsItem], response_model_exclude_unset=True,
    )
    def list_news(
        *,
        hours: int = Query(24, ge=1, le=720),
        limit: int = Query(30, ge=1, le=200),
        min_ai_relevance: float = Query(0.2, ge=0.0, le=1.0),
        query: str | None = None,
        days: int = Query(7, ge=1, le=365),
        sort: str = Query("rank", pattern="^(rank|published|category)$"),
        category: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[NewsItem]:
        try:
            deps.create_all()
            rows = news_rows(deps.SessionLocal, **_view_filters(
                hours=hours, date_from=date_from, date_to=date_to, category=category,
                limit=limit, min_ai_relevance=min_ai_relevance, query=query, days=days,
                sort=sort))
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return [
            NewsItem(
                title=article.title,
                published_at=article.published_at,
                rank_score=article.rank_score,
                url_canonical=article.url_canonical,
                source_id=article.source_id,
                source_key=source_key,
                source_name=source_name,
                **_article_category_metadata(article),
            )
            for article, source_key, source_name in rows
        ]

    @router.get("/api/news/export")
    def export_news(
        *,
        hours: int = Query(24, ge=1, le=720),
        limit: int = Query(30, ge=1, le=200),
        min_ai_relevance: float = Query(0.2, ge=0.0, le=1.0),
        query: str | None = None,
        days: int = Query(7, ge=1, le=365),
        sort: str = Query("rank", pattern="^(rank|published|category)$"),
        category: str | None = None,
        include_content: bool = False,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> JSONResponse:
        try:
            deps.create_all()
            rows = news_rows(deps.SessionLocal, **_view_filters(
                hours=hours, date_from=date_from, date_to=date_to, category=category,
                limit=limit, min_ai_relevance=min_ai_relevance, query=query, days=days,
                sort=sort, include_content=include_content))
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        payload: list[dict[str, object | None]] = []
        for article, source_key, source_name in rows:
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
            payload.append(item)

        filename = datetime.now(UTC).strftime("news-export-%Y%m%dT%H%M%SZ.json")
        return JSONResponse(
            content=jsonable_encoder(payload),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.get(
        "/api/news/links",
        response_model=list[DigestLinkFeedItem],
        response_model_exclude_unset=True,
    )
    def list_news_links(
        *,
        target_date: date = _NEWS_LINKS_DATE_QUERY,
        limit: int = Query(30, ge=1, le=200),
        offset: int = Query(0, ge=0),
        min_ai_relevance: float = Query(0.2, ge=0.0, le=1.0),
        include_content: bool = False,
        request: Request,
    ) -> list[DigestLinkFeedItem]:
        # Without a session or the publish token the content fields are left out (set by
        # the auth middleware); the answer is otherwise the same, so old clients keep working.
        include_content = include_content and getattr(request.state, "full_text_allowed", False)
        try:
            deps.create_all()
            rows = agent_rows(
                deps.SessionLocal,
                hours=None,
                limit=limit,
                offset=offset,
                query=None,
                days=1,
                sort="published",
                min_ai_relevance=min_ai_relevance,
                date_from=target_date,
                date_to=target_date,
            )
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

        return [_link_item(article, source_key, source_name, include_content)
                for article, source_key, source_name in rows]

    return router


def build_news_article_router(deps: WebDeps) -> APIRouter:
    router = APIRouter()

    @router.get("/api/news/{article_id}", response_model=NewsArticleDetail)
    def get_news_article(article_id: int) -> NewsArticleDetail:
        try:
            deps.create_all()
            row = agent_article(deps.SessionLocal, article_id)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc

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

    return router
