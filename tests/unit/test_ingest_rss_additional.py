from time import struct_time

from app.ingest.rss import _to_datetime, fetch_rss, parse_rss


class _Fetcher:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def fetch_bytes(self, *, source_id: str, url: str) -> bytes:
        _ = (source_id, url)
        return self.content


class _Response:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


class _Client:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        _ = url
        return _Response(self.content)


def test_to_datetime_none_and_struct_time() -> None:
    assert _to_datetime(None) is None
    dt = _to_datetime(struct_time((2026, 2, 21, 12, 0, 0, 0, 0, 0)))
    assert dt is not None
    assert dt.year == 2026


def test_parse_rss_skips_invalid_and_uses_updated_parsed(monkeypatch) -> None:
    class _Entry:
        def __init__(self, link=None, title=None, updated_parsed=None):
            self.link = link
            self.title = title
            self.updated_parsed = updated_parsed

    class _Parsed:
        entries = [
            _Entry(link="https://example.com/1", title=" One "),
            _Entry(link=None, title="Missing link"),
            _Entry(link="https://example.com/2", title=None),
            _Entry(
                link="https://example.com/3",
                title="Three",
                updated_parsed=struct_time((2026, 2, 20, 10, 0, 0, 0, 0, 0)),
            ),
        ]

    monkeypatch.setattr("app.ingest.rss.feedparser.parse", lambda content: _Parsed())

    items = parse_rss("source", b"x")

    assert len(items) == 2
    assert items[0].title == "One"
    assert items[1].published_at is not None


def test_fetch_rss_uses_fetcher_and_httpx_branches(monkeypatch) -> None:
    content = b"<rss></rss>"
    monkeypatch.setattr("app.ingest.rss.parse_rss", lambda source_key, content: ["ok"])

    via_fetcher = fetch_rss("s", "https://example.com/feed", fetcher=_Fetcher(content))
    monkeypatch.setattr("app.ingest.rss.httpx.Client", lambda **kwargs: _Client(content))
    via_httpx = fetch_rss("s", "https://example.com/feed", timeout_seconds=3.0, fetcher=None)

    assert via_fetcher == ["ok"]
    assert via_httpx == ["ok"]
