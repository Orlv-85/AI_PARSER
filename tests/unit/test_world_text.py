"""World text download via the archive (spec 018 item 5, W6); see src/app/core/world/world.md."""
import json
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from test_world_screen import jev_handler, make_assessor  # pylint: disable=import-error
from typer.testing import CliRunner

from app.cli import main as cli_main
from app.config.settings import Settings
from app.core.archive import capture as capture_module
from app.core.bulletin import world_change as wc
from app.core.jev import CONTENT_LIMIT
from app.core.world.gdelt import Candidate
from app.core.world_screen import rank_clusters, run_screen
from app.core.world_text import archive_text_source, run_texts
from app.ingest.fetcher import DEFAULT_USER_AGENT
from app.storage.archive import WORLD_SOURCE_KEY, ArchiveRepo
from app.storage.models_sql import (
    ArchiveDocument,
    ArchiveText,
    Article,
    Base,
    WorldCandidate,
)
from app.storage.world import (
    STATE_ASSESSED,
    STATE_NEW,
    STATE_NO_TEXT,
    STATE_SCREENED_IN,
    STATE_TEXT_READY,
    WorldRepo,
)

DAY = date(2026, 10, 30)
BODY = "An editorial article about AI in schools and hospitals. " * 30
PAGE = ("<html><head><title>Story</title></head><body><article><h1>Story</h1>"
        f"{BODY}</article></body></html>")
PAYWALL_PAGE = PAGE.replace(
    "</head>", '<script type="application/ld+json">{"isAccessibleForFree": false}</script></head>')
EMPTY_PAGE = "<html><head><title>Story</title></head><body><article>Hi</article></body></html>"


def cand(n, title=None, domain=None):
    domain = domain or f"site{n}.example.org"
    return Candidate(
        url=f"https://{domain}/{n}", title=title or f"Story number {n} about AI",
        source_domain=domain, language="eng", tld_hint=None, published_stamp="20261030000000",
        gdelt_file="20261030000000.gkg.csv.zip", translation=False, match="strong")


