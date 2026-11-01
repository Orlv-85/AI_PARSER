# pylint: disable=redefined-outer-name,unused-argument
import ast
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from typer.testing import CliRunner

from app.cli import main as cli_main
from app.config.settings import Settings
from app.core.bulletin import builder as builder_module
from app.core.bulletin import phrases as phrases_module
from app.core.bulletin.builder import (
    HEADLINE_MAX_WORDS,
    Candidate,
    DayInput,
    build_bulletin,
    day_number,
    make_headline,
)
from app.core.bulletin.phrases import PhraseError, load_phrases, validate_phrases
from app.core.bulletin.render import render_text
from app.core.bulletin.world_change import WORLD_CHANGE_VERSION, WorldChange
from app.core.canonicalize import canonical_url_hash
from app.storage.bulletin_input import load_day_input, outlet_name
from app.storage.digest_repo import NewsDigestRepo
from app.storage.models_sql import (
    Article,
    Base,
    DailySignalReport,
    Source,
    WorldCandidate,
)
from app.storage.world_change import WorldChangeRepo

DAY = date(2026, 10, 30)
LIB = load_phrases()


def cand(n, **kw):
    base = {"url": f"https://o{n}.com/a{n}", "title": f"Story {n} changes the work",
            "outlet": f"O{n}",
            "world_change": "changed", "confidence": 0.9, "area": "Work", "actor": "organisation",
            "harm": 0.0, "event_key": f"e{n}"}
    return Candidate(**{**base, **kw})


def day_input(candidates, **kw):
    base = {"day": DAY, "status": "ready", "quiet": False, "items": 83, "model_releases": 5,
            "product_launches": 13, "median_items": None, "candidates": tuple(candidates)}
    return DayInput(**{**base, **kw})


def build(candidates, **kw):
    result = build_bulletin(day_input(candidates, **kw), LIB)
    assert result.reason is None
    assert result.bulletin is not None
    return result.bulletin


def all_phrases(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, list):
        for item in node:
            yield from all_phrases(item)
    elif isinstance(node, dict):
        for item in node.values():
            yield from all_phrases(item)


# phrases

def test_phrases_load_and_validate():
    assert LIB["version"] == "phrases-1"
    assert set(LIB["openings"]) == {"ordinary", "busy", "quiet"}
    validate_phrases(json.loads(json.dumps(LIB)))


def test_phrases_validation_rejects_bad_data():
    def broken(mutate):
        data = json.loads(json.dumps(LIB))
        mutate(data)
        with pytest.raises(PhraseError):
            validate_phrases(data)

    broken(lambda d: d["openings"].pop("quiet"))
    broken(lambda d: d["openings"].update(ordinary=[]))
    broken(lambda d: d["rubrics"].append(5))
    broken(lambda d: d["reactions"]["by_area"].update(Nowhere=["Hi."]))
    broken(lambda d: d["closings"].append("{unknown} slot"))
    broken(lambda d: d["numbers"]["units"].pop("model"))
    broken(lambda d: d["cut"].update(marker=""))
    broken(lambda d: d["labels"].pop("masthead"))


def test_phrases_pass_the_never_list():
    for phrase in all_phrases(LIB):
        assert phrases_module.never_word(phrase) is None, phrase
    bad = json.loads(json.dumps(LIB))
    bad["closings"].append("The government thanks citizens.")
    with pytest.raises(PhraseError):
        validate_phrases(bad)
    bad = json.loads(json.dumps(LIB))
    bad["closings"].append("The Administration released a model.")
    with pytest.raises(PhraseError):
        validate_phrases(bad)


def test_day_number():
    assert day_number(date(2026, 10, 29)) == 1429
    assert day_number(date(2026, 10, 30)) == 1430
    assert day_number(date(2022, 11, 30)) == 0


# day type, status

def test_day_type_openings():
    assert build([cand(1)]).opening in LIB["openings"]["ordinary"]
    assert build([cand(1)], items=100, median_items=80).opening in LIB["openings"]["busy"]
    assert build([cand(1)], items=99, median_items=80).opening in LIB["openings"]["ordinary"]
    quiet = build([cand(1)], quiet=True, items=15, median_items=10)
    assert quiet.day_type == "quiet"
    assert quiet.opening in [p.format(weekday="Friday") for p in LIB["openings"]["quiet"]]


