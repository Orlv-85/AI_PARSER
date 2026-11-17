"""Bulletin repeat check (spec 018, F10) with a fake `ask`; no test makes a real call."""
import json
from datetime import date

import pytest

from app.core.bulletin.builder import MIN_CONFIDENCE, Candidate, DayInput, build_bulletin
from app.core.bulletin.phrases import load_phrases
from app.core.bulletin.repeats import (
    REPEAT_DAYS,
    REPEATS_MAX_CANDIDATES,
    REPEATS_MAX_OUTPUT,
    REPEATS_PROMPT,
    REPEATS_VERSION,
    TITLE_MAX,
    PublishedStory,
    check_repeats,
)
from app.core.bulletin.writer import WRITER_MODEL

DAY = date(2026, 11, 14)
LIB = load_phrases()
PUBLISHED = (PublishedStory(day="2026-11-13", shown="United bans AI agents from booking",
                            title="United Airlines changes how AI agents book flights"),)


def cand(n, **kw):
    base = {"url": f"https://o{n}.com/a{n}", "title": f"Story {n} changes the work",
            "outlet": f"O{n}", "world_change": "changed", "confidence": 0.9, "area": "Work",
            "actor": "organisation", "harm": 0.0, "event_key": f"e{n}"}
    return Candidate(**{**base, **kw})


def day_input(candidates):
    return DayInput(day=DAY, status="ready", quiet=False, items=83, model_releases=5,
                    product_launches=13, median_items=None, candidates=tuple(candidates))


def reply(content):
    text = content if isinstance(content, str) else json.dumps(content)
    return {"model": WRITER_MODEL, "choices": [{"finish_reason": "stop",
                                                "message": {"content": text}}]}


class Asker:
    def __init__(self, answer=None, reason=None):
        self.answer, self.reason, self.bodies = answer, reason, []

    def __call__(self, body):
        self.bodies.append(body)
        if self.reason:
            return None, self.reason
        return reply(self.answer), None


def run(candidates, answer=None, *, published=PUBLISHED, reason=None):
    asker = Asker(answer, reason)
    return check_repeats(day_input(candidates), published, asker), asker


def three():
    return [cand(1, confidence=0.95), cand(2, confidence=0.9), cand(3, confidence=0.8)]


def listing(asker):
    return json.loads(asker.bodies[0]["messages"][1]["content"])


def test_repeat_is_dropped():
    result, asker = run(three(), {"repeats": [{"candidate": "c2", "published": "p1"}],
                                  "same_event": []})
    assert [c.url for c in result.data.candidates] == ["https://o1.com/a1", "https://o3.com/a3"]
    assert result.summary == {
        "version": REPEATS_VERSION, "model": WRITER_MODEL, "reason": None, "candidates": 3,
        "published": 1, "merged": [], "kept": [],
        "dropped": [{"title": "Story 2 changes the work", "published_day": "2026-11-13",
                     "published_title": "United bans AI agents from booking"}]}
    assert len(asker.bodies) == 1
    assert result.data.digest_left_out == 1


@pytest.mark.parametrize("answer", [
    {"repeats": [{"candidate": "c9", "published": "p1"}], "same_event": []},
    {"repeats": [{"candidate": "c1", "published": "p9"}], "same_event": []},
    {"repeats": [], "same_event": [["c1", "c9"]]},
    {"repeats": [{"candidate": "c0", "published": "p1"}], "same_event": []},
    {"repeats": [{"candidate": "c1", "published": "p0"}], "same_event": []},
    {"repeats": [], "same_event": [["c0", "c1"]]},
    {"repeats": [], "same_event": [], "extra": 1},
    {"repeats": []},
    {"repeats": [{"candidate": "c1", "published": "p1"}, {"candidate": "c1", "published": "p1"}],
     "same_event": []},
    {"repeats": [], "same_event": [["c1", "c2"], ["c2", "c3"]]},
    {"repeats": [], "same_event": [["c1", "c1"]]},
    {"repeats": [], "same_event": [["c1"]]},
    {"repeats": [{"candidate": "c1"}], "same_event": []},
    {"repeats": [{"candidate": "c1", "published": "p1", "x": 1}], "same_event": []},
    {"repeats": "none", "same_event": []},
    {"repeats": [{"candidate": ["c1"], "published": "p1"}], "same_event": []},
    {"repeats": [{"candidate": "c1", "published": {}}], "same_event": []},
    {"repeats": [], "same_event": [[["c1"], "c2"]]},
    {"repeats": [], "same_event": [["c1", 2]]},
    ["c1"], "not json", "",
])
def test_invalid_answer_changes_nothing(answer):
    result, _ = run(three(), answer)
    assert result.data == day_input(three())
    assert result.summary["reason"] == "invalid_answer"
    assert result.summary["dropped"] == result.summary["merged"] == []


