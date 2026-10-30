"""Daily AI Signals snapshot computation (plan Decisions 3 and 5). Pure and deterministic.

Feature doc: signals.md. The helpers live in signals_model, signals_stories, signals_lines,
signals_naming and signals_history; the names below are re-exported for importers.
"""
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
from datetime import date, timedelta
from typing import Any

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
from app.core.daily.signals_stories import Story, _article_order, cluster, linked_articles, links
from app.core.daily.signals_trend import trend_delta, trend_windows, unit_articles, window_units
from app.storage.journal_files import fingerprint

__all__ = [
    "METHODOLOGY_VERSION", "ArticleObs", "DayCoverage", "EntityMention", "LexicalHistory",
    "SnapshotInput", "Thresholds", "compute_snapshot", "payload_hash",
]

METHODOLOGY_VERSION = "daily-signals-4"


def payload_hash(payload: Mapping[str, Any]) -> str:
    return str(fingerprint({k: v for k, v in payload.items() if k != "generated_at"}))


def _r(value: float) -> float:
    return round(value, 3)


class _Snapshot:  # pylint: disable=too-many-instance-attributes
    def __init__(self, data: SnapshotInput):
        self.data = data
        self.t = data.thresholds
        self.day = data.day
        self.articles = sorted(data.observations.get(data.day, ()), key=_article_order)
        self.notes: list[str] = []
        self.sections: dict[str, dict[str, Any]] = {}
        self.suppressed: list[dict[str, Any]] = []
        self.hidden: list[dict[str, Any]] = []

    def complete(self, day: date) -> bool:
        cov = self.data.coverage.get(day)
        return cov is not None and cov.complete(self.t.complete_ratio)

    def entity(self, key: str) -> Entity:
        return self.data.entities[key]

    def entity_id(self, key: str) -> int:
        entity_id: int = self.data.entity_ids.get(key, 0)
        return entity_id

    # New ------------------------------------------------------------------------------------
    def new_items(self) -> tuple[list[dict[str, Any]], set[str]]:
        """(shown items, entity keys of the shown items and their grouped variants); items past
        `new_max` go to `self.hidden`."""
        by_entity: dict[str, list[ArticleObs]] = defaultdict(list)
        quotes: dict[str, str] = {}
        for a in self.articles:
            for m in a.mentions:
                if a not in by_entity[m.entity_key]:
                    by_entity[m.entity_key].append(a)
                if m.role == "primary" and m.is_new and m.novelty_quote:
                    quotes.setdefault(m.entity_key, m.novelty_quote)
        eligible = []
        for key in sorted(quotes):
            e = self.entity(key)
            if e.type_group in ("person", "other") or e.needs_review \
                    or e.first_seen_day != self.day:
                continue
            if any(same_family(e, other) and other.first_seen_day < self.day
                   for other in self.data.entities.values()):
                continue
            if not self._new_name_ok(key, e):
                continue
            eligible.append(key)
        candidates = [self._new_item(key, by_entity[key], quotes[key]) for key in eligible]
        candidates.sort(key=self._new_order)
        shown, members = self._group_variants(candidates)
        keys: set[str] = set()
        for index, item in enumerate(shown):
            key = item.pop("_key")
            item.pop("_type_rank")
            if index < self.t.new_max:
                keys |= members[key]
            else:
                self.hidden.append({"name": item["name"], "entity_id": item["entity_id"]})
        return shown[:self.t.new_max], keys

    def _group_variants(self, candidates: list[dict[str, Any]]
                        ) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
        """(items in order with same-family candidates as `variants`, item key -> its keys)."""
        shown: list[dict[str, Any]] = []
        grouped: set[str] = set()
        members: dict[str, set[str]] = {}
        for item in candidates:
            key = item["_key"]
            if key in grouped:
                continue
            family = [o for o in candidates if o["_key"] != key and o["_key"] not in grouped
                      and same_family(self.entity(key), self.entity(o["_key"]))]
            item["variants"] = sorted(o["name"] for o in family)
            grouped.update(o["_key"] for o in family)
            members[key] = {key} | {o["_key"] for o in family}
            shown.append(item)
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
        item: dict[str, Any] = {"name": e.display_name, "entity_id": self.entity_id(key),
                                "reason": reason}
        if seen is not None:
            item |= {"day": seen[0].isoformat(), "match": seen[1], "text": seen[2]}
        self.suppressed.append(item)
        return False

    def _new_item(self, key: str, articles: list[ArticleObs], quote: str) -> dict[str, Any]:
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
        return {"_key": key, "_ids": {a.article_id for a in articles},
                "_type_rank": order.index(e.entity_type) if e.entity_type in order else len(order),
                "entity_id": self.entity_id(key), "name": e.display_name, "type": e.entity_type,
                "vendor": e.vendor, "level": level,
                "variant_of": variant_of.display_name if variant_of else None, "variants": [],
                "novelty_quote": quote, "one_liner": line, "one_liner_source": source,
                "articles": len(articles), "publishers": publishers,
                "links": links(articles, self.t.links_max)}

    @staticmethod
    def _new_order(item: dict[str, Any]) -> tuple:
        if item["level"] == "confirmed":
            return 0, -item["publishers"], -item["articles"], item["_type_rank"], item["name"]
        return 1, item["_type_rank"], -item["publishers"], -item["articles"], item["name"]

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
                   **fields: Any) -> dict[str, Any] | None:
        key = self.representative(unit, days)
        e = self.entity(key)
        if e.needs_review:
            return None
        return {"entity_id": self.entity_id(key), "name": e.display_name, "type": e.entity_type,
                "vendor": e.vendor, "current_7d": None, "previous_7d": None, "expected_7d": None,
                "trailing_mean": None, "spike": False, **fields,
                "links": links(articles, self.t.links_max)}

    def spikes(self, excluded: set[str]) -> list[dict[str, Any]] | None:
        trailing = [self.day - timedelta(days=i) for i in range(1, self.t.spike_trailing_days + 1)]
        usable = [d for d in trailing if self.comparable(d) and self.complete(d)
                  and self.data.coverage[d].items >= self.t.spike_trailing_min_items]
        if len(usable) < self.t.spike_min_trailing_days:
            return None
        history = [self.unit_articles(d) for d in usable]
        out = []
        for unit, articles in sorted(self.unit_articles(self.day).items()):
            publishers = len({a.publisher for a in articles})
            if unit in excluded or len(articles) < self.t.spike_min_articles \
                    or publishers < self.t.spike_min_publishers:
                continue
            mean = sum(len(h.get(unit, ())) for h in history) / len(usable)
            if len(articles) >= self.t.spike_ratio * max(mean, self.t.spike_mean_floor):
                item = self.trend_item(unit, [self.day], articles, today=len(articles),
                                       trailing_mean=_r(mean), spike=True, publishers=publishers)
                if item is not None:
                    item["_unit"] = unit
                    item["_key"] = self.representative(unit, [self.day])
                    item["_ids"] = {a.article_id for a in articles}
                    out.append(item)
        out.sort(key=lambda i: (-i["today"], i["name"]))
        return out

    # Spike folding (007 noise rules 3 and 4) ---------------------------------------------------
    def fold_spikes(self, spikes: list[dict[str, Any]], stories: list[Story],
                    shown: list[tuple[Story, dict[str, Any]]], new: list[dict[str, Any]]
                    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """(kept spikes with a reason, folded records); the target item lists the spike name
        under `spikes`."""
        kept: list[dict[str, Any]] = []
        folded: list[dict[str, Any]] = []
        for spike in spikes:
            ids = spike["_ids"]
            org = self.entity(spike["_key"]).type_group == "org"

            def share(other: set[int], ids: set[int] = ids) -> bool:
                shared: bool = len(ids & other) >= self.t.fold_share * len(ids)
                return shared

            target = self._fold_target(spike, org=org, share=share, shown=shown, new=new,
                                       kept=kept)
            if target is not None:
                kind, into, record = target
                record.setdefault("spikes", []).append(spike["name"])
                folded.append({"name": spike["name"], "into": into, "reason": kind})
                continue
            holding = [(len(ids & {m.article_id for m in s.members}), s.publishers, s.label)
                       for s in stories]
            best = min(holding, key=lambda h: (-h[0], -h[1], h[2]), default=None)
            if org and (best is None or best[0] < self.t.diffuse_story_min):
                folded.append({"name": spike["name"], "into": None, "reason": "diffuse"})
                continue
            spike["reason"] = best[2] if best is not None and best[0] else None
            kept.append(spike)
        return kept, folded

    def _fold_target(self, spike: dict[str, Any], *, org: bool, share,
                     shown: list[tuple[Story, dict[str, Any]]], new: list[dict[str, Any]],
                     kept: list[dict[str, Any]]):
        name = name_key(spike["name"])
        for story, out in shown:
            if not share({m.article_id for m in story.members}):
                continue
            if spike["_unit"] in {unit_key(k) for k in story.entity_keys} \
                    or name in name_key(story.label) \
                    or (org and any(same_vendor(self.entity(k).vendor, spike["name"])
                                    for k in story.entity_keys)):
                return "story", story.label, out
        if not org:
            return None
        for item in new:
            if share(item["_ids"]) and same_vendor(item["vendor"], spike["name"]):
                return "new", item["name"], item
        for other in kept:
            if share(other["_ids"]) and same_vendor(self.entity(other["_key"]).vendor,
                                                    spike["name"]):
                return "spike", other["name"], other
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

    def trends(self, excluded: set[str], spikes: list[dict[str, Any]] | None,
               kept: list[dict[str, Any]]):
        """Rising and cooling; `spikes` flag rising items, only `kept` spikes are listed."""
        usable = self.windows()
        spike_units = {s["_unit"]: s for s in spikes or []}
        if usable is None:
            rising = [dict(s) for s in kept][:self.t.rising_max]
            return rising, [], False
        cur_days, prev_days = usable
        today = self.unit_articles(self.day)
        rising, cooling = [], []
        for row in trend_delta(self.data.coverage, cur_days, prev_days,
                               cur_units=window_units(self.data.observations, cur_days),
                               prev_units=window_units(self.data.observations, prev_days),
                               excluded=excluded, t=self.t):
            counts = {"current_7d": row.current, "previous_7d": row.previous,
                      "expected_7d": _r(row.expected), "today": len(today.get(row.unit, ()))}
            if row.rising:
                publishers = len({a.publisher for a in row.current_articles})
                spike = spike_units.get(row.unit)
                item = self.trend_item(row.unit, cur_days, row.current_articles, **counts,
                                       publishers=publishers, spike=spike is not None,
                                       trailing_mean=spike["trailing_mean"] if spike else None)
                if item is not None and spike is not None and "reason" in spike:
                    item["reason"] = spike["reason"]
                if item is not None:
                    item["_unit"] = row.unit
                    item["_delta"] = row.rising_delta
                    rising.append(item)
            if row.cooling:
                item = self.trend_item(row.unit, prev_days, row.previous_articles, **counts,
                                       publishers=len({a.publisher
                                                       for a in row.previous_articles}))
                if item is not None:
                    item["_delta"] = row.cooling_delta
                    cooling.append(item)
        rising.sort(key=lambda i: (-i["_delta"], -i["current_7d"], i["name"]))
        cooling.sort(key=lambda i: (-i["_delta"], -i["previous_7d"], i["name"]))
        listed = {i["_unit"] for i in rising}
        rising += [dict(s) for s in kept if s["_unit"] not in listed]
        for item in rising + cooling:
            item.pop("_delta", None)
        return rising[:self.t.rising_max], cooling[:self.t.cooling_max], True

    # Payload --------------------------------------------------------------------------------
    def build(self) -> dict[str, Any]:
        cov = self.data.coverage.get(self.day) or DayCoverage(self.day, "signals", False)
        new, new_keys = self.new_items()
        history_days = sum(1 for d, c in self.data.coverage.items()
                           if d < self.day and c.complete(self.t.complete_ratio))
        self.sections["new"] = {"state": "ready", "note": None}
        if history_days < self.t.history_note_days:
            self.sections["new"] = {"state": "building",
                                    "note": f"History: {history_days} complete days."}
        stories = cluster(self.articles)
        top = [s for s in stories if s.publishers >= self.t.top_min_publishers]
        top.sort(key=lambda s: (-s.publishers, -len(s.members), s.earliest, s.label))
        self.sections["top_stories"] = {"state": "ready", "note": None} if top else {
            "state": "empty", "note": "No story was covered by more than one publisher."}
        excluded = {unit_key(k) for k in new_keys}
        spikes = self.spikes(excluded)
        shown = [(s, self._story(s)) for s in top[:self.t.top_max]]
        kept, folded = self.fold_spikes(spikes or [], stories, shown, new)
        rising, cooling, usable = self.trends(excluded, spikes, kept)
        self.sections["rising"] = {"state": "ready", "note": None} if usable else {
            "state": "spikes_only",
            "note": "Rising needs two weeks with at least 6 complete days each; showing spikes."}
        self.sections["cooling"] = {"state": "ready" if usable else "hidden", "note": None}
        self.sections["event_counts"] = {"state": "ready", "note": None}
        for item in rising + new:
            for key in ("_unit", "_key", "_ids"):
                item.pop(key, None)
        if cov.extracted < cov.items:
            self.notes.append(f"Extracted {cov.extracted}/{cov.items} digest items.")
        status = self.status(cov)
        if status == "unavailable" and cov.published and cov.items == 0:
            self.notes = ["No digest items for this date."]
        comparable_complete = sum(1 for d, c in self.data.coverage.items()
                                  if d <= self.day and c.kind == "signals"
                                  and c.complete(self.t.complete_ratio))
        return {
            "report_date": self.day.isoformat(),
            "status": status,
            "methodology_version": METHODOLOGY_VERSION,
            "extraction_version": self.data.extraction_version,
            "generated_at": self.data.generated_at.isoformat(),
            "novelty_history_days": history_days,
            "comparable_complete_days": comparable_complete,
            "coverage": {"items": cov.items, "matched": cov.matched, "extracted": cov.extracted,
                         "failed": cov.failed, "skipped": cov.skipped, "pending": cov.pending,
                         "unmatched": max(0, cov.items - cov.matched)},
            "notes": self.notes,
            "sections": self.sections,
            "thresholds": {k: _r(v) if isinstance(v, float) else
                           list(v) if isinstance(v, tuple) else v
                           for k, v in asdict(self.t).items()},
            "quiet": cov.items < self.t.quiet_items or not top,
            "new": new,
            "new_suppressed": sorted(self.suppressed, key=lambda i: (i["name"], i["entity_id"])),
            "new_hidden": self.hidden,
            "top_stories": [out for _, out in shown],
            "rising": rising,
            "spikes_folded": folded,
            "cooling": cooling,
            "event_counts": self._event_counts(stories),
            "article_event_types": {a.url: a.event_type for a in self.articles},
        }

    def status(self, cov: DayCoverage) -> str:
        if not cov.published or cov.items == 0 or cov.extracted == 0:
            return "unavailable"
        if not cov.complete(self.t.complete_ratio):
            return "partial"
        if any(s["state"] not in ("ready", "empty") for s in self.sections.values()):
            return "building_history"
        return "ready"

    def _story(self, story: Story) -> dict[str, Any]:
        return {"label": story.label, "event_type": story.event_type,
                "articles": len(story.members), "publishers": story.publishers,
                "entities": [self.entity(k).display_name for k in story.entity_keys],
                "spikes": [], "links": links(story.members, self.t.links_max)}

    def _event_counts(self, stories: list[Story]) -> list[dict[str, Any]]:
        out = []
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


def compute_snapshot(data: SnapshotInput) -> dict[str, Any]:
    """The stored payload for one comparable published day."""
    return _Snapshot(data).build()
