import logging
from datetime import datetime
from time import sleep
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.storage import SessionLocal, create_all
from app.storage.repos import ArticleRepo
from app.web.models import WebUpdateSettings
from app.web.service import UpdateRunService

try:
    from fastmcp import FastMCP  # pylint: disable=import-error
except Exception:  # pragma: no cover - optional at runtime.
    FastMCP = None  # type: ignore[assignment]

_LOGGER = logging.getLogger(__name__)


class _ListParams(BaseModel):
    hours: int = Field(default=24, ge=1, le=720)
    limit: int = Field(default=30, ge=1, le=500)
    min_ai_relevance: float = Field(default=0.2, ge=0.0, le=1.0)
    query: str | None = None
    days: int = Field(default=7, ge=1, le=365)
    sort: str = Field(default="rank", pattern="^(rank|published)$")


class _UpdateParams(BaseModel):
    wait: bool = False
    poll_interval_seconds: float = Field(default=1.0, ge=0.1, le=30.0)
    max_wait_seconds: float = Field(default=300.0, ge=1.0, le=7200.0)
    request_timeout_seconds: float | None = Field(default=None, gt=0.0, le=120.0)
    max_retries: int | None = Field(default=None, ge=0, le=10)
    per_source_min_interval_seconds: float | None = Field(default=None, ge=0.0, le=60.0)
    concurrency_limit: int | None = Field(default=None, ge=1, le=64)


class MCPNewsService:
    def __init__(
        self,
        *,
        update_service: UpdateRunService | None = None,
        session_factory: Any = SessionLocal,
        create_all_fn: Any = create_all,
    ) -> None:
        self._update_service = update_service or UpdateRunService()
        self._session_factory = session_factory
        self._create_all = create_all_fn

    @staticmethod
    def _status_to_dict(status: Any) -> dict[str, Any]:
        return {
            "run_id": status.run_id,
            "status": status.status,
            "started_at": status.started_at.isoformat() if status.started_at else None,
            "finished_at": status.finished_at.isoformat() if status.finished_at else None,
            "fetched": status.fetched,
            "new": status.new,
            "duplicates": status.duplicates,
            "errors": status.errors,
            "error_message": status.error_message,
        }

    def news_update(self, **kwargs: Any) -> dict[str, Any]:
        try:
            params = _UpdateParams.model_validate(kwargs)
        except ValidationError as exc:
            _LOGGER.info("event=news.update outcome=validation_error detail=%s", exc)
            return {"ok": False, "error_type": "validation_error", "detail": str(exc)}

        runtime_settings = WebUpdateSettings(
            **{
                key: value
                for key, value in {
                    "request_timeout_seconds": params.request_timeout_seconds,
                    "max_retries": params.max_retries,
                    "per_source_min_interval_seconds": params.per_source_min_interval_seconds,
                    "concurrency_limit": params.concurrency_limit,
                }.items()
                if value is not None
            }
        )
        status = self._update_service.start(runtime_settings)
        if status is None:
            current = self._update_service.current_status()
            _LOGGER.info(
                "event=news.update outcome=already_running run_id=%s status=%s",
                current.run_id,
                current.status,
            )
            return {
                "ok": False,
                "error_type": "already_running",
                "status": self._status_to_dict(current),
            }

        payload = self._status_to_dict(status)
        if not params.wait:
            _LOGGER.info(
                "event=news.update outcome=started run_id=%s status=%s wait=%s",
                status.run_id,
                status.status,
                params.wait,
            )
            return {"ok": True, "status": payload}

        started_at = datetime.now()
        while (datetime.now() - started_at).total_seconds() < params.max_wait_seconds:
            current = self._update_service.current_status()
            if current.status in {"finished", "failed"}:
                _LOGGER.info(
                    "event=news.update outcome=terminal run_id=%s status=%s",
                    current.run_id,
                    current.status,
                )
                return {"ok": True, "status": self._status_to_dict(current)}
            if params.poll_interval_seconds > 0:
                sleep(params.poll_interval_seconds)
        _LOGGER.info(
            "event=news.update outcome=timeout run_id=%s",
            self._update_service.current_status().run_id,
        )
        return {
            "ok": False,
            "error_type": "timeout",
            "status": self._status_to_dict(self._update_service.current_status()),
        }

    def news_update_status(self) -> dict[str, Any]:
        status = self._update_service.current_status()
        _LOGGER.info(
            "event=news.update_status outcome=ok run_id=%s status=%s",
            status.run_id,
            status.status,
        )
        return {"ok": True, "status": self._status_to_dict(status)}

    def news_list(self, **kwargs: Any) -> dict[str, Any]:
        try:
            params = _ListParams.model_validate(kwargs)
        except ValidationError as exc:
            _LOGGER.info("event=news.list outcome=validation_error detail=%s", exc)
            return {"ok": False, "error_type": "validation_error", "detail": str(exc)}

        self._create_all()
        with self._session_factory() as session:
            repo = ArticleRepo(session)
            rows = repo.list_for_agent(
                hours=params.hours,
                limit=params.limit,
                min_ai_relevance=params.min_ai_relevance,
                query=params.query,
                days=params.days,
                sort=params.sort,
            )

        items = [
            {
                "article_id": article.id,
                "title": article.title,
                "published_at": article.published_at.isoformat(),
                "rank_score": article.rank_score,
                "url_canonical": article.url_canonical,
                "source_id": article.source_id,
                "source_key": source_key,
                "source_name": source_name,
                "has_content": bool(article.content and article.content.strip()),
            }
            for article, source_key, source_name in rows
        ]
        _LOGGER.info(
            "event=news.list outcome=ok count=%s hours=%s limit=%s sort=%s",
            len(items),
            params.hours,
            params.limit,
            params.sort,
        )
        return {"ok": True, "items": items, "count": len(items)}

    def news_get(self, *, article_id: int) -> dict[str, Any]:
        if article_id <= 0:
            _LOGGER.info(
                "event=news.get outcome=validation_error article_id=%s",
                article_id,
            )
            return {
                "ok": False,
                "error_type": "validation_error",
                "detail": "article_id must be positive",
            }

        self._create_all()
        with self._session_factory() as session:
            repo = ArticleRepo(session)
            row = repo.get_article_for_agent(article_id=article_id)

        if row is None:
            _LOGGER.info("event=news.get outcome=not_found article_id=%s", article_id)
            return {"ok": False, "error_type": "not_found", "detail": "article not found"}
        article, source_key, source_name = row
        _LOGGER.info("event=news.get outcome=ok article_id=%s", article_id)
        return {
            "ok": True,
            "item": {
                "article_id": article.id,
                "title": article.title,
                "summary": article.summary,
                "content": article.content,
                "published_at": article.published_at.isoformat(),
                "rank_score": article.rank_score,
                "url": article.url,
                "url_canonical": article.url_canonical,
                "source_id": article.source_id,
                "source_key": source_key,
                "source_name": source_name,
            },
        }