@pytest.mark.parametrize("tweak", [
    lambda r: {**r, "model": "other-model"},
    lambda r: {**r, "choices": []},
    lambda r: {**r, "choices": [{"finish_reason": "length",
                                 "message": r["choices"][0]["message"]}]},
])
def test_unusable_provider_answer_changes_nothing(tweak):
    good = reply({"repeats": [{"candidate": "c1", "published": "p1"}], "same_event": []})
    result = check_repeats(day_input(three()), PUBLISHED, lambda body: (tweak(good), None))
    assert result.data == day_input(three())
    assert result.summary["reason"] == "invalid_answer"


def test_non_mapping_provider_answer_changes_nothing():
    result = check_repeats(day_input(three()), PUBLISHED, lambda body: ("x", None))
    assert result.data == day_input(three())
    assert result.summary["reason"] == "invalid_answer"


@pytest.mark.parametrize("reason", ["run_limit", "provider_outage"])
def test_provider_reason_keeps_everything(reason):
    result, _ = run(three(), reason=reason)
    assert result.data == day_input(three())
    assert result.summary["reason"] == reason and result.summary["dropped"] == []


def test_provider_none_without_reason_keeps_everything():
    result = check_repeats(day_input(three()), PUBLISHED, lambda body: (None, None))
    assert result.data == day_input(three())
    assert result.summary["reason"] == "unavailable"


def test_same_event_sets_one_event_key():
    result, _ = run(three(), {"repeats": [], "same_event": [["c3", "c2"]]})
    keys = {c.url: c.event_key for c in result.data.candidates}
    assert keys == {"https://o1.com/a1": "e1", "https://o2.com/a2": "e2",
                    "https://o3.com/a3": "e2"}
    assert result.summary["merged"] == [["Story 3 changes the work", "Story 2 changes the work"]]
    assert result.summary["reason"] is None


def test_same_event_best_member_wins_ties_by_listing_order():
    tied = [cand(1), cand(2), cand(3)]
    result, _ = run(tied, {"repeats": [], "same_event": [["c2", "c3"]]})
    assert [c.event_key for c in result.data.candidates] == ["e1", "e2", "e2"]


def test_same_event_builds_one_story_with_both_outlets():
    result, _ = run(three(), {"repeats": [], "same_event": [["c1", "c2"]]})
    built = build_bulletin(result.data, LIB).bulletin
    stories = [*built.key_results, *built.cooperation]
    assert len(stories) == 2
    merged = next(s for s in stories if len(s.links) == 2)
    assert merged.outlets == ["O1", "O2"]
    unmerged = build_bulletin(day_input(three()), LIB).bulletin
    assert len([*unmerged.key_results, *unmerged.cooperation]) == 3


def test_dropped_member_is_not_merged():
    both = [{"candidate": "c1", "published": "p1"}, {"candidate": "c2", "published": "p1"}]
    result, _ = run(three(), {"repeats": both, "same_event": [["c1", "c2"]]})
    assert [(c.url, c.event_key) for c in result.data.candidates] == [("https://o3.com/a3", "e3")]
    assert result.summary["merged"] == []


def test_unshowable_candidates_are_not_listed():
    candidates = [cand(1), cand(2, world_change="none"),
                  cand(3, confidence=MIN_CONFIDENCE - 0.01),
                  cand(4, confidence=MIN_CONFIDENCE)]
    result, asker = run(candidates, {"repeats": [{"candidate": "c1", "published": "p1"}],
                                     "same_event": []})
    assert [c["id"] for c in listing(asker)["candidates"]] == ["c1", "c2"]
    assert [c["title"] for c in listing(asker)["candidates"]] == [
        "Story 1 changes the work", "Story 4 changes the work"]
    assert [c.url for c in result.data.candidates] == [
        "https://o2.com/a2", "https://o3.com/a3", "https://o4.com/a4"]
    assert result.summary["candidates"] == 2


