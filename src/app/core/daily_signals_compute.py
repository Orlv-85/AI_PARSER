"""Daily AI Signals snapshot computation (plan Decisions 3 and 5). Pure and deterministic."""
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from app.core.daily_signals_brief import HARD_EVENTS, cut, norm
from app.core.daily_signals_entities import (
    TOKEN,
    Entity,
    clean,
    company_tokens,
    is_stopped,
    same_family,
    token_prefix,
    tokens,
    vendor_tokens,
)
from app.core.dedup import hamming_distance, simhash64
from app.storage.legacy_cleanup import fingerprint

METHODOLOGY_VERSION = "daily-signals-3"
EVENT_LABELS = {
    "model_release": "model releases", "product_launch": "product launches",
    "funding": "funding rounds", "acquisition": "acquisitions", "partnership": "partnerships",
    "infrastructure_deal": "infrastructure deals", "hardware": "hardware",
    "regulation_policy": "regulation & policy", "legal": "legal",
    "security_incident": "security incidents", "people_move": "people moves",
    "benchmark_result": "benchmark results", "research": "research",
    "opinion_analysis": "analysis", "other": "other",
}
EVENT_FAMILY = {"model_release": "launch", "product_launch": "launch"}
# Display order of New items within a level (CP1, gate finding 6).
EARLY_TYPE_ORDER = ("model", "hardware", "benchmark", "dataset", "technology", "company", "product",
                    "policy")
CONFIRMED_TYPE_ORDER = ("model", "product", "hardware", "company", "technology", "policy",
                        "benchmark", "dataset")
TITLE_STOP = frozenset("""a an the and or of to in on for with by from at as is are be its it this
that new how why what who your you we our their into over after about vs via than more can will now
just says say said could would may first using use launch launches launched releases release
released announces announced update updates""".split())
TITLE_TOKEN = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*")
# `variant of X` only for a specific earlier entity, never a bare family word (007 noise rule 2).
FAMILY_STOPWORDS = frozenset({"gpt", "claude", "gemini", "llama", "muse", "grok", "qwen", "clef",
                              "nemotron"})
# One-liners (007 plan "One-liners"): sentence split, abbreviations, launch / "is a" verbs.
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
ABBREVIATION = re.compile(r"(?:\b[A-Z]\.|\b(?:Inc|Corp|Ltd|Co|Mr|Ms|Dr|vs|St|No|U\.S|e\.g|i\.e|"
                          r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.)$")
WHAT_VERB = re.compile(r"\b(launch\w*|releas\w*|introduc\w*|announc\w*|unveil\w*|debut\w*|"
                       r"open-sourc\w*|formed|founded|(?<!-)built|"
                       r"(?:is|are) (?:an?|the|its|their) )",
                       re.IGNORECASE)
SHORT_QUOTE_WORDS = 8


@dataclass(frozen=True)
class Thresholds:  # pylint: disable=too-many-instance-attributes
    new_max: int = 8
    confirmed_publishers: int = 2
    history_note_days: int = 30
    top_max: int = 5
    top_min_publishers: int = 2
    links_max: int = 3
    complete_ratio: float = 0.9
    spike_min_articles: int = 3
    spike_min_publishers: int = 2
    spike_ratio: float = 3.0
    spike_mean_floor: float = 1 / 3
    spike_trailing_days: int = 7
    spike_min_trailing_days: int = 3
    spike_trailing_min_items: int = 10
    quiet_items: int = 20
    one_liner_max: int = 140
    fold_share: float = 0.5
    diffuse_story_min: int = 2
    chip_hard_events: tuple[str, ...] = HARD_EVENTS
    window_days: int = 7
    window_min_complete: int = 6
    rising_min_current: int = 4
    rising_min_delta: int = 3
    rising_ratio: float = 1.5
    rising_min_publishers: int = 2
    rising_max: int = 6
    cooling_min_previous: int = 5
    cooling_min_delta: int = 3
    cooling_ratio: float = 0.5
    cooling_min_publishers: int = 2
    cooling_max: int = 4


@dataclass(frozen=True)
class EntityMention:
    entity_key: str
    type_group: str
    base_key: str
    role: str
    is_new: bool = False
    novelty_quote: str | None = None


