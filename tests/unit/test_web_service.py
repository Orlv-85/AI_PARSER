# pylint: disable=protected-access,unnecessary-lambda
from queue import Empty
from types import SimpleNamespace

from app.web.models import WebUpdateSettings
from app.web.service import UpdateRunService, _coerce_int, _run_offloaded_fetch_cycle


class _Logger:
    def __init__(self) -> None:
        self.errors: list[tuple[str, dict[str, object]]] = []
        self.warnings: list[tuple[str, dict[str, object]]] = []

    def info(self, _event: str, _payload: dict[str, object]) -> None:
        pass

    def warning(self, event: str, payload: dict[str, object]) -> None:
        self.warnings.append((event, payload))

    def error(self, event: str, payload: dict[str, object]) -> None:
        self.errors.append((event, payload))


def test_run_failure_sets_failed_status(monkeypatch) -> None:
    logger = _Logger()
    service = UpdateRunService(logger=logger)

    class _ImmediateThread:
        def __init__(self, *, target, args, daemon):
            self._target = target
            self._args = args
            self._daemon = daemon

        def start(self) -> None:
            self._target(*self._args)

    monkeypatch.setattr(
        "app.web.service.get_settings",
        lambda: SimpleNamespace(model_copy=lambda **kwargs: kwargs.get("update")),
    )
    monkeypatch.setattr("app.web.service.threading.Thread", _ImmediateThread)

    def _raise_run_fetch_cycle(**_kwargs):
        raise RuntimeError("update failed")

    monkeypatch.setattr("app.web.service.run_fetch_cycle", _raise_run_fetch_cycle)

    started = service.start(WebUpdateSettings())
    assert started is not None
    status = service.current_status()

    assert status.status == "failed"
    assert status.errors == 1
    assert status.error_message == "update failed"
    assert status.finished_at is not None
    assert logger.errors and logger.errors[-1][0] == "update_run_failed"


def test_process_mode_harvests_offloaded_worker_result(monkeypatch, tmp_path) -> None:
    service = UpdateRunService(
        logger=SimpleNamespace(
            info=lambda *_a, **_k: None,
            warning=lambda *_a, **_k: None,
            error=lambda *_a, **_k: None,
        )
    )
    started_processes: list[object] = []
    process_targets: list[tuple[object, tuple[object, ...]]] = []

    class _FakeProcess:
        def __init__(self, *, target, args, daemon):
            self._target = target
            self._args = args
            self._daemon = daemon
            self._alive: bool = True
            process_targets.append((target, args))

        def start(self) -> None:
            started_processes.append(self)

        def is_alive(self) -> bool:
            return self._alive

        def finish(self) -> None:
            self._alive = False

    monkeypatch.setattr("app.web.service._DEFAULT_PROCESS_RESULT_DIR", tmp_path)
    monkeypatch.setattr("app.web.service.multiprocessing.Process", _FakeProcess)

    started = service.start(WebUpdateSettings(update_execution_mode="process"))
    assert started is not None
    assert started.status == "running"
    assert started_processes
    assert process_targets

    running_status = service.current_status()
    assert running_status.status == "running"

    result_path = tmp_path / f"{started.run_id}.json"
    result_path.write_text(
        (
            '{"status":"finished","fetched":12,"new":7,'
            '"duplicates":5,"errors":0,"error_message":null}'
        ),
        encoding="utf-8",
    )
    finished_process = started_processes[-1]
    assert isinstance(finished_process, _FakeProcess)
    finished_process.finish()

    finished_status = service.current_status()

    assert finished_status.status == "finished"
    assert finished_status.fetched == 12
    assert finished_status.new == 7
    assert finished_status.duplicates == 5
    assert finished_status.errors == 0
    assert finished_status.error_message is None