def test_repeat_check_lists_only_showable_kinds():
    candidates = [cand(1), cand(2, kind="opinion"), cand(3, kind="forecast"),
                  cand(4, kind="explainer"), cand(5, kind="promotion"), cand(6)]
    result, asker = run(candidates, {"repeats": [], "same_event": []})
    assert [c["title"] for c in listing(asker)["candidates"]] == [
        "Story 1 changes the work", "Story 6 changes the work"]
    assert result.summary["candidates"] == 2


def test_listing_is_capped_by_confidence():
    many = [cand(n, confidence=0.7 + n / 1000) for n in range(REPEATS_MAX_CANDIDATES + 5)]
    result, asker = run(many, {"repeats": [], "same_event": []})
    titles = [c["title"] for c in listing(asker)["candidates"]]
    assert len(titles) == REPEATS_MAX_CANDIDATES == result.summary["candidates"]
    assert titles[0] == f"Story {REPEATS_MAX_CANDIDATES + 4} changes the work"
    assert "Story 0 changes the work" not in titles
    assert len(result.data.candidates) == len(many)


def test_no_listed_candidate_no_call():
    result, asker = run([cand(1, world_change="none"), cand(2, confidence=0.1)],
                        {"repeats": [], "same_event": []})
    assert not asker.bodies and result.data == day_input(result.data.candidates)
    assert result.summary["reason"] == "no_candidates"
    assert not run([], {})[1].bodies


def test_one_candidate_and_no_published_story_no_call():
    result, asker = run([cand(1)], {"repeats": [], "same_event": []}, published=[])
    assert not asker.bodies and result.summary["reason"] == "nothing_to_compare"
    assert (result.summary["candidates"], result.summary["published"]) == (1, 0)


@pytest.mark.parametrize(("candidates", "published"), [
    ([cand(1)], PUBLISHED), ([cand(1), cand(2)], [])])
def test_call_is_made_with_a_published_story_or_two_candidates(candidates, published):
    _, asker = run(candidates, {"repeats": [], "same_event": []}, published=published)
    assert len(asker.bodies) == 1


def test_request_holds_titles_but_no_article_text():
    long_title = "Long " * 80
    result, asker = run([cand(1, title=long_title), cand(2)],
                        {"repeats": [], "same_event": []})
    body = asker.bodies[0]
    assert body["model"] == WRITER_MODEL and body["max_tokens"] == REPEATS_MAX_OUTPUT
    assert body["response_format"] == {"type": "json_object"}
    assert REPEATS_VERSION in body["messages"][0]["content"]
    packet = listing(asker)
    assert set(packet) == {"candidates", "published"}
    assert packet["candidates"][1] == {"id": "c2", "title": "Story 2 changes the work",
                                       "outlet": "O2"}
    assert all(len(c["title"]) <= TITLE_MAX for c in packet["candidates"])
    assert packet["candidates"][0]["title"].endswith("...")
    assert packet["published"] == [{"id": "p1", "day": "2026-11-13",
                                    "title": "United bans AI agents from booking",
                                    "original": "United Airlines changes how AI agents "
                                                "book flights"}]
    assert "https://" not in json.dumps(packet) and result.summary["published"] == 1


def test_published_title_not_repeated_when_it_is_the_shown_one():
    same = [PublishedStory(day="2026-11-13", shown="A title", title="A title")]
    _, asker = run([cand(1)], {"repeats": [], "same_event": []}, published=same)
    assert listing(asker)["published"] == [{"id": "p1", "day": "2026-11-13", "title": "A title"}]


def test_repeat_days_is_three():
    assert REPEAT_DAYS == 3


def test_request_keeps_non_ascii_titles_unescaped():
    _, asker = run([cand(1, title="Zhipu releases GLM \u2014 \u6a21\u578b"), cand(2)],
                   {"repeats": [], "same_event": []})
    assert "\u6a21\u578b" in asker.bodies[0]["messages"][1]["content"]


