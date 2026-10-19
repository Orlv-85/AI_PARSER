import json
import sqlite3
from datetime import UTC, date, datetime
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.canonicalize import canonical_url_hash
from app.core.daily_signals import RunOptions, run_days, run_signals
from app.storage.models_sql import (
    Article,
    ArticleSignal,
    Base,
    DailySignalReport,
    NewsDigestGroup,
    NewsDigestItem,
    NewsDigestReport,
)
from app.storage.repos import NewsDigestRepo

D = date(2026, 10, 16)
NOW = datetime(2026, 10, 17, 3, tzinfo=UTC)


@pytest.fixture(name="session")
def session_fixture(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'run.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    engine.dispose()


def settings(enabled=True, key="secret-key"):
    return SimpleNamespace(daily_signals_enabled=enabled,
                           daily_signals_comparable_from=date(2026, 10, 10),
                           weekly_publisher_overrides={},
                           ds_api_key=SecretStr(key) if key is not None else None)


def seed(session, day=D, n=3):
    urls = []
    for i in range(n):
        url = f"https://p{i}.com/{day}/{i}"
        name = f"Atlas {i}" if day == D else f"Atlas {day.day}-{i}"
        session.add(Article(title=f"Acme launches {name}", url=url, url_canonical=url,
                            url_canonical_hash=canonical_url_hash(url),
                            content=f"Today Acme launched {name}. SECRET-BODY-{i}",
                            published_at=datetime(day.year, day.month, day.day, 9, tzinfo=UTC)))
        urls.append(url)
    session.flush()
    NewsDigestRepo(session).save_digest(report_date=day, groups=[{
        "title": "Models", "items": [{"title": u, "summary": "s", "url": u} for u in urls]}])
    session.commit()


def answer(request, content=None):
    source = json.loads(json.loads(request.content)["messages"][1]["content"])["source"]
    title = source.split("\n")[0].removeprefix("Title: ")
    name = title.removeprefix("Acme launches ")
    body = content if content is not None else json.dumps({
        "entities": [{"name": name, "canonical_name": name, "type": "model", "vendor": None,
                      "role": "primary", "is_new": True,
                      "is_new_quote": f"Today Acme launched {name}"}],
        "event_type": "model_release", "novelty_claim": True})
    return httpx.Response(200, json={
        "model": "deepseek-flash", "usage": {"prompt_tokens": 800, "completion_tokens": 100},
        "choices": [{"finish_reason": "stop", "message": {"content": body}}]})


class Fake:
    def __init__(self, handler=answer):
        self.handler = handler
        self.requests = []

    def __call__(self, request):
        self.requests.append(json.loads(request.content))
        return self.handler(request)

    @property
    def transport(self):
        return httpx.MockTransport(self)


def run(session, tmp_path, fake=None, **options):
    values = {"report_date": D, "cache_dir": tmp_path / "cache"} | options
    config = values.pop("settings", settings())
    return run_signals(session, config, RunOptions(**values),
                       transport=(fake or Fake()).transport, now=lambda: NOW)


def digest_snapshot(session):
    return [tuple(r) for r in session.execute(
        select(NewsDigestReport.report_date, NewsDigestGroup.title, NewsDigestItem.url,
               NewsDigestItem.title)
        .join(NewsDigestGroup, NewsDigestGroup.report_id == NewsDigestReport.id)
        .join(NewsDigestItem, NewsDigestItem.group_id == NewsDigestGroup.id)
        .order_by(NewsDigestItem.id)).all()]


def test_one_call_per_article_then_cached(session, tmp_path):
    seed(session)
    before = digest_snapshot(session)
    fake = Fake()
    first = run(session, tmp_path, fake)
    assert first["state"] == "ok" and first["progress"] == 3
    assert len(fake.requests) == 3 and first["run"]["calls"] == 3
    assert first["run"]["usd"] == pytest.approx(3 * 0.00036)
    assert first["reports_written"] == [D.isoformat()]
    payload = json.loads(session.scalar(select(DailySignalReport.payload)))
    assert sorted(i["name"] for i in payload["new"]) == ["Atlas 0", "Atlas 1", "Atlas 2"]
    second = run(session, tmp_path, fake)
    assert len(fake.requests) == 3 and second["run"]["calls"] == 0
    assert not second["reports_written"] and second["articles"] == {"cached": 3}
    assert digest_snapshot(session) == before
    stored = (tmp_path / "cache" / "runs" / f"{first['run_id']}.json").read_text()
    assert "secret-key" not in stored and "SECRET-BODY" not in stored
    assert "secret-key" not in json.dumps(first) and "SECRET-BODY" not in json.dumps(first)


def test_invalid_output_recovery_skip_and_single_retry(session, tmp_path):
    seed(session, n=1)
    fake = Fake(lambda r: answer(r, content="not json"))
    report = run(session, tmp_path, fake)
    assert report["articles"] == {"dispatched": 2, "skipped": 1}
    row = session.scalar(select(ArticleSignal))
    assert (row.status, row.reason) == \
        ("skipped", "invalid_output:extraction_schema,extraction_schema")
    assert "Schema recovery" in fake.requests[1]["messages"][0]["content"]
    run(session, tmp_path, fake)
    assert len(fake.requests) == 2
    retried = run(session, tmp_path, fake, retry_skipped=True)
    assert retried["articles"]["skipped"] == 1
    assert fake.requests[2]["messages"][0]["content"].endswith("daily-signals-extract-5-retry1.")
    run(session, tmp_path, fake, retry_skipped=True)
    assert len(fake.requests) == 4  # retry used once (base + recovery), never again
    assert session.scalar(select(ArticleSignal.retry_used))


def test_outage_stops_and_leaves_articles_pending(session, tmp_path):
    seed(session, n=5)
    fake = Fake(lambda r: httpx.Response(503, json={"error": "overloaded"}))
    report = run(session, tmp_path, fake)
    assert report["state"] == report["terminal_reason"] == "provider_unavailable"
    assert len(fake.requests) == 3 and report["progress"] == 0
    day = report["incomplete_days"][D.isoformat()]
    assert (day["items"], day["extracted"], day["reason"]) == (5, 0, "provider_unavailable")
    assert report["reports_written"] == [D.isoformat()]
    payload = json.loads(session.scalar(select(DailySignalReport.payload)))
    assert payload["status"] == "unavailable"
    later = run(session, tmp_path, Fake())
    assert later["state"] == "ok" and later["progress"] == 5


def test_caps_and_deadline(session, tmp_path):
    seed(session, n=3)
    capped = run(session, tmp_path, max_calls=2)
    assert capped["state"] == "cap_reached" and capped["progress"] == 2
    assert capped["incomplete_days"][D.isoformat()]["reason"] == "cap_reached"
    deadline = run(session, tmp_path, max_seconds=90)
    assert deadline["state"] == "deadline_reached" and deadline["run"]["calls"] == 0
    cheap = run(session, tmp_path, max_usd="0.001")
    assert cheap["state"] == "cap_reached"


def test_disabled_missing_key_and_recompute_only(session, tmp_path):
    seed(session, n=1)
    fake = Fake()
    assert run(session, tmp_path, fake, settings=settings(enabled=False))["state"] == "disabled"
    assert run(session, tmp_path, fake, settings=settings(key=" "))["state"] == \
        "missing_provider_key"
    only = run(session, tmp_path, fake, settings=settings(enabled=False, key=None),
               recompute_only=True)
    assert only["state"] == "recompute_only" and not fake.requests
    assert only["reports_written"] == [D.isoformat()]
    assert not (tmp_path / "cache").exists()


def test_backfill_days_oldest_first_and_history(session, tmp_path):
    for day in (date(2026, 10, 8), date(2026, 10, 9), date(2026, 10, 10)):
        seed(session, day, n=1)
    fake = Fake()
    report = run(session, tmp_path, fake, report_date=date(2026, 10, 10), backfill_days=4)
    assert report["days"] == ["2026-10-07", "2026-10-08", "2026-10-09", "2026-10-10"]
    assert report["missing_days"] == ["2026-10-07"]
    ledger = sqlite3.connect(tmp_path / "cache" / "ledger.sqlite3")
    days = [r[0] for r in ledger.execute("SELECT scope_day FROM calls ORDER BY id")]
    ledger.close()
    assert days == ["2026-10-08", "2026-10-09", "2026-10-10"]
    assert report["progress"] == 3
    assert report["reports_written"] == ["2026-10-10"]
    assert run_days(RunOptions(report_date=D)) == [D]


def test_backfill_recomputes_through_latest_completed_day(session, tmp_path):
    # F1: a backfill for an earlier report date must not leave later published days stale.
    seed(session, date(2026, 10, 14), n=1)
    seed(session, D, n=1)
    report = run(session, tmp_path, report_date=date(2026, 10, 14), backfill_days=1)
    assert report["reports_written"] == ["2026-10-14", "2026-10-16"]
    only = run(session, tmp_path, report_date=date(2026, 10, 14), recompute_only=True,
               recompute_all=True)
    assert only["reports_unchanged"] == 2


def _skipped_article(session, tmp_path):
    seed(session, n=1)
    run(session, tmp_path, Fake(lambda r: answer(r, content="not json")))
    row = session.scalar(select(ArticleSignal))
    assert row.status == "skipped" and not row.retry_used
    return row


def test_incomplete_retry_attempt_keeps_the_retry(session, tmp_path):
    # F11: an outage during --retry-skipped must not burn the one retry.
    row = _skipped_article(session, tmp_path)
    outage = run(session, tmp_path, Fake(lambda r: httpx.Response(503, json={"error": "x"})),
                 retry_skipped=True)
    assert outage["articles"].get("pending") == 1
    session.refresh(row)
    assert (row.status, row.retry_used) == ("skipped", False)
    normal = Fake()
    run(session, tmp_path, normal)
    assert not normal.requests
    good = Fake()
    retried = run(session, tmp_path, good, retry_skipped=True)
    assert retried["articles"]["ok"] == 1 and len(good.requests) == 1
    assert good.requests[0]["messages"][0]["content"].endswith("daily-signals-extract-5-retry1.")


def test_changed_content_of_skipped_article_is_not_a_retry(session, tmp_path):
    # F11: a skipped row whose content changed is extracted normally; the retry stays unused.
    row = _skipped_article(session, tmp_path)
    article = session.scalar(select(Article))
    article.content = "Today Acme launched Atlas 0. Updated text."
    session.commit()
    fake = Fake()
    report = run(session, tmp_path, fake, retry_skipped=True)
    assert report["articles"]["ok"] == 1
    assert not fake.requests[0]["messages"][0]["content"].endswith("-retry1.")
    session.refresh(row)
    assert (row.status, row.retry_used) == ("ok", False)


def test_article_on_several_backfill_days_is_attempted_once(session, tmp_path):
    # F12: after a failed attempt the same article is not dispatched again in this invocation.
    seed(session, date(2026, 10, 15), n=1)
    url = "https://p0.com/2026-10-15/0"
    NewsDigestRepo(session).save_digest(report_date=D, groups=[{
        "title": "Models", "items": [{"title": url, "summary": "s", "url": url}]}])
    session.commit()
    fake = Fake(lambda r: httpx.Response(503, json={"error": "overloaded"}))
    report = run(session, tmp_path, fake, backfill_days=2)
    assert len(fake.requests) == 1
    assert report["articles"].get("attempted_before") == 1


def test_history_article_without_body_uses_summary_and_records_input_kind(session, tmp_path):
    # F18: the request and grounding use "Title + Summary"; the input kind is recorded.
    seed(session, n=2)
    articles = session.scalars(select(Article).order_by(Article.id)).all()
    articles[0].content = None
    articles[0].summary = "Today Acme launched Atlas 0, its fastest model."
    session.commit()
    fake = Fake()
    report = run(session, tmp_path, fake)
    assert report["articles"]["ok"] == 2
    sources = [json.loads(r["messages"][1]["content"])["source"] for r in fake.requests]
    assert sources[0] == ("Title: Acme launches Atlas 0\n"
                          "Summary: Today Acme launched Atlas 0, its fastest model.")
    assert sources[1].startswith("Title: Acme launches Atlas 1\nContent: Today Acme")
    kinds = [json.loads(r.provenance)["input"]
             for r in session.scalars(select(ArticleSignal).order_by(ArticleSignal.article_id))]
    assert kinds == ["title_summary", "title_only"]  # seed bodies are under 300 chars
