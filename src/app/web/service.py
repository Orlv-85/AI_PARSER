import json
import multiprocessing
import threading
from datetime import UTC, datetime
from logging import Logger
from pathlib import Path
from queue import Empty
from typing import Any, cast

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.core.ingestion.pipeline import run_fetch_cycle
from app.observability import setup_json_logging
from app.storage import SessionLocal
from app.storage.admission import PAUSED_MESSAGE, read_collection_status
from app.web.models import UpdateStatus, WebUpdateSettings

_DEFAULT_PROCESS_RESULT_DIR = Path("tmp/web_update_results")


def _coerce_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _run_offloaded_fetch_cycle(
    _run_id: str,
    runtime_settings_payload: dict[str, object],
    result_path_str: str,
    result_queue: object | None,
) -> None:
    result_payload: dict[str, object]
    runtime_settings = WebUpdateSettings.model_validate(runtime_settings_payload)
    base_settings = get_settings()
    merged_settings = base_settings.model_copy(
        update=runtime_settings.model_dump(
            mode="python",
            exclude={"update_execution_mode"},
        )
    )

    try:
        summary = run_fetch_cycle(settings=merged_settings, logger=setup_json_logging())
        result_payload = {
            "status": "finished",
            "source_count": int(getattr(summary, "source_count", 0)),
            "fetched": summary.fetched,
            "new": summary.new,
            "duplicates": summary.duplicates,
            "errors": summary.errors,
            "error_message": None,
        }
        if bool(getattr(summary, "screening_paused", 0)):
            result_payload["screening_paused"] = 1
            result_payload["screening_message"] = PAUSED_MESSAGE
    except Exception as exc:  # pragma: no cover - exercised via service polling
        result_payload = {
            "status": "failed",
            "fetched": 0,
            "new": 0,
            "duplicates": 0,
            "errors": 1,
            "error_message": str(exc),
        }

    if result_queue is not None:
        put_nowait = getattr(result_queue, "put_nowait", None)
        if callable(put_nowait):
            put_nowait(result_payload)
        else:
            putter = getattr(result_queue, "put", None)
            if callable(putter):
                putter(result_payload)

    result_path = Path(result_path_str)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(result_payload, ensure_ascii=True),
        encoding="utf-8",
    )


