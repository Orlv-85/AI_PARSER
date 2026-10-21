"""Web routers by area; `create_app` in `app.web.app` builds `WebDeps` and includes them."""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.web.auth import SessionSigner
from app.web.service import UpdateRunService
from app.web.settings_store import UpdateSettingsStore
from app.web.source_intake import SourceIntakeService


@dataclass(frozen=True)
class WebDeps:  # pylint: disable=too-many-instance-attributes
    """Objects built once by `create_app` and shared by the routers."""

    settings: Settings
    settings_store: UpdateSettingsStore
    update_service: UpdateRunService
    onboarding_engine: Engine
    onboarding_session_local: Callable[[], Session]
    source_intake: SourceIntakeService
    auth_enabled: bool
    signer: SessionSigner | None
    # News storage, read from `app.web.app` when the app is built (tests patch them there).
    SessionLocal: Callable[[], Session]  # pylint: disable=invalid-name
    create_all: Callable[[], None]
