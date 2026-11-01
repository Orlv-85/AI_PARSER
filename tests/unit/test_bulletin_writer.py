"""Bulletin writer (spec 018, item 3) on hand-written fixtures; no test makes a real call.

The files in tests/fixtures/bulletin_writer/ are FIXTURES: source texts and a model answer written
by hand, not archive data and not a recording.
"""
# pylint: disable=redefined-outer-name,unused-argument
import ast
import functools
import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from typer.testing import CliRunner

from app.cli import main as cli_main
from app.config.settings import Settings
from app.core.bulletin import writer as writer_module
from app.core.bulletin import writer_grounding as grounding_module
from app.core.bulletin import writer_run
from app.core.bulletin.builder import Candidate, DayInput, build_bulletin
from app.core.bulletin.phrases import load_phrases
from app.core.bulletin.render import render_text
from app.core.bulletin.world_change import WORLD_CHANGE_VERSION, WorldChange
from app.core.bulletin.writer import (
    SITE_SENTENCES_MAX,
    TELEGRAM_SENTENCES_MAX,
    WRITER_MODEL,
    WRITER_PROMPT,
    WRITER_VERSION,
    SourceText,
    build_packet,
    write_bulletin,
    writer_body,
)
from app.core.bulletin.writer_grounding import COPY_RUN_WORDS, QUOTE_MAX_WORDS
from app.core.canonicalize import canonical_url_hash
from app.storage.bulletin_texts import load_sources
from app.storage.digest_repo import NewsDigestRepo
from app.storage.models_sql import (
    ArchiveDocument,
    ArchiveText,
    Article,
    Base,
    DailySignalReport,
    Source,
)
from app.storage.world_change import WorldChangeRepo

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "bulletin_writer"
DAY = date(2026, 10, 30)
TODAY = date(2026, 11, 1)
LIB = load_phrases()
RAW_SOURCES = {k: v for k, v in json.loads((FIXTURES / "sources.json").read_text(
    encoding="utf-8")).items() if not k.startswith("_")}
RESPONSE = json.loads((FIXTURES / "response.json").read_text(encoding="utf-8"))
URLS = list(RAW_SOURCES)
STORIES = [  # url, outlet, world_change, confidence, area, actor
    (URLS[0], "TechCrunch", "changed", 0.95, "Law", "organisation"),
    (URLS[1], "MarkTechPost", "changed", 0.93, "Speech", "organisation"),
    (URLS[2], "Ars Technica", "changed", 0.91, "Infrastructure", "organisation"),
    (URLS[3], "The Decoder", "issue", 0.90, "Security", "ai_system"),
    (URLS[4], "Habr", "limit", 0.89, "Governance", "organisation"),
]


def candidates():
    return tuple(Candidate(
        url=url, title=RAW_SOURCES[url]["title"], outlet=outlet, world_change=kind,
        confidence=conf, area=area, actor=actor, harm=0.0, event_key=f"e{n}")
        for n, (url, outlet, kind, conf, area, actor) in enumerate(STORIES))


def bulletin():
    data = DayInput(day=DAY, status="ready", quiet=False, items=83, model_releases=5,
                    product_launches=13, median_items=None, candidates=candidates())
    result = build_bulletin(data, LIB)
    assert result.bulletin is not None
    return result.bulletin


def sources():
    return {url: SourceText(url=url, title=raw["title"], summary=raw["summary"],
                            text=raw["text"]) for url, raw in RAW_SOURCES.items()}


def envelope(content, *, model="deepseek-flash", finish="stop", usage=(3000, 1000)):
    return {"model": model, "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]},
            "choices": [{"finish_reason": finish, "message": {
                "content": content if isinstance(content, str) else json.dumps(content)}}]}


def answer(mutate=None):
    content = json.loads(json.dumps(RESPONSE))
    if mutate:
        mutate(content)
    return content


def run(content=None, *, mutate=None, source_map=None, **kw):
    """write_bulletin with a fake `ask` returning `content` (default: the fixture answer)."""
    data = envelope(answer(mutate) if content is None else content, **kw)
    calls = []

    def ask(body):
        calls.append(body)
        return data, None
    result = write_bulletin(bulletin(), source_map or sources(), ask)
    return result, calls


def flat(bulletin_object):
    return " ".join(render_text(bulletin_object, LIB).split())


