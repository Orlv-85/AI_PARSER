from datetime import UTC, date, datetime
from importlib import import_module
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.storage.models_sql import Article, Base, Source
from app.storage.repos import WeeklyAnalyticsRepo
from app.web.app import create_app


def test_public_digest_page_links_to_weekly_ai_analytics(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    class _DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def _session_local():
        return _DummySession()

    class _NewsDigestRepo:
        def __init__(self, _session) -> None:
            pass

        def get_digest(self, *, report_date):  # type: ignore[no-untyped-def]
            del report_date

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(web_app_module, "NewsDigestRepo", _NewsDigestRepo)

    client = TestClient(create_app())

    response = client.get("/?date=2026-03-07")

    assert response.status_code == 200
    assert 'href="/weekly-ai-analytics/reports"' in response.text
    assert "Weekly Reports" in response.text


def test_weekly_reports_page_renders(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 11, 9, 0, tzinfo=tz or UTC)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "datetime", _FrozenDateTime)

    client = TestClient(create_app())

    response = client.get("/weekly-ai-analytics/reports")

    assert response.status_code == 200
    assert "Weekly AI Reports" in response.text
    assert 'href="/?date=2026-03-10"' in response.text


def test_weekly_ai_analytics_page_renders_shell_with_requested_date(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 8, 9, 0, tzinfo=tz or UTC)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "datetime", _FrozenDateTime)

    client = TestClient(create_app())

    response = client.get("/weekly-ai-analytics?date=2026-03-07")

    assert response.status_code == 200
    assert "Weekly AI Analytics" in response.text
    assert 'value="2026-03-07"' in response.text
    assert "Management Summary" in response.text
    assert "New" in response.text
    assert "Trending Up" in response.text
    assert "Trending Down" in response.text


def test_weekly_ai_analytics_page_back_link_preserves_requested_report_date(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 8, 9, 0, tzinfo=tz or UTC)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "datetime", _FrozenDateTime)

    client = TestClient(create_app())

    response = client.get("/weekly-ai-analytics?date=2026-03-07")

    assert response.status_code == 200
    assert 'href="/?date=2026-03-07"' in response.text


def test_weekly_ai_analytics_page_back_link_preserves_default_previous_utc_day(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 8, 9, 0, tzinfo=tz or UTC)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "datetime", _FrozenDateTime)

    client = TestClient(create_app())

    response = client.get("/weekly-ai-analytics")

    assert response.status_code == 200
    assert 'href="/?date=2026-03-07"' in response.text


