from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.exc import SQLAlchemyError

from app.config.settings import get_settings
from app.storage import SessionLocal, create_all
from app.storage.repos import ArticleRepo
from app.web.models import NewsItem, UpdateStatus, WebUpdateSettings
from app.web.service import UpdateRunService
from app.web.settings_store import UpdateSettingsStore

_TEMPLATE = Path(__file__).with_name("index.html")


def _render_index() -> str:
    return _TEMPLATE.read_text(encoding="utf-8")


def create_app() -> FastAPI:
    settings_path = Path("data") / "web_update_settings.json"
    settings_store = UpdateSettingsStore(settings_path)
    update_service = UpdateRunService()

    api = FastAPI(title="AI News Collector Web")

    @api.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _render_index()

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/api/update/settings", response_model=WebUpdateSettings)
    def get_update_settings() -> WebUpdateSettings:
        return settings_store.load()

    @api.put("/api/update/settings", response_model=WebUpdateSettings)
    def put_update_settings(payload: WebUpdateSettings) -> WebUpdateSettings:
        return settings_store.save(payload)

    @api.post("/api/update/run", response_model=UpdateStatus)
    def run_update() -> UpdateStatus:
        runtime_settings = settings_store.load()
        status = update_service.start(runtime_settings)
        if status is None:
            raise HTTPException(status_code=409, detail="Update run is already active")
        return status

    @api.get("/api/update/status", response_model=UpdateStatus)
    def get_update_status() -> UpdateStatus:
        return update_service.current_status()

    @api.get("/api/news", response_model=list[NewsItem])
    def list_news(
        *,
        hours: int = Query(24, ge=1, le=720),
        limit: int = Query(30, ge=1, le=200),
        min_ai_relevance: float = Query(0.2, ge=0.0, le=1.0),
        query: str | None = None,
        days: int = Query(7, ge=1, le=365),
        sort: str = Query("rank", pattern="^(rank|published)$"),
    ) -> list[NewsItem]:
        try:
            _ = get_settings()
            create_all()
            with SessionLocal() as session:
                repo = ArticleRepo(session)
                rows = repo.list_for_view(
                    hours=hours,
                    limit=limit,
                    min_ai_relevance=min_ai_relevance,
                    query=query,
                    days=days,
                    sort=sort,
                )
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
            )
            for article, source_key, source_name in rows
        ]

    return api


app = create_app()
