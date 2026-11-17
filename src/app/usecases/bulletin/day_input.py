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

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.bulletin.builder import (
    BUSY_MIN_DAYS,
    BUSY_WINDOW_DAYS,
    READY_STATUSES,
    Candidate,
    DayInput,
    ToldBefore,
)
from app.core.bulletin.repeats import REPEAT_DAYS, PublishedStory
from app.core.bulletin.world_change import WORLD_CHANGE_VERSION
from app.core.canonicalize import canonical_url_hash
from app.core.daily.titles import digest_title
from app.storage.bulletin_store import BulletinRepo
from app.storage.models_sql import (
    Article,
    BulletinRow,
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


def _source_names(session: Session, articles: list[Article]) -> dict[int | None, str]:
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
            event_type=str(types.get(article.url) or ""), article_id=article.id,
            kind=answer.kind or ""))
    return found


def _payload_stories(payload: dict[str, Any]) -> list[dict[str, Any]]:
    stories = [*payload["key_results"], *payload["cooperation"],
               payload["rubric_story"], payload["incident_story"]]
    return [story for story in stories if story is not None]


def _bulletin_story_keys(payload: dict[str, Any]) -> tuple[set[str], set[str]]:
    stories = _payload_stories(payload)
    urls = {link["url"] for story in stories for link in story["links"]}
    titles = {cluster_key(story["title"]) for story in stories}
    return urls, titles


def _recent_payloads(session: Session, day: date) -> list[tuple[date, Any]]:
    """Payloads of the ready stored bulletins of D-1 to D-REPEAT_DAYS."""
    # `bulletin build` reads before it creates the table on a fresh database.
    if not inspect(session.connection()).has_table(BulletinRow.__tablename__):
        return []
    found = []
    for back in range(1, REPEAT_DAYS + 1):
        stored = day - timedelta(days=back)
        row = BulletinRepo(session).get(stored)
        if row is not None and row.status == "ready":
            found.append((stored, row.payload))
    return found


def _recent_story_keys(session: Session, day: date) -> tuple[dict[str, str], dict[str, str]]:
    """Story URLs and title keys of the last days with the latest day (ISO) that had each.

    An unreadable day is ignored on its own; an empty title key is never stored."""
    urls: dict[str, str] = {}
    titles: dict[str, str] = {}
    for stored, payload in _recent_payloads(session, day):  # newest day first
        try:
            day_urls, day_titles = _bulletin_story_keys(payload)
        except (AttributeError, KeyError, TypeError):
            continue
        for url in day_urls:
            urls.setdefault(url, stored.isoformat())
        for key in day_titles - {""}:
            titles.setdefault(key, stored.isoformat())
    return urls, titles


def published_stories(session: Session, day: date) -> list[PublishedStory]:
    """Stories of the ready stored bulletins of D-1 to D-REPEAT_DAYS (shown text, title)."""
    found = []
    for stored, payload in _recent_payloads(session, day):
        try:
            found += [PublishedStory(stored.isoformat(),
                                     str(story.get("headline") or story["title"]),
                                     str(story["title"]))
                      for story in _payload_stories(payload)]
        except (AttributeError, KeyError, TypeError):
            continue
    return found


def _world_candidates(session: Session, day: date) -> list[Candidate]:
    found = []
    for item in WorldRepo(session).candidates_in_window([STATE_ASSESSED], day):
        answer = WorldChangeRepo(session).get(item.url_canonical_hash, WORLD_CHANGE_VERSION)
        if answer is None:
            continue
        found.append(Candidate(
            url=item.url, title=digest_title(item.title),
            outlet=_outlet(item.source_domain, item.url),
            world_change=answer.world_change, confidence=answer.world_change_confidence,
            area=answer.area, actor=answer.actor, harm=answer.harm_to_people,
            event_key=f"title:{cluster_key(item.title)}", origin="world", language=item.language,
            kind=answer.kind or ""))
    return found


def _told(candidate: Candidate, urls: dict[str, str], titles: dict[str, str]
          ) -> ToldBefore | None:
    if candidate.url in urls:
        return ToldBefore(candidate.title, "url", urls[candidate.url])
    key = cluster_key(candidate.title)
    return ToldBefore(candidate.title, "title", titles[key]) if key in titles else None


def _split_shown(session: Session, day: date, candidates: list[Candidate]
                 ) -> tuple[list[Candidate], int, list[ToldBefore]]:
    """Candidates not told in the last days, how many digest candidates were left out, and
    one record per candidate left out (candidate order)."""
    urls, titles = _recent_story_keys(session, day)
    kept: list[Candidate] = []
    told: list[ToldBefore] = []
    for candidate in candidates:
        found = _told(candidate, urls, titles)
        if found is None:
            kept.append(candidate)
        else:
            told.append(found)
    left_out = sum(1 for c in candidates if c.origin == "digest") \
        - sum(1 for c in kept if c.origin == "digest")
    return kept, left_out, told


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
    candidates, digest_left_out, told = _split_shown(session, day, candidates)
    return DayInput(
        day=day, status=report.status if report else "missing",
        quiet=bool(payload.get("quiet")),
        items=int((payload.get("coverage") or {}).get("items") or len(articles)),
        model_releases=counts.get("model_release", 0),
        product_launches=counts.get("product_launch", 0),
        median_items=_median_items(session, day), candidates=tuple(candidates),
        digest_articles=len(articles), digest_left_out=digest_left_out,
        told_before=tuple(told))

