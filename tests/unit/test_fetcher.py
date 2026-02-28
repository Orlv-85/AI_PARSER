import json
from typing import Any, cast

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
        _ = url
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _ClientFactory:
    def __init__(self, outcomes):
        self._outcomes = outcomes

    def __call__(self, **kwargs):
        _ = kwargs
        return _Client(self._outcomes)


class _RecordingClient:
    def __init__(self, outcomes, calls: list[dict[str, object]]) -> None:
        self._outcomes = list(outcomes)
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str, **kwargs):
        self.calls.append({"url": url, "kwargs": kwargs})
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _RecordingClientFactory:
    def __init__(self, outcomes):
        self._outcomes = outcomes
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs):
        _ = kwargs
        return _RecordingClient(self._outcomes, self.calls)


class _TrackingClient:
    def __init__(self, client_id: int, outcomes, events: list[tuple[str, int, str]]) -> None:
        self.client_id = client_id
        self._outcomes = list(outcomes)
        self._events = events
        self.close_calls = 0

    def __enter__(self):
        self._events.append(("enter", self.client_id, ""))
        return self

    def __exit__(self, exc_type, exc, tb):
        _ = (exc_type, exc, tb)
        self.close()
        return False

    def close(self) -> None:
        self.close_calls += 1
        self._events.append(("close", self.client_id, ""))

    def get(self, url: str):
        self._events.append(("get", self.client_id, url))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _TrackingClientFactory:
    def __init__(self, client_outcomes):
        self._client_outcomes = [list(outcomes) for outcomes in client_outcomes]
        self.instances: list[_TrackingClient] = []
        self.events: list[tuple[str, int, str]] = []

    def __call__(self, **kwargs):
        _ = kwargs
        client_id = len(self.instances)
        outcomes = self._client_outcomes[client_id]
        client = _TrackingClient(client_id=client_id, outcomes=outcomes, events=self.events)
        self.instances.append(client)
        self.events.append(("create", client_id, ""))
        return client


def test_request_retries_and_returns_response(monkeypatch) -> None:
    request = httpx.Request("GET", "https://example.com")
    error = httpx.RequestError("boom", request=request)
    response = _Response(text="payload", content=b"payload")
    monkeypatch.setattr("app.ingest.fetcher.httpx.Client", _ClientFactory([error, response]))

    sleeps: list[float] = []
    def _record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("app.ingest.fetcher.time.sleep", _record_sleep)

    fetcher = Fetcher(max_retries=2)
    result = fetcher.request(source_id="s1", url="https://example.com")

    assert result.text == "payload"
    assert sleeps == [0.25]


def test_request_sends_conditional_headers_when_provided(monkeypatch) -> None:
    factory = _RecordingClientFactory([_Response(text="payload")])
    monkeypatch.setattr("app.ingest.fetcher.httpx.Client", factory)

    fetcher = Fetcher()
    result = fetcher.request(
        source_id="rss",
        url="https://example.com/feed.xml",
        if_none_match='"etag-123"',
        if_modified_since="Mon, 01 Jan 2024 00:00:00 GMT",
    )

    assert result.text == "payload"
    assert factory.calls == [
        {
            "url": "https://example.com/feed.xml",
            "kwargs": {
                "headers": {
                    "If-None-Match": '"etag-123"',
                    "If-Modified-Since": "Mon, 01 Jan 2024 00:00:00 GMT",
                }
            },
        }
    ]


def test_request_returns_304_not_modified_response_distinctly(monkeypatch) -> None:
    request = httpx.Request("GET", "https://example.com/feed.xml")
    not_modified = httpx.Response(304, request=request)
    factory = _RecordingClientFactory([not_modified])
    monkeypatch.setattr("app.ingest.fetcher.httpx.Client", factory)

    fetcher = Fetcher()
    result = fetcher.request(
        source_id="rss",
        url="https://example.com/feed.xml",
        if_none_match='"etag-123"',
    )

    assert result.status_code == 304
    first_call = cast(dict[str, Any], factory.calls[0])
    assert first_call["kwargs"]["headers"] == {"If-None-Match": '"etag-123"'}


def test_request_non_conditional_calls_do_not_send_conditional_headers(monkeypatch) -> None:
    factory = _RecordingClientFactory([_Response(text="payload")])
    monkeypatch.setattr("app.ingest.fetcher.httpx.Client", factory)

    fetcher = Fetcher()
    result = fetcher.request(source_id="rss", url="https://example.com/feed.xml")

    assert result.text == "payload"
    assert factory.calls == [{"url": "https://example.com/feed.xml", "kwargs": {}}]