@pytest.fixture(name="engine")
def engine_fixture(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'world.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session


def seed(session, *candidates, state=STATE_SCREENED_IN, confidence=0.9):
    WorldRepo(session).upsert_candidates(candidates)
    for item in session.scalars(select(WorldCandidate)):
        if item.state == STATE_NEW:
            item.state, item.screen_confidence = state, confidence
    session.commit()


def row(session, title):
    session.expire_all()
    return session.scalars(select(WorldCandidate).where(WorldCandidate.title == title)).one()


class Web:
    """Fake publisher sites: routes map a URL to (status, body) or an exception class."""

    def __init__(self, routes=None):
        self.routes = routes or {}
        self.requests = []

    def handle(self, request):
        self.requests.append(request)
        url = str(request.url)
        if request.url.path == "/robots.txt":
            status, body = self.routes.get(url, (404, ""))
            return httpx.Response(status, text=body)
        answer = self.routes.get(url, (200, PAGE))
        if isinstance(answer, type):
            raise answer("failure", request=request)
        status, body = answer
        return httpx.Response(status, text=body, headers={"Content-Type": "text/html"})

    def client(self, *_args, **_kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    @property
    def pages(self):
        return [str(r.url) for r in self.requests if r.url.path != "/robots.txt"]


def texts(session, tmp_path, web, **kwargs):
    options = {"cache_root": tmp_path / "archive", "daily_cache_root": tmp_path / "daily",
               "host_interval": 0, "client_factory": web.client}
    return run_texts(session, DAY, **{**options, **kwargs})


def test_world_text_goes_through_archive_robots_and_bot_agent(session, tmp_path, monkeypatch):
    seed(session, cand(1, title="One"))
    web = Web()
    real = capture_module.make_http_client

    def archive_client(concurrency):
        client = real(concurrency)  # the archive's own client: bot agent, no redirects
        client._transport = httpx.MockTransport(web.handle)  # pylint: disable=protected-access
        return client

    monkeypatch.setattr(capture_module, "make_http_client", archive_client)
    summary = run_texts(session, DAY, cache_root=tmp_path / "archive",
                        daily_cache_root=tmp_path / "daily", host_interval=0)
    assert [str(r.url) for r in web.requests] == [
        "https://site1.example.org/robots.txt", "https://site1.example.org/1"]
    assert {r.headers["user-agent"] for r in web.requests} == {DEFAULT_USER_AGENT}
    item = row(session, "One")
    assert (item.state, item.last_error) == (STATE_TEXT_READY, None)
    document = session.scalars(select(ArchiveDocument)).one()
    assert (document.url_canonical_hash, document.state, document.source_key,
            document.article_id) == (item.url_canonical_hash, "archived", WORLD_SOURCE_KEY, None)
    version = session.scalars(select(ArchiveText)).one()
    assert (version.origin, version.http_status) == ("source_page", 200)
    assert "editorial article about AI" in version.text
    assert (summary["downloads"], summary["text_ready"], summary["no_text"]) == (1, 1, 0)


def test_world_text_blocked_by_robots_is_no_text(session, tmp_path):
    seed(session, cand(1, title="Blocked"), cand(2, title="Open"))
    web = Web({"https://site1.example.org/robots.txt": (200, "User-agent: *\nDisallow: /")})
    summary = texts(session, tmp_path, web)
    assert web.pages == ["https://site2.example.org/2"]
    blocked = row(session, "Blocked")
    assert blocked.state == STATE_NO_TEXT
    assert blocked.last_error == "text: robots_disallowed_or_unavailable"
    assert row(session, "Open").state == STATE_TEXT_READY
    assert summary["reasons"] == {"robots_disallowed_or_unavailable": 1}


def test_world_text_paywall_and_empty_page_are_no_text(session, tmp_path):
    seed(session, cand(1, title="Paywalled"), cand(2, title="Empty"))
    web = Web({"https://site1.example.org/1": (200, PAYWALL_PAGE),
               "https://site2.example.org/2": (200, EMPTY_PAGE)})
    texts(session, tmp_path, web)
    assert row(session, "Paywalled").state == STATE_NO_TEXT
    assert row(session, "Paywalled").last_error == "text: paywall"
    assert row(session, "Empty").state == STATE_NO_TEXT
    assert row(session, "Empty").last_error.startswith("text: ")
    assert session.scalar(select(func.count()).select_from(ArchiveText)) == 0


def test_world_text_http_error_is_no_text_with_reason(session, tmp_path):
    seed(session, cand(1, title="Gone"), cand(2, title="Broken"), cand(3, title="Slow"))
    web = Web({"https://site1.example.org/1": (404, "<html><title>Not found</title></html>"),
               "https://site2.example.org/2": (500, "<html><title>Oops</title></html>"),
               "https://site3.example.org/3": httpx.ReadTimeout})
    summary = texts(session, tmp_path, web)
    assert row(session, "Gone").last_error == "text: http_404"
    assert row(session, "Broken").last_error == "text: http_500"
    assert row(session, "Slow").last_error == "text: ReadTimeout"
    assert {row(session, t).state for t in ("Gone", "Broken", "Slow")} == {STATE_NO_TEXT}
    assert {row(session, t).attempts for t in ("Gone", "Broken", "Slow")} == {0}
    assert summary["no_text"] == 3 and summary["kept"] == 0


def test_world_text_outage_marks_nothing(session, tmp_path):
    seed(session, *[cand(n) for n in range(1, 13)])

    def refuse(request):
        raise httpx.ConnectError("DNS unavailable", request=request)

    summary = run_texts(session, DAY, cache_root=tmp_path / "archive",
                        daily_cache_root=tmp_path / "daily", host_interval=0,
                        client_factory=lambda: httpx.AsyncClient(
                            transport=httpx.MockTransport(refuse)))
    assert summary["outage"] is True
    assert summary["no_text"] == 0 and summary["text_ready"] == 0
    assert summary["kept"] == 12
    assert {c.state for c in session.scalars(select(WorldCandidate))} == {STATE_SCREENED_IN}
    assert {d.state for d in session.scalars(select(ArchiveDocument))} == {"pending"}


def test_world_never_downloads_more_than_n(session, tmp_path):
    seed(session, *[cand(n) for n in range(1, 8)])
    web = Web()
    summary = texts(session, tmp_path, web, top_n=3)
    assert len(web.pages) == 3 and summary["downloads"] == 3
    assert summary["top"] == 3 and summary["candidates"] == 3
    states = sorted(c.state for c in session.scalars(select(WorldCandidate)))
    assert states == [STATE_SCREENED_IN] * 4 + [STATE_TEXT_READY] * 3
    again = Web()
    texts(session, tmp_path, again, top_n=3)
    assert not again.pages  # the three text_ready clusters keep the top; nothing beyond N


def test_world_text_only_cluster_representative_is_downloaded(session, tmp_path):
    same = "Schools adopt AI tutors"
    seed(session, cand(1, title=same, domain="a.org"), cand(2, title=same, domain="b.org"),
         cand(3, title="Other story about AI"))
    done = row(session, "Other story about AI")
    done.state = STATE_ASSESSED
    session.commit()
    web = Web()
    summary = texts(session, tmp_path, web)
    assert web.pages == ["https://a.org/1"]
    assert summary["top"] == 2 and summary["candidates"] == 1
    states = {c.source_domain: c.state for c in session.scalars(select(WorldCandidate))}
    assert states["a.org"] == STATE_TEXT_READY and states["b.org"] == STATE_SCREENED_IN
    assert states["site3.example.org"] == STATE_ASSESSED


def test_world_text_reuses_stored_archive_text(session, tmp_path):
    seed(session, cand(1, title="Known"))
    item = row(session, "Known")
    repo = ArchiveRepo(session)
    document = repo.upsert_document(
        url_canonical_hash=item.url_canonical_hash, url=item.url, url_canonical=item.url,
        source_key=None, host="site1.example.org", title="Known", published_at=None,
        publication_day=None, publication_status=None, article_id=None, first_seen_at=None)
    repo.add_version(document, text=BODY, origin="source_page", extraction_version="x")
    session.commit()
    web = Web()
    summary = texts(session, tmp_path, web)
    assert not web.requests
    assert row(session, "Known").state == STATE_TEXT_READY
    assert (summary["downloads"], summary["text_ready"]) == (0, 1)


def _real_document(session, item, **fields):
    repo = ArchiveRepo(session)
    document = repo.upsert_document(**{
        "url_canonical_hash": item.url_canonical_hash, "url": item.url, "url_canonical": item.url,
        "source_key": "real-source", "host": item.source_domain, "title": "Real title",
        "published_at": None, "publication_day": date(2026, 10, 29),
        "publication_status": "dated", "article_id": 42, "first_seen_at": None, **fields})
    session.commit()
    return document


def test_world_text_keeps_metadata_of_a_real_archive_document(session, tmp_path):
    seed(session, cand(1, title="Candidate title"))
    _real_document(session, row(session, "Candidate title"))
    web = Web()
    summary = texts(session, tmp_path, web)
    assert summary["text_ready"] == 1 and len(web.pages) == 1
    session.expire_all()
    document = session.scalars(select(ArchiveDocument)).one()
    assert (document.article_id, document.source_key, document.title) == (
        42, "real-source", "Real title")
    assert (document.publication_day, document.publication_status) == (
        date(2026, 10, 29), "dated")


def test_world_text_existing_failed_or_gave_up_document_is_no_text(session, tmp_path):
    seed(session, cand(1, title="Failed"), cand(2, title="Gave up"))
    failed = _real_document(session, row(session, "Failed"))
    ArchiveRepo(session).record_attempt(
        failed, issue="http_500", gave_up=False,
        next_attempt_at=datetime.now(UTC) + timedelta(days=1))
    gave_up = _real_document(session, row(session, "Gave up"))
    ArchiveRepo(session).record_attempt(gave_up, issue="paywall", gave_up=True,
                                        next_attempt_at=None)
    session.commit()
    web = Web()
    summary = texts(session, tmp_path, web)
    assert not web.requests
    assert row(session, "Failed").last_error == "text: http_500"
    assert row(session, "Gave up").last_error == "text: paywall"
    assert {row(session, t).state for t in ("Failed", "Gave up")} == {STATE_NO_TEXT}
    assert (summary["no_text"], summary["kept"], summary["downloads"]) == (2, 0, 0)


def test_world_text_next_run_tries_the_next_outlet(session, tmp_path):
    same = "Schools adopt AI tutors"
    seed(session, cand(1, title=same, domain="a.org"), cand(2, title=same, domain="b.org"))
    web = Web({"https://a.org/robots.txt": (200, "User-agent: *\nDisallow: /")})
    texts(session, tmp_path, web)
    assert web.pages == []
    states = {c.source_domain: c.state for c in session.scalars(select(WorldCandidate))}
    assert states == {"a.org": STATE_NO_TEXT, "b.org": STATE_SCREENED_IN}
    texts(session, tmp_path, web)
    assert web.pages == ["https://b.org/2"]
    states = {c.source_domain: c.state for c in session.scalars(select(WorldCandidate))}
    assert states == {"a.org": STATE_NO_TEXT, "b.org": STATE_TEXT_READY}


def test_world_text_no_text_cluster_ranks_by_remaining_outlets(session, tmp_path):
    big, small = "Big story about AI", "Small story about AI"
    seed(session, cand(1, title=big, domain="a.org"), cand(2, title=big, domain="b.org"),
         cand(3, title=big, domain="c.org"), cand(4, title=small, domain="d.org"),
         cand(5, title=small, domain="e.org"), confidence=0.9)
    for item in session.scalars(select(WorldCandidate).where(WorldCandidate.title == small)):
        item.screen_confidence = 0.95
    session.commit()
    window = [STATE_SCREENED_IN, STATE_TEXT_READY, STATE_ASSESSED]

    def order():
        items = WorldRepo(session).candidates_in_window(window, DAY)
        return [(r.rep.title, r.outlets) for r in rank_clusters(items)]
    assert order() == [(big, 3), (small, 2)]
    texts(session, tmp_path, Web({"https://a.org/robots.txt": (200, "User-agent: *\nDisallow: /")}),
          top_n=1)
    assert sum(c.state == STATE_NO_TEXT for c in session.scalars(select(WorldCandidate))) == 1
    assert order() == [(small, 2), (big, 2)]


def test_world_text_creates_no_articles_and_keeps_archive_after_prune(session, tmp_path):
    seed(session, cand(1, title="One"))
    texts(session, tmp_path, Web())
    assert session.scalar(select(func.count()).select_from(Article)) == 0
    seen = row(session, "One").first_seen_at
    WorldRepo(session).prune(now=seen.replace(year=seen.year + 1))
    session.commit()
    assert session.scalar(select(func.count()).select_from(WorldCandidate)) == 0
    assert session.scalar(select(func.count()).select_from(ArchiveDocument)) == 1
    assert session.scalar(select(func.count()).select_from(ArchiveText)) == 1
    assert session.scalar(select(func.count()).select_from(Article)) == 0


def test_world_text_dry_run_writes_nothing(engine, tmp_path):
    with Session(engine) as session:
        seed(session, cand(1), cand(2))
        web = Web()
        summary = texts(session, tmp_path, web, dry_run=True)
        assert not web.requests
        assert (summary["dry_run"], summary["candidates"], summary["downloads"]) == (True, 2, 0)
        assert session.scalar(select(func.count()).select_from(ArchiveDocument)) == 0
        assert {c.state for c in session.scalars(select(WorldCandidate))} == {STATE_SCREENED_IN}
    assert not (tmp_path / "archive").exists()


def test_world_text_seam_cuts_to_jev_limit(session, tmp_path):
    seed(session, cand(1, title="Long"), cand(2, title="Missing"))
    texts(session, tmp_path, Web({"https://site2.example.org/2": (404, "<html></html>")}))
    document = session.scalars(select(ArchiveDocument).where(
        ArchiveDocument.url.like("%site1%"))).one()
    session.add(ArchiveText(document_id=document.id, text="x" * (CONTENT_LIMIT + 500),
                            text_chars=CONTENT_LIMIT + 500, text_sha256="f" * 64,
                            origin="source_page", extraction_version="x"))
    session.commit()
    source = archive_text_source(session)
    assert source(row(session, "Long")) == "x" * CONTENT_LIMIT  # newest version, cut
    assert source(row(session, "Missing")) is None


def test_world_text_seam_feeds_step_b(session, tmp_path):
    seed(session, cand(1, title="With text"), cand(2, title="No page"))
    texts(session, tmp_path, Web({"https://site2.example.org/2": (404, "<html></html>")}))
    requests = []
    summary = run_screen(session, make_assessor(jev_handler(requests=requests)), DAY,
                         texts=archive_text_source(session))
    assert (summary["asked"], summary["assessed"], summary["awaiting_text"]) == (1, 1, 0)
    assert summary["skipped_no_text"] == 0
    assert row(session, "With text").state == STATE_ASSESSED
    assert row(session, "No page").state == STATE_NO_TEXT
    state = requests[0]["state"]
    assert "Title: With text" in state and "editorial article about AI" in state


@pytest.fixture(name="maker")
def maker_fixture(engine, monkeypatch):
    maker = sessionmaker(bind=engine)
    monkeypatch.setattr(cli_main, "SessionLocal", maker)
    monkeypatch.setattr(cli_main, "create_all", lambda: None)
    return maker


def test_cli_world_texts_summary(maker, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with maker() as session:
        seed(session, cand(1, title="One"), cand(2, title="Two"))
    web = Web({"https://site2.example.org/2": (404, "<html></html>")})
    monkeypatch.setattr(capture_module, "make_http_client", web.client)
    result = CliRunner().invoke(cli_main.app, ["world", "texts", "--date", DAY.isoformat()])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.stdout)
    assert (summary["candidates"], summary["downloads"], summary["text_ready"],
            summary["no_text"]) == (2, 2, 1, 1)
    assert summary["reasons"] == {"http_404": 1} and summary["outage"] is False
    assert (tmp_path / "data/archive/source-cache").is_dir()
    dry = CliRunner().invoke(cli_main.app, ["world", "texts", "--date", DAY.isoformat(),
                                            "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert json.loads(dry.stdout)["dry_run"] is True


def test_cli_world_screen_reads_archive_text(maker, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with maker() as session:
        seed(session, cand(1, title="One"))
        texts(session, tmp_path, Web())
    monkeypatch.setattr(cli_main, "get_settings", lambda: Settings(
        _env_file=None, jev_api_key=SecretStr("k")))
    monkeypatch.setattr(cli_main, "utc_today", lambda: date(2026, 11, 1))
    real_client = httpx.Client
    requests = []
    handler = jev_handler(requests=requests)
    monkeypatch.setattr(wc.httpx, "Client", lambda **kw: real_client(
        transport=httpx.MockTransport(handler), **kw))
    result = CliRunner().invoke(cli_main.app, ["world", "screen", "--date", DAY.isoformat()])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.stdout)
    assert (summary["asked"], summary["assessed"]) == (1, 1)
    assert "editorial article about AI" in requests[-1]["state"]
