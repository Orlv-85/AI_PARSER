"""Home/digest contract; behavior in src/app/web/pages.md."""
# pylint: disable=redefined-outer-name,import-error,unused-import
from datetime import UTC, datetime, timedelta
from html import escape
from importlib import import_module

import pytest
import test_web_bulletin_page as bulletin_helpers
from fastapi.testclient import TestClient
from lxml import html
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from test_web_bulletin_page import DAY, WEB_DIR, store

client = bulletin_helpers.client
maker = bulletin_helpers.maker


@pytest.fixture
def home(client):
    import_module("app.web.app").get_settings().bulletin_home_page = True
    return client


@pytest.mark.parametrize("switched", [False, True])
@pytest.mark.parametrize("query", ["", f"?date={DAY}"])
def test_daily_serves_the_digest(client, maker, switched, query):
    store(maker)
    expected = client.get("/" + query)
    import_module("app.web.app").get_settings().bulletin_home_page = switched
    response = client.get("/daily" + query)
    assert response.status_code == 200
    assert response.content == expected.content


def test_daily_is_public(client):
    assert client.get("/admin", follow_redirects=False).status_code == 303
    assert client.get("/daily").status_code == 200


def test_home_date_openapi_matches_daily(client):
    paths = client.get("/openapi.json").json()["paths"]
    home_date = paths["/"]["get"]["parameters"]
    daily_date = paths["/daily"]["get"]["parameters"]
    assert home_date == daily_date
    assert home_date == [{"name": "date", "in": "query", "required": False,
                          "schema": {"anyOf": [{"type": "string", "format": "date"},
                                               {"type": "null"}], "title": "Date"}}]


def test_extracted_login_preserves_credentials_and_json(client):
    settings = import_module("app.web.app").get_settings()
    settings.auth_password_hash = import_module("app.web.auth").hash_password("test-password")
    wrong = client.post("/api/auth/login", json={"username": "wrong-user",
                                                "password": "test-password"})
    assert wrong.status_code == 401
    assert wrong.json() == {"detail": "Invalid username or password"}
    login = client.post("/api/auth/login", json={"username": "operator",
                                                "password": "test-password"})
    assert login.status_code == 200 and login.json() == {"ok": True}
    assert "HttpOnly" in login.headers["set-cookie"]
    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200 and logout.json() == {"ok": True}


def test_extracted_stats_preserves_dates(client, monkeypatch):
    class FixedUTC(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 6, tzinfo=tz)
    monkeypatch.setattr("app.web.routes.pages.datetime", FixedUTC)
    end = datetime(2026, 11, 5).date()
    page = html.fromstring(client.get("/news-stats").text)
    assert page.xpath('//input[@id="date-to"]/@value') == [str(end)]
    assert page.xpath('//input[@id="date-from"]/@value') == [str(end - timedelta(days=59))]
    same_day = client.get("/news-stats", params={"date_from": str(DAY), "date_to": str(DAY)})
    assert same_day.status_code == 200
    page = html.fromstring(same_day.text)
    assert page.xpath('//input[@type="date"]/@value') == [str(DAY), str(DAY)]
    reversed_dates = client.get("/news-stats", params={
        "date_from": str(DAY + timedelta(days=1)), "date_to": str(DAY)})
    assert reversed_dates.status_code == 422
    assert reversed_dates.json() == {"detail": "date_from must be <= date_to"}


def test_digest_renderer_preserves_escaping_and_defaults():
    models = import_module("app.storage.models_sql")
    pages = import_module("app.web.routes.pages")
    day = datetime.now(UTC).date() - timedelta(days=1)
    url = 'https://example.com/?q=" onclick="alert(1)'
    unsafe = "<script>__WEEKLY_NAV__</script> &"
    digest = models.NewsDigestReport(report_date=day, groups=[models.NewsDigestGroup(
        title=unsafe, items=[models.NewsDigestItem(url=url, title=unsafe, summary=unsafe)])])
    rendered = pages._render_digest(report_date=day, digest=digest)  # pylint: disable=protected-access
    page = html.fromstring(rendered)
    assert page.xpath("//h1/text()") == ["Yesterday's Digest"]
    assert page.xpath('//li[@class="digest-item"]/a/@href') == [url]
    assert not page.xpath('//a/@onclick|//li[@class="digest-item"]//script|//a[@href="/monthly"]')
    assert rendered.count(escape(unsafe)) == 3
    with_periods = pages._render_digest(  # pylint: disable=protected-access
        report_date=day, digest=digest, week=(DAY, DAY + timedelta(days=6)), monthly=True)
    page = html.fromstring(with_periods)
    assert page.xpath('//a[@class="hero-link"]/@href') == ["/weekly", "/monthly", "/news-stats"]


