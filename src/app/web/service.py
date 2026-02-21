import threading
from datetime import UTC, datetime
from logging import Logger

from app.config.settings import get_settings
from app.core.pipeline import run_fetch_cycle
from app.observability import setup_json_logging
from app.web.models import UpdateStatus, WebUpdateSettings


class UpdateRunService:
    def __init__(self, logger: Logger | None = None) -> None:
        self._lock = threading.Lock()
        self._status = UpdateStatus()
        self._logger = logger or setup_json_logging()

    def current_status(self) -> UpdateStatus:
        with self._lock:
            return self._status.model_copy(deep=True)

    def start(self, runtime_settings: WebUpdateSettings) -> UpdateStatus | None:
        with self._lock:
            if self._status.status == "running":
                self._logger.warning(
                    "update_run_rejected",
                    {"run_id": self._status.run_id, "reason": "already_running"},
                )
                return None
            run_id = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
            self._logger.info(
                "update_run_requested",
                {"run_id": run_id, "source_id": None, "trigger": "web"},
            )
            self._status = UpdateStatus(
                run_id=run_id,
                status="running",
                started_at=datetime.now(UTC),
                finished_at=None,
                fetched=0,
                new=0,
                duplicates=0,
                errors=0,
                error_message=None,
            )
            self._logger.info(
                "update_run_started",
                {"run_id": run_id, "source_id": None, "trigger": "web"},
            )

        thread = threading.Thread(
            target=self._run,
            args=(run_id, runtime_settings),
            daemon=True,
        )
        thread.start()
        return self.current_status()

    def _run(self, run_id: str, runtime_settings: WebUpdateSettings) -> None:
        base_settings = get_settings()
        merged_settings = base_settings.model_copy(
            update=runtime_settings.model_dump(mode="python")
        )

        try:
            summary = run_fetch_cycle(settings=merged_settings, logger=self._logger)
            with self._lock:
                self._status = UpdateStatus(
                    run_id=run_id,
                    status="finished",
                    started_at=self._status.started_at,
                    finished_at=datetime.now(UTC),
                    fetched=summary.fetched,
                    new=summary.new,
                    duplicates=summary.duplicates,
                    errors=summary.errors,
                    error_message=None,
                )
            self._logger.info(
                "update_run_finished",
                {
                    "run_id": run_id,
                    "source_id": None,
                    "status": "finished",
                    "fetched": summary.fetched,
                    "new": summary.new,
                    "duplicates": summary.duplicates,
                    "errors": summary.errors,
                },
            )
        except Exception as exc:
            with self._lock:
                self._status = UpdateStatus(
                    run_id=run_id,
                    status="failed",
                    started_at=self._status.started_at,
                    finished_at=datetime.now(UTC),
                    fetched=0,
                    new=0,
                    duplicates=0,
                    errors=1,
                    error_message=str(exc),
                )
            self._logger.error(
                "update_run_failed",
                {
                    "run_id": run_id,
                    "source_id": None,
                    "status": "failed",
                    "error_message": str(exc),
                },
            )
