"""Known non-English world-title fallbacks (spec 018, F9); all model calls are fake."""
from copy import deepcopy
from dataclasses import replace

import pytest
from test_bulletin_writer import (  # pylint: disable=import-error
    LIB,
    RESPONSE,
    answer,
    bulletin,
    flat,
    run,
    sources,
    story,
)

from app.core.bulletin import writer as writer_module
from app.core.bulletin.builder import make_headline
from app.core.bulletin.writer import write_bulletin


def language_bulletin(index=0, *, language="deu", origin="world"):
    base = bulletin()
    if index == 5:
        base.incident_story = deepcopy(base.key_results[0])
        base.incidents = 3
    target = writer_module.all_stories(base)[index]
    target.origin, target.language = origin, language
    target.title = "Crosby bietet auf Weil Gotshal"
    if index == 0:
        base.headline, base.headline_cut = make_headline(target.title)
    return base


@pytest.mark.parametrize("headline", [None, "Anthropic buys Crosby"])
def test_non_english_story_without_headline_is_removed(headline):
    base = language_bulletin()
    result, _ = run(base=base, mutate=lambda c: c["stories"][0].update(headline=headline))
    assert base.key_results[0].title not in [s.title for s in writer_module.all_stories(
        result.bulletin)]
    assert base.key_results[0].title not in flat(result.bulletin)
    assert len(base.key_results) == 3  # the builder input is not mutated


@pytest.mark.parametrize("telegram", [[], ["Anthropic buys Crosby."]])
def test_non_english_story_without_telegram_is_removed(telegram):
    result, _ = run(base=language_bulletin(), mutate=lambda c: c["stories"][0].update(
        telegram=telegram))
    assert [s.title for s in result.bulletin.key_results] == [
        s.title for s in bulletin().key_results[1:]]


def test_non_english_story_with_model_text_stays():
    base = language_bulletin()
    result, _ = run(base=base, mutate=lambda c: c["stories"][0].update(site=[]))
    kept = story(result, 0)
    assert kept.title == base.key_results[0].title
    assert kept.headline == RESPONSE["stories"][0]["headline"]
    assert kept.telegram_note == RESPONSE["stories"][0]["telegram"]
    assert kept.text_origin == "model" and not kept.site_note
    assert result.bulletin.as_dict()["key_results"][0]["language"] == "deu"
    assert result.summary["dropped"] == []
    assert kept.title not in flat(result.bulletin)


@pytest.mark.parametrize(("origin", "language"), [
    ("world", "unknown"), ("world", "eng"), ("world", ""), ("digest", "deu")])
def test_unknown_or_english_language_story_falls_back_to_title(origin, language):
    base = language_bulletin(language=language, origin=origin)
    result, _ = run(base=base, mutate=lambda c: c["stories"][0].update(
        headline=None, site=[], telegram=[]))
    assert story(result, 0).title == base.key_results[0].title
    assert story(result, 0).text_origin == "title"
    assert result.bulletin.as_dict()["key_results"][0]["language"] == language
    assert "s1:story:non_english_title" not in result.summary["dropped"]
    fallback = write_bulletin(base, {}, lambda body: (None, "provider_outage"))
    assert fallback.bulletin.as_dict()["key_results"][0] == base.as_dict()["key_results"][0]


@pytest.mark.parametrize("index", [0, 3, 4, 5])
@pytest.mark.parametrize("failure", ["unavailable", "invalid"])
def test_title_only_bulletin_removes_non_english_stories(index, failure):
    base = language_bulletin(index)
    data = (None, "provider_outage") if failure == "unavailable" else ({}, None)
    result = write_bulletin(base, {}, lambda body: data)
    assert len(writer_module.all_stories(result.bulletin)) == len(
        writer_module.all_stories(base)) - 1
    assert result.bulletin.incidents == base.incidents
    assert result.summary["dropped"] == [f"s{index + 1}:story:non_english_title"]
    assert result.summary["stories_title"] == len(writer_module.all_stories(result.bulletin))
    assert result.summary["stories_model"] == 0
    assert result.summary["reason"] == ("provider_outage" if failure == "unavailable" else "model")


