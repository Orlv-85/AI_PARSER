"""Deterministic entity identity for Daily AI Signals (plan Decision 2).

Everything here is pure: the same evidence and overrides always give the same keys, entities and
assignments, whatever order the evidence arrived in.
"""
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

STOPLIST = frozenset({
    "ai", "a i", "artificial intelligence", "genai", "generative ai", "llm", "llms",
    "large language model", "large language models", "language model", "language models",
    "model", "models", "foundation model", "frontier model", "frontier models", "agent", "agents",
    "ai agent", "ai agents", "agentic ai", "chatbot", "chatbots", "ai chatbot", "assistant",
    "ai assistant",
    "copilot", "open source", "open weights", "open weight", "gpu", "gpus", "cpu", "tpu", "npu",
    "data center", "data centers", "datacenter", "cloud", "machine learning", "ml", "deep learning",
    "neural network", "neural networks", "transformer", "transformers", "rag",
    "retrieval augmented generation", "reinforcement learning", "rl", "fine tuning", "inference",
    "training", "api", "apis", "sdk", "mcp", "mcp server", "robotics", "robot", "robots", "startup",
    "startups", "big tech", "government", "researchers", "users", "developers", "internet", "web",
    "app", "apps", "software", "hardware", "chip", "chips", "semiconductor", "semiconductors",
    "benchmark", "benchmarks", "dataset", "datasets", "agi", "superintelligence", "reasoning",
    "multimodal", "vision", "computer vision", "nlp", "prompt", "prompts", "prompt injection",
    "jailbreak", "deepfake", "deepfakes", "automation", "workflow", "workflows", "platform",
})
COMPANY_SUFFIX = frozenset({"inc", "incorporated", "corp", "corporation", "ltd", "llc", "plc",
                            "gmbh", "co", "ai"})
VENDOR_ALIASES = {"bfl": "black forest labs", "aws": "amazon", "amazon web services": "amazon",
                  "alphabet": "google", "meta platforms": "meta"}
TYPE_GROUPS = {"model": "artifact", "product": "artifact", "hardware": "artifact",
               "technology": "artifact", "benchmark": "artifact", "dataset": "artifact",
               "company": "org", "person": "person", "policy": "policy", "other": "other"}
TYPE_ORDER = ("model", "product", "hardware", "company", "technology", "policy", "benchmark",
              "dataset", "person", "other")
PACKAGING = re.compile(r"^(\d+(\.\d+)?[bmk]|a\d+(\.\d+)?b|e\d+(\.\d+)?b|\d+e|\d+gb|fp\d+|int\d+|"
                       r"gguf|instruct|base|chat|it)$")
# Runs of letters/digits; "+" and "#" inside a token; a dot only between digits ("5.5", "v1.1").
TOKEN = re.compile(r"(?:[^\W_]|(?<=[^\W_]|[+#])[+#]|(?<=\d)\.(?=\d))+")
QUOTES = str.maketrans({"‘": "'", "’": "'", "‛": "'", "′": "'"})

Tokens = tuple[str, ...]


