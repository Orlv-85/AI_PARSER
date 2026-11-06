"""Reads the stored data of one day into the bulletin builder's input (spec 018, item 2).

The edge of src/app/core/bulletin/builder.py; behavior in src/app/core/bulletin/builder.md.
Read-only: nothing is written.
"""
import json
import re
from datetime import date, timedelta
from statistics import median
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.bulletin.builder import (
    BUSY_MIN_DAYS,
    BUSY_WINDOW_DAYS,
    READY_STATUSES,
    Candidate,
    DayInput,
)
from app.core.bulletin.world_change import WORLD_CHANGE_VERSION
from app.core.canonicalize import canonical_url_hash
from app.core.daily.enrichment import digest_title
from app.storage.bulletin_store import BulletinRepo
from app.storage.models_sql import (
    Article,
    DailySignalReport,
    Source,
    WorldChangeAssessment,
)
from app.storage.world import STATE_ASSESSED, WorldRepo, cluster_key
from app.storage.world_change import WorldChangeRepo


def outlet_name(name: str) -> str:
    name = re.sub(r"\s*\([^()]*(?:feed|newsletter|rss)[^()]*\)$", "", name,
                  flags=re.IGNORECASE)
    return re.sub(r"^www\.", "", name, flags=re.IGNORECASE)


def _event_counts(payload: dict[str, Any]) -> dict[str, int]:
    return {str(row.get("event_type")): int(row.get("stories") or 0)
            for row in payload.get("event_counts") or []}


def _story_keys(payload: dict[str, Any]) -> dict[str, str]:
    """Top story key by URL and by canonical URL hash."""
    keys: dict[str, str] = {}
    for index, story in enumerate(payload.get("top_stories") or []):
        for link in story.get("links") or []:
            url = str(link.get("url"))
            keys.setdefault(url, f"story:{index}")
            keys.setdefault(canonical_url_hash(url), f"story:{index}")
    return keys


def _median_items(session: Session, day: date) -> float | None:
    rows = session.scalars(select(DailySignalReport.coverage).where(
        DailySignalReport.status.in_(READY_STATUSES),
        DailySignalReport.report_date < day,
        DailySignalReport.report_date >= day - timedelta(days=BUSY_WINDOW_DAYS)))
    counts = [int(json.loads(text).get("items") or 0) for text in rows]
    return float(median(counts)) if len(counts) >= BUSY_MIN_DAYS else None


def _outlet(name: str, url: str) -> str:
    """The outlet shown: the source name, else the URL's host, else "source"."""
    return outlet_name(name) or outlet_name(urlparse(url).hostname or "") or "source"


def _answers(session: Session, articles: list[Article]) -> dict[str, WorldChangeAssessment]:
    hashes = [a.url_canonical_hash for a in articles]
    return {row.url_canonical_hash: row for row in session.scalars(
        select(WorldChangeAssessment).where(
            WorldChangeAssessment.url_canonical_hash.in_(hashes),
            WorldChangeAssessment.question_version == WORLD_CHANGE_VERSION))}


def _source_names(session: Session, articles: list[Article]) -> dict[int, str]:
    source_ids = {a.source_id for a in articles if a.source_id is not None}
    return {row.id: row.name for row in session.execute(
        select(Source.id, Source.name).where(Source.id.in_(source_ids)))}


def _event_key(stories: dict[str, str], article: Article) -> str:
    """Top story by URL, then by canonical hash, else the title key."""
    return (stories.get(article.url) or stories.get(article.url_canonical_hash)
            or f"title:{cluster_key(article.title)}")


def _digest_candidates(session: Session, articles: list[Article],
                       payload: dict[str, Any]) -> list[Candidate]:
    answers = _answers(session, articles)
    names = _source_names(session, articles)
    stories = _story_keys(payload)
    types = payload.get("article_event_types") or {}
    found = []
    for article in articles:
        answer = answers.get(article.url_canonical_hash)
        if answer is None:
            continue
        found.append(Candidate(
            url=article.url, title=digest_title(article.title),
            outlet=_outlet(names.get(article.source_id) or "", article.url),
            world_change=answer.world_change, confidence=answer.world_change_confidence,
            area=answer.area, actor=answer.actor, harm=answer.harm_to_people,
            event_key=_event_key(stories, article),
            event_type=str(types.get(article.url) or ""), article_id=article.id))
    return found


def _bulletin_story_keys(payload: dict[str, Any]) -> tuple[set[str], set[str]]:
    stories = [*payload["key_results"], *payload["cooperation"],
               payload["rubric_story"], payload["incident_story"]]
    stories = [story for story in stories if story is not None]
    urls = {link["url"] for story in stories for link in story["links"]}
    titles = {cluster_key(story["title"]) for story in stories}
    return urls, titles


def _yesterday_story_keys(session: Session, day: date) -> tuple[set[str], set[str]]:
    row = BulletinRepo(session).get(day - timedelta(days=1))
    if row is None or row.status != "ready":
        return set(), set()
    try:
        return _bulletin_story_keys(row.payload)
    except (AttributeError, KeyError, TypeError):
        return set(), set()


def _world_candidates(session: Session, day: date) -> list[Candidate]:
    yesterday_urls, yesterday_titles = _yesterday_story_keys(session, day)
    found = []
    for item in WorldRepo(session).candidates_in_window([STATE_ASSESSED], day):
        if item.url in yesterday_urls or cluster_key(digest_title(item.title)) in yesterday_titles:
            continue
        answer = WorldChangeRepo(session).get(item.url_canonical_hash, WORLD_CHANGE_VERSION)
        if answer is None:
            continue
        found.append(Candidate(
            url=item.url, title=digest_title(item.title),
            outlet=_outlet(item.source_domain, item.url),
            world_change=answer.world_change, confidence=answer.world_change_confidence,
            area=answer.area, actor=answer.actor, harm=answer.harm_to_people,
            event_key=f"title:{cluster_key(item.title)}", origin="world"))
    return found


def load_day_input(session: Session, day: date, *, include_world: bool) -> DayInput | None:
    """The day's builder input, or None when the day has no published digest."""
    scope = WorldChangeRepo(session).digest_articles(day)
    if scope is None:
        return None
    articles, _unmatched = scope
    report = session.scalar(select(DailySignalReport).where(DailySignalReport.report_date == day))
    payload: dict[str, Any] = json.loads(report.payload) if report else {}
    counts = _event_counts(payload)
    candidates = _digest_candidates(session, articles, payload)
    if include_world:
        candidates += _world_candidates(session, day)
    return DayInput(
        day=day, status=report.status if report else "missing",
        quiet=bool(payload.get("quiet")),
        items=int((payload.get("coverage") or {}).get("items") or len(articles)),
        model_releases=counts.get("model_release", 0),
        product_launches=counts.get("product_launch", 0),
        median_items=_median_items(session, day), candidates=tuple(candidates),
        digest_articles=len(articles))
