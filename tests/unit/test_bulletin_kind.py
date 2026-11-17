# pylint: disable=redefined-outer-name
"""Only events are shown (spec 018, F6): the kind of the representative article."""
import logging
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.bulletin.builder import (
    MIN_CONFIDENCE,
    SHOWN_KINDS,
    Candidate,
    DayInput,
    build_bulletin,
    showable,
)
from app.core.bulletin.phrases import load_phrases
from app.core.bulletin.world_change import WORLD_CHANGE_VERSION, WorldChange
from app.core.canonicalize import canonical_url_hash
from app.storage.models_sql import Article, Base, WorldCandidate
from app.storage.world_change import WorldChangeRepo
from app.usecases.bulletin.daily import prepare_from_input
from app.usecases.bulletin.day_input import _digest_candidates, _world_candidates

DAY = date(2026, 10, 30)
LIB = load_phrases()
NOT_SHOWN = ["opinion", "forecast", "explainer", "promotion"]


def cand(n, **kw):
    base = {"url": f"https://o{n}.com/a{n}", "title": f"Story {n} changes the work",
            "outlet": f"O{n}", "world_change": "changed", "confidence": 0.9, "area": "Work",
            "actor": "organisation", "harm": 0.0, "event_key": f"e{n}"}
    return Candidate(**{**base, **kw})


def day_input(candidates):
    return DayInput(day=DAY, status="ready", quiet=False, items=10, model_releases=0,
                    product_launches=0, median_items=None, candidates=tuple(candidates))


def shown_urls(bulletin):
    stories = [*bulletin.key_results, bulletin.rubric_story, *bulletin.cooperation,
               bulletin.incident_story, *bulletin.reserve]
    return {link["url"] for story in stories if story for link in story.links}


def test_only_events_are_shown():
    assert SHOWN_KINDS == frozenset({"event"})
    candidates = [cand(1), cand(2, world_change="limit"),
                  cand(3, world_change="issue", actor="ai_system"),
                  cand(4, world_change="issue", actor="people")]
    for number, kind in enumerate(NOT_SHOWN, start=10):
        candidates.append(cand(number, kind=kind))
        candidates.append(cand(number + 10, kind=kind, world_change="limit"))
        candidates.append(cand(number + 20, kind=kind, world_change="issue", actor="ai_system"))
    bulletin = build_bulletin(day_input(candidates), LIB).bulletin
    assert bulletin is not None
    urls = shown_urls(bulletin)
    assert urls == {"https://o1.com/a1", "https://o2.com/a2", "https://o3.com/a3",
                    "https://o4.com/a4"}
    assert bulletin.incidents == 1  # only the shown people-caused issue


def test_event_member_represents_a_mixed_event():
    event = cand(1, event_key="same", confidence=0.8)
    opinion = cand(2, event_key="same", confidence=0.9, kind="opinion")
    bulletin = build_bulletin(day_input([event, opinion]), LIB).bulletin
    assert bulletin is not None and bulletin.key_results[0].title == event.title
    assert shown_urls(bulletin) == {event.url, opinion.url}
    alone = build_bulletin(day_input([cand(3, kind="opinion")]), LIB).bulletin
    assert alone is None or not shown_urls(alone)


@pytest.mark.parametrize("kind", NOT_SHOWN)
def test_showable_needs_an_event(kind):
    assert showable(cand(1))
    assert not showable(cand(1, kind=kind))
    assert not showable(cand(1, world_change="none"))
    assert not showable(cand(1, confidence=MIN_CONFIDENCE - 0.01))
    assert showable(cand(1, confidence=MIN_CONFIDENCE))


def test_numbers_count_kinds():
    candidates = [cand(1), cand(2), cand(3, kind="opinion"), cand(4, kind="promotion"),
                  cand(5, kind="opinion"), cand(6, world_change="none", kind="forecast")]
    prepared = prepare_from_input(None, logging.getLogger("t"), DAY, day_input(candidates),
                                  write=False)
    assert prepared.numbers["kinds"] == {"event": 2, "opinion": 2, "promotion": 1}
    assert prepared.numbers["assessed"] == 6


@pytest.fixture
def session():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as opened:
        yield opened


def test_loader_fills_kind_from_the_answer(session):
    url = "https://t.com/a"
    article = Article(title="Title", url=url, url_canonical=url, source_id=None,
                      url_canonical_hash=canonical_url_hash(url))
    session.add(article)
    session.add(WorldCandidate(
        url_canonical_hash=canonical_url_hash("https://w.com/b"), url="https://w.com/b",
        title="World title", source_domain="w.com", language="eng",
        first_seen_at=datetime.now(UTC), gdelt_file="20261030120000", match_kind="strong",
        cluster_key="world title", state="assessed"))
    session.flush()
    repo = WorldChangeRepo(session)
    repo.save(article, WorldChange("changed", 0.9, "Work", 0.8, "people", 0.8, 0.0,
                                   "forecast", 0.7), version=WORLD_CHANGE_VERSION, model="m")
    repo.save(SimpleNamespace(url_canonical_hash=canonical_url_hash("https://w.com/b"), id=None),
              WorldChange("limit", 0.9, "Law", 0.8, "people", 0.8, 0.0, "promotion", 0.7),
              version=WORLD_CHANGE_VERSION, model="m")
    session.commit()
    assert [c.kind for c in _digest_candidates(session, [article], {})] == ["forecast"]
    assert [c.kind for c in _world_candidates(session, DAY)] == ["promotion"]
