import json
import time
from dataclasses import dataclass, field
from typing import Literal

import httpx

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


@dataclass
class Fetcher:
    timeout_seconds: float = 15.0
    max_retries: int = 3
    per_source_min_interval_seconds: float = 1.0
    user_agent: str = DEFAULT_USER_AGENT
    _next_allowed_time: dict[str, float] = field(default_factory=dict)
    _client: httpx.Client | None = field(default=None, init=False, repr=False)

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": self.user_agent},
            )
        return self._client

    def _respect_rate_limit(self, source_id: str) -> None:
        now = time.monotonic()
        next_allowed = self._next_allowed_time.get(source_id, now)
        if next_allowed > now:
            time.sleep(next_allowed - now)
        self._next_allowed_time[source_id] = time.monotonic() + self.per_source_min_interval_seconds

    def request(
        self,
        *,
        source_id: str,
        url: str,
        if_none_match: str | None = None,
        if_modified_since: str | None = None,
    ) -> httpx.Response:
        self._respect_rate_limit(source_id)
        last_error: Exception | None = None
        client = self._get_client()
        request_headers: dict[str, str] = {}
        if if_none_match is not None:
            request_headers["If-None-Match"] = if_none_match
        if if_modified_since is not None:
            request_headers["If-Modified-Since"] = if_modified_since
        for attempt in range(self.max_retries + 1):
            try:
                if request_headers:
                    response = client.get(url, headers=request_headers)
                else:
                    response = client.get(url)
                if getattr(response, "status_code", None) == 304:
                    return response
                response.raise_for_status()
                return response
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(0.25 * (2**attempt))
        raise RuntimeError(
            json.dumps(
                {
                    "event": "fetch_failed",
                    "source_id": source_id,
                    "url": url,
                    "error_type": type(last_error).__name__ if last_error else "UnknownError",
                }
            )
        ) from last_error

    def fetch_text(self, *, source_id: str, url: str) -> str:
        return self.request(source_id=source_id, url=url).text

    def fetch_bytes(self, *, source_id: str, url: str) -> bytes:
        return self.request(source_id=source_id, url=url).content

    def close(self) -> None:
        if self._client is None:
            return
        self._client.close()
        self._client = None

    def __enter__(self) -> Fetcher:
        return self

    def __exit__(self, exc_type, exc, tb) -> Literal[False]:
        _ = (exc_type, exc, tb)
        self.close()
        return False
