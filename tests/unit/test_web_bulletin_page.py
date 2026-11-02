"""Hidden stored bulletin preview contract (src/app/web/pages.md)."""
# pylint: disable=redefined-outer-name
import tomllib
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from html import escape
from importlib import import_module
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lxml import html
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import Settings
from app.storage.models_sql import Base, BulletinRow

DAY = date(2026, 10, 30)
WEB_DIR = Path(__file__).resolve().parents[2] / "src" / "app" / "web"
NUMBERS = {"assessed": 7, "digest_articles": 9,
           "writer": {"reason": None, "stories_model": 1, "cost_usd": 0.001}}


def story(title="Original title", **fields):
    return {"title": title, "headline": None, "site_note": [], "gloss": None,
            "area": "Work", "text_origin": "title", "origin": "digest",
            "links": [{"outlet": "Example", "url": "https://example.com/a"}], **fields}


@pytest.fixture
def maker():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def client(maker, monkeypatch, tmp_path):
    web = import_module("app.web.app")
    settings = Settings(_env_file=None, database_url="sqlite://", auth_enabled=True,
                        auth_username="operator", auth_password_hash="fake-hash",
                        auth_secret="0123456789abcdef0123456789abcdef")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(web, "get_settings", lambda: settings)
    monkeypatch.setattr(web, "SessionLocal", maker)
    monkeypatch.setattr(web, "create_all", lambda: None)
    with TestClient(web.create_app()) as test_client:
        yield test_client


def store(maker, day=DAY, *, status="ready", reason=None, **payload):
    content = {"day_number": 1430, "key_results": [story()], "rubric_story": None,
               "cooperation": [], "incident_story": None, **payload}
    with maker() as session:
        session.add(BulletinRow(day=day, status=status, reason=reason,
                                payload=content if status == "ready" else {},
                                numbers=deepcopy(NUMBERS), versions={},
                                generated_at=datetime.now(UTC)))
        session.commit()


def test_bulletin_page_shows_ready_day(maker, client):
    written = story(headline="Written headline",
                    site_note=["First paragraph.", "Second paragraph."],
                    gloss="A short gloss.", text_origin="model", origin="world")
    store(maker, key_results=[written, story("Second result")],
          rubric_story=story("Rubric story"), cooperation=[story("Cooperation story")],
          incident_story=story("Incident story"))
    response = client.get(f"/bulletin?date={DAY}")
    assert response.status_code == 200
    page = html.fromstring(response.text)
    assert DAY.isoformat() in page.xpath("string(//h1)") and "1430" in page.xpath("string(//h1)")
    assert page.xpath("//article/h2/text()") == [
        "Written headline", "Second result", "Rubric story", "Cooperation story", "Incident story"]
    assert "Original title" not in page.text_content()
    assert page.xpath("//article[1]/p/text()") == [
        "First paragraph.", "Second paragraph.", "A short gloss.",
        "Work | text_origin: model | origin: world"]
    assert page.xpath('//article//a[@href="https://example.com/a"]/text()')[0] == "Example"
    numbers = page.get_element_by_id("bulletin-numbers").text_content()
    for expected in ('"assessed": 7', '"digest_articles": 9', '"writer":',
                     '"stories_model": 1', '"cost_usd": 0.001', '"reason": null'):
        assert expected in numbers
    assert response.text.index('id="bulletin-numbers"') > response.text.index("Incident story")
    assert not page.xpath("//script")


def test_bulletin_page_title_only_day(maker, client):
    fields = story()
    for key in ("headline", "site_note", "gloss", "text_origin"):
        fields.pop(key)
    store(maker, key_results=[fields])
    response = client.get(f"/bulletin?date={DAY}")
    assert response.status_code == 200
    page = html.fromstring(response.text)
    assert page.xpath("//article/h2/text()") == ["Original title"]
    assert len(page.xpath("//article/p")) == 1
    assert "text_origin: title | origin: digest" in page.text_content()


def test_bulletin_page_defaults_to_latest_ready(maker, client):
    store(maker, DAY - timedelta(days=1), key_results=[story("Older day")])
    store(maker)
    store(maker, DAY + timedelta(days=1), status="skipped", reason="no_assessments")
    response = client.get("/bulletin")
    assert response.status_code == 200
    page = html.fromstring(response.text)
    assert DAY.isoformat() in page.xpath("string(//h1)")
    assert "Original title" in page.text_content() and "Older day" not in page.text_content()


def test_bulletin_page_skipped_day_links_digest(maker, client):
    store(maker, status="skipped", reason="no_assessments")
    response = client.get(f"/bulletin?date={DAY}")
    assert response.status_code == 200
    assert "No bulletin for this day" in response.text and "no_assessments" in response.text
    assert f'href="/?date={DAY}"' in response.text


def test_bulletin_page_missing_day_is_404(client):
    response = client.get(f"/bulletin?date={DAY}")
    assert response.status_code == 404
    assert "No bulletin for this day" in response.text
    assert f'href="/?date={DAY}"' in response.text


@pytest.mark.parametrize("value", ["bad", "2026-02-30", "20261030", "2026-W44-5", ""])
def test_bulletin_page_bad_date_is_400(client, value):
    response = client.get("/bulletin", params={"date": value})
    assert response.status_code == 400
    assert "date must be YYYY-MM-DD" in response.text


