"""Daily AI Signals snapshot computation (plan Decisions 3 and 5). Pure and deterministic.

Feature doc: signals.md. The helpers live in signals_model, signals_stories, signals_lines,
signals_naming and signals_history; the names below are re-exported for importers.
"""
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from app.core.canonical_json import fingerprint
from app.core.daily.signals_entities import Entity, same_family, token_prefix
from app.core.daily.signals_history import LexicalHistory
from app.core.daily.signals_lines import name_key, one_liner
from app.core.daily.signals_model import (
    CONFIRMED_TYPE_ORDER,
    EARLY_TYPE_ORDER,
    EVENT_LABELS,
    ArticleObs,
    DayCoverage,
    EntityMention,
    SnapshotInput,
    Thresholds,
)
from app.core.daily.signals_naming import proper_name, same_vendor, specific_variant, unit_key
from app.core.daily.signals_payload import (
    Coverage,
    EventCount,
    Folded,
    Hidden,
    NewItem,
    Section,
    SnapshotPayload,
    Suppressed,
    TopStory,
    TrendItem,
)
from app.core.daily.signals_stories import Story, _article_order, cluster, linked_articles, links
from app.core.daily.signals_trend import TrendRow, trend_delta, trend_windows, unit_articles

__all__ = [
    "METHODOLOGY_VERSION", "ArticleObs", "DayCoverage", "EntityMention", "LexicalHistory",
    "SnapshotInput", "Thresholds", "compute_snapshot", "payload_hash",
]

METHODOLOGY_VERSION = "daily-signals-4"


def payload_hash(payload: Mapping[str, object]) -> str:
    return str(fingerprint({k: v for k, v in payload.items() if k != "generated_at"}))


def _r(value: float) -> float:
    return round(value, 3)


@dataclass
class _NewCandidate:
    """A New item with its entity key, article ids and type rank (not stored)."""
    key: str
    ids: set[int]
    type_rank: int
    item: NewItem


@dataclass
class _Spike:
    """A spike item with its unit, representative entity key and article ids (not stored)."""
    unit: str
    key: str
    ids: set[int]
    item: TrendItem


@dataclass
class _Trend:
    """A Rising or Cooling item with the delta and the window count it is ranked by."""
    unit: str
    delta: float
    count: int
    item: TrendItem


@dataclass(frozen=True)
class _Counts:
    today: int
    current_7d: int | None = None
    previous_7d: int | None = None
    expected_7d: float | None = None


type FoldTarget = TopStory | NewItem | TrendItem


