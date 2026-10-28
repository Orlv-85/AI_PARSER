"""Period brief (017 R4): packet, request, validation and the paid step with a fake provider."""
import json
import sqlite3
from datetime import date, datetime
from types import SimpleNamespace

import httpx
import pytest
from period_brief_db import (  # pylint: disable=import-error
    NAMES,
    PRO,
    WEEK_START,
    Provider,
    answer,
    bad_answer,
    good_answer,
    period_payload,
    store_period,
    summary,
)
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.daily.signals_brief import BRIEF_PRICES, BRIEF_PROMPT, BriefInvalid, PacketTooLarge
from app.core.periodic import period_brief as pb
from app.core.periodic import period_brief_run as run
from app.core.periodic.period_brief import (
    PERIOD_BRIEF_MAX_USD,
    PERIOD_BRIEF_VERSION,
    PERIOD_MAX_OUTPUT,
    PERIOD_PACKET_MAX_BYTES,
    PERIOD_SENTENCES,
    parse_period_brief,
    period_body,
    period_input_hash,
    period_packet,
)
from app.storage.daily_signals_ledger import SignalsLedger
from app.storage.journal_files import encoded
from app.storage.models_sql import Base, PeriodSignalBrief
from app.storage.period_signals import PeriodSignalRepo

NEXT = date(2026, 10, 26)
MONTH = date(2026, 11, 1)


@pytest.fixture(name="maker")
def maker_fixture(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'brief.db'}")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)
    engine.dispose()


def settings(*, enabled=True, key="secret-key", model=PRO):
    return SimpleNamespace(period_signals_brief_enabled=enabled, daily_signals_brief_model=model,
                           ds_api_key=SecretStr(key) if key is not None else None)


def go(maker, tmp_path, provider, targets=(("week", WEEK_START),), *, max_usd="0.10", **config):
    with maker() as session:
        repo = PeriodSignalRepo(session, comparable_from=date(2026, 10, 10))
        return run.run_briefs(
            session, repo, settings(**config), list(targets), max_usd=max_usd,
            cache_dir=tmp_path / "cache", max_seconds=600, transport=provider.transport,
            now=lambda: datetime(2026, 10, 28, 3, 0))


def brief_row(maker, kind="week", start=WEEK_START):
    with maker() as session:
        return PeriodSignalRepo(session, comparable_from=date(2026, 10, 10)).get_brief(kind, start)


def digest_for(payload):
    return [{"title": link["title"], "summary": summary(link["title"].split()[2]),
             "url": link["url"]}
            for group in ("top_stories", "rising") for item in payload[group]
            for link in item["links"]]


# Packet and request ---------------------------------------------------------------------------
def test_values_by_kind():
    assert PERIOD_PACKET_MAX_BYTES == {"week": 16000, "month": 24000}
    assert PERIOD_SENTENCES == {"week": (4, 6), "month": (5, 8)}
    assert PERIOD_BRIEF_MAX_USD == {"week": "0.05", "month": "0.08"}
    assert PERIOD_BRIEF_VERSION == "period-signals-brief-1"


def test_period_packet_has_stories_new_risers_and_digest_articles():
    payload = period_payload(rising=True)
    payload["new"] = [{"name": "Nova", "type": "model", "vendor": "Acme", "publishers": 1,
                       "one_liner": "Acme released Nova today", "links": [
                           {"url": "https://nova.example.com/a", "title": "Nova",
                            "publisher": "n"}]}]
    items = digest_for(payload) + [{"title": "Nova", "summary": "", "url":
                                    "https://nova.example.com/a"}]
    packet, id_map = period_packet(payload, items)
    assert (packet["kind"], packet["start"], packet["quiet"]) == ("week", "2026-10-19", False)
    assert [s["label"] for s in packet["stories"]] == [f"Acme launches {n}" for n in NAMES[:5]]
    assert packet["stories"][0]["articles"] == ["a1"] and packet["stories"][0]["outlets"] == 2
    assert packet["new"][0]["what"] == "Acme released Nova today"
    assert packet["risers"][0]["name"] == "Zeta"
    assert packet["event_counts"] == {"Model release": 5}
    assert list(packet["articles"]) == list(id_map) and len(id_map) == 7
    assert packet["articles"]["a1"]["publisher"] == "atlas.example.com"
    assert packet["articles"]["a1"]["summary"] == summary("Atlas")
    assert id_map["a1"]["url"] == payload["top_stories"][0]["links"][0]["url"]


def test_risers_are_left_out_when_the_comparison_is_hidden():
    payload = period_payload(rising=True)
    payload["sections"]["rising"] = "hidden"
    packet, _ = period_packet(payload, digest_for(payload))
    assert packet["risers"] == []