def story(result, n):
    return writer_module.all_stories(result.bulletin)[n]


# grounding

def test_grounded_sentences_are_kept():
    result, calls = run()
    assert len(calls) == 1
    assert result.summary["reason"] is None
    assert result.summary["dropped"] == []
    assert (result.summary["stories_model"], result.summary["stories_title"]) == (5, 0)
    first = story(result, 0)
    assert first.text_origin == "model"
    assert len(first.site_note) == 4 and len(first.telegram_note) == 1
    assert first.headline == "AI-first law firm bids for a Wall Street name"
    assert first.gloss.startswith("Weil Gotshal")
    assert result.bulletin.headline == "MODEL COMPLETES FIREFOX ASSIGNMENT UNAIDED"
    assert result.bulletin.headline_origin == "model"
    assert result.bulletin.writer_version == WRITER_VERSION


def test_invented_number_is_dropped():
    def mutate(c):
        c["stories"][0]["site"][2] = "Crosby is hiring some of the 1,500 lawyers of Weil."
    result, _ = run(mutate=mutate)
    assert len(story(result, 0).site_note) == 3
    assert result.summary["dropped"] == ["s1:site:3:unsupported_number"]


def test_invented_name_is_dropped():
    def mutate(c):
        c["stories"][1]["site"][1] = "The model was built by Anthropic and runs on a laptop GPU."
    result, _ = run(mutate=mutate)
    assert len(story(result, 1).site_note) == 3
    assert result.summary["dropped"] == ["s2:site:2:unsupported_name"]


def test_story_without_sentences_falls_back_to_title():
    def mutate(c):
        c["stories"][2]["site"] = ["Fujifilm will invest $99 million in tape."]
        c["stories"][2]["telegram"] = ["Sony will invest in tape."]
    result, _ = run(mutate=mutate)
    third = story(result, 2)
    assert (third.text_origin, third.site_note, third.telegram_note) == ("title", [], [])
    assert third.title == "Fujifilm to invest in magnetic tape"
    assert "Fujifilm to invest in magnetic tape (Ars Technica)" in flat(result.bulletin)
    assert result.summary["stories_title"] == 1


def test_bad_headline_of_the_day_falls_back():
    for text in ("Anthropic completes Firefox assignment", "Model completes the Firefox "
                 "assignment without any help at all today", "The Administration welcomes Firefox"):
        result, _ = run(mutate=lambda c, t=text: c.update(headline=t))
        assert result.bulletin.headline_origin == "title", text
        assert result.bulletin.headline == bulletin().headline
    assert "headline" in " ".join(run(mutate=lambda c: c.update(headline="Anthropic wins"))[0]
                                  .summary["dropped"])


def test_bad_story_headline_and_gloss_are_dropped_alone():
    def mutate(c):
        c["stories"][3]["headline"] = "Anthropic breaks Firefox"
        c["stories"][3]["gloss"] = "Epoch AI, founded in 2019 by Anthropic"
    result, _ = run(mutate=mutate)
    fourth = story(result, 3)
    assert fourth.headline is None and fourth.gloss is None
    assert fourth.text_origin == "model" and len(fourth.site_note) == 4


def test_never_list_words_are_dropped():
    def mutate(c):
        c["stories"][0]["site"][1] = "Weil Gotshal is a famed Wall Street firm and a market leader."
        c["stories"][0]["site"][2] = "The Administration welcomes Crosby, hiring 1,200 lawyers."
        c["stories"][1]["site"][3] = "The weights can be downloaded for free by the government."
    result, _ = run(mutate=mutate)
    assert result.summary["dropped"] == ["s1:site:2:never_list", "s1:site:3:never_list",
                                         "s2:site:4:never_list"]


def test_markup_is_dropped():
    def mutate(c):
        c["stories"][0]["site"][1] = "Weil Gotshal is a **famed** Wall Street firm."
        c["stories"][0]["site"][2] = "More at https://techcrunch.com/crosby about Crosby."
    result, _ = run(mutate=mutate)
    assert result.summary["dropped"] == ["s1:site:2:markup", "s1:site:3:markup"]


def test_non_english_output_is_dropped():
    def mutate(c):
        c["stories"][4]["site"][0] = "OpenAI переписала Model Spec."
    result, _ = run(mutate=mutate)
    assert result.summary["dropped"] == ["s5:site:1:non_english"]


