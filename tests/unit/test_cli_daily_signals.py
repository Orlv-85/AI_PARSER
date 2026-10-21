import json
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from typer.testing import CliRunner

from app.cli import main as cli_main
from app.config.settings import Settings
from app.core.canonicalize import canonical_url_hash
from app.core.daily.signals_extract import ExtractedEntity, Extraction
from app.storage.daily_signals import DailySignalRepo
from app.storage.digest_repo import NewsDigestRepo
from app.storage.models_sql import AIEntity, AIEntityOverride, Article, Base, DailySignalReport

YESTERDAY = datetime.now(UTC).date() - timedelta(days=1)
runner = CliRunner()


@pytest.fixture(name="factory")
def factory_fixture(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'cli.db'}")
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine)
    monkeypatch.setattr(cli_main, "SessionLocal", maker)
    monkeypatch.setattr(cli_main, "create_all", lambda: None)
    monkeypatch.setattr(cli_main, "get_settings", lambda: Settings(
        _env_file=None, daily_signals_comparable_from=YESTERDAY - timedelta(days=30)))
    yield maker
    engine.dispose()


def invoke(*args):
    result = runner.invoke(cli_main.app, list(args))
    return result.exit_code, result.output


def seed(maker, day, *names, new=False):
    """One digest per day holding one article per name. Titles do not name the entity, so the
    lexical history rule (F19) stays out of these override tests."""
    with maker() as session:
        articles = []
        for name in names:
            url = f"https://p.com/{day}/{name}"
            article = Article(title=f"Story {day} {len(articles)}", url=url, url_canonical=url,
                              url_canonical_hash=canonical_url_hash(url), content=name)
            session.add(article)
            articles.append((name, article))
        session.flush()
        NewsDigestRepo(session).save_digest(report_date=day, groups=[{
            "title": "Models", "items": [{"title": a.title, "summary": "s", "url": a.url}
                                         for _, a in articles]}])
        repo = DailySignalRepo(session, comparable_from=YESTERDAY - timedelta(days=30))
        repo.replace_membership(day)
        for name, article in articles:
            quote = f"Today we launch {name}" if new else None
            repo.save_extraction(article, Extraction("model_release", True, (ExtractedEntity(
                name, name, "model", None, "primary", new, quote),)), content_hash="h")
        session.commit()


def entity_id(maker, key):
    with maker() as session:
        return session.scalar(select(AIEntity.id).where(AIEntity.entity_key == key))


def new_names(maker, day=YESTERDAY):
    with maker() as session:
        payload = session.scalar(select(DailySignalReport.payload)
                                 .where(DailySignalReport.report_date == day))
    return [i["name"] for i in json.loads(payload)["new"]]


def test_dates_and_usd_validation(factory):
    del factory
    assert invoke("daily-signals", "--report-date", "2026-13-01")[0] == 2
    today = datetime.now(UTC).date().isoformat()
    assert invoke("daily-signals", "--report-date", today)[0] == 2
    assert invoke("daily-signals", "--max-usd", "abc")[0] == 2
    assert invoke("daily-signals", "--max-calls", "0")[0] == 2


def test_disabled_flag_makes_no_calls_and_recompute_only_works(factory, monkeypatch):
    seed(factory, YESTERDAY, "Atlas", new=True)
    monkeypatch.setattr("app.storage.daily_signals_ledger.SignalsLedger.dispatch",
                        lambda *a, **k: pytest.fail("provider call"))
    code, out = invoke("daily-signals")
    assert code == 0 and json.loads(out)["state"] == "disabled"
    code, out = invoke("daily-signals", "--recompute-only", "--backfill-days", "3")
    report = json.loads(out)
    assert code == 0 and report["state"] == "recompute_only"
    assert report["days"][0] == (YESTERDAY - timedelta(days=2)).isoformat()
    assert report["reports_written"] == [YESTERDAY.isoformat()]
    assert new_names(factory) == ["Atlas"]
    code, out = invoke("daily-signals", "--recompute-only", "--recompute-all")
    assert code == 0 and json.loads(out)["reports_written"] == []