class _Snapshot:  # pylint: disable=too-many-instance-attributes
    def __init__(self, data: SnapshotInput):
        self.data = data
        self.t = data.thresholds
        self.day = data.day
        self.articles = sorted(data.observations.get(data.day, ()), key=_article_order)
        self.notes: list[str] = []
        self.sections: dict[str, Section] = {}
        self.suppressed: list[Suppressed] = []
        self.hidden: list[Hidden] = []

    def complete(self, day: date) -> bool:
        cov = self.data.coverage.get(day)
        return cov is not None and cov.complete(self.t.complete_ratio)

    def entity(self, key: str) -> Entity:
        return self.data.entities[key]

    def entity_id(self, key: str) -> int:
        entity_id: int = self.data.entity_ids.get(key, 0)
        return entity_id

    # New ------------------------------------------------------------------------------------
    def new_items(self) -> tuple[list[_NewCandidate], set[str]]:
        """(shown items, entity keys of the shown items and their grouped variants); items past
        `new_max` go to `self.hidden`."""
        by_entity, quotes = self._new_mentions()
        eligible = [key for key in sorted(quotes) if self._new_eligible(key)]
        candidates = [self._new_item(key, by_entity[key], quotes[key]) for key in eligible]
        candidates.sort(key=self._new_order)
        shown, members = self._group_variants(candidates)
        keys: set[str] = set()
        for index, c in enumerate(shown):
            if index < self.t.new_max:
                keys |= members[c.key]
            else:
                self.hidden.append({"name": c.item["name"], "entity_id": c.item["entity_id"]})
        return shown[:self.t.new_max], keys

    def _new_mentions(self) -> tuple[dict[str, list[ArticleObs]], dict[str, str]]:
        """(entity key -> its articles of the day, entity key -> first novelty quote of a
        primary new mention)."""
        by_entity: dict[str, list[ArticleObs]] = defaultdict(list)
        quotes: dict[str, str] = {}
        for a in self.articles:
            for m in a.mentions:
                if a not in by_entity[m.entity_key]:
                    by_entity[m.entity_key].append(a)
                if m.role == "primary" and m.is_new and m.novelty_quote:
                    quotes.setdefault(m.entity_key, m.novelty_quote)
        return by_entity, quotes

    def _new_eligible(self, key: str) -> bool:
        e = self.entity(key)
        if e.type_group in ("person", "other") or e.needs_review or e.first_seen_day != self.day:
            return False
        if any(same_family(e, other) and other.first_seen_day < self.day
               for other in self.data.entities.values()):
            return False
        return self._new_name_ok(key, e)

    def _group_variants(self, candidates: list[_NewCandidate]
                        ) -> tuple[list[_NewCandidate], dict[str, set[str]]]:
        """(items in order with same-family candidates as `variants`, item key -> its keys)."""
        shown: list[_NewCandidate] = []
        grouped: set[str] = set()
        members: dict[str, set[str]] = {}
        for c in candidates:
            key = c.key
            if key in grouped:
                continue
            family = [o for o in candidates if o.key != key and o.key not in grouped
                      and same_family(self.entity(key), self.entity(o.key))]
            c.item["variants"] = sorted(o.item["name"] for o in family)
            grouped.update(o.key for o in family)
            members[key] = {key} | {o.key for o in family}
            shown.append(c)
        return shown, members

    def _new_name_ok(self, key: str, e: Entity) -> bool:
        """F22 name shape and F19 lexical history; refusals are kept in the payload."""
        reason, seen = None, None
        if not proper_name(e.display_name):
            reason = "generic_name"
        elif self.data.history is not None:
            seen = self.data.history.first(e, self.day)
            reason = "lexical_history" if seen is not None else None
        if reason is None:
            return True
        item: Suppressed = {"name": e.display_name, "entity_id": self.entity_id(key),
                            "reason": reason}
        if seen is not None:
            item["day"], item["match"], item["text"] = seen[0].isoformat(), seen[1], seen[2]
        self.suppressed.append(item)
        return False

    def _new_item(self, key: str, articles: list[ArticleObs], quote: str) -> _NewCandidate:
        e = self.entity(key)
        publishers = len({a.publisher for a in articles})
        older = [o for o in self.data.entities.values()
                 if o.first_seen_day < self.day and token_prefix(o, e) and specific_variant(o, e)]
        variant_of = max(older, key=lambda o: (len(o.base_tokens), o.display_name), default=None)
        level = "confirmed" if publishers >= self.t.confirmed_publishers else "early"
        order = CONFIRMED_TYPE_ORDER if level == "confirmed" else EARLY_TYPE_ORDER
        line, source = one_liner(e.display_name, quote,
                                 [a.summary for a in linked_articles(articles, self.t.links_max)],
                                 self.t.one_liner_max)
        return _NewCandidate(
            key=key, ids={a.article_id for a in articles},
            type_rank=order.index(e.entity_type) if e.entity_type in order else len(order),
            item={"entity_id": self.entity_id(key), "name": e.display_name,
                  "type": e.entity_type, "vendor": e.vendor, "level": level,
                  "variant_of": variant_of.display_name if variant_of else None, "variants": [],
                  "novelty_quote": quote, "one_liner": line, "one_liner_source": source,
                  "articles": len(articles), "publishers": publishers,
                  "links": links(articles, self.t.links_max)})

    @staticmethod
    def _new_order(c: _NewCandidate) -> tuple[int, int, int, int, str]:
        item = c.item
        if item["level"] == "confirmed":
            return 0, -item["publishers"], -item["articles"], c.type_rank, item["name"]
        return 1, c.type_rank, -item["publishers"], -item["articles"], item["name"]

    # Counts ---------------------------------------------------------------------------------
    def unit_articles(self, day: date) -> dict[str, list[ArticleObs]]:
        out: dict[str, list[ArticleObs]] = unit_articles(self.data.observations.get(day, ()))
        return out

    def representative(self, unit: str, days: Iterable[date]) -> str:
        counts: Counter[str] = Counter()
        for day in days:
            for a in self.data.observations.get(day, ()):
                counts.update({m.entity_key for m in a.mentions if unit_key(m.entity_key) == unit})
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

    def trend_item(self, unit: str, days: Iterable[date], articles: Sequence[ArticleObs],
                   counts: _Counts, trailing_mean: float | None = None) -> TrendItem | None:
        """The item of `unit`; a `trailing_mean` marks it as a spike."""
        key = self.representative(unit, days)
        e = self.entity(key)
        if e.needs_review:
            return None
        return {"entity_id": self.entity_id(key), "name": e.display_name, "type": e.entity_type,
                "vendor": e.vendor, "current_7d": counts.current_7d,
                "previous_7d": counts.previous_7d, "expected_7d": counts.expected_7d,
                "trailing_mean": trailing_mean, "spike": trailing_mean is not None,
                "today": counts.today, "publishers": len({a.publisher for a in articles}),
                "links": links(articles, self.t.links_max)}

    def spikes(self, excluded: set[str]) -> list[_Spike] | None:
        trailing = [self.day - timedelta(days=i) for i in range(1, self.t.spike_trailing_days + 1)]
        usable = [d for d in trailing if self.comparable(d) and self.complete(d)
                  and self.data.coverage[d].items >= self.t.spike_trailing_min_items]
        if len(usable) < self.t.spike_min_trailing_days:
            return None
        history = [self.unit_articles(d) for d in usable]
        out: list[_Spike] = []
        for unit, articles in sorted(self.unit_articles(self.day).items()):
            publishers = len({a.publisher for a in articles})
            if unit in excluded or len(articles) < self.t.spike_min_articles \
                    or publishers < self.t.spike_min_publishers:
                continue
            mean = sum(len(h.get(unit, ())) for h in history) / len(usable)
            if len(articles) >= self.t.spike_ratio * max(mean, self.t.spike_mean_floor):
                item = self.trend_item(unit, [self.day], articles, _Counts(today=len(articles)),
                                       trailing_mean=_r(mean))
                if item is not None:
                    out.append(_Spike(unit, self.representative(unit, [self.day]),
                                      {a.article_id for a in articles}, item))
        out.sort(key=lambda s: (-s.item["today"], s.item["name"]))
        return out

    # Spike folding (007 noise rules 3 and 4) ---------------------------------------------------
    def fold_spikes(self, spikes: list[_Spike], stories: list[Story],
                    shown: list[tuple[Story, TopStory]], new: list[_NewCandidate]
                    ) -> tuple[list[_Spike], list[Folded]]:
        """(kept spikes with a reason, folded records); the target item lists the spike name
        under `spikes`."""
        kept: list[_Spike] = []
        folded: list[Folded] = []
        for spike in spikes:
            ids, name = spike.ids, spike.item["name"]
            org = self.entity(spike.key).type_group == "org"

            def share(other: set[int], ids: set[int] = ids) -> bool:
                shared: bool = len(ids & other) >= self.t.fold_share * len(ids)
                return shared

            target = self._fold_target(spike, org=org, share=share, into=(shown, new, kept))
            if target is not None:
                kind, into, record = target
                record.setdefault("spikes", []).append(name)
                folded.append({"name": name, "into": into, "reason": kind})
                continue
            holding = [(len(ids & {m.article_id for m in s.members}), s.publishers, s.label)
                       for s in stories]
            best = min(holding, key=lambda h: (-h[0], -h[1], h[2]), default=None)
            if org and (best is None or best[0] < self.t.diffuse_story_min):
                folded.append({"name": name, "into": None, "reason": "diffuse"})
                continue
            spike.item["reason"] = best[2] if best is not None and best[0] else None
            kept.append(spike)
        return kept, folded

    def _fold_target(self, spike: _Spike, *, org: bool, share: Callable[[set[int]], bool],
                     into: tuple[list[tuple[Story, TopStory]], list[_NewCandidate], list[_Spike]]
                     ) -> tuple[str, str, FoldTarget] | None:
        """Where a spike folds: a shown story, a new item or a kept spike (`into`)."""
        shown, new, kept = into
        spike_name = spike.item["name"]
        name = name_key(spike_name)
        for story, out in shown:
            if not share({m.article_id for m in story.members}):
                continue
            if spike.unit in {unit_key(k) for k in story.entity_keys} \
                    or name in name_key(story.label) \
                    or (org and any(same_vendor(self.entity(k).vendor, spike_name)
                                    for k in story.entity_keys)):
                return "story", story.label, out
        if not org:
            return None
        for c in new:
            if share(c.ids) and same_vendor(c.item["vendor"], spike_name):
                return "new", c.item["name"], c.item
        for other in kept:
            if share(other.ids) and same_vendor(self.entity(other.key).vendor, spike_name):
                return "spike", other.item["name"], other.item
        return None

    def comparable(self, day: date) -> bool:
        cov = self.data.coverage.get(day)
        return cov is not None and cov.kind == "signals"

    def windows(self) -> tuple[list[date], list[date]] | None:
        usable: tuple[list[date], list[date]] | None = trend_windows(
            self.day, self.data.coverage, self.data.comparable_from, self.t)
        return usable

    def extracted(self, days: Iterable[date]) -> int:
        return sum(self.data.coverage[d].extracted for d in days)

    def trends(self, excluded: set[str], spikes: list[_Spike] | None, kept: list[_Spike]
               ) -> tuple[list[TrendItem], list[TrendItem], bool]:
        """Rising and cooling; `spikes` flag rising items, only `kept` spikes are listed."""
        usable = self.windows()
        if usable is None:
            return [s.item.copy() for s in kept][:self.t.rising_max], [], False
        cur_days, prev_days = usable
        spike_units = {s.unit: s for s in spikes or []}
        today = self.unit_articles(self.day)
        rising: list[_Trend] = []
        cooling: list[_Trend] = []
        for row in trend_delta(self.data.coverage, self.data.observations,
                               (cur_days, prev_days), excluded=excluded, t=self.t):
            counts = _Counts(today=len(today.get(row.unit, ())), current_7d=row.current,
                             previous_7d=row.previous, expected_7d=_r(row.expected))
            trend = self._rising_item(row, cur_days, counts, spike_units.get(row.unit))
            if trend is not None:
                rising.append(trend)
            trend = self._cooling_item(row, prev_days, counts)
            if trend is not None:
                cooling.append(trend)
        for trends in (rising, cooling):
            trends.sort(key=lambda r: (-r.delta, -r.count, r.item["name"]))
        listed = {r.unit for r in rising}
        items = [r.item for r in rising] + [s.item.copy() for s in kept if s.unit not in listed]
        return items[:self.t.rising_max], [r.item for r in cooling][:self.t.cooling_max], True

    def _rising_item(self, row: TrendRow, cur_days: list[date], counts: _Counts,
                     spike: _Spike | None) -> _Trend | None:
        if not row.rising:
            return None
        item = self.trend_item(row.unit, cur_days, row.current_articles, counts,
                               trailing_mean=spike.item["trailing_mean"] if spike else None)
        if item is None:
            return None
        if spike is not None and "reason" in spike.item:
            item["reason"] = spike.item["reason"]
        return _Trend(row.unit, row.rising_delta, row.current, item)

    def _cooling_item(self, row: TrendRow, prev_days: list[date], counts: _Counts
                      ) -> _Trend | None:
        if not row.cooling:
            return None
        item = self.trend_item(row.unit, prev_days, row.previous_articles, counts)
        return None if item is None else _Trend(row.unit, row.cooling_delta, row.previous, item)

    # Payload --------------------------------------------------------------------------------
    def build(self) -> SnapshotPayload:
        cov = self.data.coverage.get(self.day) or DayCoverage(self.day, "signals", False)
        new, new_keys = self.new_items()
        history_days = self._complete_days(lambda d, c: d < self.day)
        self.sections["new"] = self._new_section(history_days)
        stories = cluster(self.articles)
        top = self._top(stories)
        excluded = {unit_key(k) for k in new_keys}
        spikes = self.spikes(excluded)
        shown = [(s, self._story(s)) for s in top[:self.t.top_max]]
        kept, folded = self.fold_spikes(spikes or [], stories, shown, new)
        rising, cooling, usable = self.trends(excluded, spikes, kept)
        self._trend_sections(usable)
        status = self._day_status(cov)
        return {
            "report_date": self.day.isoformat(),
            "status": status,
            "methodology_version": METHODOLOGY_VERSION,
            "extraction_version": self.data.extraction_version,
            "generated_at": self.data.generated_at.isoformat(),
            "novelty_history_days": history_days,
            "comparable_complete_days": self._complete_days(
                lambda d, c: d <= self.day and c.kind == "signals"),
            "coverage": _coverage(cov),
            "notes": self.notes,
            "sections": self.sections,
            "thresholds": _thresholds(self.t),
            "quiet": cov.items < self.t.quiet_items or not top,
            "new": [c.item for c in new],
            "new_suppressed": sorted(self.suppressed, key=lambda i: (i["name"], i["entity_id"])),
            "new_hidden": self.hidden,
            "top_stories": [out for _, out in shown],
            "rising": rising,
            "spikes_folded": folded,
            "cooling": cooling,
            "event_counts": self._event_counts(stories),
            "article_event_types": {a.url: a.event_type for a in self.articles},
        }

    def _new_section(self, history_days: int) -> Section:
        if history_days < self.t.history_note_days:
            return {"state": "building", "note": f"History: {history_days} complete days."}
        return {"state": "ready", "note": None}

    def _top(self, stories: list[Story]) -> list[Story]:
        """Stories with enough publishers, best first; sets the Top stories section."""
        top = [s for s in stories if s.publishers >= self.t.top_min_publishers]
        top.sort(key=lambda s: (-s.publishers, -len(s.members), s.earliest, s.label))
        self.sections["top_stories"] = {"state": "ready", "note": None} if top else {
            "state": "empty", "note": "No story was covered by more than one publisher."}
        return top

    def _complete_days(self, counted: Callable[[date, DayCoverage], bool]) -> int:
        return sum(1 for d, c in self.data.coverage.items()
                   if counted(d, c) and c.complete(self.t.complete_ratio))

    def _trend_sections(self, usable: bool) -> None:
        self.sections["rising"] = {"state": "ready", "note": None} if usable else {
            "state": "spikes_only",
            "note": "Rising needs two weeks with at least 6 complete days each; showing spikes."}
        self.sections["cooling"] = {"state": "ready" if usable else "hidden", "note": None}
        self.sections["event_counts"] = {"state": "ready", "note": None}

    def _day_status(self, cov: DayCoverage) -> str:
        """The day status; adds the coverage notes."""
        if cov.extracted < cov.items:
            self.notes.append(f"Extracted {cov.extracted}/{cov.items} digest items.")
        status = self.status(cov)
        if status == "unavailable" and cov.published and cov.items == 0:
            self.notes = ["No digest items for this date."]
        return status

    def status(self, cov: DayCoverage) -> str:
        if not cov.published or cov.items == 0 or cov.extracted == 0:
            return "unavailable"
        if not cov.complete(self.t.complete_ratio):
            return "partial"
        if any(s["state"] not in ("ready", "empty") for s in self.sections.values()):
            return "building_history"
        return "ready"

    def _story(self, story: Story) -> TopStory:
        return {"label": story.label, "event_type": story.event_type,
                "articles": len(story.members), "publishers": story.publishers,
                "entities": [self.entity(k).display_name for k in story.entity_keys],
                "spikes": [], "links": links(story.members, self.t.links_max)}

    def _event_counts(self, stories: list[Story]) -> list[EventCount]:
        out: list[EventCount] = []
        articles = Counter(a.event_type for a in self.articles)
        for event, label in EVENT_LABELS.items():
            members = [s for s in stories if s.event_type == event]
            if not members and not articles[event]:
                continue
            members.sort(key=lambda s: (-s.publishers, -len(s.members), s.earliest, s.label))
            out.append({"event_type": event, "label": label, "stories": len(members),
                        "articles": articles[event],
                        "links": [links(s.members, 1)[0] for s in members[:self.t.links_max]]})
        return out


def _coverage(cov: DayCoverage) -> Coverage:
    return {"items": cov.items, "matched": cov.matched, "extracted": cov.extracted,
            "failed": cov.failed, "skipped": cov.skipped, "pending": cov.pending,
            "unmatched": max(0, cov.items - cov.matched)}


def _thresholds(t: Thresholds) -> dict[str, object]:
    return {k: _r(v) if isinstance(v, float) else list(v) if isinstance(v, tuple) else v
            for k, v in asdict(t).items()}


def compute_snapshot(data: SnapshotInput) -> SnapshotPayload:
    """The stored payload for one comparable published day."""
    return _Snapshot(data).build()
