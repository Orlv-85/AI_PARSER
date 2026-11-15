"""Reserve stories for the bulletin writer (spec 018, F11); the model is a fake."""
import json
import re
from dataclasses import replace
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.bulletin import builder as builder_module
from app.core.bulletin.builder import (
    KEY_RESULTS_MAX,
    RESERVE_MAX,
    Candidate,
    DayInput,
    build_bulletin,
)
from app.core.bulletin.phrases import load_phrases
from app.core.bulletin.render import render_text
from app.core.bulletin.writer import (
    WRITER_MAX_OUTPUT,
    SourceText,
    all_stories,
    build_packet,
    write_bulletin,
)
from app.storage.bulletin_texts import load_sources
from app.storage.models_sql import Base

DAY = date(2026, 10, 30)
LIB = load_phrases()
NAMES = ["Zentra", "Orbix", "Quillon", "Marlow", "Nexen", "Tavari", "Brisko", "Corvid",
         "Dunmar", "Elbren", "Fyrnex", "Gallow"]


def cand(n, **kw):
    base = {"url": f"https://o{n}.example/a{n}", "title": f"{NAMES[n]} unveils a compact system",
            "outlet": f"Outlet{n}", "world_change": "changed", "confidence": 0.99 - n * 0.01,
            "area": "Work", "actor": "organisation", "harm": 0.0, "event_key": f"e{n}"}
    return Candidate(**{**base, **kw})


def build(candidates):
    data = DayInput(day=DAY, status="ready", quiet=False, items=40, model_releases=0,
                    product_launches=0, median_items=None, candidates=tuple(candidates))
    result = build_bulletin(data, LIB)
    assert result.bulletin is not None
    return result.bulletin


def titles(stories):
    return [s.title for s in stories]


# builder

def test_reserve_follows_key_results_in_rank_order():
    bulletin = build(cand(n) for n in range(10))
    assert titles(bulletin.key_results) == [cand(n).title for n in range(4)]
    assert titles(bulletin.reserve) == [cand(n).title for n in range(4, 8)]
    assert builder_module.RESERVE_MAX == 4


@pytest.mark.parametrize(("count", "expected"), [(4, 0), (5, 1), (7, 3), (8, 4), (12, 4)])
def test_reserve_is_capped_and_can_be_short_or_empty(count, expected):
    assert len(build(cand(n) for n in range(count)).reserve) == expected


def test_reserve_has_no_overlap_with_shown_stories():
    extra = [cand(8, world_change="issue", actor="ai_system", confidence=0.995),
             cand(9, world_change="limit", confidence=0.994),
             cand(10, world_change="issue", actor="people", confidence=0.993),
             cand(11, harm=0.9, confidence=0.992)]
    bulletin = build([*(cand(n) for n in range(8)), *extra])
    shown = {s.title for s in all_stories(bulletin)}
    assert bulletin.rubric_story and bulletin.cooperation and bulletin.incident_story
    assert len(bulletin.reserve) == 4
    assert not shown & {s.title for s in bulletin.reserve}
    assert cand(11).title not in {s.title for s in bulletin.reserve}


def test_reserve_obeys_the_model_launch_cap():
    launches = [cand(n, event_type="model_release") for n in range(4)]
    bulletin = build([*launches, *(cand(n) for n in range(4, 9))])
    assert titles(bulletin.key_results)[:2] == [cand(0).title, cand(1).title]
    released = [s for s in [*bulletin.key_results, *bulletin.reserve]
                if s.event_type == "model_release"]
    assert len(released) == builder_module.MODEL_LAUNCHES_MAX


def test_reserve_is_not_in_the_object_or_the_text():
    bulletin = build(cand(n) for n in range(8))
    assert "reserve" not in bulletin.as_dict()
    text = render_text(bulletin, LIB)
    assert not any(s.title in text for s in bulletin.reserve)
    assert "reserve" not in json.dumps(bulletin.as_dict())


def test_reserve_does_not_change_headline_or_reactions():
    with_reserve = build(cand(n) for n in range(8))
    without = replace(with_reserve, reserve=[])
    assert with_reserve.as_dict() == without.as_dict()
    shown_only = build(cand(n) for n in range(4)).as_dict()
    assert shown_only["headline"] == with_reserve.headline
    assert shown_only["reactions_used"] == with_reserve.reactions_used


# writer

