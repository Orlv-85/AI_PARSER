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
from app.core.daily.signals import RunOptions, run_days, run_signals
from app.storage.digest_repo import NewsDigestRepo
from app.storage.models_sql import (
    Article,
    ArticleSignal,
    Base,
    DailySignalBrief,
    DailySignalReport,
    NewsDigestGroup,
    NewsDigestItem,
    NewsDigestReport,
)

D = date(2026, 10, 16)
NOW = datetime(2026, 10, 17, 3, tzinfo=UTC)


@pytest.fixture(name="session")
def session_fixture(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'run.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    engine.dispose()


def settings(enabled=True, key="secret-key", brief_model="unpriced-model"):
    # 006 tests keep briefs out of the way: an unpriced brief model never calls.
    return SimpleNamespace(daily_signals_enabled=enabled,
                           daily_signals_comparable_from=date(2026, 10, 10),
                           weekly_publisher_overrides={},
                           ds_api_key=SecretStr(key) if key is not None else None,
                           daily_signals_brief_model=brief_model)


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


# 007: brief step -----------------------------------------------------------------------------
# run_signals starts the report with "brief": None; pylint infers only that literal.
# pylint: disable=unsubscriptable-object
PRO = "deepseek-v4-pro"


def brief_answer(request, *, valid=True, usage=(800, 100)):
    body = json.loads(request.content)
    packet = json.loads(body["messages"][1]["content"])
    item = packet["new"][0]
    text = item["what"] + "." if valid else "Atlas 9 shipped, Zorg says, to everyone today."
    content = {"sentences": [{"text": text, "ids": [item["articles"][0]],
                              "quote": {"id": item["articles"][0], "span": item["what"]}}]}
    return httpx.Response(200, json={
        "model": body["model"], "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]},
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}]})


def is_brief(request):
    return json.loads(request.content)["messages"][0]["content"].startswith(
        "Task: daily-signals-brief")


class Both(Fake):
    """Extraction answers as in 006; brief answers from `brief` (valid by default)."""

    def __init__(self, brief=brief_answer, extraction=answer):
        super().__init__(lambda r: brief(r) if is_brief(r) else extraction(r))

    @property
    def briefs(self):
        return [r for r in self.requests
                if r["messages"][0]["content"].startswith("Task: daily-signals-brief")]


def paid(session, tmp_path, fake, **options):
    return run(session, tmp_path, fake, settings=settings(brief_model=PRO), **options)


def brief_row(session, day=D):
    return session.scalar(select(DailySignalBrief).where(DailySignalBrief.report_date == day))


def brief_ledger_rows(tmp_path):
    ledger = sqlite3.connect(tmp_path / "cache" / "ledger.sqlite3")
    rows = ledger.execute("SELECT COUNT(*) FROM calls WHERE run_id LIKE '%-brief'").fetchone()[0]
    ledger.close()
    return rows


def test_brief_disabled_missing_key_recompute_only_and_unpriced_make_no_call(session, tmp_path):
    seed(session)
    fake = Both()
    for config, extra in ((settings(enabled=False, brief_model=PRO), {}),
                          (settings(key=" ", brief_model=PRO), {}),
                          (settings(brief_model=PRO), {"recompute_only": True})):
        report = run(session, tmp_path, fake, settings=config, **extra)
        assert report["brief"] is None
    assert not fake.requests and brief_row(session) is None
    unpriced = run(session, tmp_path, fake, settings=settings(brief_model="deepseek-v9"))
    assert unpriced["brief"]["days"] == {D.isoformat(): "skipped:brief_model_unpriced"}
    assert not fake.briefs and brief_row(session) is None