@pytest.mark.parametrize("index", [0, 3, 4, 5])
def test_removed_story_is_in_dropped(index):
    base = language_bulletin(index)
    content = answer()
    if index == 5:
        content["stories"].append({**content["stories"][0], "id": "s6"})
    content["stories"][index]["headline"] = "Anthropic buys Crosby"
    result, _ = run(base=base, content=content)
    assert f"s{index + 1}:story:non_english_title" in result.summary["dropped"]
    assert len(writer_module.all_stories(result.bulletin)) == len(
        writer_module.all_stories(base)) - 1
    assert result.bulletin.incidents == base.incidents
    assert result.summary["stories_model"] == len(writer_module.all_stories(base)) - 1


@pytest.mark.parametrize("title", [
    "Crosby bietet auf Weil Gotshal",
    "Crosby bietet auf Weil Gotshal: die Kanzlei will weiter wachsen"])
@pytest.mark.parametrize("day_headline", ["invalid", "model", "unrelated", "missing"])
def test_day_headline_not_from_removed_story(title, day_headline):
    base = language_bulletin()
    base.key_results[0].title = title
    headline, cut = make_headline(title)
    base.headline, base.headline_cut = headline + (LIB["cut"]["marker"] if cut else ""), cut
    if day_headline == "unrelated":
        base.headline, base.headline_cut = "ANOTHER TITLE HERE", False
    if day_headline == "missing":
        base.headline, base.headline_cut = None, False
    content = answer()
    content["stories"][0]["headline"] = None
    if day_headline != "model":
        content["headline"] = "Anthropic invented everything"
    result, _ = run(base=base, content=content)
    expected = {"invalid": None, "model": RESPONSE["headline"].upper(),
                "unrelated": "ANOTHER TITLE HERE", "missing": None}
    assert result.bulletin.headline == expected[day_headline]
    assert result.bulletin.headline_cut is False
    fallback = write_bulletin(base, {}, lambda body: (None, "provider_outage"))
    assert fallback.bulletin.headline == ("ANOTHER TITLE HERE" if day_headline == "unrelated"
                                          else None)
    assert fallback.bulletin.headline_cut is False


def test_missing_writer_entries_remove_world_stories_in_original_order():
    base = language_bulletin()
    base.cooperation[0].origin, base.cooperation[0].language = "world", "vie"
    result, _ = run(base=base, content={"headline": "", "stories": []})
    assert result.summary["dropped"] == ["headline:word_count", "s1:story:non_english_title",
                                          "s5:story:non_english_title"]
    assert not result.bulletin.cooperation
    assert result.summary["stories_title"] == 3


def test_removed_title_without_headline_boundary_keeps_other_day_headline():
    base = language_bulletin()
    base.key_results[0].title = "Crosby bietet auf Weil Gotshal und will die Kanzlei ausbauen"
    base.headline, base.headline_cut = "ANOTHER TITLE HERE", False
    result = write_bulletin(base, {}, lambda body: (None, "provider_outage"))
    assert result.bulletin.headline == "ANOTHER TITLE HERE"
    assert result.bulletin.headline_cut is False
    assert len(result.bulletin.key_results) == 2


@pytest.mark.parametrize(("removed_title", "same_cut_prefix"), [
    ("Crosby bietet auf Weil Gotshal", False),
    ("Crosby bietet auf Weil Gotshal: die Kanzlei will weiter wachsen", False),
    ("Crosby bietet auf Weil Gotshal", True)])
def test_removed_title_prefix_does_not_clear_another_cut_headline(removed_title, same_cut_prefix):
    base = language_bulletin()
    base.key_results[0].title = removed_title
    other = base.key_results[1]
    other.title = "Crosby bietet auf Weil Gotshal Beratung: die Kanzlei will weiter wachsen"
    if same_cut_prefix:
        other.title = "Crosby bietet auf Weil Gotshal: die Kanzlei will weiter wachsen"
    other.confidence = 1.0
    headline, cut = make_headline(other.title)
    assert cut
    base.headline, base.headline_cut = headline + LIB["cut"]["marker"], cut
    result = write_bulletin(base, {}, lambda body: (None, "provider_outage"))
    assert result.bulletin.headline == base.headline
    assert result.bulletin.headline_cut is True
    assert len(result.bulletin.key_results) == 2


@pytest.mark.parametrize("title", [
    "Crosby bietet auf Weil Gotshal",
    "Crosby bietet auf Weil Gotshal: die Kanzlei will weiter wachsen"])