def test_a_link_without_a_digest_item_is_not_cited():
    payload = period_payload()
    packet, _ = period_packet(payload, digest_for(payload)[:2])
    assert [s["articles"] for s in packet["stories"]] == [["a1"], ["a2"], [], [], []]


def test_packet_is_cut_to_the_cap_of_its_kind_and_loses_its_tail_before_failing(monkeypatch):
    payload = period_payload(stories=2)
    payload["new"] = [{"name": f"New{i}", "type": "model", "vendor": None, "publishers": 1,
                       "one_liner": "x", "links": [
                           {"url": f"https://n{i}.example.com/a", "title": f"T{i}",
                            "publisher": "n"}]}
                      for i in range(10)]
    items = digest_for(payload) + [
        {"title": f"T{i} " + "word " * 20, "summary": "long " * 120,
         "url": f"https://n{i}.example.com/a"} for i in range(10)]
    full, _ = pb._build(payload, items, new_max=None, risers_max=None)  # pylint: disable=W0212
    monkeypatch.setattr(pb, "PERIOD_PACKET_MAX_BYTES", {"week": 3000, "month": 24000})
    packet, _ = period_packet(payload, items)
    assert len(encoded(packet).encode()) <= 3000
    assert len(packet["new"]) < len(full["new"]) and len(packet["stories"]) == 2
    monkeypatch.setattr(pb, "PERIOD_PACKET_MAX_BYTES", {"week": 200, "month": 24000})
    with pytest.raises(PacketTooLarge):
        period_packet(payload, items)


def test_request_body_by_kind():
    packet, _ = period_packet(period_payload(), digest_for(period_payload()))
    week = period_body(packet, PRO)
    assert week["model"] == PRO and week["max_tokens"] == PERIOD_MAX_OUTPUT["week"]
    system = week["messages"][0]["content"]
    assert system.startswith("Task: period-signals-brief-1.") and "4 to 6 sentences" in system
    assert "week" in system and system != BRIEF_PROMPT
    month = period_body({**packet, "kind": "month"}, PRO, recovery="sentence_count")
    assert "5 to 8 sentences" in month["messages"][0]["content"]
    assert month["messages"][0]["content"].endswith("rejected for: sentence_count.")
    assert month["max_tokens"] == PERIOD_MAX_OUTPUT["month"]
    assert json.loads(week["messages"][1]["content"]) == packet


def test_period_input_hash_changes_with_packet_version_and_model(monkeypatch):
    packet, _ = period_packet(period_payload(), digest_for(period_payload()))
    base = period_input_hash(packet, PRO)
    assert base == period_input_hash(json.loads(json.dumps(packet)), PRO)
    assert period_input_hash(packet, "deepseek-flash") != base
    assert period_input_hash({**packet, "digest_items": 1}, PRO) != base
    monkeypatch.setattr(pb, "PERIOD_BRIEF_VERSION", "period-signals-brief-2")
    assert period_input_hash(packet, PRO) != base


def sentence_for(packet, index):
    article = packet["stories"][index]["articles"][0]
    text = packet["articles"][article]["summary"]
    return {"text": text + ".", "ids": [article],
            "quote": {"id": article, "span": " ".join(text.split()[1:7])}}


def test_validation_uses_the_sentence_counts_of_the_kind():
    packet, _ = period_packet(period_payload(stories=6), digest_for(period_payload(stories=6)))

    def parse(count, kind="week"):
        data = answer({"sentences": [sentence_for(packet, i % 6) for i in range(count)]}).json()
        return parse_period_brief(data, {**packet, "kind": kind}, PRO)

    assert len(parse(4)) == 4 and len(parse(6)) == 6
    for count in (3, 7):
        with pytest.raises(BriefInvalid) as error:
            parse(count)
        assert error.value.code == "sentence_count"
    assert len(parse(5, "month")) == 5
    with pytest.raises(BriefInvalid):
        parse(4, "month")


def test_validation_keeps_the_daily_rules():
    packet, _ = period_packet(period_payload(), digest_for(period_payload()))
    sentences = [sentence_for(packet, i) for i in range(4)]
    sentences[0]["text"] = "Acme launched Atlas for 7 million users."  # number not in sources
    with pytest.raises(BriefInvalid) as error:
        parse_period_brief(answer({"sentences": sentences}).json(), packet, PRO)
    assert str(error.value) == "unsupported_number (sentence 1)"