def test_cap_flags_reach_the_run(factory, monkeypatch, tmp_path):
    del factory
    seen = {}

    def fake_run(_session, _settings, options):
        seen.update(vars(options))
        return {"state": "ok"}

    monkeypatch.setattr(cli_main, "run_signals", fake_run)
    code, _ = invoke("daily-signals", "--report-date", "2026-10-16", "--backfill-days", "75",
                     "--max-calls", "700", "--max-seconds", "3500", "--max-usd", "1.818",
                     "--cache-dir", str(tmp_path / "c"), "--retry-skipped")
    assert code == 0
    assert (seen["report_date"], seen["backfill_days"], seen["max_calls"], seen["max_seconds"],
            seen["max_usd"], seen["retry_skipped"]) == (date(2026, 10, 16), 75, 700, 3500, "1.818",
                                                         True)
    invoke("daily-signals", "--report-date", "2026-10-16")
    assert (seen["max_calls"], seen["max_seconds"], seen["max_usd"]) == (200, 2700, "0.50")


def test_alias_merge_overrides_and_purge(factory):
    seed(factory, YESTERDAY - timedelta(days=3), "GPT-6")
    seed(factory, YESTERDAY, "GPT-6 Astra", "Clef-omni", new=True)
    seed(factory, YESTERDAY - timedelta(days=2), "Clef Omni Beta")
    invoke("daily-signals", "--recompute-only")
    assert sorted(new_names(factory)) == ["Clef-omni", "GPT-6 Astra"]
    gpt6 = entity_id(factory, "auto:artifact:gpt6")
    code, out = invoke("daily-signals-entities", "alias", "--entity", str(gpt6),
                       "--name", "GPT-6 Astra")
    assert code == 0 and json.loads(out)["override"]["match_key"] == "gpt6astra"
    assert new_names(factory) == ["Clef-omni"]
    code, out = invoke("daily-signals-entities", "alias", "--entity", str(gpt6), "--name", "AI")
    assert code == 1 and json.loads(out)["state"] == "refused"
    source = entity_id(factory, "auto:artifact:clefomni")
    target = entity_id(factory, "auto:artifact:clefomnibeta")
    code, out = invoke("daily-signals-entities", "merge", "--source", str(source),
                       "--target", str(target))
    assert code == 0 and new_names(factory) == []
    code, out = invoke("daily-signals-entities", "merge", "--source", str(target),
                       "--target", str(source))
    assert code == 1
    code, out = invoke("daily-signals-entities", "overrides")
    overrides = json.loads(out)["overrides"]
    assert [o["kind"] for o in overrides] == ["alias", "merge"]
    code, out = invoke("daily-signals-entities", "overrides", "--delete", str(overrides[1]["id"]))
    assert code == 0 and new_names(factory) == ["Clef-omni"]
    assert invoke("daily-signals-entities", "overrides", "--delete", "999")[0] == 1
    with factory() as session:
        assert session.scalar(select(AIEntityOverride.id)) == overrides[0]["id"]
    code, out = invoke("daily-signals-entities", "purge-evidence", "--article", "1")
    assert code == 1 and "still exists" in json.loads(out)["error"]
    with factory() as session:
        session.delete(session.get(Article, 1))
        session.commit()
    code, out = invoke("daily-signals-entities", "purge-evidence", "--article", "1")
    assert code == 0 and json.loads(out)["purged"] == 1


def test_json_line_includes_the_brief_block(factory, monkeypatch, tmp_path):
    seed(factory, YESTERDAY, "Atlas", new=True)
    code, out = invoke("daily-signals", "--recompute-only")
    assert code == 0 and json.loads(out)["brief"] is None
    monkeypatch.setattr(cli_main, "get_settings", lambda: Settings(
        _env_file=None, daily_signals_enabled=True, ds_api_key="secret-key",
        daily_signals_comparable_from=YESTERDAY - timedelta(days=30)))

    def provider(request):
        body = json.loads(request.content)
        if body["messages"][0]["content"].startswith("Task: daily-signals-brief"):
            content = {"sentences": []}  # invalid: a quiet day needs 1-2 sentences
        else:
            content = {"entities": [], "event_type": "other", "novelty_claim": False}
        return httpx.Response(200, json={
            "model": body["model"], "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}]})

    real = cli_main.run_signals
    monkeypatch.setattr(cli_main, "run_signals", lambda *a: real(
        *a, transport=httpx.MockTransport(provider)))
    code, out = invoke("daily-signals", "--cache-dir", str(tmp_path / "c"))
    report = json.loads(out)
    assert code == 0 and report["state"] == "ok"
    assert report["brief"]["model"] == "deepseek-v4-pro"
    assert report["brief"]["days"] == {YESTERDAY.isoformat(): "invalid"}
    assert report["brief"]["run"]["calls"] == 2
