"""Daily AI Signals: lexical first-seen history from published digest text (see signals.md)."""
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date

from app.core.daily.signals_entities import (
    TOKEN,
    Entity,
    clean,
    company_tokens,
    is_stopped,
    tokens,
    vendor_tokens,
)


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
