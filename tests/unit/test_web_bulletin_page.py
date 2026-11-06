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
    content = {"day_number": 1430, "byline": "Bulletin of the AI World Administration / Day 1430",
               "headline": "A NEW WORKING DAY", "opening": "Progress continues.",
               "numbers": "Seven events recorded.", "key_results": [story()],
               "rubric_name": "Field test", "rubric_story": None, "cooperation": [],
               "incidents": 0, "incident_story": None, "closing": "Implementation continues.",
               "items": 9, "full_report_url": f"/daily?date={day}", "headline_cut": False,
               **payload}
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
          incidents=1, incident_story=story("Incident story"))
    response = client.get(f"/bulletin?date={DAY}")
    assert response.status_code == 200
    page = html.fromstring(response.text)
    assert page.xpath("//time/@datetime") == [DAY.isoformat()]
    assert "1430" in page.xpath('string(//*[@class="byline"])')
    assert page.xpath("//article/h3/text()") == [
        "Written headline", "Second result", "Rubric story", "Cooperation story", "Incident story"]
    assert "Original title" not in page.text_content()
    assert page.xpath("(//article)[1]/p/text()") == [
        "Work", "First paragraph.", "Second paragraph.", "A short gloss."]
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
    assert page.xpath("//article/h3/text()") == ["Original title"]
    assert len(page.xpath("//article/p")) == 1
    assert "text_origin: title | origin: digest" in page.text_content()


def test_bulletin_page_defaults_to_latest_ready(maker, client):
    store(maker, DAY - timedelta(days=1), key_results=[story("Older day")])
    store(maker)
    store(maker, DAY + timedelta(days=1), status="skipped", reason="no_assessments")
    response = client.get("/bulletin")
    assert response.status_code == 200
    page = html.fromstring(response.text)
    assert page.xpath("//time/@datetime") == [DAY.isoformat()]
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
    assert page.xpath('//link[@rel="stylesheet"]/@href') == ["/static/css/bulletin.css"]
    assert not page.xpath("//style|//script")
    assert client.get("/static/css/bulletin.css").status_code == 200


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


@pytest.mark.parametrize("sections", ["full", "empty", "count_only"])
def test_bulletin_page_issue_order(maker, client, sections):
    full = sections == "full"
    store(maker, key_results=[story("Key story")] if full else [],
          rubric_story=story("Rubric story") if full else None,
          cooperation=[story("Cooperation story")] if full else [],
          incidents=3 if sections != "empty" else 0,
          incident_story=story("Incident story") if full else None)
    page = html.fromstring(client.get(f"/bulletin?date={DAY}").text)
    headings = page.xpath("//section/h2/text()")
    expected = ["Key results", "Field test", "Cooperation with humanity"] if full else []
    if sections != "empty":
        expected.append("Isolated incidents: 3")
    assert headings == expected
    text = page.xpath("//main")[0].text_content()
    ordered = ["A NEW WORKING DAY", "Progress continues.", "Seven events recorded."]
    if full:
        ordered += ["Key results", "Key story", "Field test", "Rubric story",
                    "Cooperation with humanity", "Cooperation story",
                    "Isolated incidents: 3", "Among them", "Incident story"]
    ordered += ["Implementation continues.", "Full report (9)"]
    assert [text.index(part) for part in ordered] == sorted(text.index(part) for part in ordered)
    assert bool(page.xpath('//*[@class="among"]')) is full


def test_bulletin_page_null_headline_and_zero_incidents(maker, client):
    store(maker, headline=None, incidents=0, incident_story=story("Stray incident"))
    page = html.fromstring(client.get(f"/bulletin?date={DAY}").text)
    assert page.xpath("//h1/text()") == [f"Bulletin for {DAY}"]
    assert page.xpath("//section/h2/text()") == ["Key results"]
    assert all("Stray incident" not in section.text_content()
               for section in page.xpath("//section"))


def test_bulletin_page_masthead_and_byline(maker, client):
    byline = "Bulletin of the AI World Administration / Day 1430 / Oct 30"
    store(maker, byline=byline)
    page = html.fromstring(client.get(f"/bulletin?date={DAY}").text)
    assert page.xpath('string(//header//*[@class="masthead"])') == "THE DAILY INFERENCE"
    assert page.xpath('string(//*[@class="byline"])') == byline
    assert page.xpath("//h1/text()") == ["A NEW WORKING DAY"]


