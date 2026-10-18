import json
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.core.daily_signals_compute import EVENT_LABELS
from app.storage.models_sql import Base, DailySignalReport
from app.web.app import create_app
from app.web.signals_view import SINGULAR, event_label


def test_public_digest_page_renders_digest_shell_with_yesterday_selected(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path}/public-digest-page.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 1, 9, 30, tzinfo=tz or UTC)

    def _create_all_local() -> None:
        Base.metadata.create_all(bind=engine)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", _create_all_local)
    monkeypatch.setattr(web_app_module, "SessionLocal", session_local)
    monkeypatch.setattr(web_app_module, "datetime", _FrozenDateTime)

    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "Yesterday&#39;s Digest" in response.text or "Yesterday's Digest" in response.text
    assert 'type="date"' in response.text
    assert 'value="2026-02-28"' in response.text
    assert 'href="/news-stats"' in response.text
    assert "/api/news/links?date=" in response.text


def test_public_digest_page_shows_clean_empty_state_when_digest_missing(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path}/public-digest-empty.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 2, 8, 0, tzinfo=tz or UTC)

    def _create_all_local() -> None:
        Base.metadata.create_all(bind=engine)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", _create_all_local)
    monkeypatch.setattr(web_app_module, "SessionLocal", session_local)
    monkeypatch.setattr(web_app_module, "datetime", _FrozenDateTime)

    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "No digest has been published for this date yet." in response.text


def test_public_digest_page_keeps_explicit_query_date_selected(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path}/public-digest-query-date.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _create_all_local() -> None:
        Base.metadata.create_all(bind=engine)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 1, 9, 30, tzinfo=tz or UTC)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", _create_all_local)
    monkeypatch.setattr(web_app_module, "SessionLocal", session_local)
    monkeypatch.setattr(web_app_module, "datetime", _FrozenDateTime)

    client = TestClient(create_app())

    response = client.get("/?date=2026-02-27")

    assert response.status_code == 200
    assert "Digest for 2026-02-27" in response.text
    assert 'value="2026-02-27"' in response.text
    assert '"?date=2026-02-27"' in response.text
    assert '"2026-02-28"' in response.text
    assert "history.replaceState" in response.text
    assert "updateHeroTitle" in response.text


def test_public_digest_page_stays_public_when_auth_is_enabled(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AINEWS_AUTH_ENABLED", "true")
    monkeypatch.setenv("AINEWS_AUTH_USERNAME", "admin")
    monkeypatch.setenv(
        "AINEWS_AUTH_PASSWORD_HASH",
        "$2b$12$abcdefghijklmnopqrstuuuuuuuuuuuuuuuuuuuuuuuuuu",
    )
    monkeypatch.setenv("AINEWS_AUTH_SECRET", "12345678901234567890123456789012")
    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path}/public-digest-auth.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 3, 8, 0, tzinfo=tz or UTC)

    def _create_all_local() -> None:
        Base.metadata.create_all(bind=engine)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", _create_all_local)
    monkeypatch.setattr(web_app_module, "SessionLocal", session_local)
    monkeypatch.setattr(web_app_module, "datetime", _FrozenDateTime)

    client = TestClient(create_app())

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 200
    assert "Yesterday&#39;s Digest" in response.text or "Yesterday's Digest" in response.text


SIGNALS: dict[str, Any] = {
    "report_date": "2026-10-16", "status": "building_history",
    "coverage": {"items": 4, "matched": 4, "extracted": 4},
    "notes": [],
    "sections": {"new": {"state": "building", "note": "History: 6 complete days."},
                 "top_stories": {"state": "ready"},
                 "rising": {"state": "spikes_only",
                            "note": "Rising needs two weeks with at least 6 complete days each; "
                                    "showing spikes."},
                 "cooling": {"state": "hidden"}, "event_counts": {"state": "ready"}},
    "new": [{"entity_id": 1, "name": "<script>alert(1)</script>", "type": "model",
             "vendor": "Acme", "level": "early", "variant_of": "Muse Spark",
             "variants": ["Muse Spark Open 8B"], "novelty_quote": "Today we launch <b>it</b>",
             "articles": 1, "publishers": 1,
             "links": [{"title": "Safe", "url": "https://a.com/x", "publisher": "a.com"},
                       {"title": "Bad", "url": "javascript:alert(1)", "publisher": "b.com"}]}],
    "top_stories": [{"label": "Beam launch", "event_type": "model_release", "articles": 4,
                     "publishers": 4, "entities": ["Beam"], "links": []}],
    "rising": [{"entity_id": 2, "name": "Beam", "type": "model", "today": 4,
                "trailing_mean": 0.25, "spike": True, "publishers": 4, "links": []}],
    "cooling": [],
    "event_counts": [{"event_type": "model_release", "label": "model releases", "stories": 1,
                      "articles": 4, "links": []},
                     {"event_type": "funding", "label": "funding rounds", "stories": 2,
                      "articles": 2, "links": []}],
    "article_event_types": {},
}


