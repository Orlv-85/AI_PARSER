"""Bulletin builder: the Daily Inference of one day from plain data (spec 018, item 2).

Pure core: no database, no network, no model. Behavior, decisions and tests:
src/app/core/bulletin/builder.md. Rules of voice: specs/018-daily-inference/voice.md.
"""
import zlib
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

FIRST_DAY = date(2022, 11, 30)  # Day 0 (FR-006)
MIN_CONFIDENCE = 0.7  # world_change confidence needed to show a story (item 1 proposal)
HARM_MIN = 0.7  # harm_to_people probability that makes a story count-only (ER-11)
KEY_RESULTS_MAX = 4
MODEL_LAUNCHES_MAX = 2
RUBRIC_MAX = 1
COOPERATION_MAX = 2
HEADLINE_MAX_WORDS = 8
HEADLINE_MIN_WORDS = 3
BUSY_FACTOR = 1.25
BUSY_WINDOW_DAYS = 30
BUSY_MIN_DAYS = 7
READY_STATUSES = ("ready", "building_history")
CLAUSE_WORDS = frozenset({"but", "while", "because", "although"})
DASHES = frozenset({"-", "–", "—"})


@dataclass(frozen=True)
class Candidate:  # pylint: disable=too-many-instance-attributes
    """One article (or world candidate) with its world_change answers."""
    url: str
    title: str
    outlet: str
    world_change: str
    confidence: float
    area: str
    actor: str
    harm: float
    event_key: str
    event_type: str = ""
    origin: str = "digest"


@dataclass(frozen=True)
class DayInput:  # pylint: disable=too-many-instance-attributes
    day: date
    status: str
    quiet: bool
    items: int
    model_releases: int
    product_launches: int
    median_items: float | None
    candidates: tuple[Candidate, ...]
    digest_articles: int = 0


@dataclass
class Story:  # pylint: disable=too-many-instance-attributes
    title: str
    area: str
    links: list[dict[str, str]]
    outlets: list[str]
    confidence: float
    event_type: str
    origin: str
    reaction: str | None = None
    # Set by the writer (writer.md); text_origin says who wrote the text: title or model.
    headline: str | None = None
    site_note: list[str] = field(default_factory=list)
    telegram_note: list[str] = field(default_factory=list)
    gloss: str | None = None
    text_origin: str = "title"


@dataclass
class Bulletin:  # pylint: disable=too-many-instance-attributes
    day_number: int
    date: str
    masthead: str
    byline: str
    day_type: str
    headline: str | None
    headline_cut: bool
    opening: str
    numbers: str
    key_results: list[Story]
    rubric_name: str | None
    rubric_story: Story | None
    cooperation: list[Story]
    incidents: int
    incident_story: Story | None
    closing: str
    items: int
    full_report_url: str
    reactions_used: int = 0
    phrases_version: str = ""
    headline_origin: str = "title"
    writer_version: str = ""
    writer_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BuildResult:
    bulletin: Bulletin | None
    reason: str | None


@dataclass
class _Event:
    rep: Candidate
    members: list[Candidate]
    harm: bool

    @property
    def outlets(self) -> list[str]:
        names = [self.rep.outlet] + [m.outlet for m in self.members]
        return list(dict.fromkeys(names))

    @property
    def score(self) -> float:
        return self.rep.confidence * len(self.outlets)

    @property
    def model_release(self) -> bool:
        return any(m.event_type == "model_release" for m in self.members)

    def story(self) -> Story:
        urls = dict.fromkeys([self.rep.url] + [m.url for m in self.members])
        by_url = {m.url: m.outlet for m in self.members}
        return Story(
            title=self.rep.title, area=self.rep.area,
            links=[{"outlet": by_url[u], "url": u} for u in urls],
            outlets=self.outlets, confidence=self.rep.confidence,
            event_type="model_release" if self.model_release else self.rep.event_type,
            origin=self.rep.origin)


def day_number(day: date) -> int:
    return (day - FIRST_DAY).days


def make_headline(title: str) -> tuple[str, bool] | None:
    """Capitals, at most HEADLINE_MAX_WORDS words; a longer title is cut at a clause boundary
    (ER-8). Returns (text, cut) or None when there is no boundary to cut at."""
    words = title.split()
    if not words:
        return None
    if len(words) <= HEADLINE_MAX_WORDS:
        return " ".join(words).rstrip(".").upper(), False
    for end in range(HEADLINE_MAX_WORDS, HEADLINE_MIN_WORDS - 1, -1):
        if (words[end - 1][-1] in ":;" or words[end] in DASHES
                or words[end].lower() in CLAUSE_WORDS):
            return " ".join(words[:end]).rstrip(":,;.").upper(), True
    return None


def _pick(options: list[str], day: date, slot: str) -> str:
    """Variant by date; the slot offset keeps phrases of one day from moving in step."""
    return options[(day.toordinal() + zlib.crc32(slot.encode())) % len(options)]


def _events(candidates: tuple[Candidate, ...]) -> list[_Event]:
    groups: dict[str, list[Candidate]] = {}
    for item in candidates:
        groups.setdefault(item.event_key, []).append(item)
    events = []
    for members in groups.values():
        rep = max([m for m in members if m.world_change != "none"] or members,
                  key=lambda m: m.confidence)
        if rep.world_change == "none" or rep.confidence < MIN_CONFIDENCE:
            continue
        events.append(_Event(rep, members, any(m.harm >= HARM_MIN for m in members)))
    return sorted(events, key=lambda e: (-e.rep.confidence, -len(e.outlets)))


