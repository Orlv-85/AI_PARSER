"""Stored bulletin API; contract: src/app/storage/bulletin_store.md."""
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from app.usecases.bulletin.stored import stored_bulletin
from app.web.routes import WebDeps

_DATE_QUERY = Query(None, alias="date")


def parse_day(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        day = date.fromisoformat(value)
        if day.isoformat() != value:
            raise ValueError("Expected YYYY-MM-DD")
        return day
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD") from exc


def build_bulletin_router(deps: WebDeps) -> APIRouter:
    router = APIRouter()

    @router.get("/api/news/bulletin")
    def get_bulletin(*, target_date: str | None = _DATE_QUERY) -> dict[str, Any]:
        day = parse_day(target_date)
        try:
            deps.create_all()
            row = stored_bulletin(deps.SessionLocal, day)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="News storage is unavailable") from exc
        if row is None:
            raise HTTPException(status_code=404, detail="Bulletin not found")
        return {"day": row.day, "status": row.status, "reason": row.reason,
                "payload": row.payload, "numbers": row.numbers, "versions": row.versions,
                "generated_at": row.generated_at}

    return router