def test_one_day_brief_then_cached_then_regenerated(session, tmp_path):
    seed(session)
    fake = Both()
    first = paid(session, tmp_path, fake)
    assert first["state"] == "ok" and len(fake.briefs) == 1
    assert first["brief"]["days"] == {D.isoformat(): "ok"}
    assert first["brief"]["run"] == {"calls": 1, "usd": pytest.approx((800 * 1.32 + 100 * 3.96)
                                                                     / 1e6)}
    row = brief_row(session)
    assert (row.status, row.model, row.brief_version) == ("ok", PRO, "daily-signals-brief-3")
    stored = json.loads(row.payload)["sentences"][0]
    assert stored["text"] == "Today Acme launched Atlas 0." and stored["links"][0]["url"]
    assert fake.briefs[0]["model"] == PRO and fake.briefs[0]["max_tokens"] == 900
    again = paid(session, tmp_path, fake)
    assert again["brief"]["days"] == {D.isoformat(): "cached"} and len(fake.briefs) == 1
    item = session.scalar(select(NewsDigestItem).order_by(NewsDigestItem.id))
    item.summary = "Acme says Atlas 0 is fast."
    session.commit()
    changed = paid(session, tmp_path, fake)
    assert changed["brief"]["days"] == {D.isoformat(): "ok"} and len(fake.briefs) == 2
    report_text = json.dumps(changed) + (tmp_path / "cache" / "runs" /
                                         f"{changed['run_id']}.json").read_text()
    assert "secret-key" not in report_text and "Today Acme launched" not in report_text


def test_invalid_answer_recovers_or_is_stored_invalid(session, tmp_path):
    seed(session)
    answers = iter([False, True])
    fake = Both(brief=lambda r: brief_answer(r, valid=next(answers)))
    report = paid(session, tmp_path, fake)
    assert report["brief"]["days"] == {D.isoformat(): "ok"} and len(fake.briefs) == 2
    assert fake.briefs[1]["messages"][0]["content"].endswith(
        " Correct the previous answer, rejected for: unsupported_number (sentence 1).")
    session.query(DailySignalBrief).delete()
    session.commit()
    bad = Both(brief=lambda r: brief_answer(r, valid=False))
    # Same bodies as before: the ledger replays the saved first answer, the recovery is new.
    report = paid(session, tmp_path, bad)
    assert report["brief"]["days"] == {D.isoformat(): "ok"}
    session.query(DailySignalBrief).delete()
    session.commit()
    seed(session, date(2026, 10, 15))
    item = session.scalar(select(NewsDigestItem).order_by(NewsDigestItem.id))
    item.summary = "Changed text."
    session.commit()
    worse = Both(brief=lambda r: brief_answer(r, valid=False))
    report = paid(session, tmp_path, worse)
    row = brief_row(session)
    assert report["brief"]["days"][D.isoformat()] == "invalid" and len(worse.briefs) == 2
    assert (row.status, row.reason) == \
        ("invalid", "unsupported_number (sentence 1),unsupported_number (sentence 1)")
    assert paid(session, tmp_path, worse)["brief"]["days"][D.isoformat()] == "cached"
    assert len(worse.briefs) == 2


def test_ledger_stop_skips_briefs_and_keeps_extraction(session, tmp_path):
    seed(session)
    clock = {"now": 0.0, "wall": 0}

    def wall():
        # `now` is read at the start and again after extraction (recompute): from then on the
        # run's deadline has passed.
        clock["wall"] += 1
        if clock["wall"] > 1:
            clock["now"] = 10_000.0
        return NOW

    fake = Both()
    report = run_signals(session, settings(brief_model=PRO),
                         RunOptions(report_date=D, cache_dir=tmp_path / "cache"),
                         transport=fake.transport, clock=lambda: clock["now"], now=wall)
    assert (report["state"], report["progress"]) == ("ok", 3)
    assert report["brief"]["days"] == {D.isoformat(): "skipped:deadline_reached"}
    assert report["brief"]["terminal_reason"] == "deadline_reached"
    assert not fake.briefs and brief_row(session) is None
    assert report["reports_written"] == [D.isoformat()]
    capped = paid(session, tmp_path, Both(), max_usd="0.005")
    assert capped["state"] == "ok" and capped["articles"] == {"cached": 3}
    assert capped["brief"]["days"] == {D.isoformat(): "skipped:cap_reached"}