def test_weekly_ai_analytics_page_defaults_to_latest_published_report_date(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            # Wednesday after Monday autopublish of previous Mon-Sun week.
            return cls(2026, 3, 11, 9, 0, tzinfo=tz or UTC)

    class _WeeklyAnalyticsRepo:
        def __init__(self, _session) -> None:
            pass

        def get_latest_report_date(self) -> date:
            return date(2026, 3, 8)

    class _DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def _session_local():
        return _DummySession()

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(web_app_module, "datetime", _FrozenDateTime)
    monkeypatch.setattr(web_app_module, "WeeklyAnalyticsRepo", _WeeklyAnalyticsRepo, raising=False)

    client = TestClient(create_app())

    response = client.get("/weekly-ai-analytics")

    assert response.status_code == 200
    assert 'value="2026-03-08"' in response.text
    assert 'href="/?date=2026-03-08"' in response.text


def test_weekly_ai_analytics_api_returns_report_sections_for_last_7_days(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    captured: dict[str, object] = {}

    class _WeeklyAnalyticsRepo:
        def __init__(self, _session) -> None:
            pass

        def get_weekly_report(self, *, report_date: date):
            captured["report_date"] = report_date
            return SimpleNamespace(
                report_date=report_date,
                date_from=date(2026, 3, 1),
                date_to=date(2026, 3, 7),
                summary="Leaders should watch infrastructure efficiency and coding agents.",
                new=[
                    SimpleNamespace(
                        title="AI Browser Launches",
                        summary="A new entrant shipped an AI-native browser for enterprise teams.",
                        url="https://example.com/ai-browser",
                    )
                ],
                trending_up=[
                    SimpleNamespace(
                        title="Coding Agents Expand",
                        summary="More vendors are packaging coding agents into core workflows.",
                        url="https://example.com/coding-agents",
                    )
                ],
                trending_down=[
                    SimpleNamespace(
                        title="Standalone Vector DBs Cool Off",
                        summary=(
                            "Fewer launches are centered on pure-play vector database "
                            "positioning."
                        ),
                        url="https://example.com/vector-dbs",
                    )
                ],
            )

    class _DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def _session_local():
        return _DummySession()

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(web_app_module, "WeeklyAnalyticsRepo", _WeeklyAnalyticsRepo, raising=False)

    client = TestClient(create_app())

    response = client.get("/api/news/weekly-analytics?date=2026-03-07")

    assert response.status_code == 200
    assert captured == {"report_date": date(2026, 3, 7)}
    assert response.json() == {
        "report_date": "2026-03-07",
        "date_from": "2026-03-01",
        "date_to": "2026-03-07",
        "summary": "Leaders should watch infrastructure efficiency and coding agents.",
        "new": [
            {
                "title": "AI Browser Launches",
                "summary": "A new entrant shipped an AI-native browser for enterprise teams.",
                "url": "https://example.com/ai-browser",
            }
        ],
        "trending_up": [
            {
                "title": "Coding Agents Expand",
                "summary": "More vendors are packaging coding agents into core workflows.",
                "url": "https://example.com/coding-agents",
            }
        ],
        "trending_down": [
            {
                "title": "Standalone Vector DBs Cool Off",
                "summary": "Fewer launches are centered on pure-play vector database positioning.",
                "url": "https://example.com/vector-dbs",
            }
        ],
    }


def test_weekly_ai_analytics_reports_api_returns_published_list(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    class _WeeklyAnalyticsRepo:
        def __init__(self, _session) -> None:
            pass

        def list_stored_reports(self, *, limit: int):
            assert limit == 52
            return [
                SimpleNamespace(
                    report_date=date(2026, 3, 8),
                    date_from=date(2026, 3, 2),
                    date_to=date(2026, 3, 8),
                    summary="Saved management weekly summary",
                    created_at=datetime(2026, 3, 10, 6, 30, tzinfo=UTC),
                )
            ]

    class _DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def _session_local():
        return _DummySession()

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(web_app_module, "WeeklyAnalyticsRepo", _WeeklyAnalyticsRepo, raising=False)

    client = TestClient(create_app())
    response = client.get("/api/news/weekly-analytics/reports")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "report_date": "2026-03-08",
                "date_from": "2026-03-02",
                "date_to": "2026-03-08",
                "summary": "Saved management weekly summary",
                "created_at": "2026-03-10T06:30:00Z",
            }
        ]
    }


def test_weekly_ai_analytics_api_defaults_to_previous_utc_day(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    captured: dict[str, object] = {}

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 8, 9, 0, tzinfo=tz or UTC)

    class _WeeklyAnalyticsRepo:
        def __init__(self, _session) -> None:
            pass

        def get_weekly_report(self, *, report_date: date):
            captured["report_date"] = report_date
            return SimpleNamespace(
                report_date=report_date,
                date_from=date(2026, 3, 1),
                date_to=date(2026, 3, 7),
                summary="Antigravity synthesized the last seven days of AI news.",
                new=[],
                trending_up=[],
                trending_down=[],
            )

    class _DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def _session_local():
        return _DummySession()

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(web_app_module, "datetime", _FrozenDateTime)
    monkeypatch.setattr(web_app_module, "WeeklyAnalyticsRepo", _WeeklyAnalyticsRepo, raising=False)

    client = TestClient(create_app())

    response = client.get("/api/news/weekly-analytics")

    assert response.status_code == 200
    assert captured == {"report_date": date(2026, 3, 7)}
    assert response.json() == {
        "report_date": "2026-03-07",
        "date_from": "2026-03-01",
        "date_to": "2026-03-07",
        "summary": "Antigravity synthesized the last seven days of AI news.",
        "new": [],
        "trending_up": [],
        "trending_down": [],
    }