# Run ------------------------------------------------------------------------------------------
def test_ok_brief_is_stored_then_cached_by_input_hash(maker, tmp_path):
    store_period(maker, period_payload())
    provider = Provider()
    first = go(maker, tmp_path, provider)
    assert first["periods"] == {"week:2026-10-19": "ok"} and len(provider.requests) == 1
    assert first["run"] == {"calls": 1, "usd": pytest.approx((3000 * 1.32 + 400 * 3.96) / 1e6)}
    row = brief_row(maker)
    assert (row.status, row.model, row.brief_version) == ("ok", PRO, PERIOD_BRIEF_VERSION)
    data = json.loads(row.payload)
    assert len(data["sentences"]) == 4
    assert data["sentences"][0]["links"][0]["url"].startswith("https://atlas.example.com/")
    assert provider.requests[0]["max_tokens"] == PERIOD_MAX_OUTPUT["week"]
    again = go(maker, tmp_path, provider)
    assert again["periods"] == {"week:2026-10-19": "cached"} and len(provider.requests) == 1
    assert again["run"]["calls"] == 0
    store_period(maker, period_payload(items=301), digest=False)  # changed numbers: new hash
    changed = go(maker, tmp_path, provider)
    assert changed["periods"] == {"week:2026-10-19": "ok"} and len(provider.requests) == 2


def test_recovery_attempt_then_ok(maker, tmp_path):
    store_period(maker, period_payload())
    answers = iter([bad_answer, good_answer])

    def handler(request):
        return next(answers)(request)

    provider = Provider(handler)
    report = go(maker, tmp_path, provider)
    assert report["periods"] == {"week:2026-10-19": "ok"} and len(provider.requests) == 2
    assert provider.requests[1]["messages"][0]["content"].endswith(
        "rejected for: sentence_count.")
    assert brief_row(maker).status == "ok"


def test_invalid_after_one_recovery_is_never_paid_twice(maker, tmp_path):
    store_period(maker, period_payload())
    provider = Provider(bad_answer)
    report = go(maker, tmp_path, provider)
    assert report["periods"] == {"week:2026-10-19": "invalid"} and len(provider.requests) == 2
    row = brief_row(maker)
    assert (row.status, row.payload) == ("invalid", "{}")
    assert row.reason == "sentence_count,sentence_count"
    again = go(maker, tmp_path, provider)
    assert again["periods"] == {"week:2026-10-19": "cached"} and len(provider.requests) == 2


def test_per_brief_cap_stops_before_the_call(maker, tmp_path, monkeypatch):
    store_period(maker, period_payload())
    monkeypatch.setitem(pb.PERIOD_BRIEF_MAX_USD, "week", "0.005")
    monkeypatch.setattr(run, "PERIOD_BRIEF_MAX_USD", pb.PERIOD_BRIEF_MAX_USD)
    provider = Provider()
    report = go(maker, tmp_path, provider)  # one attempt is reserved at about $0.007
    assert report["periods"] == {"week:2026-10-19": "skipped:cap_reached"}
    assert not provider.requests and brief_row(maker) is None
    assert report["terminal_reason"] == "cap_reached"


def test_the_reservation_of_a_full_packet_fits_the_default_caps():
    for kind, limit in PERIOD_PACKET_MAX_BYTES.items():
        filler = {"kind": kind, "start": "2026-10-19", "end": "2026-10-25", "quiet": False,
                  "stories": [], "new": [], "risers": [], "event_counts": {},
                  "articles": {"a1": {"title": "t", "summary": "x" * (limit - 200)}}}
        body = period_body(filler, PRO)
        assert limit - 300 < len(encoded(filler).encode()) <= limit
        reserved = SignalsLedger.bound_micro(
            SimpleNamespace(prices=BRIEF_PRICES[PRO]), body, PERIOD_MAX_OUTPUT[kind])
        cap = int(float(PERIOD_BRIEF_MAX_USD[kind]) * 1_000_000)
        # an attempt fits the cap; a second one fits after a first one that cost a third of it
        assert reserved < cap and reserved * 4 // 3 < cap, (kind, reserved)


def test_run_cap_limits_the_second_brief(maker, tmp_path):
    store_period(maker, period_payload())
    store_period(maker, period_payload(start=NEXT))
    provider = Provider()
    report = go(maker, tmp_path, provider, [("week", WEEK_START), ("week", NEXT)],
                max_usd="0.012")
    # The first brief costs about $0.0055; the next attempt is reserved at about $0.007 > $0.0065.
    assert report["periods"] == {"week:2026-10-19": "ok", "week:2026-10-26": "skipped:cap_reached"}
    assert report["terminal_reason"] == "cap_reached" and len(provider.requests) == 1
    assert report["run"]["usd"] == pytest.approx((3000 * 1.32 + 400 * 3.96) / 1e6)
    assert brief_row(maker, "week", NEXT) is None
    tight = go(maker, tmp_path, Provider(), [("week", NEXT)], max_usd="0.001")
    assert tight["run"] == {"calls": 0, "usd": 0.0}
    assert tight["periods"] == {"week:2026-10-26": "skipped:cap_reached"}