def test_brief_failure_never_breaks_the_run(session, tmp_path, monkeypatch):
    seed(session)
    monkeypatch.setattr("app.core.daily.signals.brief_packet",
                        lambda *a: (_ for _ in ()).throw(KeyError("boom")))
    report = paid(session, tmp_path, Both())
    assert report["state"] == "ok" and report["reports_written"] == [D.isoformat()]
    assert report["brief"]["terminal_reason"] == "error:KeyError"


def test_backfill_range_and_one_day_catch_up(session, tmp_path):
    seed(session, date(2026, 10, 15))
    seed(session)
    fake = Both()
    report = paid(session, tmp_path, fake, backfill_days=2)
    assert report["brief"]["days"] == {"2026-10-15": "ok", "2026-10-16": "ok"}
    assert len(fake.briefs) == 2
    session.delete(brief_row(session, date(2026, 10, 15)))
    session.commit()
    catch_up = paid(session, tmp_path, fake)
    assert catch_up["brief"]["days"] == {"2026-10-15": "ok", "2026-10-16": "cached"}
    # The ledger replays the identical request: no new provider call.
    assert len(fake.briefs) == 2 and catch_up["brief"]["run"]["calls"] == 0
    history = paid(session, tmp_path, fake, report_date=date(2026, 10, 9), backfill_days=1)
    assert history["brief"]["days"] == {}


def _extraction_spend(monkeypatch, usd):
    def fake_extract(*_args, **kwargs):
        kwargs["report"]["run"] = {"calls": 0, "usd": usd, "states": {}}
        return round(usd * 1_000_000)

    monkeypatch.setattr("app.core.daily.signals._extract_days", fake_extract)


def test_max_usd_is_the_run_total(session, tmp_path, monkeypatch):
    seed(session, date(2026, 10, 15))
    seed(session)
    run(session, tmp_path, Both(), backfill_days=2)  # extraction cached, snapshots written
    _extraction_spend(monkeypatch, 0.50)
    exhausted = paid(session, tmp_path, Both(), backfill_days=2)
    assert exhausted["brief"]["days"] == {"2026-10-15": "skipped:brief_budget_exhausted",
                                          "2026-10-16": "skipped:brief_budget_exhausted"}
    assert brief_ledger_rows(tmp_path) == 0
    _extraction_spend(monkeypatch, 0.49)
    fake = Both(brief=lambda r: brief_answer(r, usage=(3000, 500)))
    capped = paid(session, tmp_path, fake, backfill_days=2)
    assert capped["brief"]["days"] == {"2026-10-15": "ok", "2026-10-16": "skipped:cap_reached"}
    assert capped["run"]["usd"] + capped["brief"]["run"]["usd"] <= 0.50
    assert capped["brief"]["run"]["usd"] == pytest.approx((3000 * 1.32 + 500 * 3.96) / 1e6)


SIGNAL_TABLES = frozenset({"article_signals", "daily_signal_scope", "signal_mentions",
                           "ai_entities", "ai_entity_overrides", "daily_signal_reports",
                           "daily_signal_briefs"})


def other_tables(session):
    # Every table signals does not own, including tables added later.
    return {table.name: sorted(map(tuple, session.execute(select(table)).all()), key=repr)
            for table in Base.metadata.sorted_tables if table.name not in SIGNAL_TABLES}


def test_signals_write_only_their_own_tables(session, tmp_path):
    seed(session, date(2026, 10, 15))
    seed(session)
    before = other_tables(session)
    assert before["articles"] and before["news_digest_items"]
    fake = Both()
    report = paid(session, tmp_path, fake, backfill_days=2)
    assert report["state"] == "ok" and fake.briefs
    run(session, tmp_path, fake, recompute_only=True, recompute_all=True)
    session.expire_all()
    assert session.scalar(select(DailySignalReport.report_date).limit(1)) is not None
    assert other_tables(session) == before
