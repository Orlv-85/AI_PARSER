import json
from datetime import UTC, date, datetime
from importlib import import_module
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.core.daily.signals_brief import HARD_EVENTS
from app.core.daily.signals_model import EVENT_LABELS
from app.storage.digest_repo import NewsDigestRepo
from app.storage.models_sql import Base, DailySignalBrief, DailySignalReport
from app.web.app import create_app
from app.web.routes import common as common_routes
from app.web.routes import pages as pages_routes
from app.web.signals_view import AI_NOTE, SINGULAR, event_label

_WEB_DIR = Path(__file__).resolve().parents[2] / "src/app/web"
_DIGEST_JS = _WEB_DIR / "static/js/digest.js"


def _digest_source() -> str:
    """The public page as shipped: template, its stylesheet and its script."""
    return "".join((_WEB_DIR / name).read_text()
                   for name in ("digest.html", "static/css/digest.css", "static/js/digest.js"))


def test_public_digest_page_renders_digest_shell_with_yesterday_selected(
    monkeypatch, tmp_path, page_with_assets
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
    monkeypatch.setattr(pages_routes, "datetime", _FrozenDateTime)

    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "Yesterday&#39;s Digest" in response.text or "Yesterday's Digest" in response.text
    assert 'type="date"' in response.text
    assert 'value="2026-02-28"' in response.text
    assert 'href="/news-stats"' in response.text
    assert "/api/news/links?date=" in page_with_assets(client, response)


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
    monkeypatch.setattr(pages_routes, "datetime", _FrozenDateTime)

    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "No digest has been published for this date yet." in response.text


def test_public_digest_page_keeps_explicit_query_date_selected(
    monkeypatch, tmp_path, page_with_assets
) -> None:
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
    monkeypatch.setattr(pages_routes, "datetime", _FrozenDateTime)

    client = TestClient(create_app())

    response = client.get("/?date=2026-02-27")

    assert response.status_code == 200
    assert "Digest for 2026-02-27" in response.text
    assert 'value="2026-02-27"' in response.text
    assert '"?date=2026-02-27"' in response.text
    assert '"2026-02-28"' in response.text
    text = page_with_assets(client, response)
    assert "history.replaceState" in text
    assert "updateHeroTitle" in text


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
    monkeypatch.setattr(pages_routes, "datetime", _FrozenDateTime)

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


def _signals_client(monkeypatch, tmp_path, payload=None, *, broken=False, brief=None):
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
            if brief is not None:
                session.add(DailySignalBrief(
                    report_date=datetime(2026, 10, 16).date(), brief_version="b", model="m",
                    input_hash="h", status="ok", reason=None,
                    payload=brief if isinstance(brief, str) else json.dumps(brief),
                    created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
            session.commit()
    web = import_module("app.web.app")
    monkeypatch.setattr(web, "create_all", lambda: Base.metadata.create_all(bind=engine))
    monkeypatch.setattr(web, "SessionLocal", session_local)
    if broken:
        class _Broken:
            def __init__(self, _session, **_kwargs):
                raise SQLAlchemyError("signals table missing")
        monkeypatch.setattr(common_routes, "DailySignalRepo", _Broken)
    return TestClient(create_app())


def test_signals_block_renders_escaped_states_and_links(monkeypatch, tmp_path) -> None:
    html = _signals_client(monkeypatch, tmp_path, SIGNALS).get("/?date=2026-10-16").text
    block = html.split('id="daily-signals-body">', 1)[1].split("</section>\n", 1)[0]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in block and "<script>alert" not in block
    # 007 D3: no per-item badge; a single-source item is muted with "via <publisher>".
    assert "early signal" not in block and "variant of Muse Spark" in block
    assert '<li class="signal-muted">' in block and "via a.com" in block
    assert "also: Muse Spark Open 8B" in block
    assert 'Source says: "Today we launch &lt;b&gt;it&lt;/b&gt;"' in block
    assert 'href="https://a.com/x"' in block and "javascript:" not in block
    assert "1 model release<" in block and "2 funding rounds" in block
    assert "History: 6 complete days." in block
    assert "<h3>Spikes</h3>" in block and "today 4 vs 0.25/day" in block
    assert "4 outlets &middot; model release" in block
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
    template = _digest_source()
    assert "/api/news/daily-signals?date=" in template
    assert "function renderSignals(payload)" in template
    assert "if (dateInput.value !== selectedDate) return;" in template
    change = template.split('dateInput.addEventListener("change"', 1)[1].split("});", 1)[0]
    assert "loadSignals(selected)" in change
    assert "escapeHtml(item.name)" in template and "/^https?:\\/\\//i.test(link.url)" in template


def test_event_labels_singular_and_plural() -> None:
    assert event_label(1, "product launches") == "1 product launch"
    assert event_label(2, "product launches") == "2 product launches"
    assert event_label(1, "analysis") == "1 analysis"
    assert set(SINGULAR) <= set(EVENT_LABELS.values())
    template = _digest_source()
    for plural, singular in SINGULAR.items():
        assert f'"{plural}": "{singular}"' in template


def test_trend_without_expected_value_and_any_render_error_keep_page(monkeypatch,
                                                                     tmp_path) -> None:
    # F5: a stored trend with `current_7d` but `expected_7d: null` passed the model and then
    # crashed the page; any signals failure must leave the digest page up.
    odd = dict(SIGNALS, rising=[{"entity_id": 9, "name": "Odd Trend", "type": "model",
                                 "today": 2, "current_7d": 3, "previous_7d": None,
                                 "expected_7d": None, "publishers": 2, "links": []}])
    response = _signals_client(monkeypatch, tmp_path, odd).get("/?date=2026-10-16")
    assert response.status_code == 200
    assert "Odd Trend" in response.text and "7d: - &rarr; 3" in response.text
    original = pages_routes.render_signals

    def _boom(signals, *, read_error=False):
        if not read_error:
            raise RuntimeError("render bug")
        return original(signals, read_error=True)

    monkeypatch.setattr(pages_routes, "render_signals", _boom)
    (tmp_path / "b").mkdir()
    response = _signals_client(monkeypatch, tmp_path / "b", SIGNALS).get("/?date=2026-10-16")
    assert response.status_code == 200
    assert "Daily signals are temporarily unavailable." in response.text


def test_placeholders_in_digest_text_are_not_substituted(monkeypatch, tmp_path) -> None:
    # N1: digest text naming a template placeholder stays literal (single-pass substitution).
    client = _signals_client(monkeypatch, tmp_path, SIGNALS)
    web = import_module("app.web.app")
    with web.SessionLocal() as session:
        NewsDigestRepo(session).save_digest(report_date=date(2026, 10, 16), groups=[{
            "title": "Models", "items": [{"title": "__SIGNALS_CONTENT__ and __REPORT_DATE__",
                                          "summary": "s", "url": "https://a.com/p"}]}])
        session.commit()
    html = client.get("/?date=2026-10-16").text
    assert "__SIGNALS_CONTENT__ and __REPORT_DATE__" in html
    assert html.count('id="signals-new"') == 1


def test_signals_reload_on_date_change_independent_of_digest() -> None:
    # F16: the block is reset while loading, loaded even if the digest request fails, and an
    # error answer says "temporarily unavailable" rather than "not available yet".
    script = _DIGEST_JS.read_text()
    change = script.split('dateInput.addEventListener("change"', 1)[1].split("});", 1)[0]
    assert "loadSignals(" in change and change.index("loadSignals(") < change.index("loadDigest(")
    load_digest = script.split("async function loadDigest", 1)[1].split("\n      }\n", 1)[0]
    assert "loadSignals(" not in load_digest
    load_signals = script.split("async function loadSignals", 1)[1].split("\n      }\n", 1)[0]
    assert load_signals.index("SIGNALS_LOADING") < load_signals.index("fetch(")
    assert "SIGNALS_ERROR" in load_signals
    assert 'const SIGNALS_ERROR = "Daily signals are temporarily unavailable.";' in script


# 007 ----------------------------------------------------------------------------------------
BRIEF = {"sentences": [
    {"text": "Reflection released <b>Beam</b>, covered by 4 outlets.", "quote": "q",
     "links": [{"title": "Welcome \"Beam\"", "url": "https://hf.co/b", "publisher": "hf.co"},
               {"title": "Bad", "url": "javascript:alert(1)", "publisher": "x.com"},
               {"title": "VB", "url": "https://vb.com/b", "publisher": "vb.com"}]}]}
SIGNALS_007 = dict(
    SIGNALS, quiet=False,
    new=[dict(SIGNALS["new"][0], name="Beam", level="confirmed", publishers=3,
              one_liner="Reflection released Beam, an open model.", one_liner_source="summary",
              variant_of=None, variants=[]),
         dict(SIGNALS["new"][0], name="d1-ultra", one_liner="Today, we release d1-ultra",
              one_liner_source="quote", variant_of=None, variants=[])],
    top_stories=[dict(SIGNALS["top_stories"][0], spikes=["Beam", "Reflection"])],
    rising=[],
    event_counts=SIGNALS["event_counts"] + [
        {"event_type": "opinion_analysis", "label": "analysis", "stories": 11, "articles": 11,
         "links": []},
        {"event_type": "other", "label": "other", "stories": 5, "articles": 5, "links": []}])


def _block(html):
    return html.split('id="daily-signals-body">', 1)[1].split("</section>\n", 1)[0]


def test_brief_rendered_escaped_with_http_links_and_ai_note(monkeypatch, tmp_path) -> None:
    block = _block(_signals_client(monkeypatch, tmp_path, SIGNALS_007, brief=BRIEF)
                   .get("/?date=2026-10-16").text)
    assert block.startswith('<div class="signal-brief-block"><h3>In brief</h3>')
    assert '<ul class="signal-brief"><li>Reflection released &lt;b&gt;Beam&lt;/b&gt;' in block
    assert ('<a class="signal-ref" href="https://hf.co/b" title="Welcome &quot;Beam&quot;" '
            'target="_blank" rel="noreferrer">[1]</a>') in block
    assert 'href="https://vb.com/b"' in block and ">[2]</a>" in block and ">[3]<" not in block
    assert "javascript:" not in block
    assert "Written by AI from the linked articles; check the sources." in block
    assert block.index("signal-brief-block") < block.index("signal-chips")


def test_d3_one_liners_spike_tags_chips_and_hidden_spikes(monkeypatch, tmp_path) -> None:
    block = _block(_signals_client(monkeypatch, tmp_path, SIGNALS_007)
                   .get("/?date=2026-10-16").text)
    assert "signal-brief-block" not in block  # no brief and not quiet: nothing shown
    assert "early signal" not in block
    beam = block.split('<li class="signal-confirmed"><strong>Beam</strong>', 1)[1]
    assert beam.startswith('<p class="signal-meta">model &middot; Acme &middot; 3 outlets</p>'
                           '<p class="signal-what">Reflection released Beam, an open model.</p>')
    assert 'Source says: "Today we launch' in beam.split("</details>", 1)[0]
    d1 = block.split('<li class="signal-muted"><strong>d1-ultra</strong>', 1)[1]
    d1 = d1.split("</details>", 1)[0]
    assert "via a.com" in d1 and '<p class="signal-what">&quot;Today, we release d1-ultra&quot;' \
        in d1 and "Source says" not in d1 and "variant of" not in d1
    assert "4 outlets &middot; model release &middot; spike: Beam, Reflection" in block
    assert '<li class="signal-chip">2 funding rounds</li>' in block
    assert ('<li class="signal-chip signal-chip-more" title="11 analysis, 5 other">+16 more</li>'
            in block)
    assert "<h3>Spikes</h3>" not in block and 'class="signal-grid cols-2"' in block
    assert '<p class="signals-status">Rising needs two weeks' in block


def test_spike_reason_line(monkeypatch, tmp_path) -> None:
    payload = dict(SIGNALS_007, rising=[
        dict(SIGNALS["rising"][0], name="GPT-6 Astra", reason="Argon vs <Astra>"),
        dict(SIGNALS["rising"][0], name="Zeta", trailing_mean=0.0, reason=None)])
    block = _block(_signals_client(monkeypatch, tmp_path, payload).get("/?date=2026-10-16").text)
    assert "<h3>Spikes</h3>" in block and 'class="signal-grid cols-3"' in block
    assert "today 4 vs 0.25/day - Argon vs &lt;Astra&gt;" in block
    assert "today 4 vs none before</p>" in block


def test_quiet_day_render(monkeypatch, tmp_path) -> None:
    quiet = dict(SIGNALS_007, quiet=True, coverage={"items": 14}, top_stories=[],
                 new=SIGNALS_007["new"][1:])
    brief = {"sentences": [dict(BRIEF["sentences"][0], text="Anthropic announced a fund.")]}
    block = _block(_signals_client(monkeypatch, tmp_path, quiet, brief=brief)
                   .get("/?date=2026-10-16").text)
    assert ('<p class="signal-quiet">Quiet day: 14 items, no story covered by more than one '
            'outlet.</p><ul class="signal-brief"><li>Anthropic announced a fund.') in block
    assert 'id="signals-new"' in block and 'class="signal-grid cols-1"' in block
    assert 'id="signals-top"' not in block and 'id="signals-rising"' not in block
    assert "Rising needs two weeks" not in block
    empty = dict(quiet, new=[], top_stories=[SIGNALS["top_stories"][0]])
    (tmp_path / "q").mkdir()
    block = _block(_signals_client(monkeypatch, tmp_path / "q", empty)
                   .get("/?date=2026-10-16").text)
    assert "Quiet day: 14 items, 1 story covered by more than one outlet." in block
    assert "signal-brief\"" not in block and "Written by AI" not in block
    # F1: a quiet day still shows a card that has items (here the one top story).
    assert 'id="signals-top"' in block and "Beam launch" in block
    assert 'id="signals-new"' not in block and 'id="signals-rising"' not in block
    assert 'class="signal-grid cols-1"' in block
    rising = dict(empty, top_stories=[], sections=dict(SIGNALS["sections"], rising={
        "state": "ready", "note": None}), rising=[dict(SIGNALS["rising"][0], spike=False,
                                                       current_7d=6, previous_7d=1,
                                                       expected_7d=1.0)])
    (tmp_path / "r").mkdir()
    block = _block(_signals_client(monkeypatch, tmp_path / "r", rising)
                   .get("/?date=2026-10-16").text)
    assert "<h3>Rising</h3>" in block and "7d: 1 &rarr; 6" in block
    assert 'id="signals-top"' not in block and 'id="signals-new"' not in block
    spikes = dict(empty, top_stories=[], rising=[SIGNALS["rising"][0]])
    (tmp_path / "s").mkdir()
    block = _block(_signals_client(monkeypatch, tmp_path / "s", spikes)
                   .get("/?date=2026-10-16").text)
    assert "<h3>Spikes</h3>" in block and "Rising needs two weeks" not in block
    none = dict(empty, top_stories=[])
    (tmp_path / "n").mkdir()
    block = _block(_signals_client(monkeypatch, tmp_path / "n", none)
                   .get("/?date=2026-10-16").text)
    assert "signal-grid" not in block and "Rising needs two weeks" not in block


def test_page_200_with_a_corrupt_brief_row(monkeypatch, tmp_path) -> None:
    response = _signals_client(monkeypatch, tmp_path, SIGNALS_007, brief="{broken").get(
        "/?date=2026-10-16")
    assert response.status_code == 200
    block = _block(response.text)
    assert "signal-brief-block" not in block and "<strong>Beam</strong>" in block


def test_client_renderer_matches_server_classes() -> None:
    template = _digest_source()
    script = template.split("function renderSignals(payload)", 1)[0]
    for marker in ('class="signal-brief-block"><h3>In brief</h3>', 'class="signal-brief"',
                   'class="signal-ref"', 'rel="noreferrer">[${i + 1}]</a>', 'class="signal-quiet"',
                   'class="signal-ai-note"', 'class="signal-what"', '"signal-confirmed"',
                   '"signal-muted"', "signal-chip signal-chip-more", "via ${links[0].publisher}",
                   "spike: ${story.spikes.join", "none before", "Quiet day: "):
        assert marker in template, marker
    assert "HARD_EVENTS.includes(c.event_type)" in template
    assert "early signal" not in template
    hard = script.split("const HARD_EVENTS = [", 1)[1].split("];", 1)[0]
    assert [x.strip().strip('"') for x in hard.replace("\n", " ").split(",")] == list(HARD_EVENTS)
    assert f'const SIGNALS_AI_NOTE = "{AI_NOTE}";' in template