def test_run_budget_exhausted_skips_without_a_call(maker, tmp_path):
    store_period(maker, period_payload())
    store_period(maker, period_payload(start=NEXT))
    # A measured cost above the reservation (the ledger records it) can use up the run budget.
    provider = Provider(lambda r: good_answer(r, usage=(100_000, 1000)))
    report = go(maker, tmp_path, provider, [("week", WEEK_START), ("week", NEXT)],
                max_usd="0.13")
    assert report["periods"] == {"week:2026-10-19": "ok",
                                 "week:2026-10-26": "skipped:brief_budget_exhausted"}
    assert report["terminal_reason"] == "brief_budget_exhausted" and len(provider.requests) == 1


def test_unpriced_model_flag_off_and_no_key_make_no_call(maker, tmp_path, monkeypatch):
    store_period(maker, period_payload())
    provider = Provider()
    unpriced = go(maker, tmp_path, provider, model="deepseek-v9")
    assert unpriced["periods"] == {"week:2026-10-19": "skipped:brief_model_unpriced"}
    monkeypatch.setattr("app.core.periodic.period_brief_run.SignalsLedger",
                        lambda *a, **k: pytest.fail("provider object created"))
    assert go(maker, tmp_path, provider, enabled=False)["state"] == "disabled"
    for key in (None, " "):
        assert go(maker, tmp_path, provider, key=key)["state"] == "missing_provider_key"
    assert not provider.requests and brief_row(maker) is None
    assert not (tmp_path / "cache").exists()


def test_only_ready_or_building_history_periods_without_a_brief_are_attempted(maker, tmp_path):
    for status, start in (("partial", WEEK_START), ("unavailable", NEXT),
                          ("building_history", date(2026, 10, 12))):
        store_period(maker, period_payload(start=start, status=status))
    store_period(maker, period_payload(start=date(2026, 10, 5), quiet=True))
    provider = Provider()
    report = go(maker, tmp_path, provider, [
        ("week", date(2026, 10, 5)), ("week", date(2026, 10, 12)), ("week", WEEK_START),
        ("week", NEXT), ("week", date(2026, 9, 28))])
    assert report["periods"] == {
        "week:2026-10-05": "skipped:quiet", "week:2026-10-12": "ok",
        "week:2026-10-19": "skipped:status_partial",
        "week:2026-10-26": "skipped:status_unavailable",
        "week:2026-09-28": "skipped:no_period"}
    assert len(provider.requests) == 1


def test_a_month_brief_needs_a_month_row_and_uses_month_values(maker, tmp_path):
    provider = Provider()
    none = go(maker, tmp_path, provider, [("month", MONTH)])
    assert none["periods"] == {"month:2026-11-01": "skipped:no_period"} and not provider.requests
    store_period(maker, period_payload("month", MONTH, stories=6))
    month = Provider(lambda r: good_answer(r, sentences=5))
    report = go(maker, tmp_path, month, [("month", MONTH)])
    assert report["periods"] == {"month:2026-11-01": "ok"}
    body = month.requests[0]
    assert body["max_tokens"] == PERIOD_MAX_OUTPUT["month"]
    assert "5 to 8 sentences" in body["messages"][0]["content"]
    assert len(json.loads(brief_row(maker, "month", MONTH).payload)["sentences"]) == 5


def test_a_stop_is_a_terminal_reason_and_stores_nothing(maker, tmp_path):
    store_period(maker, period_payload())
    provider = Provider(lambda r: httpx.Response(200, content=b"not json"))
    report = go(maker, tmp_path, provider)
    assert report["periods"] == {"week:2026-10-19": "skipped:attempt_unknown"}
    assert brief_row(maker) is None


def test_the_ledger_has_its_own_run_id(maker, tmp_path):
    store_period(maker, period_payload())
    go(maker, tmp_path, Provider())
    ledger = sqlite3.connect(tmp_path / "cache" / "ledger.sqlite3")
    runs = [r[0] for r in ledger.execute("SELECT run_id FROM calls")]
    ledger.close()
    assert len(runs) == 1 and runs[0].endswith("-brief-week:2026-10-19")


def test_no_table_but_the_brief_row_is_written(maker, tmp_path):
    store_period(maker, period_payload())
    go(maker, tmp_path, Provider())
    with maker() as session:
        assert len(session.scalars(select(PeriodSignalBrief)).all()) == 1