def test_variants_differ_on_neighbouring_days():
    for kind, kw in (("ordinary", {}), ("busy", {"items": 100, "median_items": 80}),
                     ("quiet", {"quiet": True})):
        for offset in range(10):
            one = day_input([cand(1)], day=DAY + timedelta(days=offset), **kw)
            two = day_input([cand(1)], day=DAY + timedelta(days=offset + 1), **kw)
            first = build_bulletin(one, LIB).bulletin
            second = build_bulletin(two, LIB).bulletin
            assert first.opening != second.opening, kind
    closings = {
        build_bulletin(day_input([cand(1)], day=DAY + timedelta(days=i)), LIB).bulletin.closing
        for i in range(3)}
    assert closings == set(LIB["closings"])


def test_numbers_line():
    assert build([cand(1)]).numbers in (
        "In one day, 5 new models and 13 new products entered service.",
        "The day brought 5 new models and 13 new products.")
    assert build([cand(1)], model_releases=1, product_launches=1).numbers in (
        "In one day, 1 new model and 1 new product entered service.",
        "The day brought 1 new model and 1 new product.")
    assert build([cand(1)], model_releases=0).numbers in (
        "83 events recorded.", "The day recorded 83 events.")


def test_numbers_line_varies_by_date():
    for kw in ({}, {"model_releases": 0}):
        lines = {build_bulletin(day_input([cand(1)], day=DAY + timedelta(days=i), **kw),
                                LIB).bulletin.numbers for i in range(2)}
        assert len(lines) == 2


def test_partial_and_unavailable_days_are_skipped():
    for status in ("partial", "unavailable"):
        result = build_bulletin(day_input([cand(1)], status=status), LIB)
        assert result.bulletin is None
        assert result.reason == f"signals_{status}"


def test_day_without_answers_is_skipped():
    result = build_bulletin(day_input([]), LIB)
    assert (result.bulletin, result.reason) == (None, "no_assessments")


def test_quiet_day_leaves_out_empty_sections():
    quiet = build([cand(1)], quiet=True, items=15, model_releases=0, product_launches=0)
    assert quiet.opening in [p.format(weekday="Friday") for p in LIB["openings"]["quiet"]]
    assert quiet.numbers in ("15 events recorded.", "The day recorded 15 events.")
    assert len(quiet.key_results) == 1
    assert quiet.cooperation == [] and quiet.rubric_story is None and quiet.incidents == 0
    text = render_text(quiet, LIB)
    assert "Key results" in text
    for absent in ("Cooperation with humanity", "Isolated incidents"):
        assert absent not in text


# stories and sections

def test_caps_per_section():
    stories = [cand(n, confidence=0.99 - n / 100) for n in range(1, 8)]
    stories += [cand(10 + n, world_change="limit", area="Law") for n in range(4)]
    stories += [cand(20 + n, world_change="issue", actor="ai_system") for n in range(3)]
    stories += [cand(30, world_change="issue", actor="people")]
    bulletin = build(stories)
    assert [s.title for s in bulletin.key_results] == [
        f"Story {n} changes the work" for n in range(1, 5)]
    assert len(bulletin.cooperation) == 2
    assert bulletin.rubric_name in LIB["rubrics"]
    assert bulletin.rubric_story is not None
    assert bulletin.rubric_story.title == "Story 20 changes the work"
    assert bulletin.incidents == 3
    for story in [*bulletin.key_results, *bulletin.cooperation, bulletin.rubric_story]:
        assert story.links and all(link["url"].startswith("https://") for link in story.links)


def test_model_launches_are_capped():
    stories = [cand(n, event_type="model_release", confidence=0.99 - n / 100) for n in range(1, 5)]
    stories += [cand(10, confidence=0.7)]
    bulletin = build(stories)
    titles = [s.title for s in bulletin.key_results]
    assert titles == ["Story 1 changes the work", "Story 2 changes the work",
                      "Story 10 changes the work"]


def test_below_threshold_is_not_shown():
    bulletin = build([cand(1, confidence=0.69), cand(2, world_change="none"),
                      cand(3, confidence=0.7)])
    assert [s.title for s in bulletin.key_results] == ["Story 3 changes the work"]


def test_ranking_by_confidence_then_outlets():
    stories = [cand(1, confidence=0.8), cand(2, confidence=0.9),
               cand(3, confidence=0.8, event_key="e1", outlet="Other", url="https://z.com/3")]
    bulletin = build(stories)
    assert [s.title for s in bulletin.key_results] == [
        "Story 2 changes the work", "Story 1 changes the work"]