def test_legacy_weekly_redirects_stay_hidden_from_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/weekly-ai-analytics" not in paths
    assert "/weekly-ai-analytics/reports" not in paths


@pytest.mark.parametrize("case", [
    (*page, failed)
    for failed in (False, True)
    for page in ((False, False, "/"), (True, False, "/"), (True, True, "/"), (True, True, "/daily"))
])
def test_page_views_runs_after_response(client, maker, monkeypatch, caplog, case):
    switched, ready, path, failed = case
    events = []
    import_module("app.web.app").get_settings().bulletin_home_page = switched
    if ready:
        store(maker)

    def count(*_args):
        events.append("counter")
        if failed:
            raise SQLAlchemyError("counter unavailable")

    monkeypatch.setattr("app.usecases.page_views.PageViewRepo.increment", count)

    async def observe_response(scope, receive, send):
        async def observe_send(message):
            await send(message)
            if message["type"] == "http.response.start":
                events.append("response_start")
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                events.append("response_body")
        await client.app(scope, receive, observe_send)

    response = TestClient(observe_response).get(path)
    assert response.status_code == 200
    assert events == ["response_start", "response_body", "counter"]
    assert ("page_views_increment_failed" in caplog.text) is failed


@pytest.mark.usefixtures("client")
def test_page_views_create_all_before_background(maker, monkeypatch):
    web = import_module("app.web.app")
    base = import_module("app.storage.models_sql").Base
    engine = maker.kw["bind"]
    with maker() as session:
        session.execute(text("DROP TABLE page_views"))
        session.commit()
    monkeypatch.setattr(web, "create_all", lambda: base.metadata.create_all(engine))
    response = TestClient(web.create_app()).get("/daily")
    assert response.status_code == 200
    with maker() as session:
        assert session.execute(text("SELECT route, count FROM page_views")).one() == ("/daily", 1)


def test_home_is_digest_when_switch_off(client, maker):
    store(maker)
    for query in ("", f"?date={DAY}"):
        assert client.get("/" + query).content == client.get("/daily" + query).content


def test_home_shows_latest_bulletin_when_switch_on(home, maker):
    store(maker, DAY - timedelta(days=1), headline="OLDER ISSUE")
    store(maker)
    store(maker, DAY + timedelta(days=1), status="skipped", reason="no_digest")
    response = home.get("/")
    assert response.status_code == 200
    page = html.fromstring(response.text)
    assert page.xpath("//time/@datetime") == [str(DAY)]
    assert page.xpath("//h1/text()") == ["A NEW WORKING DAY"]


def test_home_old_date_link_shows_that_bulletin(home, maker):
    store(maker, headline="OLDER ISSUE")
    store(maker, DAY + timedelta(days=1))
    page = html.fromstring(home.get(f"/?date={DAY}").text)
    assert page.xpath("//h1/text()") == ["OLDER ISSUE"]
    assert page.xpath('//a[@class="full-report"]/@href') == [f"/daily?date={DAY}"]


@pytest.mark.parametrize("skipped", [False, True])
def test_home_without_ready_bulletin_shows_digest(home, maker, skipped):
    if skipped:
        store(maker, status="skipped", reason="no_assessments")
    response = home.get("/")
    assert response.status_code == 200
    assert response.content == home.get("/daily").content


def test_home_missing_day_is_404_with_daily_link(home):
    response = home.get(f"/?date={DAY}")
    assert response.status_code == 404
    assert "No bulletin for this day" in response.text
    assert f'href="/daily?date={DAY}"' in response.text