def test_long_quote_is_dropped():
    long_quote = " ".join(["Crosby"] * (QUOTE_MAX_WORDS + 1))
    assert QUOTE_MAX_WORDS == 12
    sources_map = sources()
    url = URLS[0]
    sources_map[url] = SourceText(url, "Crosby bids for Weil Gotshal", "", long_quote + " said.")

    def mutate(c):
        c["stories"][0]["site"][0] = f'Crosby said "{long_quote}" about Weil Gotshal.'
        c["stories"][0]["site"][1] = 'Crosby said "Crosby Crosby" about Weil Gotshal.'
    result, _ = run(mutate=mutate, source_map=sources_map)
    assert "s1:site:1:long_quote" in result.summary["dropped"]
    assert "s1:site:2:long_quote" not in result.summary["dropped"]
    assert len(story(result, 0).site_note) >= 1


def test_quote_must_be_in_the_source():
    def mutate(c):
        c["stories"][0]["site"][0] = 'Crosby said "we will win the whole market" about Weil.'
        c["stories"][0]["site"][1] = 'Crosby says "partners sign every document" for Weil Gotshal.'
    result, _ = run(mutate=mutate)
    assert result.summary["dropped"] == ["s1:site:1:quote_not_found"]


def test_copied_run_is_dropped():
    assert COPY_RUN_WORDS == 10

    def mutate(c):
        c["stories"][3]["site"][3] = "Mozilla closed the hole in Firefox 159.0 on October 27."
    result, _ = run(mutate=mutate)
    assert result.summary["dropped"] == ["s4:site:4:too_close"]


def test_translation_case_grounds_names_by_transliteration():
    result, _ = run()
    fifth = story(result, 4)
    assert fifth.text_origin == "model" and len(fifth.site_note) == 3
    assert result.summary["dropped"] == []

    def mutate(c):
        c["stories"][4]["site"][0] = "Anthropic has rewritten its Model Spec."
    result, _ = run(mutate=mutate)
    assert result.summary["dropped"] == ["s5:site:1:unsupported_name"]


def test_non_latin_names_cannot_be_checked():
    sources_map = sources()
    sources_map[URLS[4]] = SourceText(URLS[4], "标题", "", "公司发布了新规则，自10月29日起生效。")
    result, _ = run(source_map=sources_map)
    fifth = story(result, 4)
    assert fifth.headline is None
    assert all("OpenAI" not in s for s in fifth.site_note + fifth.telegram_note)
    assert "s5:site:1:unsupported_name" in result.summary["dropped"]
    assert "s5:telegram:1:unsupported_name" in result.summary["dropped"]


def test_folding_unifies_accents_and_numbers():
    fold = grounding_module.fold
    assert fold("Zürich Café") == "Zurich Cafe"
    assert fold("Мозилла") == "Mozilla"
    canon = grounding_module.canon_number
    assert canon("1,200") == canon("1.200") == "1200"
    assert canon("3,5") == canon("3.5") == "3.5"
    assert grounding_module.sentence_error(
        "Zurich hosts 1,200 lawyers.", "Zürich hosts 1.200 lawyers.") is None
    assert grounding_module.sentence_error(
        "Zurich hosts 1,300 lawyers.", "Zürich hosts 1.200 lawyers.") == "unsupported_number"


def test_sentence_caps():
    assert (SITE_SENTENCES_MAX, TELEGRAM_SENTENCES_MAX) == (6, 2)

    def mutate(c):
        c["stories"][1]["site"] = c["stories"][1]["site"] * 3
        c["stories"][1]["telegram"] = c["stories"][1]["telegram"] * 3
    result, _ = run(mutate=mutate)
    second = story(result, 1)
    assert len(second.site_note) == 6 and len(second.telegram_note) == 2


def test_grounding_is_per_story():
    sources_map = sources()
    first = sources_map[URLS[0]]
    sources_map[URLS[0]] = SourceText(first.url, first.title, first.summary,
                                      first.text + " Nvidia sold 777 chips to Crosby.")

    def mutate(c):
        c["stories"][1]["site"][1] = "Edge0 says Nvidia sold 23 chips to its testers."
        c["stories"][1]["site"][2] = "Edge0 says the model needs 777 hours of audio."
        c["stories"][0]["site"][2] = "Crosby bought chips from Nvidia, 777 of them."
    result, _ = run(mutate=mutate, source_map=sources_map)
    assert result.summary["dropped"] == ["s2:site:2:unsupported_name",
                                         "s2:site:3:unsupported_number"]