def test_weekly_ai_analytics_api_defaults_to_latest_published_report_date(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    captured: dict[str, object] = {}

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            # Wednesday after Monday autopublish of previous Mon-Sun week.
            return cls(2026, 3, 11, 9, 0, tzinfo=tz or UTC)

    class _WeeklyAnalyticsRepo:
        def __init__(self, _session) -> None:
            pass

        def get_latest_report_date(self) -> date:
            return date(2026, 3, 8)

        def get_weekly_report(self, *, report_date: date):
            captured["report_date"] = report_date
            return SimpleNamespace(
                report_date=report_date,
                date_from=date(2026, 3, 2),
                date_to=date(2026, 3, 8),
                summary="Saved Monday-published weekly report.",
                new=[],
                trending_up=[],
                trending_down=[],
            )

    class _DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def _session_local():
        return _DummySession()

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(web_app_module, "datetime", _FrozenDateTime)
    monkeypatch.setattr(web_app_module, "WeeklyAnalyticsRepo", _WeeklyAnalyticsRepo, raising=False)

    client = TestClient(create_app())

    response = client.get("/api/news/weekly-analytics")

    assert response.status_code == 200
    assert captured == {"report_date": date(2026, 3, 8)}
    assert response.json() == {
        "report_date": "2026-03-08",
        "date_from": "2026-03-02",
        "date_to": "2026-03-08",
        "summary": "Saved Monday-published weekly report.",
        "new": [],
        "trending_up": [],
        "trending_down": [],
    }


def test_public_digest_page_renders_weekly_ai_analytics_section(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    class _DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def _session_local():
        return _DummySession()

    class _NewsDigestRepo:
        def __init__(self, _session) -> None:
            pass

        def get_digest(self, *, report_date):  # type: ignore[no-untyped-def]
            del report_date

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(web_app_module, "NewsDigestRepo", _NewsDigestRepo)

    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert 'href="/weekly-ai-analytics/reports"' in response.text
    assert 'id="weekly-analytics-preview"' in response.text
    assert "Weekly Management View" in response.text
    assert "Management Summary" in response.text
    assert "/api/news/weekly-analytics?date=" in response.text


def test_weekly_ai_analytics_api_uses_prior_week_only_for_trending_down_baseline(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path}/weekly-analytics-window.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with session_local() as session:
        Base.metadata.create_all(bind=engine)
        source = Source(
            source_key="weekly-source",
            name="Weekly Source",
            type="rss",
            url="https://example.com/feed",
        )
        session.add(source)
        session.flush()
        session.add_all(
            [
                Article(
                    source_id=source.id,
                    title="Recent Launch Window Story",
                    summary="A newly launched AI product landed during the selected week.",
                    content=None,
                    url="https://example.com/recent-launch",
                    url_canonical="https://example.com/recent-launch",
                    url_canonical_hash="recent-launch",
                    published_at=datetime(2026, 3, 7, 10, 0, tzinfo=UTC),
                    ai_relevance_score=0.9,
                    freshness_score=0.8,
                    rank_score=0.95,
                ),
                Article(
                    source_id=source.id,
                    title="Recent Trending Up Story",
                    summary="Momentum accelerated for coding agents during the selected week.",
                    content=None,
                    url="https://example.com/recent-up",
                    url_canonical="https://example.com/recent-up",
                    url_canonical_hash="recent-up",
                    published_at=datetime(2026, 3, 5, 9, 0, tzinfo=UTC),
                    ai_relevance_score=0.85,
                    freshness_score=0.7,
                    rank_score=0.9,
                ),
                Article(
                    source_id=source.id,
                    title="Recent Trending Down Story",
                    summary="Interest softened for a theme within the same selected week.",
                    content=None,
                    url="https://example.com/recent-down",
                    url_canonical="https://example.com/recent-down",
                    url_canonical_hash="recent-down",
                    published_at=datetime(2026, 3, 2, 8, 0, tzinfo=UTC),
                    ai_relevance_score=0.55,
                    freshness_score=0.4,
                    rank_score=0.35,
                ),
                    Article(
                        source_id=source.id,
                        title="Prior Week Story Can Drive Trending Down",
                        summary=(
                            "This article belongs to the comparison window and should "
                            "shape the baseline."
                        ),
                        content=None,
                    url="https://example.com/prior-week",
                    url_canonical="https://example.com/prior-week",
                    url_canonical_hash="prior-week",
                    published_at=datetime(2026, 2, 24, 12, 0, tzinfo=UTC),
                    ai_relevance_score=0.99,
                    freshness_score=0.9,
                    rank_score=0.99,
                ),
            ]
        )
        session.commit()

    def _create_all_local() -> None:
        Base.metadata.create_all(bind=engine)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", _create_all_local)
    monkeypatch.setattr(web_app_module, "SessionLocal", session_local)

    client = TestClient(create_app())

    response = client.get("/api/news/weekly-analytics?date=2026-03-07")

    assert response.status_code == 200
    payload = response.json()
    assert payload["date_from"] == "2026-03-01"
    assert payload["date_to"] == "2026-03-07"
    assert {item["title"] for item in payload["new"]} == {
        "Recent Launch Window Story",
        "Recent Trending Up Story",
        "Recent Trending Down Story",
    }
    assert payload["trending_up"] == []
    assert "Recent Trending Down Story" in {
        item["title"] for item in payload["new"]
    }
    assert "Prior Week Story Can Drive Trending Down" in {
        item["title"] for item in payload["trending_down"]
    }


def test_weekly_analytics_repo_uses_previous_week_baseline_for_section_meaning(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path}/weekly-analytics-baseline.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    try:
        Base.metadata.create_all(bind=engine)

        with session_local() as session:
            source = Source(
                source_key="weekly-source",
                name="Weekly Source",
                type="rss",
                url="https://example.com/feed",
            )
            session.add(source)
            session.flush()
            session.add_all(
                [
                    Article(
                        source_id=source.id,
                        title="Coding Agents Expand",
                        summary="The topic showed up last week at a lower intensity.",
                        content=None,
                        url="https://example.com/coding-agents-prior",
                        url_canonical="https://example.com/coding-agents-prior",
                        url_canonical_hash="coding-agents-prior",
                        published_at=datetime(2026, 2, 25, 9, 0, tzinfo=UTC),
                        ai_relevance_score=0.7,
                        freshness_score=0.5,
                        rank_score=0.35,
                    ),
                    Article(
                        source_id=source.id,
                        title="Standalone Vector DBs Cool Off",
                        summary="This topic mattered last week but does not recur this week.",
                        content=None,
                        url="https://example.com/vector-dbs-prior",
                        url_canonical="https://example.com/vector-dbs-prior",
                        url_canonical_hash="vector-dbs-prior",
                        published_at=datetime(2026, 2, 27, 13, 0, tzinfo=UTC),
                        ai_relevance_score=0.82,
                        freshness_score=0.6,
                        rank_score=0.88,
                    ),
                    Article(
                        source_id=source.id,
                        title="Coding Agents Expand",
                        summary="The same topic accelerated this week and should be trending up.",
                        content=None,
                        url="https://example.com/coding-agents-recent",
                        url_canonical="https://example.com/coding-agents-recent",
                        url_canonical_hash="coding-agents-recent",
                        published_at=datetime(2026, 3, 5, 11, 0, tzinfo=UTC),
                        ai_relevance_score=0.92,
                        freshness_score=0.8,
                        rank_score=0.97,
                    ),
                    Article(
                        source_id=source.id,
                        title="AI Browser Launches",
                        summary="This topic is net new in the selected seven-day report window.",
                        content=None,
                        url="https://example.com/ai-browser-recent",
                        url_canonical="https://example.com/ai-browser-recent",
                        url_canonical_hash="ai-browser-recent",
                        published_at=datetime(2026, 3, 6, 10, 30, tzinfo=UTC),
                        ai_relevance_score=0.9,
                        freshness_score=0.82,
                        rank_score=0.91,
                    ),
                ]
            )
            session.commit()

        with session_local() as session:
            report = WeeklyAnalyticsRepo(session).get_weekly_report(report_date=date(2026, 3, 7))

        new_titles = {item.title for item in report.new}
        trending_up_titles = {item.title for item in report.trending_up}
        trending_down_titles = {item.title for item in report.trending_down}

        assert "AI Browser Launches" in new_titles
        assert "Coding Agents Expand" not in new_titles
        assert "Coding Agents Expand" in trending_up_titles
        assert "Standalone Vector DBs Cool Off" in trending_down_titles
    finally:
        engine.dispose()
