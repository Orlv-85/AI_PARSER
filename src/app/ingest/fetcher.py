import json
import time
from dataclasses import dataclass, field

import httpx


@dataclass
class Fetcher:
    timeout_seconds: float = 15.0
    max_retries: int = 3
    per_source_min_interval_seconds: float = 1.0
    _next_allowed_time: dict[str, float] = field(default_factory=dict)

    def _respect_rate_limit(self, source_id: str) -> None:
        now = time.monotonic()
        next_allowed = self._next_allowed_time.get(source_id, now)
        if next_allowed > now:
            time.sleep(next_allowed - now)
        self._next_allowed_time[source_id] = time.monotonic() + self.per_source_min_interval_seconds

    def request(self, *, source_id: str, url: str) -> httpx.Response:
        self._respect_rate_limit(source_id)
        last_error: Exception | None = None
        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    response = client.get(url)
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

