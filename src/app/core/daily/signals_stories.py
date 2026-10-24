"""Daily AI Signals: story clustering and article links of one day (see signals.md)."""
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from app.core.daily.signals_model import EVENT_FAMILY, ArticleObs
from app.core.ingestion.dedup import hamming_distance, simhash64

TITLE_STOP = frozenset("""a an the and or of to in on for with by from at as is are be its it this
that new how why what who your you we our their into over after about vs via than more can will now
just says say said could would may first using use launch launches launched releases release
released announces announced update updates""".split())


TITLE_TOKEN = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*")


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
