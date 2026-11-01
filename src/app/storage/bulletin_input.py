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


def _digest_candidates(session: Session, articles: list[Article],
                       payload: dict[str, Any]) -> list[Candidate]:
    hashes = [a.url_canonical_hash for a in articles]
    answers = {row.url_canonical_hash: row for row in session.scalars(
        select(WorldChangeAssessment).where(
            WorldChangeAssessment.url_canonical_hash.in_(hashes),
            WorldChangeAssessment.question_version == WORLD_CHANGE_VERSION))}
    source_ids = {a.source_id for a in articles if a.source_id is not None}
    names = {row.id: row.name for row in session.execute(
        select(Source.id, Source.name).where(Source.id.in_(source_ids)))}
    stories = _story_keys(payload)
    types = payload.get("article_event_types") or {}
    found = []
    for article in articles:
        answer = answers.get(article.url_canonical_hash)
        if answer is None:
            continue
        outlet = outlet_name(names.get(article.source_id) or "")
        outlet = outlet or outlet_name(urlparse(article.url).hostname or "") or "source"
        found.append(Candidate(
            url=article.url, title=article.title, outlet=outlet,
            world_change=answer.world_change, confidence=answer.world_change_confidence,
            area=answer.area, actor=answer.actor, harm=answer.harm_to_people,
            event_key=stories.get(article.url)
            or stories.get(article.url_canonical_hash) or f"title:{cluster_key(article.title)}",
            event_type=str(types.get(article.url) or "")))
    return found


def _world_candidates(session: Session, day: date) -> list[Candidate]:
    found = []
    for item in WorldRepo(session).candidates_in_window([STATE_ASSESSED], day):
        answer = WorldChangeRepo(session).get(item.url_canonical_hash, WORLD_CHANGE_VERSION)
        if answer is None:
            continue
        outlet = outlet_name(item.source_domain)
        outlet = outlet or outlet_name(urlparse(item.url).hostname or "") or "source"
        found.append(Candidate(
            url=item.url, title=item.title, outlet=outlet,
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
