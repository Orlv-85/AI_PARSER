import json

import httpx
import pytest

from app.ingest.fetcher import Fetcher


class _Response:
    def __init__(self, text: str = "ok", content: bytes = b"ok") -> None:
        self.text = text
        self.content = content

    def raise_for_status(self) -> None:
        return None


class _Client:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _ClientFactory:
    def __init__(self, outcomes):
        self._outcomes = outcomes

    def __call__(self, **kwargs):
        return _Client(self._outcomes)


def test_request_retries_and_returns_response(monkeypatch) -> None:
    request = httpx.Request("GET", "https://example.com")
    error = httpx.RequestError("boom", request=request)
    response = _Response(text="payload", content=b"payload")
    monkeypatch.setattr("app.ingest.fetcher.httpx.Client", _ClientFactory([error, response]))

    sleeps: list[float] = []
    monkeypatch.setattr("app.ingest.fetcher.time.sleep", lambda seconds: sleeps.append(seconds))

    fetcher = Fetcher(max_retries=2)
    result = fetcher.request(source_id="s1", url="https://example.com")

    assert result.text == "payload"
    assert sleeps == [0.25]


def test_request_raises_runtime_error_with_json_payload(monkeypatch) -> None:
    request = httpx.Request("GET", "https://example.com")
    response = httpx.Response(500, request=request)
    error = httpx.HTTPStatusError("bad", request=request, response=response)
    monkeypatch.setattr("app.ingest.fetcher.httpx.Client", _ClientFactory([error]))
    monkeypatch.setattr("app.ingest.fetcher.time.sleep", lambda seconds: None)

    fetcher = Fetcher(max_retries=0)
    with pytest.raises(RuntimeError) as exc_info:
        fetcher.request(source_id="rss", url="https://example.com/feed")

    payload = json.loads(str(exc_info.value))
    assert payload["event"] == "fetch_failed"
    assert payload["source_id"] == "rss"
    assert payload["error_type"] == "HTTPStatusError"


def test_respect_rate_limit_sleeps_until_allowed(monkeypatch) -> None:
    timeline = iter([10.0, 10.2, 12.0, 12.0])
    monkeypatch.setattr("app.ingest.fetcher.time.monotonic", lambda: next(timeline))

    slept: list[float] = []
    monkeypatch.setattr("app.ingest.fetcher.time.sleep", lambda seconds: slept.append(seconds))

    fetcher = Fetcher(per_source_min_interval_seconds=2.0)
    fetcher._respect_rate_limit("source")
    fetcher._respect_rate_limit("source")

    assert slept == [pytest.approx(0.2)]


def test_request_raises_unknown_error_when_no_attempts_run(monkeypatch) -> None:
    monkeypatch.setattr("app.ingest.fetcher.httpx.Client", _ClientFactory([]))
    fetcher = Fetcher(max_retries=-1)

    with pytest.raises(RuntimeError) as exc_info:
        fetcher.request(source_id="none", url="https://example.com")

    payload = json.loads(str(exc_info.value))
    assert payload["error_type"] == "UnknownError"


def test_fetch_text_and_fetch_bytes_delegate_to_request(monkeypatch) -> None:
    response = _Response(text="hello", content=b"world")
    monkeypatch.setattr(Fetcher, "request", lambda self, **kwargs: response)

    fetcher = Fetcher()
    assert fetcher.fetch_text(source_id="x", url="https://example.com") == "hello"
    assert fetcher.fetch_bytes(source_id="x", url="https://example.com") == b"world"