def test_day_headline_from_kept_non_english_story_is_cleared(title):
    base = language_bulletin()
    base.key_results[0].title = title
    headline, cut = make_headline(title)
    base.headline, base.headline_cut = headline + (LIB["cut"]["marker"] if cut else ""), cut
    result, _ = run(base=base, mutate=lambda c: c.update(headline="Anthropic invented everything"))
    assert result.bulletin.headline is None
    assert result.bulletin.headline_cut is False
    assert result.bulletin.headline_origin == "title"
    assert story(result, 0).headline == RESPONSE["stories"][0]["headline"]
    assert story(result, 0).telegram_note == RESPONSE["stories"][0]["telegram"]
    assert result.summary["dropped"] == ["headline:unsupported_name"]
    assert base.headline == headline + (LIB["cut"]["marker"] if cut else "")


@pytest.mark.parametrize(("title", "gloss"), [
    ("Crosby bietet auf Weil Gotshal", "Crosby bietet auf"),
    ("Crosby bietet auf Weil Gotshal", "bietet auf Weil"),
    ("Crosby bietet auf Weil Gotshal", "auf Weil Gotshal"),
    ("Crosby bietet auf Weil Gotshal", "CROSBY, BIETET AUF"),
    ("Crosby bietet auf die Z\u00fcrcher Kanzlei", "auf die zurcher"),
    ("Crosby bietet auf Weil Gotshal", "The report nennt bietet auf Weil")])
def test_gloss_echoing_non_english_title_is_dropped(title, gloss):
    base = language_bulletin()
    base.key_results[0].title = title
    source_map = sources()
    url = base.key_results[0].links[0]["url"]
    source_map[url] = replace(source_map[url], title=title)
    result, _ = run(base=base, source_map=source_map,
                    mutate=lambda c: c["stories"][0].update(gloss=gloss))
    assert story(result, 0).gloss is None
    assert story(result, 0).headline == RESPONSE["stories"][0]["headline"]
    assert story(result, 0).telegram_note == RESPONSE["stories"][0]["telegram"]
    assert story(result, 0).text_origin == "model"
    assert result.summary["dropped"] == ["s1:gloss:non_english_title"]


@pytest.mark.parametrize(("origin", "language", "gloss"), [
    ("world", "deu", "bietet auf"),
    ("world", "deu", "bietet neue auf"),
    ("world", "deu", "bietet auftrag weil"),
    ("world", "deu", "Weil Gotshal, a famed Wall Street firm"),
    ("world", "deu", None),
    ("world", "unknown", "Crosby bietet auf"),
    ("world", "eng", "Crosby bietet auf"),
    ("world", "", "Crosby bietet auf"),
    ("digest", "deu", "Crosby bietet auf")])
def test_gloss_of_non_english_story_without_title_run_stays(origin, language, gloss):
    assert writer_module.TITLE_RUN_WORDS == 3
    base = language_bulletin(origin=origin, language=language)
    result, _ = run(base=base, mutate=lambda c: c["stories"][0].update(gloss=gloss))
    assert story(result, 0).gloss == gloss
    assert result.summary["dropped"] == []


def echo_bulletin():
    base = language_bulletin()
    source_map = sources()
    url = base.key_results[0].links[0]["url"]
    source_map[url] = replace(source_map[url], title=base.key_results[0].title)
    return base, source_map


def test_story_headline_echoing_non_english_title_is_removed():
    base, source_map = echo_bulletin()
    result, _ = run(base=base, source_map=source_map, mutate=lambda c: c["stories"][0].update(
        headline="Crosby bietet auf Weil Gotshal"))
    assert all(s.title != "Crosby bietet auf Weil Gotshal"
               for s in writer_module.all_stories(result.bulletin))
    assert "s1:headline:non_english_title" in result.summary["dropped"]
    assert "s1:story:non_english_title" in result.summary["dropped"]


def test_model_day_headline_echoing_non_english_title_is_cleared():
    base, source_map = echo_bulletin()
    result, _ = run(base=base, source_map=source_map,
                    mutate=lambda c: c.update(headline="Crosby bietet auf Weil Gotshal heute"))
    assert result.bulletin.headline is None
    assert result.bulletin.headline_cut is False
    assert "headline:non_english_title" in result.summary["dropped"]
    assert story(result, 0).headline == RESPONSE["stories"][0]["headline"]