def test_home_has_no_checking_block_and_is_indexable(home, maker):
    store(maker)
    for url in ("/", f"/?date={DAY}", "/?date=2000-01-01"):
        page = html.fromstring(home.get(url).text)
        assert "THE DAILY INFERENCE" in page.text_content()
        assert not page.xpath('//details|//meta[@name="robots"]')
        assert "For checking" not in page.text_content()
        assert "text_origin" not in page.text_content()
    preview = html.fromstring(home.get("/bulletin").text)
    assert preview.xpath('//details/summary/text()') == ["For checking"]
    assert preview.xpath('//meta[@name="robots"]/@content') == ["noindex, nofollow"]


def test_home_date_form(home, maker):
    store(maker)
    page = html.fromstring(home.get("/").text)
    form = page.xpath('//form[@method="get"]')
    assert len(form) == 1
    assert form[0].get("action", "/") == "/"
    assert form[0].xpath('.//input[@type="date"]/@name') == ["date"]
    assert form[0].xpath('.//input/@value') == [str(DAY)]
    assert form[0].xpath('.//button[@type="submit"]')
    assert page.xpath('//a[@rel="prev"]/@href') == [f"/?date={DAY - timedelta(days=1)}"]
    assert page.xpath('//a[@rel="next"]/@href') == [f"/?date={DAY + timedelta(days=1)}"]
    assert not page.xpath("//script")


@pytest.mark.parametrize("path", ["/", "/bulletin"])
def test_full_report_links_daily(home, maker, path):
    store(maker, items=42, full_report_url="/daily?date=2000-01-01")
    page = html.fromstring(home.get(path).text)
    link = page.xpath('//a[@class="full-report"]')[0]
    assert link.get("href") == "/daily?date=2000-01-01"
    assert link.text_content() == "Full report (42) \u2192"


@pytest.mark.parametrize("reason", ["no_digest", "no_signals", "signals_partial",
                                    "signals_unavailable", "no_assessments", "unknown_code"])
def test_skipped_day_plain_sentence(home, maker, reason):
    store(maker, status="skipped", reason=reason)
    for path in ("/", "/bulletin"):
        response = home.get(f"{path}?date={DAY}")
        assert response.status_code == 200
        page = html.fromstring(response.text)
        checking = page.xpath("//details")
        if path == "/bulletin":
            assert len(checking) == 1 and reason in checking[0].text_content()
            checking[0].drop_tree()
        assert reason not in page.text_content()
        assert "No bulletin was issued for this day." in page.text_content()
        assert page.xpath('//a[@class="full-report"]/@href') == [f"/daily?date={DAY}"]


def test_skipped_day_explains_missing_digest(home, maker):
    store(maker, status="skipped", reason="no_digest")
    for path in ("/", "/bulletin"):
        page = html.fromstring(home.get(f"{path}?date={DAY}").text)
        assert page.xpath('//section[@class="status"]/p/text()') == [
            "No bulletin was issued for this day. The daily digest is not available."]


def test_bulletin_renderer_defaults_to_preview(maker):
    store(maker)
    with maker() as session:
        row = session.get(import_module("app.storage.models_sql").BulletinRow, DAY)
        view = import_module("app.web.bulletin_view")
        page = html.fromstring(view.render_bulletin_page(row, DAY))
    assert page.xpath('//meta[@name="robots"]/@content') == ["noindex, nofollow"]
    assert page.xpath('//details/summary/text()') == ["For checking"]


def test_bulletin_preview_is_hidden_from_openapi(client):
    assert "/bulletin" not in client.get("/openapi.json").json()["paths"]


def test_period_links_point_to_daily():
    view = import_module("app.web.period_view")
    assert 'href="/daily">Daily Digest</a>' in view.render_page("", "")
    assert f'href="/daily?date={DAY}"' in view._day(DAY)  # pylint: disable=protected-access


def test_news_stats_links_daily(client):
    response = client.get("/news-stats?date_to=2026-10-30")
    assert 'href="/daily?date=2026-10-30">Back to Daily Digest' in response.text