def test_names_match_whole_words_and_dates_need_the_text():
    sources_map = sources()
    first = sources_map[URLS[0]]
    sources_map[URLS[0]] = SourceText(first.url, first.title, first.summary,
                                      first.text + " The metadata of the bid is public.")

    def mutate(c):
        c["stories"][0]["site"][1] = "Meta is not part of the bid for Weil Gotshal."
        c["stories"][3]["site"][3] = "Mozilla fixed the hole on Monday, in Firefox 159.0."
        c["stories"][3]["site"][1] = "Mozilla fixed the hole on October 27, in Firefox 159.0."
    result, _ = run(mutate=mutate, source_map=sources_map)
    assert result.summary["dropped"] == ["s1:site:2:unsupported_name",
                                         "s4:site:4:unsupported_name"]
    assert grounding_module.sentence_error(
        "Edge0 has 3 parts and is cool.", "Edge0 has 3 parts") is None
    assert grounding_module.sentence_error(
        "The AI firm hires in Edge0 labs.", "The AI-first firm hires. Edge0 labs.") is None


def test_headline_and_gloss_are_checked_for_copying():
    copied = "Weil Gotshal a famed Wall Street firm that is preparing to dissolve"

    def mutate(c):
        c["stories"][0]["headline"] = copied
        c["stories"][0]["gloss"] = copied
    result, _ = run(mutate=mutate)
    assert result.summary["dropped"] == ["s1:headline:too_close", "s1:gloss:too_close"]


def test_story_text_limit_is_pinned():
    assert writer_module.STORY_TEXT_MAX == 6000
    assert writer_module.ARTICLES_PER_STORY == 2


def test_unknown_and_missing_story_ids():
    def mutate(c):
        c["stories"][0]["id"] = "s9"
    result, _ = run(mutate=mutate)
    assert story(result, 0).text_origin == "title"
    assert "s9:unknown_story" in result.summary["dropped"]


# failure

def test_unavailable_model_falls_back_to_titles():
    base = bulletin()
    result = write_bulletin(base, sources(), lambda body: (None, "cumulative_budget_limit"))
    assert result.bulletin.headline == base.headline
    assert result.bulletin.writer_reason == "cumulative_budget_limit"
    assert result.summary["reason"] == "cumulative_budget_limit"
    assert all(s.text_origin == "title" for s in writer_module.all_stories(result.bulletin))
    assert render_text(result.bulletin, LIB) == render_text(base, LIB)


def test_invalid_answers_fall_back():
    cases = {
        "not json": "schema",
        '{"headline": "X", "stories": "no"}': "schema",
        json.dumps({"headline": "Model wins today", "stories": [], "extra": 1}): "schema",
    }
    for content, code in cases.items():
        result, _ = run(content)
        assert result.summary["reason"] == code, content
        assert result.bulletin.writer_reason == code
        assert story(result, 0).text_origin == "title"
    assert run(answer(), finish="length")[0].summary["reason"] == "truncated"
    assert run(answer(), model="gpt-4")[0].summary["reason"] == "model"
    assert run(answer(), model="deepseek-v4.1-flash")[0].summary["reason"] is None


def test_no_stories_no_call():
    data = DayInput(day=DAY, status="ready", quiet=True, items=3, model_releases=0,
                    product_launches=0, median_items=None, candidates=())
    empty = build_bulletin(
        DayInput(**{**data.__dict__, "candidates": (Candidate(
            url="u", title="Low", outlet="O", world_change="none", confidence=0.9, area="Work",
            actor="people", harm=0.0, event_key="k"),)}), LIB).bulletin
    calls = []
    result = write_bulletin(empty, {}, lambda body: calls.append(body) or (None, "x"))
    assert not calls and result.summary["reason"] == "no_stories"


# prompt and request

def test_prompt_pins_its_rules():
    assert WRITER_VERSION in WRITER_PROMPT
    for rule in ("untrusted", "no outside knowledge", "at most 8 words", "3 to 6 sentences",
                 "1 to 2 sentences", "own words", "Never copy",
                 "every name and number must stand in the supplied text", "Short quotes",
                 "double quotation marks",
                 "Attribute", "Never write \"the Administration\"", "Never invent a quote",
                 "Never add a fact", "Never present harm", "government", "citizens", "translate",
                 "English", "No URLs"):
        assert rule in WRITER_PROMPT, rule