def source_map(bulletin):
    found = {}
    for story in [*all_stories(bulletin), *bulletin.reserve]:
        url, name = story.links[0]["url"], story.title.split()[0]
        k = 10 + int(re.search(r"/a(\d+)$", url).group(1))
        found[url] = SourceText(url=url, title=story.title, summary="", text=(
            f"{name} unveiled a compact language system. The company says it lowers inference "
            f"bills by {k} percent. Pilot customers tested it for six weeks."))
    return found


def entry(sid, story):
    name = story.title.split()[0]
    k = 10 + int(re.search(r"/a(\d+)$", story.links[0]["url"]).group(1))
    return {"id": sid, "headline": f"{name} presents cheaper language system",
            "site": [f"{name} presented a small language system aimed at cheaper inference.",
                     f"The company claims a {k} percent cut in inference bills.",
                     "The pilot with customers lasted six weeks."],
            "telegram": [f"{name} presented a small language system that cuts inference bills "
                         f"by {k} percent."], "gloss": None}


def answer(bulletin, mutate=None):
    stories = [*all_stories(bulletin), *bulletin.reserve]
    content = {"headline": f"{stories[0].title.split()[0]} presents cheaper language system",
               "stories": [entry(f"s{i}", s) for i, s in enumerate(stories, start=1)]}
    if mutate:
        mutate(content)
    return content


