"""World stream Jev screen and assessment (spec 018, item 5, step W5).

Behavior in core/world/world.md. Step A asks `ai_relevant` on the title of one candidate per
cluster; step B asks the four FR-001 questions for the top ranked candidates that have text.
Lives outside core/world/ because it imports storage.
"""
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from logging import Logger
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.bulletin.world_change import (
    WORLD_CHANGE_VERSION,
    WorldChangeAssessor,
    open_assessor,
)
from app.core.world.screen import (
    MAX_ATTEMPTS,
    SCREEN_QUESTIONS,
    SCREEN_THRESHOLD,
    WORLD_JEV_MAX_USD_PER_DAY,
    WORLD_JOURNAL_VERSION,
    WORLD_SCREEN_VERSION,
    WORLD_TOP_N,
    parse_screen,
    priority,
    screen_state,
)
from app.storage.models_sql import WorldCandidate
from app.storage.world import (
    STATE_ASSESSED,
    STATE_FAILED,
    STATE_NEW,
    STATE_SCREENED_IN,
    STATE_SCREENED_OUT,
    STATE_TEXT_READY,
    WorldRepo,
)
from app.storage.world_change import WorldChangeRepo

STEP_SCREEN = "screen"
STEP_ASSESS = "assess"
CAP_REASON = "cumulative_budget_limit"
RUN_LIMIT_REASON = "run_limit"
# Where a failed candidate goes back to, by the step named in `last_error`.
RETURN_STATE = {STEP_SCREEN: STATE_NEW, STEP_ASSESS: STATE_TEXT_READY}
_REP_ORDER = {STATE_ASSESSED: 0, STATE_TEXT_READY: 1, STATE_SCREENED_IN: 2}

TextSource = Callable[[WorldCandidate], str | None]


def no_text(_candidate: WorldCandidate) -> str | None:
    """W5 text source: there is no text store yet; W6 replaces it."""
    return None


@dataclass(frozen=True)
class WorldItem:
    """What `WorldChangeAssessor` and `WorldChangeRepo` read from a candidate with text."""
    url_canonical_hash: str
    title: str
    content: str
    id: int | None = None
    summary: str = ""


@dataclass
class RankedCluster:
    rep: WorldCandidate
    priority: float
    outlets: int


def utc_today() -> date:
    return datetime.now(UTC).date()


def open_world_assessor(settings: Any, logger: Logger,
                        today: date) -> AbstractContextManager[WorldChangeAssessor]:
    """Assessor on the world's journal of the real UTC day `today` with the fixed daily cap.

    One file per real day, whatever `--date` or `--max-usd` a run has; not the digest's journal.
    """
    manager: AbstractContextManager[WorldChangeAssessor] = open_assessor(
        settings, logger, today, WORLD_JEV_MAX_USD_PER_DAY,
        root=Path("data/world") / today.isoformat(), version=WORLD_JOURNAL_VERSION,
        usage_event="world_screen_usage", file_name=f"journal-{WORLD_JOURNAL_VERSION}.sqlite3")
    return manager


def _key(item: WorldCandidate) -> str:
    return item.cluster_key or f"hash:{item.url_canonical_hash}"


def _group(candidates: Iterable[WorldCandidate]) -> list[list[WorldCandidate]]:
    groups: dict[str, list[WorldCandidate]] = {}
    for item in candidates:
        groups.setdefault(_key(item), []).append(item)
    return list(groups.values())


def rank_clusters(candidates: Iterable[WorldCandidate]) -> list[RankedCluster]:
    """Clusters by priority (confidence x distinct outlets); assessed clusters first."""
    ranked = []
    for members in _group(candidates):
        rep = min(members, key=lambda m: (_REP_ORDER[m.state], m.first_seen_at, m.id))
        outlets = len({m.source_domain for m in members})
        ranked.append(RankedCluster(rep, priority(rep.screen_confidence or 0.0, outlets), outlets))
    ranked.sort(key=lambda r: (r.rep.state != STATE_ASSESSED, -r.priority,
                               r.rep.first_seen_at, r.rep.id))
    return ranked


def _step_of(candidate: WorldCandidate) -> str:
    return (candidate.last_error or "").split(":", 1)[0]