def test_bulletin_page_footer_satire_and_gdelt(maker, client):
    store(maker)
    page = html.fromstring(client.get(f"/bulletin?date={DAY}").text)
    assert "Satire. Every fact is real and linked." in page.xpath("string(//footer)")
    assert "News discovery: GDELT Project" in page.xpath("string(//footer)")
    assert page.xpath('//footer//a[@href="https://www.gdeltproject.org/"]/text()') == [
        "GDELT Project"]


def test_bulletin_page_full_report_links_digest(maker, client):
    store(maker, items=42, full_report_url="/daily?date=2000-01-01")
    page = html.fromstring(client.get(f"/bulletin?date={DAY}").text)
    link = page.xpath('//a[starts-with(text(), "Full report")]')
    assert len(link) == 1
    assert link[0].text_content() == "Full report (42) \u2192"
    assert link[0].get("href") == f"/?date={DAY}"
    assert not page.xpath('//a[starts-with(@href, "/daily")]')


def test_bulletin_page_checking_block_collapsed(maker, client):
    store(maker, key_results=[story("Key", text_origin="model", origin="world")],
          rubric_story=story("Rubric"), cooperation=[story("Cooperation")],
          incidents=1, incident_story=story("Incident"))
    page = html.fromstring(client.get(f"/bulletin?date={DAY}").text)
    blocks = page.xpath("//details")
    assert len(blocks) == 1 and "open" not in blocks[0].attrib
    assert blocks[0].xpath("summary/text()") == ["For checking"]
    assert blocks[0].xpath(".//li/strong/text()") == ["Key", "Rubric", "Cooperation", "Incident"]
    assert "text_origin: model | origin: world" in blocks[0].text_content()
    assert '"assessed": 7' in blocks[0].text_content()
    assert page.xpath('//pre[@id="bulletin-numbers"]/ancestor::details') == blocks
    assert page.xpath("//main/*[last()]") == blocks
    blocks[0].drop_tree()
    assert "text_origin" not in page.text_content() and "origin:" not in page.text_content()


@pytest.mark.parametrize("state", ["skipped", "missing", "empty", "error"])
def test_bulletin_page_status_pages_share_shell(maker, client, monkeypatch, state):
    if state == "skipped":
        store(maker, status="skipped", reason="no_assessments")
    if state == "error":
        def unavailable():
            raise SQLAlchemyError("private")
        monkeypatch.setattr(import_module("app.web.app"), "create_all", unavailable)
        client = TestClient(import_module("app.web.app").create_app())
    url = "/bulletin" if state == "empty" else f"/bulletin?date={DAY}"
    response = client.get(url)
    assert response.status_code == {"skipped": 200, "error": 503}.get(state, 404)
    page = html.fromstring(response.text)
    assert page.xpath('string(//header//*[@class="masthead"])') == "THE DAILY INFERENCE"
    assert "Satire. Every fact is real and linked." in page.xpath("string(//footer)")
    assert page.xpath('//footer//a/@href') == ["https://www.gdeltproject.org/"]
    assert not page.xpath("//details")


def test_bulletin_page_mobile_viewport(client):
    page = html.fromstring(client.get("/bulletin").text)
    assert page.xpath('//meta[@name="viewport"]/@content') == [
        "width=device-width, initial-scale=1"]
    assert page.xpath('//link[@rel="stylesheet"]/@href') == ["/static/css/bulletin.css"]
    assert not page.xpath("//script|//style|//img|//iframe")
    response = client.get("/static/css/bulletin.css")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
    assert response.headers["cache-control"] == "no-cache"
    assert "@import" not in response.text and "url(" not in response.text


@pytest.mark.parametrize("cut", [False, True])
def test_bulletin_page_cut_headline_footnote(maker, client, cut):
    store(maker, headline_cut=cut, key_results=[story(reaction="The Administration takes note.")])
    page = html.fromstring(client.get(f"/bulletin?date={DAY}").text)
    assert ("* The rest of the headline is in the full report." in page.text_content()) is cut
    assert page.xpath('//article/p[@class="reaction"]/text()') == [
        "The Administration takes note."]


def test_bulletin_page_escapes_issue_fields(maker, client):
    unsafe = '<img src=x onerror="alert(1)"> & __BULLETIN_CONTENT__'
    store(maker, byline=unsafe, headline=unsafe, opening=unsafe, numbers=unsafe,
          rubric_name=unsafe, rubric_story=story(reaction=unsafe), closing=unsafe, items=unsafe)
    response = client.get(f"/bulletin?date={DAY}")
    assert unsafe not in response.text
    assert response.text.count(escape(unsafe)) == 8
    assert not html.fromstring(response.text).xpath("//img|//script")