def clean(name: str) -> str:
    value = unicodedata.normalize("NFKC", name).translate(QUOTES)
    value = re.sub(r"\([^)]*\)", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def tokens(name: str) -> Tokens:
    value = re.sub(r"'s\b", "", clean(name).casefold())
    return tuple(TOKEN.findall(value))


def join(parts: Iterable[str]) -> str:
    out = ""
    for part in parts:
        if out and out[-1].isdigit() and part[:1].isdigit():
            out += "-"
        out += part
    return out


def company_tokens(parts: Sequence[str]) -> Tokens:
    rest = list(parts)
    while len(rest) > 1 and rest[-1] in COMPANY_SUFFIX and len("".join(rest[:-1])) >= 3:
        rest.pop()
    return tuple(rest)


def is_stopped(parts: Sequence[str]) -> bool:
    key = join(parts)
    numeric = key.replace(".", "").replace("-", "").isdigit()
    return not parts or " ".join(parts) in STOPLIST or numeric or len(key) < 2


def type_group(entity_type: str) -> str:
    return TYPE_GROUPS.get(entity_type, "other")


def name_tokens(name: str, entity_type: str) -> Tokens:
    parts = tokens(name)
    return company_tokens(parts) if type_group(entity_type) == "org" else parts


def vendor_tokens(vendor: str | None) -> Tokens:
    if not vendor:
        return ()
    parts = company_tokens(tokens(vendor))
    alias = VENDOR_ALIASES.get(" ".join(parts))
    return tuple(alias.split()) if alias else parts


def strip_vendor(parts: Tokens, vendor: Tokens) -> Tokens | None:
    """The remainder after a leading vendor prefix, or None if it would not be a usable name."""
    n = len(vendor)
    rest = parts[n:]
    if not vendor or parts[:n] != vendor or not rest or rest[0][:1].isdigit() or is_stopped(rest):
        return None
    return rest


def family_tokens(base: Tokens) -> Tokens:
    family = list(base)
    while len(family) > 1 and PACKAGING.match(family[-1]):
        family.pop()
    return tuple(family)


@dataclass(frozen=True)
class Mention:  # pylint: disable=too-many-instance-attributes
    """One stored mention (evidence row) as input to reconciliation."""
    mention_id: int
    scope_day: date
    article_id: int
    publisher: str
    name: str
    canonical_name: str
    entity_type: str
    vendor: str | None
    role: str
    is_new: bool = False
    novelty_quote: str | None = None


@dataclass(frozen=True)
class MentionKeys:
    type_group: str
    name_key: str
    base_key: str
    base_tokens: Tokens
    family_key: str
    vendor_key: str
    vendor_inferred: bool


@dataclass(frozen=True)
class Override:  # pylint: disable=too-many-instance-attributes
    """Stored operator override; `vendor_class == ""` matches any vendor class."""
    override_id: int
    kind: str  # alias | merge
    type_group: str
    match_key: str
    vendor_class: str
    target_base_key: str
    target_vendor_class: str
    target_entity_key: str


@dataclass(frozen=True)
class Entity:  # pylint: disable=too-many-instance-attributes
    entity_key: str
    display_name: str
    type_group: str
    entity_type: str
    vendor: str | None
    vendor_class: str
    base_key: str
    base_tokens: Tokens
    family_key: str
    first_seen_day: date
    needs_review: bool


@dataclass
class Reconciliation:
    keys: dict[int, MentionKeys] = field(default_factory=dict)
    assignments: dict[int, str] = field(default_factory=dict)
    entities: dict[str, Entity] = field(default_factory=dict)


class VendorClasses:
    """Vendor equivalence classes over the whole evidence set (plan Decision 2 rule 6)."""

    def __init__(self, vendors: Iterable[str | None], org_names: Iterable[Tokens] = ()):
        members: set[Tokens] = set()
        for vendor in vendors:
            raw = company_tokens(tokens(vendor or ""))
            if raw:
                members.add(raw)
                members.add(vendor_tokens(vendor))
        parent = {m: m for m in members}

        def find(m: Tokens) -> Tokens:
            while parent[m] != m:
                parent[m] = parent[parent[m]]
                m = parent[m]
            return m

        ordered = sorted(members)
        for a in ordered:
            alias = VENDOR_ALIASES.get(" ".join(a))
            if alias and tuple(alias.split()) in parent:
                parent[find(a)] = find(tuple(alias.split()))
            for b in ordered:
                if len(a) < len(b) and b[:len(a)] == a:
                    parent[find(b)] = find(a)
        components: dict[Tokens, list[Tokens]] = defaultdict(list)
        for m in members:
            components[find(m)].append(m)
        self.key: dict[Tokens, str] = {}
        for component in components.values():
            best = min(component, key=lambda m: (len(join(m)), join(m)))
            for m in component:
                self.key[m] = join(best)
        orgs = set(org_names)
        # Only org-backed classes count (CP1, gate finding 5): a product named as a vendor
        # ("Gemini") neither strips a prefix nor splits an entity by vendor.
        self.backed = {self.key[m] for m in members if m in orgs}
        self.strippable = sorted((m for m in members if self.key[m] in self.backed),
                                 key=lambda m: (-len(m), m))

    def of(self, vendor: str | None) -> str:
        if not vendor:
            return ""
        key = self.key.get(company_tokens(tokens(vendor)), "")
        return key if key in self.backed else ""


def mention_keys(mention: Mention, classes: VendorClasses) -> MentionKeys:
    group = type_group(mention.entity_type)
    parts = name_tokens(mention.canonical_name, mention.entity_type)
    vendor_key = classes.of(mention.vendor)
    inferred = False
    base = parts
    for member in classes.strippable:
        rest = strip_vendor(parts, member)
        if rest is not None:
            base = rest
            if not vendor_key:
                vendor_key, inferred = classes.key[member], True
            break
    return MentionKeys(type_group=group, name_key=join(parts), base_key=join(base),
                       base_tokens=base, family_key=join(family_tokens(base)),
                       vendor_key=vendor_key, vendor_inferred=inferred)


def evidence_classes(mentions: Iterable[Mention]) -> VendorClasses:
    rows = list(mentions)
    orgs = [name_tokens(m.canonical_name, m.entity_type) for m in rows
            if type_group(m.entity_type) == "org"]
    return VendorClasses([m.vendor for m in rows], orgs)


def _ranked(counter: Counter, tie=lambda value: value):
    return sorted(counter.items(), key=lambda kv: (-kv[1], tie(kv[0])))[0][0]


def _override_target(keys: MentionKeys, overrides: Sequence[Override]) -> str | None:
    def vendor_ok(selector_class: str) -> bool:
        return selector_class in ("", keys.vendor_key)

    group = [o for o in overrides if o.type_group == keys.type_group]
    for kind in ("alias", "merge"):
        for o in group:
            if o.kind != kind or not vendor_ok(o.vendor_class):
                continue
            if o.match_key == keys.base_key or (kind == "alias" and o.match_key == keys.name_key):
                return o.target_entity_key
    for o in group:
        if o.target_base_key == keys.base_key and vendor_ok(o.target_vendor_class):
            return o.target_entity_key
    return None


def reconcile(mentions: Iterable[Mention], overrides: Iterable[Override] = ()) -> Reconciliation:
    """Derive entities and mention assignments from evidence (plan Decision 2, Reconciliation)."""
    rows = sorted(mentions, key=lambda m: m.mention_id)
    ordered_overrides = sorted(overrides, key=lambda o: o.override_id)
    classes = evidence_classes(rows)
    result = Reconciliation()
    for m in rows:
        result.keys[m.mention_id] = mention_keys(m, classes)
    by_resolution: dict[tuple[str, str], list[Mention]] = defaultdict(list)
    for m in rows:
        keys = result.keys[m.mention_id]
        target = _override_target(keys, ordered_overrides)
        if target is not None:
            result.assignments[m.mention_id] = target
        else:
            by_resolution[(keys.type_group, keys.base_key)].append(m)
    for (group, base), members in sorted(by_resolution.items()):
        vendor_counts = Counter(result.keys[m.mention_id].vendor_key for m in members
                                if result.keys[m.mention_id].vendor_key)
        if len(vendor_counts) <= 1:
            for m in members:
                result.assignments[m.mention_id] = f"auto:{group}:{base}"
            continue
        top, top_n = sorted(vendor_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        dominant = top_n >= 0.8 * sum(vendor_counts.values())
        for m in members:
            vendor_key = result.keys[m.mention_id].vendor_key
            suffix = vendor_key or (top if dominant else "?")
            result.assignments[m.mention_id] = f"auto:{group}:{base}:{suffix}"
    grouped: dict[str, list[Mention]] = defaultdict(list)
    for m in rows:
        grouped[result.assignments[m.mention_id]].append(m)
    for entity_key, members in sorted(grouped.items()):
        result.entities[entity_key] = _entity(entity_key, members, result.keys)
    return result


def _entity(entity_key: str, members: list[Mention], keys: dict[int, MentionKeys]) -> Entity:
    member_keys = [keys[m.mention_id] for m in members]
    names = Counter(m.canonical_name for m in members)
    types = Counter(m.entity_type for m in members)
    classes = Counter(k.vendor_key for k in member_keys if k.vendor_key)
    vendor_class = _ranked(classes) if classes else ""
    # Display vendor: an explicit spelling of the entity's class, else any explicit vendor.
    vendors = Counter(m.vendor for m, k in zip(members, member_keys, strict=True)
                      if m.vendor and k.vendor_key == vendor_class and not k.vendor_inferred)
    if not vendors and not vendor_class:
        vendors = Counter(m.vendor for m in members if m.vendor)
    base = Counter(k.base_tokens for k in member_keys)
    base_tokens = _ranked(base, tie=join)
    families = Counter(k.family_key for k in member_keys)
    return Entity(
        entity_key=entity_key,
        display_name=_ranked(names),
        type_group=member_keys[0].type_group,
        entity_type=_ranked(types, tie=lambda t: TYPE_ORDER.index(t) if t in TYPE_ORDER else 99),
        vendor=_ranked(vendors) if vendors else None,
        vendor_class=vendor_class,
        base_key=join(base_tokens),
        base_tokens=base_tokens,
        family_key=_ranked(families),
        first_seen_day=min(m.scope_day for m in members),
        needs_review=entity_key.endswith(":?"),
    )


def same_family(a: Entity, b: Entity) -> bool:
    """Packaging variants of one model (New suppression and same-day grouping only)."""
    return a.entity_key != b.entity_key and a.type_group == b.type_group == "artifact" \
        and a.vendor_class == b.vendor_class and a.family_key == b.family_key


def token_prefix(older: Entity, newer: Entity) -> bool:
    """`older` names a strict token prefix of `newer` (same vendor class): `variant_of`."""
    n = len(older.base_tokens)
    return older.type_group == newer.type_group == "artifact" \
        and older.vendor_class == newer.vendor_class and n < len(newer.base_tokens) \
        and newer.base_tokens[:n] == older.base_tokens


def selectors_conflict(existing: Iterable[Override], new: Override) -> Override | None:
    """An override that already owns one of `new`'s selectors (no cycles, no silent conflicts)."""
    def selectors(o: Override) -> set[tuple[str, str, str]]:
        return {(o.type_group, o.match_key, o.vendor_class),
                (o.type_group, o.target_base_key, o.target_vendor_class)}

    wanted = selectors(new)
    for o in sorted(existing, key=lambda o: o.override_id):
        if o.target_entity_key != new.target_entity_key and selectors(o) & wanted:
            return o
    return None