def test_process_mode_stays_running_until_current_status_harvests_finished_result(
    monkeypatch,
) -> None:
    logger = _Logger()
    service = UpdateRunService(logger=logger)
    process_starts: list[tuple[object, tuple[object, ...], bool]] = []
    queue_messages = [
        {
            "status": "finished",
            "fetched": 12,
            "new": 5,
            "duplicates": 6,
            "errors": 1,
            "error_message": None,
        }
    ]

    class _FakeQueue:
        def empty(self) -> bool:
            return not queue_messages

        def get_nowait(self):
            return queue_messages.pop(0)

        def get(self, _timeout: float | None = None):
            return self.get_nowait()

    class _FakeProcess:
        def __init__(self, *, target, args, daemon):
            self._target = target
            self._args = args
            self._daemon = daemon
            process_starts.append((target, args, daemon))

        def start(self) -> None:
            return None

        def is_alive(self) -> bool:
            return False

        def join(self, _timeout: float | None = None) -> None:
            return None

    class _UnexpectedThread:
        def __init__(self, *, target, args, daemon):
            self._target = target
            self._args = args
            self._daemon = daemon

        def start(self) -> None:
            return None

    monkeypatch.setattr("app.web.service.get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr("app.web.service.threading.Thread", _UnexpectedThread)
    monkeypatch.setattr(
        "app.web.service.multiprocessing",
        SimpleNamespace(Process=_FakeProcess, Queue=_FakeQueue),
        raising=False,
    )

    started = service.start(WebUpdateSettings(update_execution_mode="process"))

    assert started is not None
    assert started.status == "running"
    assert process_starts

    status = service.current_status()

    assert status.status == "finished"
    assert status.fetched == 12
    assert status.new == 5
    assert status.duplicates == 6
    assert status.errors == 1
    assert status.error_message is None
    assert status.finished_at is not None


def test_process_mode_stays_running_until_current_status_harvests_failed_result(
    monkeypatch,
) -> None:
    logger = _Logger()
    service = UpdateRunService(logger=logger)
    process_starts: list[tuple[object, tuple[object, ...], bool]] = []
    queue_messages = [
        {
            "status": "failed",
            "fetched": 0,
            "new": 0,
            "duplicates": 0,
            "errors": 1,
            "error_message": "worker crashed",
        }
    ]

    class _FakeQueue:
        def empty(self) -> bool:
            return not queue_messages

        def get_nowait(self):
            return queue_messages.pop(0)

        def get(self, _timeout: float | None = None):
            return self.get_nowait()

    class _FakeProcess:
        def __init__(self, *, target, args, daemon):
            self._target = target
            self._args = args
            self._daemon = daemon
            process_starts.append((target, args, daemon))

        def start(self) -> None:
            return None

        def is_alive(self) -> bool:
            return False

        def join(self, _timeout: float | None = None) -> None:
            return None

    class _UnexpectedThread:
        def __init__(self, *, target, args, daemon):
            self._target = target
            self._args = args
            self._daemon = daemon

        def start(self) -> None:
            return None

    monkeypatch.setattr("app.web.service.get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr("app.web.service.threading.Thread", _UnexpectedThread)
    monkeypatch.setattr(
        "app.web.service.multiprocessing",
        SimpleNamespace(Process=_FakeProcess, Queue=_FakeQueue),
        raising=False,
    )

    started = service.start(WebUpdateSettings(update_execution_mode="process"))

    assert started is not None
    assert started.status == "running"
    assert process_starts

    status = service.current_status()

    assert status.status == "failed"
    assert status.errors == 1
    assert status.error_message == "worker crashed"
    assert status.finished_at is not None


def test_run_offloaded_fetch_cycle_writes_finished_payload_to_queue_and_file(
    monkeypatch, tmp_path
) -> None:
    captured: dict[str, object] = {}
    queue_payloads: list[dict[str, object]] = []

    class _BaseSettings:
        def model_copy(self, *, update):
            merged = SimpleNamespace(**update)
            captured["settings"] = merged
            return merged

    class _QueueWithPutNowait:
        def put_nowait(self, payload) -> None:
            queue_payloads.append(payload)

    monkeypatch.setattr("app.web.service.get_settings", lambda: _BaseSettings())
    monkeypatch.setattr("app.web.service.setup_json_logging", lambda: object())

    def _run_fetch_cycle(**kwargs):
        captured["run_fetch_cycle_settings"] = kwargs["settings"]
        return SimpleNamespace(fetched=4, new=3, duplicates=1, errors=0)

    monkeypatch.setattr("app.web.service.run_fetch_cycle", _run_fetch_cycle)

    result_path = tmp_path / "worker.json"
    _run_offloaded_fetch_cycle(
        "run-1",
        WebUpdateSettings(update_execution_mode="process").model_dump(mode="python"),
        str(result_path),
        _QueueWithPutNowait(),
    )

    assert queue_payloads == [
        {
            "status": "finished",
            "source_count": 0,
            "fetched": 4,
            "new": 3,
            "duplicates": 1,
            "errors": 0,
            "error_message": None,
        }
    ]
    assert result_path.exists()
    assert '"status": "finished"' in result_path.read_text(encoding="utf-8")
    assert not hasattr(captured["settings"], "update_execution_mode")


def test_run_offloaded_fetch_cycle_failure_uses_put_fallback(monkeypatch, tmp_path) -> None:
    queue_payloads: list[dict[str, object]] = []

    class _BaseSettings:
        def model_copy(self, *, update):
            return SimpleNamespace(**update)

    class _QueueWithPut:
        def put(self, payload) -> None:
            queue_payloads.append(payload)

    monkeypatch.setattr("app.web.service.get_settings", lambda: _BaseSettings())
    monkeypatch.setattr("app.web.service.setup_json_logging", lambda: object())

    def _raise_run_fetch_cycle(**_kwargs):
        raise RuntimeError("worker boom")

    monkeypatch.setattr("app.web.service.run_fetch_cycle", _raise_run_fetch_cycle)

    result_path = tmp_path / "worker-failed.json"
    _run_offloaded_fetch_cycle(
        "run-2",
        WebUpdateSettings(update_execution_mode="process").model_dump(mode="python"),
        str(result_path),
        _QueueWithPut(),
    )

    assert queue_payloads == [
        {
            "status": "failed",
            "fetched": 0,
            "new": 0,
            "duplicates": 0,
            "errors": 1,
            "error_message": "worker boom",
        }
    ]
    assert '"status": "failed"' in result_path.read_text(encoding="utf-8")


def test_run_offloaded_fetch_cycle_without_queue_still_writes_result_file(
    monkeypatch, tmp_path
) -> None:
    class _BaseSettings:
        def model_copy(self, *, update):
            return SimpleNamespace(**update)

    monkeypatch.setattr("app.web.service.get_settings", lambda: _BaseSettings())
    monkeypatch.setattr("app.web.service.setup_json_logging", lambda: object())
    monkeypatch.setattr(
        "app.web.service.run_fetch_cycle",
        lambda **_kwargs: SimpleNamespace(fetched=2, new=2, duplicates=0, errors=0),
    )

    result_path = tmp_path / "worker-no-queue.json"
    _run_offloaded_fetch_cycle(
        "run-3",
        WebUpdateSettings(update_execution_mode="process").model_dump(mode="python"),
        str(result_path),
        None,
    )

    assert '"status": "finished"' in result_path.read_text(encoding="utf-8")


def test_run_offloaded_fetch_cycle_ignores_queue_without_put_methods(
    monkeypatch, tmp_path
) -> None:
    class _BaseSettings:
        def model_copy(self, *, update):
            return SimpleNamespace(**update)

    class _QueueWithoutPut:
        pass

    monkeypatch.setattr("app.web.service.get_settings", lambda: _BaseSettings())
    monkeypatch.setattr("app.web.service.setup_json_logging", lambda: object())
    monkeypatch.setattr(
        "app.web.service.run_fetch_cycle",
        lambda **_kwargs: SimpleNamespace(fetched=1, new=1, duplicates=0, errors=0),
    )

    result_path = tmp_path / "worker-no-put.json"
    _run_offloaded_fetch_cycle(
        "run-4",
        WebUpdateSettings(update_execution_mode="process").model_dump(mode="python"),
        str(result_path),
        _QueueWithoutPut(),
    )

    assert '"status": "finished"' in result_path.read_text(encoding="utf-8")


def test_start_rejects_when_process_run_is_already_running(monkeypatch) -> None:
    logger = _Logger()
    service = UpdateRunService(logger=logger)

    class _FakeQueue:
        def empty(self) -> bool:
            return True

    class _AliveProcess:
        def __init__(self, *, target, args, daemon):
            self._target = target
            self._args = args
            self._daemon = daemon

        def start(self) -> None:
            return None

        def is_alive(self) -> bool:
            return True

    monkeypatch.setattr(
        "app.web.service.multiprocessing",
        SimpleNamespace(Process=_AliveProcess, Queue=_FakeQueue),
        raising=False,
    )

    started = service.start(WebUpdateSettings(update_execution_mode="process"))
    rejected = service.start(WebUpdateSettings(update_execution_mode="process"))

    assert started is not None
    assert rejected is None
    assert logger.warnings
    assert logger.warnings[-1][0] == "update_run_rejected"


def test_process_mode_without_result_stays_running(monkeypatch) -> None:
    service = UpdateRunService(
        logger=SimpleNamespace(
            info=lambda *_a, **_k: None,
            warning=lambda *_a, **_k: None,
            error=lambda *_a, **_k: None,
        )
    )

    class _EmptyQueue:
        def empty(self) -> bool:
            return True

    class _FinishedProcess:
        def __init__(self, *, target, args, daemon):
            self._target = target
            self._args = args
            self._daemon = daemon

        def start(self) -> None:
            return None

        def is_alive(self) -> bool:
            return False

        def join(self, _timeout: float | None = None) -> None:
            return None

    monkeypatch.setattr(
        "app.web.service.multiprocessing",
        SimpleNamespace(Process=_FinishedProcess, Queue=_EmptyQueue),
        raising=False,
    )

    started = service.start(WebUpdateSettings(update_execution_mode="process"))
    assert started is not None
    assert started.status == "running"

    status = service.current_status()

    assert status.status == "running"


def test_worker_helper_methods_handle_edge_cases() -> None:
    service = UpdateRunService(
        logger=SimpleNamespace(
            info=lambda *_a, **_k: None,
            warning=lambda *_a, **_k: None,
            error=lambda *_a, **_k: None,
        )
    )

    assert service._read_worker_queue_locked() is None
    service._cleanup_worker_queue_locked()

    class _QueueWithoutGetter:
        def empty(self) -> bool:
            return False

    service._worker_queue = _QueueWithoutGetter()
    assert service._read_worker_queue_locked() is None

    class _QueueEmptyError:
        def empty(self) -> bool:
            return False

        def get_nowait(self):
            raise Empty()

    service._worker_queue = _QueueEmptyError()
    assert service._read_worker_queue_locked() is None

    assert service._read_worker_result_path_locked() is None

    class _BadJsonPath:
        def exists(self) -> bool:
            return True

        def read_text(self, *, encoding: str) -> str:
            _ = encoding
            return "{not-json"

    service._worker_result_path = _BadJsonPath()
    assert service._read_worker_result_path_locked() is None

    class _UnlinkFailPath:
        def exists(self) -> bool:
            return True

        def read_text(self, *, encoding: str) -> str:
            _ = encoding
            return '{"status": "finished"}'

        def unlink(self, *, missing_ok: bool) -> None:
            _ = missing_ok
            raise OSError("unlink blocked")

    service._worker_result_path = _UnlinkFailPath()
    assert service._read_worker_result_path_locked() == {"status": "finished"}


def test_coerce_int_handles_supported_and_fallback_types() -> None:
    assert _coerce_int(True, default=9) == 1
    assert _coerce_int(7, default=9) == 7
    assert _coerce_int(3.8, default=9) == 3
    assert _coerce_int("12", default=9) == 12
    assert _coerce_int("bad", default=9) == 9
    assert _coerce_int(object(), default=9) == 9