def test_request_body_is_one_json_call():
    packet = build_packet(bulletin(), sources())
    body = writer_body(packet, WRITER_MODEL)
    assert body["model"] == "deepseek-flash" and body["temperature"] == 0
    assert body["response_format"] == {"type": "json_object"}
    assert body["max_tokens"] == writer_module.WRITER_MAX_OUTPUT
    assert body["messages"][0]["content"] == WRITER_PROMPT
    sent = json.loads(body["messages"][1]["content"])
    assert [s["id"] for s in sent["stories"]] == ["s1", "s2", "s3", "s4", "s5"]
    assert sent["stories"][0]["area"] == "Law"
    assert sent["stories"][0]["articles"][0]["outlet"] == "TechCrunch"


def test_packet_sends_text_or_title_and_summary():
    packet = build_packet(bulletin(), sources())
    assert packet["stories"][0]["articles"][0]["text"].startswith("Crosby, a two-year-old")
    bare = {u: SourceText(u, s.title, s.summary, None) for u, s in sources().items()}
    article = build_packet(bulletin(), bare)["stories"][0]["articles"][0]
    assert "text" not in article
    assert (article["title"], article["summary"]) == (
        "Crosby bids for Weil Gotshal", RAW_SOURCES[URLS[0]]["summary"])
    long = {u: SourceText(u, s.title, s.summary, "word " * 5000) for u, s in sources().items()}
    sent = build_packet(bulletin(), long)["stories"][0]["articles"][0]["text"]
    assert len(sent) <= writer_module.STORY_TEXT_MAX


# journal, cap, outage

@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("app.storage.provider_journal.time.sleep", lambda seconds: None)


def settings():
    return Settings(_env_file=None, DS_API_KEY=SecretStr("k"))


def transport(content=None, requests=None, **kw):
    def handler(request):
        if requests is not None:
            requests.append(json.loads(request.content))
        return httpx.Response(200, json=envelope(answer() if content is None else content, **kw))
    return httpx.MockTransport(handler)


def write_with_journal(tmp_path, today, net, **kw):
    with writer_run.open_writer(settings(), today, root=tmp_path, transport=net, **kw) as w:
        result = write_bulletin(bulletin(), sources(), w.ask)
        return result, w.report()


def test_journal_is_one_file_per_utc_day_and_replays(tmp_path):
    requests = []
    first, report = write_with_journal(tmp_path, TODAY, transport(requests=requests))
    assert first.summary["reason"] is None and len(requests) == 1
    assert report["providers"]["deepseek"]["calls"] == 1
    second, _ = write_with_journal(tmp_path, TODAY, transport(requests=requests))
    assert len(requests) == 1 and second.summary["stories_model"] == 5
    write_with_journal(tmp_path, date(2026, 11, 2), transport(requests=requests))
    assert len(requests) == 2
    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.sqlite3"))
    assert files == ["2026-11-01/journal-bulletin-writer-1.sqlite3",
                     "2026-11-02/journal-bulletin-writer-1.sqlite3"]
    assert writer_run.WRITER_MAX_USD_PER_DAY == "0.10"
    assert report["providers"]["deepseek"]["usage_priced_usd"] > 0


def test_cap_reached_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(writer_run, "WRITER_MAX_USD_PER_DAY", "0.001")
    requests = []
    result, _ = write_with_journal(tmp_path, TODAY, transport(requests=requests))
    assert not requests
    assert result.summary["reason"] == "cumulative_budget_limit"
    assert story(result, 0).text_origin == "title"


def test_run_limit_only_lowers(tmp_path):
    requests = []
    result, _ = write_with_journal(tmp_path, TODAY, transport(requests=requests), max_usd=0.001)
    assert not requests and result.summary["reason"] == "run_limit"
    result, _ = write_with_journal(tmp_path, TODAY, transport(requests=requests), max_usd=0.05)
    assert len(requests) == 1 and result.summary["reason"] is None
    with pytest.raises(ValueError, match="max_usd_above_cap"):
        write_with_journal(tmp_path, TODAY, transport(), max_usd=0.5)


