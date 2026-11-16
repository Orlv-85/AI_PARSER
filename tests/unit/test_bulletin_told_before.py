# pylint: disable=redefined-outer-name
"""What the free repeat check (R1) left out is recorded (spec 018); in-memory database."""
import logging
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.bulletin.builder import Candidate, DayInput, ToldBefore
from app.storage.models_sql import Base, BulletinRow
from app.usecases.bulletin.daily import prepare_from_input
from app.usecases.bulletin.day_input import _split_shown

DAY = date(2026, 11, 15)
YESTERDAY = (DAY - timedelta(days=1)).isoformat()
OLDER = (DAY - timedelta(days=2)).isoformat()


def cand(n, **kw):
    base = {"url": f"https://o{n}.com/a{n}", "title": f"Story {n} changes the work",
            "outlet": f"O{n}", "world_change": "changed", "confidence": 0.9, "area": "Work",
            "actor": "organisation", "harm": 0.0, "event_key": f"e{n}"}
    return Candidate(**{**base, **kw})


def payload(*stories):
    return {"key_results": [{"title": title, "links": [{"url": url}]} for title, url in stories],
            "cooperation": [], "rubric_story": None, "incident_story": None}


@pytest.fixture
def session():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as opened:
        yield opened


def store(session, day, *stories):
    session.add(BulletinRow(day=day, status="ready", payload=payload(*stories), numbers={},
                            versions={}))
    session.commit()


def test_told_before_records_url_match(session):
    store(session, DAY - timedelta(days=1), ("Another title", "https://o1.com/a1"))
    kept, left_out, told = _split_shown(session, DAY, [cand(1), cand(2)])
    assert [c.url for c in kept] == ["https://o2.com/a2"]
    assert left_out == 1  # candidates are digest ones by default
    assert told == [ToldBefore("Story 1 changes the work", "url", YESTERDAY)]


def test_told_before_records_title_match(session):
    store(session, DAY - timedelta(days=2), ("STORY 1: changes the work!", "https://x.com/z"))
    store(session, DAY - timedelta(days=3), ("Story 1 changes the work", "https://x.com/y"))
    kept, _left_out, told = _split_shown(session, DAY, [cand(1, origin="digest"), cand(2)])
    assert [c.url for c in kept] == ["https://o2.com/a2"]
    assert told == [ToldBefore("Story 1 changes the work", "title", OLDER)]


def test_empty_title_key_does_not_match(session):
    store(session, DAY - timedelta(days=1), ("???", "https://x.com/z"))
    kept, _left_out, told = _split_shown(
        session, DAY, [cand(1, title="!!!"), cand(2, url="https://x.com/z", title="...")])
    assert [c.url for c in kept] == ["https://o1.com/a1"]
    assert told == [ToldBefore("...", "url", YESTERDAY)]


def test_numbers_list_told_before(session):
    told = (ToldBefore("Story 1 changes the work", "url", YESTERDAY),)
    data = DayInput(day=DAY, status="ready", quiet=False, items=40, model_releases=0,
                    product_launches=0, median_items=None, candidates=(cand(2, origin="digest"),),
                    digest_articles=3, digest_left_out=1, told_before=told)
    prepared = prepare_from_input(session, logging.getLogger("t"), DAY, data, write=False)
    assert prepared.numbers == {
        "assessed": 2, "digest_articles": 3, "told_before": [
            {"title": "Story 1 changes the work", "match": "url", "published_day": YESTERDAY}]}
    data = DayInput(day=DAY, status="ready", quiet=False, items=40, model_releases=0,
                    product_launches=0, median_items=None, candidates=(cand(2),))
    prepared = prepare_from_input(session, logging.getLogger("t"), DAY, data, write=False)
    assert prepared.numbers["told_before"] == []