class UpdateRunService:
    def __init__(self, logger: Logger | None = None) -> None:
        self._lock = threading.Lock()
        self._status = UpdateStatus()
        self._logger = logger or setup_json_logging()
        self._worker_process: Any | None = None
        self._worker_queue: Any | None = None
        self._worker_result_path: Path | None = None

    def current_status(self) -> UpdateStatus:
        with self._lock:
            self._harvest_process_result_locked()
            self._apply_screening_status_locked()
            return self._status.model_copy(deep=True)

    def _apply_screening_status_locked(self) -> None:
        try:
            with SessionLocal() as session:
                paused, message = read_collection_status(session)
        except Exception:
            return
        self._status.screening_paused = paused
        self._status.screening_message = message

    def start(self, runtime_settings: WebUpdateSettings) -> UpdateStatus | None:
        with self._lock:
            self._harvest_process_result_locked()
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
                source_count=0,
                fetched=0,
                new=0,
                duplicates=0,
                errors=0,
                error_message=None,
            )
            self._apply_screening_status_locked()
            self._logger.info(
                "update_run_started",
                {"run_id": run_id, "source_id": None, "trigger": "web"},
            )

        if runtime_settings.update_execution_mode == "process":
            self._start_process_locked(run_id, runtime_settings)
        else:
            self._start_thread_locked(run_id, runtime_settings)

        with self._lock:
            return self._status.model_copy(deep=True)

    def _start_thread_locked(
        self, run_id: str, runtime_settings: WebUpdateSettings
    ) -> None:
        thread = threading.Thread(
            target=self._run,
            args=(run_id, runtime_settings),
            daemon=True,
        )
        thread.start()

    def _start_process_locked(
        self, run_id: str, runtime_settings: WebUpdateSettings
    ) -> None:
        result_path = _DEFAULT_PROCESS_RESULT_DIR / f"{run_id}.json"
        worker_queue: Any = multiprocessing.Queue()
        worker_process = multiprocessing.Process(
            target=_run_offloaded_fetch_cycle,
            args=(
                run_id,
                runtime_settings.model_dump(mode="python"),
                str(result_path),
                worker_queue,
            ),
            daemon=True,
        )
        worker_process.start()
        with self._lock:
            self._worker_result_path = result_path
            self._worker_queue = worker_queue
            self._worker_process = worker_process

    def _run(self, run_id: str, runtime_settings: WebUpdateSettings) -> None:
        base_settings = get_settings()
        merged_settings = base_settings.model_copy(
            update=runtime_settings.model_dump(
                mode="python",
                exclude={"update_execution_mode"},
            )
        )

        try:
            summary = run_fetch_cycle(settings=merged_settings, logger=self._logger)
            screening_paused = bool(getattr(summary, "screening_paused", 0))
            with self._lock:
                self._status = UpdateStatus(
                    run_id=run_id,
                    status="finished",
                    started_at=self._status.started_at,
                    finished_at=datetime.now(UTC),
                    source_count=int(getattr(summary, "source_count", 0)),
                    fetched=summary.fetched,
                    new=summary.new,
                    duplicates=summary.duplicates,
                    errors=summary.errors,
                    error_message=None,
                    screening_paused=screening_paused,
                    screening_message=PAUSED_MESSAGE if screening_paused else None,
                )
                self._apply_screening_status_locked()
            self._logger.info(
                "update_run_finished",
                {
                    "run_id": run_id,
                    "source_id": None,
                    "status": "finished",
                    "source_count": int(getattr(summary, "source_count", 0)),
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
                    source_count=0,
                    fetched=0,
                    new=0,
                    duplicates=0,
                    errors=1,
                    error_message=str(exc),
                )
                self._apply_screening_status_locked()
            self._logger.error(
                "update_run_failed",
                {
                    "run_id": run_id,
                    "source_id": None,
                    "status": "failed",
                    "error_message": str(exc),
                },
            )

    def _harvest_process_result_locked(self) -> None:
        if self._status.status != "running" or self._worker_process is None:
            return
        if self._worker_process.is_alive():
            return

        result_payload = self._read_worker_queue_locked()
        if result_payload is None:
            result_payload = self._read_worker_result_path_locked()
        if result_payload is None:
            return

        if hasattr(self._worker_process, "join"):
            self._worker_process.join(0.0)
        self._cleanup_worker_queue_locked()
        self._finalize_harvested_status_locked(result_payload)
        self._worker_process = None
        self._worker_queue = None
        self._worker_result_path = None

    def _read_worker_queue_locked(self) -> dict[str, object] | None:
        if self._worker_queue is None:
            return None
        if hasattr(self._worker_queue, "empty") and self._worker_queue.empty():
            return None
        getter = getattr(self._worker_queue, "get_nowait", None)
        if getter is None:
            getter = getattr(self._worker_queue, "get", None)
        if not callable(getter):
            return None
        try:
            payload = getter()  # pylint: disable=not-callable
        except Empty:
            return None
        return payload if isinstance(payload, dict) else None

    def _read_worker_result_path_locked(self) -> dict[str, object] | None:
        if self._worker_result_path is None or not self._worker_result_path.exists():
            return None
        try:
            payload = json.loads(self._worker_result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        try:
            self._worker_result_path.unlink(missing_ok=True)
        except OSError:
            pass
        return payload if isinstance(payload, dict) else None

    def _finalize_harvested_status_locked(self, result_payload: dict[str, object]) -> None:
        status = str(result_payload.get("status", "failed"))
        fetched = _coerce_int(result_payload.get("fetched", 0), default=0)
        source_count = _coerce_int(result_payload.get("source_count", 0), default=0)
        new_items = _coerce_int(result_payload.get("new", 0), default=0)
        duplicates = _coerce_int(result_payload.get("duplicates", 0), default=0)
        errors = _coerce_int(result_payload.get("errors", 1), default=1)
        screening_message: str | None = None
        if "screening_paused" in result_payload:
            screening_paused = bool(_coerce_int(result_payload.get("screening_paused", 0), 0))
            raw_screening_message = result_payload.get("screening_message")
            if raw_screening_message is not None:
                screening_message = str(raw_screening_message)
            elif screening_paused:
                screening_message = PAUSED_MESSAGE
        else:
            screening_paused = self._status.screening_paused
            screening_message = self._status.screening_message
        error_message = result_payload.get("error_message")
        if error_message is not None:
            error_message = str(error_message)

        self._status = UpdateStatus(
            run_id=self._status.run_id,
            status="finished" if status == "finished" else "failed",
            started_at=self._status.started_at,
            finished_at=datetime.now(UTC),
            source_count=source_count,
            fetched=fetched,
            new=new_items,
            duplicates=duplicates,
            errors=errors,
            error_message=error_message,
            screening_paused=screening_paused,
            screening_message=screening_message,
        )

        log_payload = {
            "run_id": self._status.run_id,
            "source_id": None,
            "status": self._status.status,
            "source_count": source_count,
            "fetched": fetched,
            "new": new_items,
            "duplicates": duplicates,
            "errors": errors,
        }
        if self._status.status == "finished":
            self._logger.info("update_run_finished", log_payload)
            return

        self._logger.error(
            "update_run_failed",
            {**log_payload, "error_message": error_message},
        )

    def _cleanup_worker_queue_locked(self) -> None:
        if self._worker_queue is None:
            return
        closer = getattr(self._worker_queue, "close", None)
        if callable(closer):
            closer()  # pylint: disable=not-callable
        joiner = getattr(self._worker_queue, "join_thread", None)
        if callable(joiner):
            joiner()  # pylint: disable=not-callable