def _retryable(repo: WorldRepo, target: date) -> list[WorldCandidate]:
    return [c for c in repo.candidates_in_window([STATE_FAILED], target)
            if c.attempts < MAX_ATTEMPTS and _step_of(c) in RETURN_STATE]


def _jev_usage(assessor: WorldChangeAssessor | None) -> tuple[dict[str, int], float]:
    journal = assessor.payment_journal if assessor is not None else None
    if journal is None:
        return {}, 0.0
    jev = journal.report()["providers"]["jev"]
    return dict(jev["tokens"]), float(jev["usage_priced_usd"])


def _delta(after: dict[str, int], before: dict[str, int]) -> dict[str, int]:
    return {k: v - before.get(k, 0) for k, v in after.items() if v != before.get(k, 0)}


def _halted(assessor: WorldChangeAssessor, limit_usd: float | None) -> bool:
    """True when the run must send nothing more: a journal stop or the run limit is reached."""
    journal = assessor.payment_journal
    if (not assessor.stopped and limit_usd is not None and journal is not None
            and journal.committed_usd() >= limit_usd):
        assessor.stopped = RUN_LIMIT_REASON
    return bool(assessor.stopped)


def _known_clusters(repo: WorldRepo, target: date) -> dict[str, tuple[str, float]]:
    """Cluster key to (state, confidence) of its oldest member that already has a screen answer."""
    known: dict[str, tuple[str, float]] = {}
    for item in repo.candidates_in_window(
            [STATE_SCREENED_IN, STATE_SCREENED_OUT, STATE_TEXT_READY, STATE_ASSESSED],
            target):
        if item.screen_confidence is not None:
            state = STATE_SCREENED_OUT if item.state == STATE_SCREENED_OUT else STATE_SCREENED_IN
            known.setdefault(_key(item), (state, item.screen_confidence))
    return known


def _follow_known(repo: WorldRepo, pending: list[WorldCandidate],
                  known: dict[str, tuple[str, float]],
                  summary: dict[str, Any]) -> list[WorldCandidate]:
    """Late outlets take the answer of their screened cluster; returns the candidates left."""
    rest = []
    for item in pending:
        if _key(item) not in known:
            rest.append(item)
            continue
        state, confidence = known[_key(item)]
        repo.transition(item, state, screen_confidence=confidence)
        summary["screened"] += 1
        summary["in" if state == STATE_SCREENED_IN else "out"] += 1
    repo.session.commit()
    return rest


def _screen(repo: WorldRepo, assessor: WorldChangeAssessor, pending: list[WorldCandidate],
            threshold: float, summary: dict[str, Any], *, limit_usd: float | None) -> None:
    clusters = _group(pending)
    for index, members in enumerate(clusters):
        if _halted(assessor, limit_usd):
            summary["not_attempted"] += sum(len(m) for m in clusters[index:])
            return
        rep = members[0]
        body = {"model": assessor.model, "state": screen_state(rep),
                "questions": SCREEN_QUESTIONS}
        probability = assessor.ask(body, parse_screen, "world_screen")
        if probability is None and assessor.stopped:
            summary["not_attempted"] += len(members)
            continue
        summary["requests"] += 1
        if probability is None:
            repo.transition(rep, STATE_FAILED, error=f"{STEP_SCREEN}: jev_failed")
            summary["failed"] += 1
            summary["not_attempted"] += len(members) - 1
        else:
            state = STATE_SCREENED_IN if probability >= threshold else STATE_SCREENED_OUT
            for member in members:
                repo.transition(member, state, screen_confidence=probability)
            summary["screened"] += len(members)
            summary["in" if state == STATE_SCREENED_IN else "out"] += len(members)
        repo.session.commit()