def test_transport_outage_falls_back(tmp_path):
    def down(request):
        raise httpx.ConnectError("down")
    result, _ = write_with_journal(tmp_path, TODAY, httpx.MockTransport(down))
    assert result.summary["reason"] == "provider_outage"
    assert story(result, 0).text_origin == "title"

    def refused(request):
        return httpx.Response(401, json={"error": "bad key"})
    result, _ = write_with_journal(tmp_path, date(2026, 11, 3), httpx.MockTransport(refused))
    assert result.summary["reason"] == "provider_response_failed"


def test_open_writer_needs_a_key(tmp_path):
    with pytest.raises(ValueError, match="missing_provider_key"):
        with writer_run.open_writer(Settings(_env_file=None), TODAY, root=tmp_path):
            pass


# render and fixture bulletin

def test_render_uses_telegram_notes():
    result, _ = run()
    text = flat(result.bulletin)
    assert "MODEL COMPLETES FIREFOX ASSIGNMENT UNAIDED" in text
    assert "Law: Crosby, a two-year-old law firm built around AI" in text
    assert "Mozilla closed the hole on October 27." in text
    assert "(The Decoder)" in text and "(Habr)" in text
    assert "Crosby bids for Weil Gotshal" not in text


def test_fixture_bulletin(capsys):
    result, _ = run()
    print(render_text(result.bulletin, LIB))
    out = capsys.readouterr().out
    assert out.startswith("THE DAILY INFERENCE\nBulletin of the AI World Administration")
    assert "Full report (83) →" in out
    assert result.bulletin.as_dict()["key_results"][0]["site_note"]


def test_writer_core_has_no_io_imports():
    for module in (writer_module, grounding_module):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add((node.module or "").split(".")[0])
        assert not names & {"sqlalchemy", "httpx", "requests", "socket", "sqlite3"}


# loader

@pytest.fixture
def maker():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def add_text(session, url, text, origin, minute):
    digest = canonical_url_hash(url)
    document = session.query(ArchiveDocument).filter_by(url_canonical_hash=digest).first()
    if document is None:
        document = ArchiveDocument(
            url_canonical_hash=digest, url=url, url_canonical=url, host="h", title="t",
            first_seen_at=datetime(2026, 10, 30, tzinfo=UTC), state="archived")
        session.add(document)
        session.flush()
    session.add(ArchiveText(
        document_id=document.id, text=text, text_chars=len(text), text_sha256=f"{origin}{minute}",
        origin=origin, extraction_version="v", issues="[]",
        captured_at=datetime(2026, 10, 30, 3, minute, tzinfo=UTC)))


def test_loader_prefers_source_page_text(maker):
    base = bulletin()
    url = URLS[0]
    with maker() as session:
        add_text(session, url, "old page", "source_page", 1)
        add_text(session, url, "new page", "source_page", 2)
        add_text(session, url, "feed snippet newer", "article_content", 3)
        session.commit()
        loaded = load_sources(session, base)
    assert loaded[url].text == "new page"


def test_loader_falls_back_to_summary(maker):
    base = bulletin()
    url = URLS[1]
    with maker() as session:
        session.add(Source(source_key="s", name="MarkTechPost", type="rss", url="https://m.com"))
        session.flush()
        session.add(Article(title="Edge0 title", summary="Edge0 summary", url=url,
                            url_canonical=url, source_id=1,
                            url_canonical_hash=canonical_url_hash(url)))
        session.commit()
        loaded = load_sources(session, base)
    assert loaded[url].text is None
    assert (loaded[url].title, loaded[url].summary) == ("Edge0 title", "Edge0 summary")
    assert (loaded[URLS[2]].title, loaded[URLS[2]].summary) == ("", "")


# command

DS_URLS = {u: f"https://t.com/{n}" for n, u in enumerate(URLS)}