def _day_type(data: DayInput) -> str:
    if data.quiet:
        return "quiet"
    if data.median_items is not None and data.items >= data.median_items * BUSY_FACTOR:
        return "busy"
    return "ordinary"


def _numbers(data: DayInput, lib: dict[str, Any]) -> str:
    numbers = lib["numbers"]
    if data.model_releases > 0 and data.product_launches > 0:
        def unit(count: int, kind: str) -> str:
            singular, plural = numbers["units"][kind]
            return f"{count} {singular if count == 1 else plural}"
        return _pick(numbers["launches"], data.day, "launches").format(
            models=unit(data.model_releases, "model"),
            products=unit(data.product_launches, "product"))
    return _pick(numbers["items"], data.day, "items").format(items=data.items)


def _headline(shown: list[Story], marker: str) -> tuple[str | None, bool]:
    """Headline of the best scored story that has one; a cut one ends with the marker."""
    for story in sorted(shown, key=lambda s: -(s.confidence * len(s.outlets))):
        made = make_headline(story.title)
        if made:
            return made[0] + (marker if made[1] else ""), made[1]
    return None, False


def _byline(day: date, lib: dict[str, Any]) -> str:
    return f"{lib['labels']['byline']} \u00b7 Day {day_number(day)} \u00b7 {day:%b} {day.day}"


def _incidents(clean: list[_Event]) -> tuple[_Event | None, list[_Event], _Event | None]:
    """Rubric event (first AI-actor issue), the other issues (counted) and the plain-line one."""
    issues = [e for e in clean if e.rep.world_change == "issue"]
    rubric_event = next((e for e in issues if e.rep.actor == "ai_system"), None)
    others = [e for e in issues if e is not rubric_event]
    plain = next((e for e in others if e.rep.actor != "ai_system"), None)
    return rubric_event, others, plain


def _skip_reason(data: DayInput) -> str | None:
    if data.status not in READY_STATUSES:
        return "no_signals" if data.status == "missing" else f"signals_{data.status}"
    return None if data.candidates else "no_assessments"


def build_bulletin(data: DayInput, lib: dict[str, Any]) -> BuildResult:
    """The bulletin of the day, or a skipped result with the reason."""
    reason = _skip_reason(data)
    if reason:
        return BuildResult(None, reason)
    events = _events(data.candidates)
    harm = [e for e in events if e.harm]
    clean = [e for e in events if not e.harm]
    rubric_event, others, plain = _incidents(clean)
    key_stories = [e.story() for e in _key_results(clean)]
    rubric_story = rubric_event.story() if rubric_event else None
    coop_stories = [e.story() for e in clean if e.rep.world_change == "limit"][:COOPERATION_MAX]
    used = _add_reactions(key_stories, rubric_story, coop_stories, lib, data.day)
    headline, cut = _headline([*key_stories, *([rubric_story] if rubric_story else []),
                               *coop_stories], lib["cut"]["marker"])
    day_type = _day_type(data)
    return BuildResult(Bulletin(
        day_number=day_number(data.day), date=data.day.isoformat(),
        masthead=lib["labels"]["masthead"], byline=_byline(data.day, lib),
        day_type=day_type, headline=headline, headline_cut=cut,
        opening=_pick(lib["openings"][day_type], data.day, day_type).format(
            weekday=f"{data.day:%A}"),
        numbers=_numbers(data, lib), key_results=key_stories,
        rubric_name=_pick(lib["rubrics"], data.day, "rubric") if rubric_story else None,
        rubric_story=rubric_story, cooperation=coop_stories,
        incidents=len(harm) + len(others),
        incident_story=plain.story() if plain else None,
        closing=_pick(lib["closings"], data.day, "closing"), items=data.items,
        full_report_url=f"/daily?date={data.day.isoformat()}", reactions_used=used,
        phrases_version=lib["version"]), None)


def _key_results(events: list[_Event]) -> list[_Event]:
    picked: list[_Event] = []
    launches = 0
    for event in events:
        if event.rep.world_change not in ("added", "changed"):
            continue
        if event.model_release:
            if launches >= MODEL_LAUNCHES_MAX:
                continue
            launches += 1
        picked.append(event)
        if len(picked) == KEY_RESULTS_MAX:
            break
    return picked


def _add_reactions(key: list[Story], rubric: Story | None, coop: list[Story],
                   lib: dict[str, Any], day: date) -> int:
    """Rubric story, first Cooperation story, then (only if neither got one) one Key result."""
    reactions = lib["reactions"]
    used = 0
    if rubric is not None:
        rubric.reaction = _pick(reactions["ai_issue"], day, "ai_issue")
        used += 1
    if coop:
        coop[0].reaction = _pick(reactions["limit"], day, "limit")
        used += 1
    if used == 0:
        for story in key:
            options = reactions["by_area"].get(story.area)
            if options:
                story.reaction = _pick(options, day, f"area-{story.area}")
                used += 1
                break
    return used