def _assess(repo: WorldRepo, assessor: WorldChangeAssessor, top: list[RankedCluster],
            texts: TextSource, summary: dict[str, Any], *, limit_usd: float | None) -> None:
    saver = WorldChangeRepo(repo.session)
    for item in top:
        rep = item.rep
        repo.set_priority(rep, item.priority)
        if rep.state == STATE_SCREENED_IN:
            summary["awaiting_text"] += 1
        elif rep.state != STATE_TEXT_READY:
            continue
        elif _halted(assessor, limit_usd):
            summary["not_attempted"] += 1
        elif not (text := texts(rep)):
            summary["skipped_no_text"] += 1
        else:
            summary["asked"] += 1
            thing = WorldItem(rep.url_canonical_hash, rep.title, text)
            answer = assessor.assess(thing)
            if answer is None and assessor.stopped:
                summary["not_attempted"] += 1
            elif answer is None:
                repo.transition(rep, STATE_FAILED, error=f"{STEP_ASSESS}: jev_failed")
                summary["failed"] += 1
            else:
                saver.save(thing, answer, version=WORLD_CHANGE_VERSION, model=assessor.model)
                repo.transition(rep, STATE_ASSESSED)
                summary["assessed"] += 1
        repo.session.commit()


def _new_summary(target: date, dry_run: bool) -> dict[str, Any]:
    return {
        "date": target.isoformat(), "dry_run": dry_run,
        "question_versions": {"screen": WORLD_SCREEN_VERSION, "assess": WORLD_CHANGE_VERSION},
        "screened": 0, "in": 0, "out": 0, "requests": 0, "asked": 0, "assessed": 0,
        "skipped_no_text": 0, "awaiting_text": 0, "failed": 0, "not_attempted": 0,
        "cost_usd": 0.0, "tokens": {"screen": {}, "assess": {}}, "note": None}


def _dry_run(repo: WorldRepo, target: date, top_n: int, summary: dict[str, Any]) -> dict[str, Any]:
    known = _known_clusters(repo, target)
    new = repo.candidates_in_window([STATE_NEW], target)
    late = [item for item in new if _key(item) in known]
    clusters = _group([item for item in new if _key(item) not in known])
    top = rank_clusters(repo.candidates_in_window(
        [STATE_SCREENED_IN, STATE_TEXT_READY, STATE_ASSESSED], target))[:top_n]
    summary["would_screen"] = len(clusters)
    summary["would_follow"] = len(late) + sum(len(m) - 1 for m in clusters)
    summary["would_assess"] = sum(1 for r in top if r.rep.state == STATE_TEXT_READY)
    summary["awaiting_text"] = sum(1 for r in top if r.rep.state == STATE_SCREENED_IN)
    summary["retryable_failed"] = len(_retryable(repo, target))
    return summary


def run_screen(  # pylint: disable=too-many-arguments
    session: Session, assessor: WorldChangeAssessor | None, target: date, *,
    texts: TextSource = no_text, top_n: int = WORLD_TOP_N,
    threshold: float = SCREEN_THRESHOLD, dry_run: bool = False, limit_usd: float | None = None,
) -> dict[str, Any]:
    """Step A for the pending candidates of the window, then step B for the top ranked ones."""
    repo = WorldRepo(session)
    summary = _new_summary(target, dry_run)
    if dry_run:
        return _dry_run(repo, target, top_n, summary)
    if assessor is None:
        raise ValueError("assessor required")
    for item in _retryable(repo, target):
        repo.transition(item, RETURN_STATE[_step_of(item)])
    session.commit()
    start = _jev_usage(assessor)
    pending = _follow_known(repo, repo.candidates_in_window([STATE_NEW], target),
                            _known_clusters(repo, target), summary)
    _screen(repo, assessor, pending, threshold, summary, limit_usd=limit_usd)
    middle = _jev_usage(assessor)
    top = rank_clusters(repo.candidates_in_window(
        [STATE_SCREENED_IN, STATE_TEXT_READY, STATE_ASSESSED], target))[:top_n]
    _assess(repo, assessor, top, texts, summary, limit_usd=limit_usd)
    end = _jev_usage(assessor)
    summary["tokens"] = {"screen": _delta(middle[0], start[0]),
                         "assess": _delta(end[0], middle[0])}
    summary["cost_usd"] = end[1]
    if assessor.stopped in (CAP_REASON, RUN_LIMIT_REASON):
        assessor.logger.error("world_cost_cap", {"cost_usd": end[1], "date": summary["date"]})
    if not summary["asked"] and not assessor.stopped:
        summary["note"] = "step B asked nothing: no text for any top candidate"
    return summary