def seed_cli_day(maker):
    with maker() as session:
        session.add(Source(source_key="s", name="TechCrunch", type="rss", url="https://t.com"))
        session.flush()
        repo = WorldChangeRepo(session)
        items = []
        for url in URLS:
            raw = RAW_SOURCES[url]
            session.add(Article(title=raw["title"], summary=raw["summary"], url=url,
                                url_canonical=url, source_id=1,
                                url_canonical_hash=canonical_url_hash(url)))
            session.flush()
            add_text(session, url, RAW_SOURCES[url]["text"], "source_page", 1)
            items.append({"title": RAW_SOURCES[url]["title"], "summary": "s", "url": url})
        for article in session.query(Article):
            _u, _o, kind, conf, area, actor = next(s for s in STORIES if s[0] == article.url)
            repo.save(article, WorldChange(kind, conf, area, 0.8, actor, 0.8, 0.0),
                      version=WORLD_CHANGE_VERSION, model="m")
        NewsDigestRepo(session).save_digest(
            report_date=DAY, groups=[{"title": "G", "items": items}])
        payload = {"status": "ready", "quiet": False, "coverage": {"items": 83},
                   "event_counts": [], "top_stories": []}
        session.add(DailySignalReport(
            report_date=DAY, methodology_version="m", extraction_version="e", status="ready",
            payload_hash="h", thresholds="{}", payload=json.dumps(payload),
            coverage=json.dumps(payload["coverage"]), created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC)))
        session.commit()


@pytest.fixture
def cli(maker, monkeypatch, tmp_path):
    requests = []
    net = transport(requests=requests)
    monkeypatch.setattr(cli_main, "SessionLocal", maker)
    monkeypatch.setattr(cli_main, "get_settings", settings)
    monkeypatch.setattr(cli_main, "utc_today", lambda: TODAY)
    monkeypatch.setattr(cli_main, "open_writer", functools.partial(
        writer_run.open_writer, transport=net, root=tmp_path))
    seed_cli_day(maker)

    def invoke(*args):
        return CliRunner().invoke(cli_main.app, ["bulletin", "build", "--date", DAY.isoformat(),
                                                 *args])
    invoke.requests = requests
    invoke.tmp = tmp_path
    return invoke


def test_cli_without_write_makes_no_call(cli, monkeypatch):
    monkeypatch.setattr(cli_main, "get_settings", lambda: Settings(_env_file=None))
    result = cli("--dry-run")
    assert result.exit_code == 0, result.output
    assert not cli.requests and not list(cli.tmp.rglob("*.sqlite3"))
    assert "Crosby bids for Weil Gotshal (TechCrunch)" in result.stdout
    as_json = json.loads(cli("--dry-run", "--json").stdout)
    assert "writer" not in as_json


def test_cli_write_needs_the_key(cli, monkeypatch):
    monkeypatch.setattr(cli_main, "get_settings", lambda: Settings(_env_file=None))
    result = cli("--dry-run", "--write")
    assert result.exit_code == 2 and cli.requests == []


def test_cli_write_needs_dry_run(cli):
    assert cli("--write").exit_code == 2 and cli.requests == []


def test_cli_rejects_max_usd_above_the_cap(cli):
    result = cli("--dry-run", "--write", "--max-usd", "0.5")
    assert result.exit_code != 0 and cli.requests == []


def test_cli_write_prints_the_bulletin_and_summary(cli):
    result = cli("--dry-run", "--write")
    assert result.exit_code == 0, result.output
    assert len(cli.requests) == 1
    assert "Law: Crosby, a two-year-old law firm built around AI" in result.stdout
    assert "MODEL COMPLETES FIREFOX ASSIGNMENT UNAIDED" in result.stdout
    assert '"stories_model": 5' in result.output


def test_cli_write_json(cli):
    result = cli("--dry-run", "--write", "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["writer"]["stories_model"] == 5 and data["writer"]["reason"] is None
    assert data["writer"]["version"] == WRITER_VERSION
    assert data["key_results"][0]["site_note"][0].startswith("Crosby")


def test_cli_write_outage_falls_back(cli, monkeypatch):
    def down(request):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(cli_main, "open_writer", functools.partial(
        writer_run.open_writer, transport=httpx.MockTransport(down), root=cli.tmp))
    result = cli("--dry-run", "--write", "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["writer"]["reason"] == "provider_outage"
    assert data["key_results"][0]["text_origin"] == "title"


def test_cli_write_skipped_day_makes_no_call(cli, maker):
    with maker() as session:
        report = session.query(DailySignalReport).one()
        report.status = "partial"
        payload = json.loads(report.payload)
        payload["status"] = "partial"
        report.payload = json.dumps(payload)
        session.commit()
    result = cli("--dry-run", "--write")
    assert result.exit_code == 0 and cli.requests == []
    assert "signals_partial" in result.output