def test_one_story_per_event_with_all_outlets():
    stories = [cand(1, confidence=0.8, event_key="same"),
               cand(2, confidence=0.95, event_key="same", outlet="Wired"),
               cand(3, confidence=0.9, event_key="same", outlet="Wired", url="https://w.com/x")]
    bulletin = build(stories)
    assert len(bulletin.key_results) == 1
    story = bulletin.key_results[0]
    assert story.title == "Story 2 changes the work"
    assert story.outlets == ["Wired", "O1"]
    assert len(story.links) == 3
    assert "(Wired, O1)" in render_text(bulletin, LIB)


def test_harm_story_is_only_counted():
    harmful = [cand(1, confidence=0.99, harm=0.9),
               cand(2, confidence=0.98, harm=0.7, world_change="issue", actor="ai_system"),
               cand(3, confidence=0.97, harm=0.8, world_change="limit"),
               cand(4, confidence=0.96, harm=0.95, world_change="issue", actor="people")]
    ok = cand(5, confidence=0.8)
    bulletin = build([*harmful, ok])
    assert [s.title for s in bulletin.key_results] == [ok.title]
    assert bulletin.rubric_story is None and bulletin.rubric_name is None
    assert bulletin.cooperation == [] and bulletin.incident_story is None
    assert bulletin.incidents == 4
    assert bulletin.headline == "STORY 5 CHANGES THE WORK"
    text = render_text(bulletin, LIB)
    assert "Story 1" not in text and "Story 3" not in text and "Story 4" not in text
    # one member of an event with harm turns the whole event into a counted one
    merged = build([cand(1, event_key="x"), cand(2, event_key="x", harm=0.8)])
    assert merged.key_results == [] and merged.incidents == 1
    only_harm = build([cand(1, harm=0.9)])
    assert only_harm.headline is None
    assert only_harm.reactions_used == 0


def test_incidents_are_counted_with_a_plain_line():
    bulletin = build([cand(1, world_change="issue", actor="people", confidence=0.8),
                      cand(2, world_change="issue", actor="organisation", confidence=0.9),
                      cand(3, world_change="issue", actor="ai_system"),
                      cand(4, world_change="issue", actor="ai_system", confidence=0.8)])
    assert bulletin.incidents == 3
    assert bulletin.rubric_story.title == "Story 3 changes the work"
    assert bulletin.incident_story.title == "Story 2 changes the work"
    text = render_text(bulletin, LIB)
    flat = " ".join(text.split())
    assert "Isolated incidents: 3. Among them: Story 2 changes the work (O2)" in flat


def test_none_member_does_not_drop_the_event():
    bulletin = build([cand(1, event_key="x", world_change="none", confidence=0.99),
                      cand(2, event_key="x", world_change="added", confidence=0.8)])
    assert [s.title for s in bulletin.key_results] == ["Story 2 changes the work"]


def test_issue_is_never_a_key_result():
    bulletin = build([cand(1, world_change="issue", actor="people", confidence=0.95)])
    assert bulletin.key_results == [] and bulletin.incidents == 1
    assert bulletin.rubric_story is None


def test_plain_line_is_never_an_ai_actor_issue():
    bulletin = build([cand(1, world_change="issue", actor="ai_system", confidence=0.95),
                      cand(2, world_change="issue", actor="ai_system", confidence=0.9),
                      cand(3, world_change="issue", actor="people", confidence=0.8)])
    assert bulletin.rubric_story.title == "Story 1 changes the work"
    assert bulletin.incident_story.title == "Story 3 changes the work"
    only_ai = build([cand(1, world_change="issue", actor="ai_system", confidence=0.95),
                     cand(2, world_change="issue", actor="ai_system", confidence=0.9)])
    assert only_ai.incident_story is None and only_ai.incidents == 1


# headline

def test_headline_is_the_highest_scored_shown_story():
    bulletin = build([cand(1, confidence=0.9, title="Small thing happened"),
                      cand(2, confidence=0.8, event_key="b", title="Two outlets agree"),
                      cand(3, confidence=0.8, event_key="b", outlet="X", url="https://x.com/3")])
    assert bulletin.headline == "TWO OUTLETS AGREE"
    assert bulletin.headline_cut is False