@dataclass(frozen=True)
class ArticleObs:  # pylint: disable=too-many-instance-attributes
    article_id: int
    scope_day: date
    title: str
    url: str
    publisher: str
    published_at: datetime | None
    event_type: str
    mentions: tuple[EntityMention, ...] = ()
    summary: str = ""  # the digest item summary of this day's item URL


@dataclass(frozen=True)
class DayCoverage:  # pylint: disable=too-many-instance-attributes
    day: date
    kind: str  # signals | history
    published: bool
    items: int = 0
    matched: int = 0
    extracted: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def pending(self) -> int:
        return max(0, self.matched - self.extracted - self.failed - self.skipped)

    def complete(self, ratio: float = 0.9) -> bool:
        return self.published and (self.items == 0 or self.extracted >= ratio * self.items)


@dataclass
class Story:
    members: list[ArticleObs]
    label: str = ""
    event_type: str = "other"
    entity_keys: list[str] = field(default_factory=list)

    @property
    def publishers(self) -> int:
        return len({m.publisher for m in self.members})

    @property
    def earliest(self) -> str:
        return min(_time_key(m) for m in self.members)


def _time_key(article: ArticleObs) -> str:
    return article.published_at.isoformat() if article.published_at else "9999"


def _article_order(article: ArticleObs) -> tuple[bool, str, int]:
    return article.published_at is None, _time_key(article), article.article_id


def title_tokens(title: str) -> frozenset[str]:
    words = TITLE_TOKEN.findall(unicodedata.normalize("NFKC", title).casefold())
    return frozenset(w for w in words if w not in TITLE_STOP and (len(w) > 2 or w.isdigit()))


def cluster(articles: Sequence[ArticleObs]) -> list[Story]:
    """Greedy strict-majority linkage over one day's articles (plan Decision 3)."""
    order = sorted(articles, key=_article_order)
    info = {}
    for a in order:
        primary = {(m.type_group, m.base_key): m.type_group for m in a.mentions
                   if m.role == "primary"}
        info[a.article_id] = (primary, title_tokens(a.title), simhash64(a.title),
                              EVENT_FAMILY.get(a.event_type, a.event_type))

    def edge(x: ArticleObs, y: ArticleObs) -> bool:
        px, tx, hx, fx = info[x.article_id]
        py, ty, hy, fy = info[y.article_id]
        if fx != fy:
            return False
        shared = px.keys() & py.keys()
        if any(px[k] != "org" for k in shared):
            return True
        if shared and len(tx & ty) / max(1, len(tx | ty)) >= 0.20:
            return True
        return bool(hamming_distance(hx, hy) <= 6)

    stories: list[Story] = []
    for a in order:
        best_score: tuple[float, int, int] | None = None
        best_story: Story | None = None
        for index, story in enumerate(stories):
            linked = sum(1 for m in story.members if edge(a, m))
            ratio = linked / len(story.members)
            score = (ratio, len(story.members), -index)
            if ratio > 0.5 and (best_score is None or score > best_score):
                best_score, best_story = score, story
        if best_story is None:
            stories.append(Story(members=[a]))
        else:
            best_story.members.append(a)
    for story in stories:
        _describe(story)
    return stories


