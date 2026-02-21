from types import SimpleNamespace

from app.web.models import WebUpdateSettings
from app.web.service import UpdateRunService


class _Logger:
    def __init__(self) -> None:
        self.errors: list[tuple[str, dict[str, object]]] = []

    def info(self, _event: str, _payload: dict[str, object]) -> None:
        pass

    def warning(self, _event: str, _payload: dict[str, object]) -> None:
        pass

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