def _signals_client(monkeypatch, tmp_path, payload=None, *, broken=False):
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    engine = create_engine(f"sqlite:///{tmp_path}/signals-page.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, future=True)
    Base.metadata.create_all(bind=engine)
    if payload is not None:
        with session_local() as session:
            session.add(DailySignalReport(
                report_date=datetime(2026, 10, 16).date(), methodology_version="m",
                extraction_version="e", status=payload["status"], payload_hash="x" * 64,
                thresholds="{}", coverage="{}", payload=json.dumps(payload),
                created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
            session.commit()
    web = import_module("app.web.app")
    monkeypatch.setattr(web, "create_all", lambda: Base.metadata.create_all(bind=engine))
    monkeypatch.setattr(web, "SessionLocal", session_local)
    if broken:
        class _Broken:
            def __init__(self, _session, **_kwargs):
                raise SQLAlchemyError("signals table missing")
        monkeypatch.setattr(web, "DailySignalRepo", _Broken)
    return TestClient(create_app())


def test_signals_block_renders_escaped_states_and_links(monkeypatch, tmp_path) -> None:
    html = _signals_client(monkeypatch, tmp_path, SIGNALS).get("/?date=2026-10-16").text
    block = html.split('id="daily-signals-body">', 1)[1].split("</section>\n", 1)[0]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in block and "<script>alert" not in block
    assert "early signal" in block and "variant of Muse Spark" in block
    assert "also: Muse Spark Open 8B" in block
    assert 'Source says: "Today we launch &lt;b&gt;it&lt;/b&gt;"' in block
    assert 'href="https://a.com/x"' in block and "javascript:" not in block
    assert "1 model release<" in block and "2 funding rounds" in block
    assert "History: 6 complete days." in block
    assert "<h3>Spikes</h3>" in block and "today 4 vs 0.25/day" in block
    assert "4 sources &middot; model release" in block
    assert "Cooling" not in block
    assert 'id="weekly-analytics-preview"' in html
    assert html.index('id="daily-signals"') < html.index('class="digest-shell"')


def test_signals_unavailable_partial_and_cooling(monkeypatch, tmp_path) -> None:
    html = _signals_client(monkeypatch, tmp_path).get("/?date=2026-10-16").text
    assert "Daily signals are not available for this date yet." in html
    assert 'class="signal-grid"' not in html.split('id="daily-signals-body">', 1)[1][:400]
    partial = dict(SIGNALS, status="partial", coverage={"items": 64, "extracted": 50},
                   sections=dict(SIGNALS["sections"], rising={"state": "ready"},
                                 cooling={"state": "ready"}),
                   cooling=[{"entity_id": 3, "name": "Old Thing", "type": "model", "today": 0,
                             "current_7d": 1, "previous_7d": 8, "expected_7d": 8.0,
                             "publishers": 3, "links": []}])
    (tmp_path / "p").mkdir()
    html = _signals_client(monkeypatch, tmp_path / "p", partial).get("/?date=2026-10-16").text
    assert "Extracted 50/64 digest items; signals may be incomplete." in html
    assert "<h3>Rising</h3>" in html and "Cooling (1)" in html
    assert "7d: 8 &rarr; 1 (expected 8)" in html


def test_signals_read_error_keeps_page(monkeypatch, tmp_path) -> None:
    response = _signals_client(monkeypatch, tmp_path, SIGNALS, broken=True).get(
        "/?date=2026-10-16")
    assert response.status_code == 200
    assert "Daily signals are temporarily unavailable." in response.text
    assert "Digest for 2026-10-16" in response.text


def test_signals_client_rendering_hooks() -> None:
    template = (Path(__file__).resolve().parents[2] / "src/app/web/digest.html").read_text()
    assert "/api/news/daily-signals?date=" in template
    assert "function renderSignals(payload)" in template
    assert "if (dateInput.value !== selectedDate) return;" in template
    load_digest = template.split("async function loadDigest", 1)[1].split("\n      }\n", 1)[0]
    assert "loadSignals(selectedDate)" in load_digest
    assert "escapeHtml(item.name)" in template and "/^https?:\\/\\//i.test(link.url)" in template


def test_event_labels_singular_and_plural() -> None:
    assert event_label(1, "product launches") == "1 product launch"
    assert event_label(2, "product launches") == "2 product launches"
    assert event_label(1, "analysis") == "1 analysis"
    assert set(SINGULAR) <= set(EVENT_LABELS.values())
    template = (Path(__file__).resolve().parents[2] / "src/app/web/digest.html").read_text()
    for plural, singular in SINGULAR.items():
        assert f'"{plural}": "{singular}"' in template