def build_mcp_server() -> Any:
    if FastMCP is None:
        raise RuntimeError(
            "fastmcp is not installed. Install project dependencies to run MCP server."
        )

    service = MCPNewsService()
    mcp = FastMCP("ai-news-collector")

    @mcp.tool(name="news.update")
    # pylint: disable=too-many-positional-arguments
    def news_update(  # type: ignore[misc]
        wait: bool = False,
        poll_interval_seconds: float = 1.0,
        max_wait_seconds: float = 300.0,
        request_timeout_seconds: float | None = None,
        max_retries: int | None = None,
        per_source_min_interval_seconds: float | None = None,
        concurrency_limit: int | None = None,
    ) -> dict[str, Any]:
        return service.news_update(
            wait=wait,
            poll_interval_seconds=poll_interval_seconds,
            max_wait_seconds=max_wait_seconds,
            request_timeout_seconds=request_timeout_seconds,
            max_retries=max_retries,
            per_source_min_interval_seconds=per_source_min_interval_seconds,
            concurrency_limit=concurrency_limit,
        )

    @mcp.tool(name="news.update_status")
    def news_update_status() -> dict[str, Any]:  # type: ignore[misc]
        return service.news_update_status()

    @mcp.tool(name="news.list")
    # pylint: disable=too-many-positional-arguments
    def news_list(  # type: ignore[misc]
        hours: int = 24,
        limit: int = 30,
        min_ai_relevance: float = 0.2,
        query: str | None = None,
        days: int = 7,
        sort: str = "rank",
    ) -> dict[str, Any]:
        return service.news_list(
            hours=hours,
            limit=limit,
            min_ai_relevance=min_ai_relevance,
            query=query,
            days=days,
            sort=sort,
        )

    @mcp.tool(name="news.get")
    def news_get(article_id: int) -> dict[str, Any]:  # type: ignore[misc]
        return service.news_get(article_id=article_id)

    return mcp


def run_mcp_server() -> None:
    mcp = build_mcp_server()
    mcp.run()
