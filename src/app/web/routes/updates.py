"""Update settings and manual update runs (admin)."""

from fastapi import APIRouter, HTTPException

from app.web.models import UpdateStatus, WebUpdateSettings
from app.web.routes import WebDeps


def build_updates_router(deps: WebDeps) -> APIRouter:
    settings_store = deps.settings_store
    update_service = deps.update_service
    router = APIRouter()

    @router.get("/api/update/settings", response_model=WebUpdateSettings)
    def get_update_settings() -> WebUpdateSettings:
        return settings_store.load()

    @router.put("/api/update/settings", response_model=WebUpdateSettings)
    def put_update_settings(payload: WebUpdateSettings) -> WebUpdateSettings:
        return settings_store.save(payload)

    @router.post("/api/update/run", response_model=UpdateStatus)
    def run_update() -> UpdateStatus:
        runtime_settings = settings_store.load()
        status = update_service.start(runtime_settings)
        if status is None:
            raise HTTPException(status_code=409, detail="Update run is already active")
        return status

    @router.get("/api/update/status", response_model=UpdateStatus)
    def get_update_status() -> UpdateStatus:
        return update_service.current_status()

    return router