def test_page_views_counts_digest_home_and_fallback(client, maker):
    assert client.get("/").status_code == 200
    import_module("app.web.app").get_settings().bulletin_home_page = True
    assert client.get("/").status_code == 200
    store(maker, status="skipped", reason="no_digest")
    assert client.get(f"/?date={DAY}").status_code == 200
    with maker() as session:
        assert session.scalar(text("SELECT count FROM page_views WHERE route = '/'")) == 3


def test_digest_date_picker_keeps_current_path():
    script = (WEB_DIR / "static/js/digest.js").read_text()
    assert 'window.location.pathname + (selectedDate ? "?date="' in script
    assert 'encodeURIComponent(selectedDate) : "")' in script


@pytest.mark.parametrize("bad", ["bad", "2026-02-30", "20261030", ""])
def test_home_errors(home, monkeypatch, bad):
    assert home.get("/", params={"date": bad}).status_code == 400
    def unavailable(*_args):
        raise SQLAlchemyError("private detail")
    monkeypatch.setattr("app.usecases.bulletin.stored.BulletinRepo.latest_ready", unavailable)
    # This lookup fails before a digest fallback, even if the store has no ready day.
    response = home.get("/")
    assert response.status_code == 503 and "News storage is unavailable" in response.text
    assert "private detail" not in response.text


def test_digest_errors_match(client, monkeypatch):
    assert client.get("/?date=bad").status_code == client.get("/daily?date=bad").status_code == 422
    assert client.get("/?date=bad").json() == client.get("/daily?date=bad").json()
    def unavailable(*_args, **_kwargs):
        raise SQLAlchemyError("private detail")
    monkeypatch.setattr("app.usecases.digest.NewsDigestRepo.get_digest", unavailable)
    for url in ("/", "/daily"):
        response = client.get(url)
        assert response.status_code == 503
        assert response.json() == {"detail": "News storage is unavailable"}


def test_page_views_counts_home_and_daily(home, maker):
    store(maker)
    assert home.get("/").status_code == 200
    assert home.get(f"/?date={DAY}").status_code == 200
    assert home.get("/daily").status_code == 200
    assert home.get("/bulletin").status_code == 200
    assert home.get("/weekly").status_code == 200
    assert home.get("/?date=2000-01-01").status_code == 404
    assert home.get("/?date=bad").status_code == 400
    assert home.get("/daily?date=bad").status_code == 422
    home.head("/")
    home.post("/daily")
    with maker() as session:
        rows = session.execute(text("SELECT day, route, count FROM page_views ORDER BY route"))
        assert [(str(d), r, n) for d, r, n in rows] == [
            (str(datetime.now(UTC).date()), "/", 2),
            (str(datetime.now(UTC).date()), "/daily", 1)]


def test_page_views_failure_keeps_page(client, maker, caplog):
    expected = client.get("/").content
    with maker() as session:
        session.execute(text("DROP TABLE page_views"))
        session.commit()
    response = client.get("/")
    assert response.status_code == 200 and response.content == expected
    assert [r.exc_info is not None for r in caplog.records
            if r.getMessage().startswith("page_views_increment_failed")] == [True]


def test_page_views_uses_utc_today(client, maker, monkeypatch):
    class FixedUTC(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is UTC
            return cls(2026, 12, 1, 0, 1, tzinfo=UTC)
    monkeypatch.setattr("app.web.routes.pages.datetime", FixedUTC)
    assert client.get(f"/daily?date={DAY}").status_code == 200
    with maker() as session:
        assert session.execute(text("SELECT day, route, count FROM page_views")).one() == (
            "2026-12-01", "/daily", 1)


def test_page_views_stores_no_visitor_data(client, maker):
    response = client.get("/daily", headers={"User-Agent": "secret-agent",
                                           "X-Forwarded-For": "192.0.2.1", "Cookie": "id=secret"})
    assert response.status_code == 200
    assert "set-cookie" not in response.headers
    with maker() as session:
        inspector = inspect(session.get_bind())
        assert [c["name"] for c in inspector.get_columns("page_views")] == ["day", "route", "count"]
        assert inspector.get_pk_constraint("page_views")["constrained_columns"] == ["day", "route"]