def test_long_headline_is_cut_at_a_clause_boundary():
    title = "AI makes junior patent attorneys instantly better, but seniors gain little"
    text, cut = make_headline(title)
    assert (text, cut) == ("AI MAKES JUNIOR PATENT ATTORNEYS INSTANTLY BETTER", True)
    text, cut = make_headline(
        "Open model finds Firefox bugs: it needed twelve hours and a small budget")
    assert (text, cut) == ("OPEN MODEL FINDS FIREFOX BUGS", True)
    assert make_headline("Crosby, an AI-first law firm, bids for the brand of a famed firm") is None
    assert make_headline("One two three four five six seven eight") == (
        "ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT", False)
    assert HEADLINE_MAX_WORDS == 8
    bulletin = build([cand(1, title="Open model finds Firefox bugs: it needed twelve hours")])
    assert bulletin.headline == "OPEN MODEL FINDS FIREFOX BUGS*"
    assert bulletin.headline_cut is True
    text = render_text(bulletin, LIB)
    assert text.rstrip().endswith("* The rest of the headline is in the full report.")
    assert "OPEN MODEL FINDS FIREFOX BUGS*" in text


def test_headline_without_boundary_is_skipped():
    assert make_headline("one two three four five six seven eight nine ten") is None
    long_one = cand(1, confidence=0.99, title="one two three four five six seven eight nine ten")
    short = cand(2, confidence=0.8, title="Short title here")
    assert build([long_one, short]).headline == "SHORT TITLE HERE"
    assert build([long_one]).headline is None


# reactions

def reaction_count(bulletin):
    stories = [*bulletin.key_results, *bulletin.cooperation]
    stories += [bulletin.rubric_story] if bulletin.rubric_story else []
    return [s.reaction for s in stories if s.reaction]


def test_reactions_follow_the_limits():
    full = build([cand(1), cand(2, world_change="limit", area="Law"),
                  cand(3, world_change="limit", area="Law"),
                  cand(4, world_change="issue", actor="ai_system")])
    reactions = reaction_count(full)
    assert len(reactions) == 2 == full.reactions_used
    assert full.cooperation[0].reaction in LIB["reactions"]["limit"]
    assert full.cooperation[1].reaction is None
    assert full.rubric_story.reaction in LIB["reactions"]["ai_issue"]
    assert full.key_results[0].reaction is None
    only_key = build([cand(1, area="Law"), cand(2, event_key="b", area="Faith"),
                      cand(3, area="Work", event_key="c")])
    assert only_key.key_results[1].reaction in LIB["reactions"]["by_area"]["Faith"]
    assert [only_key.key_results[0].reaction, only_key.key_results[2].reaction] == [None, None]
    assert set(LIB["reactions"]["by_area"]) == {"Faith", "Culture"}
    no_area = build([cand(1, area="Law")])
    assert reaction_count(no_area) == []
    for story in (*full.key_results, *full.cooperation):
        assert story.reaction is None or len(story.reaction.split(". ")) == 1
    assert full.reactions_used <= 3


# render

def test_render_text_matches_the_voice_layout():
    bulletin = build([cand(1, title="Crosby bids for Weil Gotshal", area="Law",
                           outlet="TechCrunch"),
                      cand(2, world_change="limit", title="OpenAI rewrites its Model Spec",
                           outlet="The Decoder", area="Governance"),
                      cand(3, world_change="issue", actor="ai_system", outlet="The Decoder",
                           title="Open model builds attacks on Firefox on its own")], items=83)
    text = render_text(bulletin, LIB)
    lines = text.splitlines()
    assert lines[0] == "THE DAILY INFERENCE"
    assert lines[1] == "Bulletin of the AI World Administration · Day 1430 · Oct 30"
    assert "• Law: Crosby bids for Weil Gotshal (TechCrunch)" in text
    assert "Key results" in lines and "Cooperation with humanity" in lines
    assert bulletin.rubric_name in lines
    assert "• OpenAI rewrites its Model Spec (The Decoder)." in text
    assert lines[-1] == "Full report (83) →"
    assert lines[-2] in LIB["closings"]
    assert max(len(line) for line in lines) <= 60
    assert bulletin.full_report_url == "/daily?date=2026-10-30"
    assert bulletin.as_dict()["day_number"] == 1430
    json.dumps(bulletin.as_dict())


# the core does no I/O

def test_core_has_no_io_imports():
    for module in (builder_module, phrases_module):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add((node.module or "").split(".")[0])
        assert not names & {"sqlalchemy", "httpx", "requests", "socket", "sqlite3"}


# loader and switch