@pytest.mark.parametrize("phase", ["create_all", "SessionLocal", "get", "latest_ready"])
@pytest.mark.usefixtures("client")
def test_bulletin_page_storage_failure_is_503(monkeypatch, phase):
    def unavailable(*_args):
        raise SQLAlchemyError("private database detail")

    target = (import_module("app.storage.bulletin_store").BulletinRepo
              if phase in {"get", "latest_ready"} else import_module("app.web.app"))
    monkeypatch.setattr(target, phase, unavailable)
    web = import_module("app.web.app")
    with TestClient(web.create_app()) as failing_client:
        url = "/bulletin?date=2026-10-30" if phase == "get" else "/bulletin"
        response = failing_client.get(url)
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("text/html")
    assert "News storage is unavailable" in response.text
    assert "private database detail" not in response.text


@pytest.mark.parametrize("skipped", [False, True])
def test_bulletin_page_empty_store_is_404(maker, client, skipped):
    if skipped:
        store(maker, status="skipped", reason="no_assessments")
    response = client.get("/bulletin")
    assert response.status_code == 404
    assert "No bulletin is stored yet" in response.text


@pytest.mark.parametrize("title_only", [False, True])
def test_bulletin_page_escapes_stored_text(maker, client, title_only):
    unsafe = '<script>alert("x")</script> & __BULLETIN_NAV__'
    fields = story(headline=unsafe, site_note=[unsafe], gloss=unsafe, area=unsafe,
                   text_origin=unsafe, origin=unsafe,
                   links=[{"outlet": unsafe, "url": "javascript:alert(1)"},
                          {"outlet": "Safe & outlet", "url": 'HTTPS://example.com/?a="&b=2'},
                          {"outlet": "Mail", "url": "mailto:test@example.com"},
                          {"outlet": "HTTP", "url": "http://example.com/plain"}])
    if title_only:
        fields.update(headline=None, title=unsafe)
    store(maker, key_results=[fields], day_number=unsafe)
    response = client.get(f"/bulletin?date={DAY}")
    assert response.status_code == 200
    assert unsafe not in response.text and escape(unsafe) in response.text
    page = html.fromstring(response.text)
    assert not page.xpath("//script")
    assert page.xpath("//article//a/@href") == [
        'HTTPS://example.com/?a="&b=2', "http://example.com/plain"]
    assert unsafe in page.xpath("//article")[0].text_content()
    assert "Mail" in page.xpath("//article")[0].text_content()
    assert "__BULLETIN_NAV__" in page.text_content()
    with maker() as session:
        row = session.get(BulletinRow, DAY)
        row.numbers = {"writer": {"reason": unsafe}}
        session.commit()
    assert escape(unsafe).replace("&quot;", "\\&quot;") in client.get(
        f"/bulletin?date={DAY}").text
    store(maker, DAY + timedelta(days=1), status="skipped", reason=unsafe)
    skipped = client.get(f"/bulletin?date={DAY + timedelta(days=1)}")
    assert escape(unsafe) in skipped.text and not html.fromstring(skipped.text).xpath("//script")


def test_bulletin_page_is_public_and_noindex(maker, client):
    store(maker)
    assert client.get("/admin", follow_redirects=False).status_code == 303
    response = client.get(f"/bulletin?date={DAY}")
    assert response.status_code == 200
    page = html.fromstring(response.text)
    assert page.xpath('//meta[@name="robots"]/@content') == ["noindex, nofollow"]
    assert page.get("lang") == "en"
    assert page.xpath('//link[@rel="stylesheet"]/@href') == ["/static/css/digest.css"]
    assert not page.xpath("//style|//script")
    assert client.get("/static/css/digest.css").status_code == 200


def test_bulletin_page_template_is_packaged():
    config = tomllib.loads((WEB_DIR.parents[2] / "pyproject.toml").read_text(encoding="utf-8"))
    assert "bulletin.html" in config["tool"]["setuptools"]["package-data"]["app.web"]


def test_bulletin_page_is_not_linked():
    assert (WEB_DIR / "bulletin.html").exists()
    assert (WEB_DIR / "bulletin_view.py").exists()
    candidates = [*WEB_DIR.glob("*.html"), *WEB_DIR.glob("*_view.py"),
                  *(p for p in (WEB_DIR / "static").rglob("*") if p.is_file())]
    for path in candidates:
        if path.name in {"bulletin.html", "bulletin_view.py"}:
            continue
        assert "/bulletin" not in path.read_text(encoding="utf-8"), path


@pytest.mark.parametrize("offset", [-2, -1, 0, 1])
def test_bulletin_page_prev_next_links(client, offset):
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    day = yesterday + timedelta(days=offset)
    response = client.get(f"/bulletin?date={day}")
    page = html.fromstring(response.text)
    nav = page.xpath('//nav[@aria-label="Bulletin dates"]')
    assert len(nav) == 1
    assert nav[0].xpath('a[@rel="prev"]/@href') == [f"/bulletin?date={day - timedelta(days=1)}"]
    following = nav[0].xpath('a[@rel="next"]/@href')
    if offset < 0:
        assert following == [f"/bulletin?date={day + timedelta(days=1)}"]
    else:
        assert not following


def test_bulletin_page_first_calendar_day_has_no_previous(client):
    response = client.get("/bulletin?date=0001-01-01")
    assert response.status_code == 404
    page = html.fromstring(response.text)
    assert not page.xpath('//nav/a[@rel="prev"]')
    assert page.xpath('//nav/a[@rel="next"]/@href') == ["/bulletin?date=0001-01-02"]