def go(bulletin, mutate=None, *, sources=None):
    data = {"model": "deepseek-flash", "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps(answer(bulletin, mutate))}}]}
    calls = []

    def ask(body):
        calls.append(body)
        return data, None
    return write_bulletin(bulletin, sources or source_map(bulletin), ask), calls


def foreign(bulletin, story, language="deu"):
    story.origin, story.language = "world", language
    return bulletin


def day(count=8, **kw):
    return build([*(cand(n) for n in range(count)), *kw.get("extra", [])])


def test_packet_lists_reserve_after_shown_stories():
    bulletin = day()
    packet = build_packet(bulletin, source_map(bulletin))
    assert [s["id"] for s in packet["stories"]] == [f"s{i}" for i in range(1, 9)]
    assert [s.get("reserve") for s in packet["stories"]] == [None] * 4 + [True] * 4
    assert packet["stories"][4]["articles"][0]["title"] == bulletin.reserve[0].title
    assert packet["stories"][4]["articles"][0]["text"].startswith(NAMES[4])


def test_loader_loads_reserve_texts():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    bulletin = day()
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        found = load_sources(session, bulletin)
    assert {s.links[0]["url"] for s in bulletin.reserve} <= set(found)


def test_removed_key_story_is_replaced_by_first_qualifying_reserve():
    bulletin = day()
    foreign(bulletin, bulletin.key_results[1])
    result, calls = go(bulletin, lambda c: c["stories"][1].update(headline=None))
    assert len(calls) == 1
    assert titles(result.bulletin.key_results) == [
        cand(n).title for n in (0, 2, 3, 4)]
    promoted = result.bulletin.key_results[-1]
    assert promoted.text_origin == "model" and promoted.headline and promoted.site_note
    assert not result.bulletin.reserve
    assert len(bulletin.key_results) == 4 and len(bulletin.reserve) == 4  # input untouched


def test_reserve_without_checked_text_is_skipped():
    bulletin = day()
    foreign(bulletin, bulletin.key_results[0])
    def mutate(c):
        c["stories"][0].update(headline=None)
        c["stories"][4].update(site=["Short."])  # no checked site sentence
        c["stories"][5].update(headline="Anthropic breaks Firefox")  # no checked headline
    result, _ = go(bulletin, mutate)
    assert titles(result.bulletin.key_results)[-1] == cand(6).title
    assert result.summary["reserve"] == {"offered": 4, "promoted": ["s7"]}
    assert "s5:site:1:word_count" in result.summary["dropped"]


def test_non_english_reserve_needs_headline_and_telegram():
    bulletin = day()
    foreign(bulletin, bulletin.key_results[0])
    foreign(bulletin, bulletin.reserve[0])
    foreign(bulletin, bulletin.reserve[1])
    def mutate(c):
        c["stories"][0].update(headline=None)
        c["stories"][4].update(telegram=[])
        c["stories"][5].update(headline=None)
    result, _ = go(bulletin, mutate)
    assert titles(result.bulletin.key_results)[-1] == cand(6).title
    assert result.summary["reserve"]["promoted"] == ["s7"]
    ok = day()
    foreign(ok, ok.key_results[0])
    foreign(ok, ok.reserve[0])
    result, _ = go(ok, lambda c: c["stories"][0].update(headline=None))
    assert titles(result.bulletin.key_results)[-1] == cand(4).title


def test_no_promotion_when_nothing_was_removed():
    bulletin = day()
    result, _ = go(bulletin)
    assert titles(result.bulletin.key_results) == [cand(n).title for n in range(4)]
    assert result.summary["reserve"] == {"offered": 4, "promoted": []}
    assert not result.bulletin.reserve


def test_no_promotion_on_fallback():
    bulletin = day()
    foreign(bulletin, bulletin.key_results[0])
    result = write_bulletin(bulletin, {}, lambda body: (None, "provider_outage"))
    assert titles(result.bulletin.key_results) == [cand(n).title for n in (1, 2, 3)]
    assert not result.bulletin.reserve
    assert result.summary["reserve"] == {"offered": 4, "promoted": []}
    assert result.summary["dropped"] == ["s1:story:non_english_title"]


def test_other_sections_are_not_refilled():
    bulletin = build([*(cand(n) for n in range(8)),
                      cand(8, world_change="limit", confidence=0.75)])
    assert len(bulletin.cooperation) == 1
    foreign(bulletin, bulletin.cooperation[0])
    result, _ = go(bulletin, lambda c: c["stories"][4].update(headline=None))
    assert not result.bulletin.cooperation
    assert titles(result.bulletin.key_results) == [cand(n).title for n in range(4)]
    assert result.summary["reserve"]["promoted"] == []


def test_day_headline_grounded_only_in_a_reserve_story_is_dropped():
    bulletin = day()
    result, _ = go(bulletin, lambda c: c.update(headline="Corvid presents cheaper language system"))
    assert result.bulletin.headline_origin == "title"
    assert result.bulletin.headline == bulletin.headline
    assert any(d.startswith("headline:") for d in result.summary["dropped"])


def test_summary_reports_the_reserve():
    bulletin = day()
    foreign(bulletin, bulletin.key_results[0])
    foreign(bulletin, bulletin.key_results[3])
    result, _ = go(bulletin, lambda c: (c["stories"][0].update(headline=None),
                                        c["stories"][3].update(headline=None),
                                        c["stories"][4].update(site=["Short."])))
    summary = result.summary
    assert summary["reserve"] == {"offered": 4, "promoted": ["s6", "s7"]}
    assert (summary["stories_model"], summary["stories_title"]) == (4, 0)
    assert "s5:site:1:word_count" in summary["dropped"]
    assert "s1:story:non_english_title" in summary["dropped"]
    assert "s4:story:non_english_title" in summary["dropped"]


def test_reserve_story_echoing_its_non_english_title_is_not_promoted():
    bulletin = day()
    foreign(bulletin, bulletin.key_results[0])
    foreign(bulletin, bulletin.reserve[0])
    foreign(bulletin, bulletin.reserve[1])
    title = bulletin.reserve[0].title

    def mutate(c):
        c["stories"][0].update(headline=None)
        c["stories"][4].update(headline=title)
        c["stories"][5].update(gloss=bulletin.reserve[1].title)
    result, _ = go(bulletin, mutate)
    assert "s5:headline:non_english_title" in result.summary["dropped"]
    assert "s6:gloss:non_english_title" in result.summary["dropped"]
    assert result.summary["reserve"]["promoted"] == ["s6"]
    assert result.bulletin.key_results[-1].gloss is None



def test_english_reserve_story_may_repeat_its_title():
    bulletin = day()
    foreign(bulletin, bulletin.key_results[0])
    title = bulletin.reserve[0].title

    def mutate(c):
        c["stories"][0].update(headline=None)
        c["stories"][4].update(headline=title)
    result, _ = go(bulletin, mutate)
    assert result.summary["reserve"]["promoted"] == ["s5"]
    assert result.bulletin.key_results[-1].headline == title


def test_output_budget_holds_twelve_stories():
    # About 310 tokens a story (headline, four sentences, Telegram note, gloss) plus the day
    # headline, and half as much again: a cut answer falls back to titles for the whole day.
    stories = KEY_RESULTS_MAX + RESERVE_MAX + 4  # rubric, two Cooperation, incident story
    assert int(1.5 * (stories * 310 + 50)) <= WRITER_MAX_OUTPUT