def test_outlet_name_drops_feed_label():
    for name, expected in (
        ("TechCrunch (main feed)", "TechCrunch"),
        ("Machine Learnings (newsletter/feed)", "Machine Learnings"),
        ("TechCrunch (RSS)", "TechCrunch"),
        ("Machine Learnings (NEWSLETTER)", "Machine Learnings"),
        ("Machine Intelligence Research Institute (MIRI)",
         "Machine Intelligence Research Institute (MIRI)"),
        ("Simon Willison's Weblog", "Simon Willison's Weblog"),
        ("www.bbc.com", "bbc.com"),
        ("WWW.bbc.com", "bbc.com"),
        ("bbc.com", "bbc.com"),
        ("(main feed)", ""),
        ("", ""),
    ):
        assert outlet_name(name) == expected


@pytest.fixture
def maker():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def answer(world_change="changed", confidence=0.9, area="Work", actor="organisation", harm=0.0):
    return WorldChange(world_change, confidence, area, 0.8, actor, 0.8, harm)


def seed_day(maker, *, status="ready", quiet=False, items=83, history=(),
             source_name="TechCrunch (main feed)"):
    with maker() as session:
        session.add(Source(source_key="s", name=source_name, type="rss", url="https://t.com"))
        session.flush()
        urls = []
        for index in range(3):
            url = f"https://t.com/{index}"
            session.add(Article(title=f"Title {index}", url=url, url_canonical=url, source_id=1,
                                url_canonical_hash=canonical_url_hash(url)))
            urls.append(url)
        session.flush()
        repo = WorldChangeRepo(session)
        for article in session.query(Article):
            repo.save(article, answer(), version=WORLD_CHANGE_VERSION, model="m")
        NewsDigestRepo(session).save_digest(report_date=DAY, groups=[{"title": "G", "items": [
            {"title": f"Title {i}", "summary": "s", "url": u} for i, u in enumerate(urls)]}])
        payload = {"status": status, "quiet": quiet, "coverage": {"items": items},
                   "event_counts": [{"event_type": "model_release", "stories": 2},
                                    {"event_type": "product_launch", "stories": 4}],
                   "article_event_types": {urls[0]: "model_release"},
                   "top_stories": [{"links": [{"url": urls[1]}, {"url": urls[2]}]}]}
        _add_report(session, DAY, payload)
        for offset, count in enumerate(history, start=1):
            _add_report(session, DAY - timedelta(days=offset),
                        {"status": "ready", "coverage": {"items": count}})
        session.commit()


def _add_report(session, day, payload):
    session.add(DailySignalReport(
        report_date=day, methodology_version="m", extraction_version="e",
        status=payload["status"], payload_hash="h", thresholds="{}",
        payload=json.dumps(payload), coverage=json.dumps(payload["coverage"]),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC)))


def add_world(maker, state="assessed"):
    with maker() as session:
        url = "https://news.example/ai-court"
        digest = canonical_url_hash(url)
        session.add(WorldCandidate(
            url_canonical_hash=digest, url=url, title="Court rules on AI evidence",
            source_domain="www.news.example", language="eng", first_seen_at=datetime.now(UTC),
            gdelt_file="20261030120000", match_kind="strong", cluster_key="court rules",
            state=state))
        session.flush()
        WorldChangeRepo(session).save(
            SimpleNamespace(url_canonical_hash=digest, id=None), answer("limit", 0.95, "Law"),
            version=WORLD_CHANGE_VERSION, model="m")
        session.commit()


@pytest.mark.parametrize(("source_name", "expected_outlet"), [
    ("TechCrunch (main feed)", "TechCrunch"),
    ("(main feed)", "t.com"),
    ("", "t.com"),
])
def test_loader_builds_the_day_input(maker, source_name, expected_outlet):
    seed_day(maker, history=[80] * 7, source_name=source_name)
    with maker() as session:
        loaded = load_day_input(session, DAY, include_world=False)
    assert loaded is not None
    assert (loaded.status, loaded.quiet, loaded.items) == ("ready", False, 83)
    assert (loaded.model_releases, loaded.product_launches) == (2, 4)
    assert loaded.median_items == 80
    assert len(loaded.candidates) == 3
    by_title = {c.title: c for c in loaded.candidates}
    assert by_title["Title 0"].event_type == "model_release"
    assert by_title["Title 0"].outlet == expected_outlet
    assert by_title["Title 1"].event_key == by_title["Title 2"].event_key
    assert by_title["Title 0"].event_key != by_title["Title 1"].event_key
    result = build_bulletin(loaded, LIB)
    assert len(result.bulletin.key_results) == 2