REAL_PUBLISHED = PublishedStory(
    day="2026-11-14", shown="Google smartglasses from Gentle Monster and Warby Parker open for "
    "preorder", title="Google pushes privacy angle as Gemini-powered smartglasses debut starting "
    "at $395")
PAIR = {"repeats": [{"candidate": "c1", "published": "p1"}], "same_event": []}


def test_repeat_without_a_shared_word_is_kept():
    korea = cand(1, title="South Korea probes top exam scorer after AI cheating confession")
    result, _ = run([korea, cand(2)], PAIR, published=(REAL_PUBLISHED,))
    assert [c.url for c in result.data.candidates] == ["https://o1.com/a1", "https://o2.com/a2"]
    assert result.summary["dropped"] == []
    assert result.summary["kept"] == [{
        "title": korea.title, "published_day": "2026-11-14",
        "published_title": REAL_PUBLISHED.shown, "reason": "no_shared_word"}]
    assert result.data.digest_left_out == 0


def test_repeat_with_a_shared_word_is_dropped():
    wallet = PublishedStory(day="2026-11-14", shown="OpenAI launches ChatGPT Wallet",
                            title="OpenAI launches ChatGPT Wallet")
    result, _ = run([cand(1, title="ChatGPT Wallet lets agents buy things"), cand(2)], PAIR,
                    published=(wallet,))
    assert [c.url for c in result.data.candidates] == ["https://o2.com/a2"]
    assert result.summary["kept"] == []
    assert len(result.summary["dropped"]) == 1


def test_shared_word_may_come_from_the_original_title():
    published = PublishedStory(day="2026-11-14", shown="Banks get a new rulebook",
                               title="Regulators publish Basel guidance")
    result, _ = run([cand(1, title="BASEL guidance delayed again"), cand(2)], PAIR,
                    published=(published,))
    assert [c.url for c in result.data.candidates] == ["https://o2.com/a2"]
    assert result.summary["kept"] == []


def test_short_words_do_not_count_as_shared():
    published = PublishedStory(day="2026-11-14", shown="AI deal signed", title="AI deal signed")
    result, _ = run([cand(1, title="AI deal rejected"), cand(2)], PAIR, published=(published,))
    assert len(result.data.candidates) == 2 and len(result.summary["kept"]) == 1


def test_prompt_says_duplicates_of_today_are_not_repeats():
    assert REPEATS_VERSION == "bulletin-repeats-2"
    assert REPEATS_VERSION in REPEATS_PROMPT
    assert "only for a candidate that tells the same event as a story in" in REPEATS_PROMPT
    assert "never in" in REPEATS_PROMPT and "same_event" in REPEATS_PROMPT


def exam_group():
    return [cand(n, title=f"Korean exam cheating story {n}") for n in range(1, 6)]


def test_repeat_inside_a_partly_repeated_group_is_kept():
    published = PublishedStory(day="2026-11-16", shown="Korean IT services face pricing pressure",
                               title="Systematix says AI may deepen pricing pressure")
    answer = {"repeats": [{"candidate": f"c{n}", "published": "p1"} for n in (2, 3, 4, 5)],
              "same_event": [["c1", "c2", "c3", "c4", "c5"]]}
    result, _ = run(exam_group(), answer, published=(published,))
    assert len(result.data.candidates) == 5
    assert {c.event_key for c in result.data.candidates} == {"e1"}
    assert result.summary["dropped"] == []
    assert [k["reason"] for k in result.summary["kept"]] == ["same_event_conflict"] * 4
    assert len(result.summary["merged"][0]) == 5


def test_fully_repeated_group_is_dropped():
    published = PublishedStory(day="2026-11-16", shown="Korean exam cheating story",
                               title="Korean exam cheating story")
    answer = {"repeats": [{"candidate": f"c{n}", "published": "p1"} for n in (1, 2, 3)],
              "same_event": [["c1", "c2", "c3"]]}
    result, _ = run(exam_group()[:3], answer, published=(published,))
    assert not result.data.candidates
    assert len(result.summary["dropped"]) == 3 and result.summary["kept"] == []