def _describe(story: Story) -> None:
    members = story.members
    toks = [title_tokens(m.title) for m in members]

    def label_key(i: int) -> tuple[int, int, int]:
        overlap = sum(len(toks[i] & toks[k]) for k in range(len(members)) if k != i)
        return -overlap, len(members[i].title), members[i].article_id

    story.label = members[min(range(len(members)), key=label_key)].title
    events = Counter(m.event_type for m in members)
    story.event_type = sorted(events.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    primary = Counter(k for m in members for k in {
        x.entity_key for x in m.mentions if x.role == "primary" and x.type_group != "org"})
    story.entity_keys = sorted(k for k, n in primary.items() if n > len(members) / 2)


def linked_articles(articles: Iterable[ArticleObs], limit: int) -> list[ArticleObs]:
    """Up to `limit` articles: distinct publishers first, then earliest."""
    ordered = sorted({a.article_id: a for a in articles}.values(), key=_article_order)
    first: list[ArticleObs] = []
    rest: list[ArticleObs] = []
    seen: set[str] = set()
    for a in ordered:
        (rest if a.publisher in seen else first).append(a)
        seen.add(a.publisher)
    return (first + rest)[:limit]


def links(articles: Iterable[ArticleObs], limit: int) -> list[dict[str, str]]:
    return [{"title": a.title, "url": a.url, "publisher": a.publisher}
            for a in linked_articles(articles, limit)]


def sentences(text: str) -> list[str]:
    parts: list[str] = []
    buffer = ""
    for piece in SENTENCE_END.split(norm(text)):
        buffer = f"{buffer} {piece}".strip()
        if not ABBREVIATION.search(buffer):
            parts.append(buffer)
            buffer = ""
    if buffer:
        parts.append(buffer)
    return parts


def name_key(text: str) -> str:
    return re.sub(r"[\s.\-_]+", " ", norm(text).casefold()).strip()


def one_liner(name: str, quote: str | None, summaries: Iterable[str],
              limit: int = 140) -> tuple[str, str]:
    """(line, source) for a New item: a digest-summary sentence that names the item and says what
    it is or that it launched; a naming sentence when the novelty quote is a short fragment; else
    the novelty quote (`quote`, rendered in quotation marks). Never generated."""
    key = name_key(name)
    named = [s for text in summaries for s in sentences(text) if key in name_key(s)]
    for sentence in named:
        if WHAT_VERB.search(sentence):
            return cut(sentence, limit), "summary"
    text = norm(quote)
    if named and len(text.split()) < SHORT_QUOTE_WORDS:
        return cut(named[0], limit), "summary"
    return cut(text, limit), "quote"


def specific_variant(older: Entity, newer: Entity) -> bool:
    """`variant of` names a specific earlier entity of the same type (007 noise rule 2)."""
    if older.entity_type != newer.entity_type:
        return False
    vendor = set(vendor_tokens(newer.vendor)) | set(tokens(newer.vendor or ""))
    rest = [t for t in tokens(older.display_name) if t not in vendor]
    if not rest or " ".join(rest) in FAMILY_STOPWORDS:
        return False
    return len(rest) > 1 or any(ch.isdigit() for ch in "".join(rest))


def same_vendor(vendor: str | None, org: str) -> bool:
    parts = vendor_tokens(vendor)
    return bool(parts) and parts == vendor_tokens(org)


def payload_hash(payload: Mapping[str, Any]) -> str:
    return str(fingerprint({k: v for k, v in payload.items() if k != "generated_at"}))


def _r(value: float) -> float:
    return round(value, 3)


def unit_key(entity_key: str) -> str:
    """Counting unit: vendor-split automatic entities count together (plan Decision 2)."""
    parts = entity_key.split(":")
    return ":".join(parts[:3]) if parts[0] == "auto" else entity_key


def proper_name(name: str) -> bool:
    """F22: a New item needs a name shape: an uppercase letter or digit, or one hyphen/dot-joined
    token ("agent-engineer"). "dynamic workflows" is a description, not a name."""
    value = name.strip()
    return any(ch.isupper() or ch.isdigit() for ch in value) or \
        (" " not in value and any(ch in value for ch in "-."))


def _contains(seq: Sequence[str], sub: Sequence[str]) -> bool:
    n = len(sub)
    return any(tuple(seq[i:i + n]) == tuple(sub) for i in range(len(seq) - n + 1))


# F19 decision: a text that frames the entity as not yet released is not a "seen before" hit
# ("mentioned before" is not "released before"; GA after a preview stays New, OD1).
NOT_RELEASED = re.compile(r"\b(previews?|previewed|beta|alpha|waitlist|early access|roadmap|"
                          r"plans to|will release|will launch|coming soon|upcoming)\b",
                          re.IGNORECASE)
SNIPPET_MAX = 200


def _snippet(raw: str, word: str) -> str:
    if len(raw) <= SNIPPET_MAX:
        return raw
    start = max(0, raw.casefold().find(word) - 80)
    return raw[start:start + SNIPPET_MAX]


class LexicalHistory:
    """F19: earliest day a name occurs in published digest text (item title and summary) before D,
    the gate's lexical rule.

    A multi-token or digit-bearing name matches as a token run. A single common-word token needs
    its exact capitalization and the entity's vendor name (or its alias) as a token run in the same
    item; without a vendor it never suppresses (V02). The not-released check and the snippet use
    the raw text, parentheses included (V01). Built once per recompute; results are cached per
    entity as (day, matched words, text snippet)."""

    def __init__(self, texts: Iterable[tuple[date, str]]):
        self.rows: list[tuple[date, str, tuple[str, ...]]] = []
        self.index: dict[str, list[int]] = defaultdict(list)
        for day, raw in sorted((d, re.sub(r"\s+", " ", unicodedata.normalize("NFKC", t)).strip())
                               for d, t in texts):
            toks = tokens(raw)
            for token in set(toks):
                self.index[token].append(len(self.rows))
            self.rows.append((day, raw, toks))
        self.cache: dict[str, tuple[date, str, str] | None] = {}

    def first(self, entity: Entity, before: date) -> tuple[date, str, str] | None:
        if entity.entity_key not in self.cache:
            self.cache[entity.entity_key] = self._earliest(entity)
        found = self.cache[entity.entity_key]
        return found if found is not None and found[0] < before else None

    def _single_word_hit(self, entity: Entity, word: str, raw: str,
                         toks: tuple[str, ...]) -> bool:
        vendors = {v for v in (company_tokens(tokens(entity.vendor or "")),
                               vendor_tokens(entity.vendor)) if v}
        if not vendors or not any(_contains(toks, v) for v in vendors):
            return False
        exact = [t for t in TOKEN.findall(clean(entity.display_name)) if t.casefold() == word]
        cased = exact[0] if exact else word[:1].upper() + word[1:]
        return re.search(r"(?<!\w)" + re.escape(cased) + r"(?!\w)", raw) is not None

    def _earliest(self, entity: Entity) -> tuple[date, str, str] | None:
        parts = tokens(entity.display_name)
        candidates = {company_tokens(parts) if entity.type_group == "org" else parts,
                      entity.base_tokens}
        best: tuple[date, str, str] | None = None
        limit = date.max
        for words in sorted(c for c in candidates if c and not is_stopped(c)):
            ids = sorted(set.intersection(*(set(self.index.get(w, ())) for w in words)))
            for i in ids:
                day, raw, toks = self.rows[i]
                if day >= limit:
                    break
                if NOT_RELEASED.search(raw):
                    continue
                if len(words) > 1 or any(ch.isdigit() for ch in words[0]):
                    hit = _contains(toks, words)
                else:
                    hit = self._single_word_hit(entity, words[0], raw, toks)
                if hit:
                    best, limit = (day, " ".join(words), _snippet(raw, words[0])), day
                    break
        return best


@dataclass(frozen=True)
class SnapshotInput:  # pylint: disable=too-many-instance-attributes
    day: date
    observations: Mapping[date, Sequence[ArticleObs]]
    coverage: Mapping[date, DayCoverage]
    entities: Mapping[str, Entity]
    entity_ids: Mapping[str, int]
    extraction_version: str
    generated_at: datetime
    comparable_from: date
    thresholds: Thresholds = Thresholds()
    history: LexicalHistory | None = None


class _Snapshot:
    def __init__(self, data: SnapshotInput):
        self.data = data
        self.t = data.thresholds
        self.day = data.day
        self.articles = sorted(data.observations.get(data.day, ()), key=_article_order)
        self.notes: list[str] = []
        self.sections: dict[str, dict[str, Any]] = {}
        self.suppressed: list[dict[str, Any]] = []

    def complete(self, day: date) -> bool:
        cov = self.data.coverage.get(day)
        return cov is not None and cov.complete(self.t.complete_ratio)

    def entity(self, key: str) -> Entity:
        return self.data.entities[key]

    def entity_id(self, key: str) -> int:
        return self.data.entity_ids.get(key, 0)

    # New ------------------------------------------------------------------------------------
    def new_items(self) -> tuple[list[dict[str, Any]], set[str]]:
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
        shown: list[dict[str, Any]] = []
        grouped: set[str] = set()
        for item in candidates:
            key = item["_key"]
            if key in grouped:
                continue
            family = [o for o in candidates if o["_key"] != key and o["_key"] not in grouped
                      and same_family(self.entity(key), self.entity(o["_key"]))]
            item["variants"] = sorted(o["name"] for o in family)
            grouped.update(o["_key"] for o in family)
            shown.append(item)
        for item in shown:
            item.pop("_key")
            item.pop("_type_rank")
        return shown[:self.t.new_max], set(eligible)

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
        out: dict[str, list[ArticleObs]] = defaultdict(list)
        for a in self.data.observations.get(day, ()):
            for unit in sorted({unit_key(m.entity_key) for m in a.mentions}):
                out[unit].append(a)
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
                return len(ids & other) >= self.t.fold_share * len(ids)

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
        w = self.t.window_days
        current = [self.day - timedelta(days=i) for i in range(w)]
        previous = [self.day - timedelta(days=i) for i in range(w, 2 * w)]
        if min(previous) < self.data.comparable_from:
            return None
        cur = [d for d in current if self.complete(d)]
        prev = [d for d in previous if self.complete(d)]
        if len(cur) < self.t.window_min_complete or len(prev) < self.t.window_min_complete:
            return None
        if not self.extracted(cur) or not self.extracted(prev):
            return None
        return cur, prev

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
        ratio = self.extracted(cur_days) / self.extracted(prev_days)
        cur_units = self._window_units(cur_days)
        prev_units = self._window_units(prev_days)
        rising, cooling = [], []
        today = self.unit_articles(self.day)
        for unit in sorted(set(cur_units) | set(prev_units)):
            if unit in excluded:
                continue
            cur_a, prev_a = cur_units.get(unit, []), prev_units.get(unit, [])
            cur, prev = len(cur_a), len(prev_a)
            expected = prev * ratio
            counts = {"current_7d": cur, "previous_7d": prev, "expected_7d": _r(expected),
                      "today": len(today.get(unit, ()))}
            if cur >= self.t.rising_min_current and cur - expected >= self.t.rising_min_delta \
                    and cur >= self.t.rising_ratio * max(expected, 1) \
                    and len({a.publisher for a in cur_a}) >= self.t.rising_min_publishers:
                spike = spike_units.get(unit)
                item = self.trend_item(unit, cur_days, cur_a, **counts,
                                       publishers=len({a.publisher for a in cur_a}),
                                       spike=spike is not None,
                                       trailing_mean=spike["trailing_mean"] if spike else None)
                if item is not None and spike is not None and "reason" in spike:
                    item["reason"] = spike["reason"]
                if item is not None:
                    item["_unit"] = unit
                    item["_delta"] = cur - expected
                    rising.append(item)
            if prev >= self.t.cooling_min_previous and expected - cur >= self.t.cooling_min_delta \
                    and cur <= self.t.cooling_ratio * expected \
                    and len({a.publisher for a in prev_a}) >= self.t.cooling_min_publishers:
                item = self.trend_item(unit, prev_days, prev_a, **counts,
                                       publishers=len({a.publisher for a in prev_a}))
                if item is not None:
                    item["_delta"] = expected - cur
                    cooling.append(item)
        rising.sort(key=lambda i: (-i["_delta"], -i["current_7d"], i["name"]))
        cooling.sort(key=lambda i: (-i["_delta"], -i["previous_7d"], i["name"]))
        listed = {i["_unit"] for i in rising}
        rising += [dict(s) for s in kept if s["_unit"] not in listed]
        for item in rising + cooling:
            item.pop("_delta", None)
        return rising[:self.t.rising_max], cooling[:self.t.cooling_max], True

    def _window_units(self, days: Iterable[date]) -> dict[str, list[ArticleObs]]:
        out: dict[str, list[ArticleObs]] = defaultdict(list)
        for day in days:
            for unit, articles in self.unit_articles(day).items():
                out[unit].extend(articles)
        return out

    # Payload --------------------------------------------------------------------------------
    def build(self) -> dict[str, Any]:
        cov = self.data.coverage.get(self.day) or DayCoverage(self.day, "signals", False)
        new, eligible = self.new_items()
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
        excluded = {unit_key(k) for k in eligible}
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