def test_median_counts_only_ready_days_before_the_day(maker):
    seed_day(maker, items=83, history=[10, 10, 10, 10, 100, 100, 100])
    with maker() as session:
        assert load_day_input(session, DAY, include_world=False).median_items == 10
        for offset in range(8, 16):
            _add_report(session, DAY - timedelta(days=offset),
                        {"status": "partial" if offset % 2 else "unavailable",
                         "coverage": {"items": 1}})
        session.commit()
        assert load_day_input(session, DAY, include_world=False).median_items == 10


def test_story_key_matches_by_canonical_hash(maker):
    seed_day(maker)
    with maker() as session:
        report = session.query(DailySignalReport).filter_by(report_date=DAY).one()
        payload = json.loads(report.payload)
        payload["top_stories"] = [{"links": [
            {"url": "https://t.com/1?utm_source=x"}, {"url": "https://t.com/2?utm_source=x"}]}]
        report.payload = json.dumps(payload)
        session.commit()
        loaded = load_day_input(session, DAY, include_world=False)
    by_title = {c.title: c for c in loaded.candidates}
    assert by_title["Title 1"].event_key == by_title["Title 2"].event_key == "story:0"


def test_loader_without_history_or_signals(maker):
    seed_day(maker, history=[80] * 3)
    with maker() as session:
        assert load_day_input(session, DAY, include_world=False).median_items is None
        session.query(DailySignalReport).delete()
        loaded = load_day_input(session, DAY, include_world=False)
    assert loaded.status == "missing"
    assert build_bulletin(loaded, LIB).reason == "no_signals"
    with maker() as session:
        assert load_day_input(session, DAY + timedelta(days=5), include_world=False) is None


def test_world_candidates_only_with_the_switch(maker):
    seed_day(maker)
    add_world(maker)
    with maker() as session:
        off = load_day_input(session, DAY, include_world=False)
        on = load_day_input(session, DAY, include_world=True)
    assert all(c.origin == "digest" for c in off.candidates)
    world = [c for c in on.candidates if c.origin == "world"]
    assert len(on.candidates) == len(off.candidates) + 1
    assert [(c.title, c.outlet, c.world_change) for c in world] == [
        ("Court rules on AI evidence", "news.example", "limit")]
    assert build_bulletin(on, LIB).bulletin.cooperation[0].title == "Court rules on AI evidence"
    assert build_bulletin(off, LIB).bulletin.cooperation == []


def test_world_stream_setting_defaults_off(monkeypatch):
    monkeypatch.delenv("AINEWS_WORLD_STREAM_IN_BULLETIN", raising=False)
    assert Settings(_env_file=None).world_stream_in_bulletin is False
    monkeypatch.setenv("AINEWS_WORLD_STREAM_IN_BULLETIN", "true")
    assert Settings(_env_file=None).world_stream_in_bulletin is True


# command

@pytest.fixture
def cli(maker, monkeypatch):
    monkeypatch.setattr(cli_main, "SessionLocal", maker)
    monkeypatch.setattr(cli_main, "get_settings", lambda: Settings(_env_file=None))
    return lambda *args: CliRunner().invoke(cli_main.app, ["bulletin", "build", *args])


def test_cli_dry_run_prints_text(maker, cli):
    seed_day(maker)
    result = cli("--date", DAY.isoformat(), "--dry-run")
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("THE DAILY INFERENCE\nBulletin of the AI World Administration")
    assert "Day 1430 · Oct 30" in result.stdout
    assert "Title 0 (TechCrunch)" in result.stdout
    assert "Full report (83) →" in result.stdout


def test_cli_json_prints_the_object(maker, cli):
    seed_day(maker)
    result = cli("--date", DAY.isoformat(), "--dry-run", "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["day_number"] == 1430 and data["date"] == "2026-10-30"
    assert (data["assessed"], data["digest_articles"]) == (3, 3)
    assert [s["title"] for s in data["key_results"]] == ["Title 0", "Title 1"]


def test_cli_needs_dry_run(maker, cli):
    seed_day(maker)
    assert cli("--date", DAY.isoformat()).exit_code == 2


def test_cli_no_digest(maker, cli):
    assert cli("--date", "2026-10-01", "--dry-run").exit_code == 2
    assert cli("--date", "nonsense", "--dry-run").exit_code != 0


def test_cli_skipped_day_logs_reason(maker, cli):
    seed_day(maker, status="partial")
    result = cli("--date", DAY.isoformat(), "--dry-run")
    assert result.exit_code == 0
    assert result.stdout.strip() == ""
    assert "signals_partial" in result.output