def test_request_builds_client_with_limits_when_configured(monkeypatch) -> None:
    client_calls: list[dict[str, object]] = []

    class _ClientWithRecordedInit:
        def __init__(self, **kwargs) -> None:
            client_calls.append(kwargs)

        def get(self, url: str, **kwargs):
            _ = (url, kwargs)
            return _Response(text="payload")

        def close(self) -> None:
            return None

    monkeypatch.setattr("app.ingest.fetcher.httpx.Client", _ClientWithRecordedInit)

    fetcher = Fetcher(
        http_max_connections=50,
        http_max_keepalive_connections=25,
    )
    result = fetcher.request(source_id="rss", url="https://example.com/feed.xml")

    assert result.text == "payload"
    assert len(client_calls) == 1
    limits = cast(httpx.Limits, client_calls[0]["limits"])
    assert limits.max_connections == 50
    assert limits.max_keepalive_connections == 25


def test_request_retries_5xx_and_preserves_conditional_headers(monkeypatch) -> None:
    request = httpx.Request("GET", "https://example.com/feed.xml")
    response_500 = httpx.Response(500, request=request)
    error_500 = httpx.HTTPStatusError("bad", request=request, response=response_500)
    ok = httpx.Response(200, request=request, text="ok")
    factory = _RecordingClientFactory([error_500, ok])
    monkeypatch.setattr("app.ingest.fetcher.httpx.Client", factory)

    sleeps: list[float] = []

    def _record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("app.ingest.fetcher.time.sleep", _record_sleep)

    fetcher = Fetcher(max_retries=1)
    result = fetcher.request(
        source_id="rss",
        url="https://example.com/feed.xml",
        if_none_match='"etag-123"',
        if_modified_since="Mon, 01 Jan 2024 00:00:00 GMT",
    )

    assert result.status_code == 200
    assert sleeps == [0.25]
    assert factory.calls == [
        {
            "url": "https://example.com/feed.xml",
            "kwargs": {
                "headers": {
                    "If-None-Match": '"etag-123"',
                    "If-Modified-Since": "Mon, 01 Jan 2024 00:00:00 GMT",
                }
            },
        },
        {
            "url": "https://example.com/feed.xml",
            "kwargs": {
                "headers": {
                    "If-None-Match": '"etag-123"',
                    "If-Modified-Since": "Mon, 01 Jan 2024 00:00:00 GMT",
                }
            },
        },
    ]


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
    def _record_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("app.ingest.fetcher.time.sleep", _record_sleep)

    fetcher = Fetcher(per_source_min_interval_seconds=2.0)
    # pylint: disable=protected-access
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


def test_request_reuses_single_client_across_multiple_calls(monkeypatch) -> None:
    factory = _TrackingClientFactory(
        [[_Response(text="one"), _Response(text="two")], [_Response(text="two")]]
    )
    monkeypatch.setattr("app.ingest.fetcher.httpx.Client", factory)

    fetcher = Fetcher()
    first = fetcher.request(source_id="s1", url="https://example.com/1")
    second = fetcher.request(source_id="s1", url="https://example.com/2")

    assert first.text == "one"
    assert second.text == "two"
    assert len(factory.instances) == 1
    assert [event for event in factory.events if event[0] == "get"] == [
        ("get", 0, "https://example.com/1"),
        ("get", 0, "https://example.com/2"),
    ]


def test_retries_within_one_request_use_same_client_instance(monkeypatch) -> None:
    request = httpx.Request("GET", "https://example.com")
    error = httpx.RequestError("boom", request=request)
    factory = _TrackingClientFactory([[error, _Response(text="ok")]])
    monkeypatch.setattr("app.ingest.fetcher.httpx.Client", factory)
    monkeypatch.setattr("app.ingest.fetcher.time.sleep", lambda seconds: None)

    fetcher = Fetcher(max_retries=1)
    result = fetcher.request(source_id="s1", url="https://example.com")

    assert result.text == "ok"
    assert len(factory.instances) == 1
    assert [event for event in factory.events if event[0] == "get"] == [
        ("get", 0, "https://example.com"),
        ("get", 0, "https://example.com"),
    ]


def test_close_closes_reused_client(monkeypatch) -> None:
    factory = _TrackingClientFactory([[_Response(text="ok")]])
    monkeypatch.setattr("app.ingest.fetcher.httpx.Client", factory)

    fetcher = Fetcher()
    fetcher.request(source_id="s1", url="https://example.com")
    fetcher.close()

    assert len(factory.instances) == 1
    assert factory.instances[0].close_calls == 1


def test_context_manager_closes_client(monkeypatch) -> None:
    factory = _TrackingClientFactory([[_Response(text="ok")]])
    monkeypatch.setattr("app.ingest.fetcher.httpx.Client", factory)

    with Fetcher() as fetcher:
        result = fetcher.request(source_id="s1", url="https://example.com")

    assert result.text == "ok"
    assert len(factory.instances) == 1
    assert factory.instances[0].close_calls == 1
