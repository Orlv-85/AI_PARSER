"""World stream first days report (spec 018, item 5, step W7); behavior in core/world/world.md.

Read-only: counts of the window of `world screen`, the answers of `world_change`, the cost of the
world journals and a sample of assessed stories. Lives outside core/world/ because it imports
storage.
"""
import sqlite3
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.bulletin.world_change import WORLD_CHANGE_VERSION
from app.core.world.screen import WORLD_JOURNAL_VERSION
from app.storage.models_sql import WorldCandidate, WorldChangeAssessment
from app.storage.world import (
    STATE_ASSESSED,
    STATE_FAILED,
    STATE_NEW,
    STATE_NO_TEXT,
    STATE_SCREENED_IN,
    STATE_SCREENED_OUT,
    STATE_TEXT_READY,
    WorldRepo,
)

SAMPLE_SIZE = 20
JOURNAL_ROOT = Path("data/world")
PASSED_SCREEN = (STATE_SCREENED_IN, STATE_TEXT_READY, STATE_NO_TEXT, STATE_ASSESSED)
TEXT_PREFIX = "text: "


def read_journal_cost(root: Path, day: date) -> dict[str, Any] | None:
    """Calls and dollars of the world journal of a real UTC day, or None when it has no file.

    The file is opened read-only and is never created.
    """
    path = root / day.isoformat() / f"journal-{WORLD_JOURNAL_VERSION}.sqlite3"
    if not path.is_file():
        return None
    db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        calls, committed, priced = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(committed), 0), COALESCE(SUM(actual), 0) FROM calls"
        ).fetchone()
    finally:
        db.close()
    return {"calls": calls, "committed_usd": committed / 1e6, "priced_usd": priced / 1e6}


def _assessed(session: Session, items: list[WorldCandidate]) -> list[tuple[WorldCandidate,
                                                                          WorldChangeAssessment]]:
    answers = {a.url_canonical_hash: a for a in session.scalars(
        select(WorldChangeAssessment).where(
            WorldChangeAssessment.question_version == WORLD_CHANGE_VERSION,
            WorldChangeAssessment.url_canonical_hash.in_([i.url_canonical_hash for i in items])))}
    return [(item, answers[item.url_canonical_hash]) for item in items
            if item.url_canonical_hash in answers]


def _sample_row(item: WorldCandidate, answer: WorldChangeAssessment) -> dict[str, Any]:
    return {"title": item.title, "domain": item.source_domain,
            "world_change": answer.world_change, "area": answer.area, "actor": answer.actor,
            "harm_to_people": answer.harm_to_people}


def build_report(session: Session, target: date, *,
                 journal_root: Path = JOURNAL_ROOT) -> dict[str, Any]:
    """Numbers of the window (GDELT days `target - 1` and `target`) for the first days check."""
    every = [STATE_SCREENED_IN, STATE_SCREENED_OUT, STATE_TEXT_READY, STATE_NO_TEXT,
             STATE_ASSESSED, STATE_FAILED, STATE_NEW]
    items = WorldRepo(session).candidates_in_window(every, target)
    states = Counter(item.state for item in items)
    reasons = Counter(
        (item.last_error or "")[len(TEXT_PREFIX):] for item in items
        if item.state == STATE_NO_TEXT and (item.last_error or "").startswith(TEXT_PREFIX))
    assessed = [item for item in items if item.state == STATE_ASSESSED]
    answered = _assessed(session, assessed)
    answered.sort(key=lambda pair: (-(pair[0].priority or 0.0), pair[0].id))
    next_day = target + timedelta(days=1)
    return {
        "date": target.isoformat(),
        "window": [(target - timedelta(days=1)).isoformat(), target.isoformat()],
        "candidates": len(items),
        "clusters": len({item.cluster_key or item.url_canonical_hash for item in items}),
        "states": dict(states),
        "screened_in": sum(states[state] for state in PASSED_SCREEN),
        "screened_out": states[STATE_SCREENED_OUT],
        "text_ready": states[STATE_TEXT_READY], "no_text": states[STATE_NO_TEXT],
        "no_text_reasons": dict(reasons), "failed": states[STATE_FAILED],
        "assessed": len(assessed),
        "world_change": dict(Counter(answer.world_change for _item, answer in answered)),
        "cost": {day.isoformat(): read_journal_cost(journal_root, day)
                 for day in (target, next_day)},
        "sample": [_sample_row(item, answer) for item, answer in answered[:SAMPLE_SIZE]],
    }
