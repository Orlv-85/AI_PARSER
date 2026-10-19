import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.core.daily_signals_compute import (
    ArticleObs,
    DayCoverage,
    EntityMention,
    LexicalHistory,
    SnapshotInput,
    Thresholds,
    cluster,
    compute_snapshot,
    links,
    payload_hash,
)
from app.core.daily_signals_entities import Mention, Override, reconcile

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "daily_signals"
COMPARABLE_FROM = date(2026, 10, 10)
D = date(2026, 10, 16)
GENERATED = datetime(2026, 10, 17, 2, 30)


def e(name, entity_type="model", role="primary", new=False, vendor=None, *, quote=None):
    return {"name": name, "type": entity_type, "role": role, "is_new": new, "vendor": vendor,
            "quote": quote or (f"Today Acme launched {name}" if new else None)}


class World:
    def __init__(self):
        self.mentions = []
        self.articles = {}
        self.coverage = {}
        self.overrides = []

    def article(self, day, publisher, *entities, event="model_release", title=None, at=None):
        article_id = len(self.articles) + 1
        ids = []
        for spec in entities:
            self.mentions.append(Mention(
                mention_id=len(self.mentions) + 1, scope_day=day, article_id=article_id,
                publisher=publisher, name=spec["name"], canonical_name=spec["name"],
                entity_type=spec["type"], vendor=spec["vendor"], role=spec["role"],
                is_new=spec["is_new"], novelty_quote=spec["quote"]))
            ids.append(len(self.mentions))
        when = at if at is not None else datetime(day.year, day.month, day.day, 12)
        self.articles[article_id] = (day, title or f"Article {article_id}", publisher, event, when,
                                     ids)
        return article_id

    def day(self, day, items, extracted=None, kind=None, published=True):
        self.coverage[day] = DayCoverage(
            day=day, kind=kind or ("signals" if day >= COMPARABLE_FROM else "history"),
            published=published, items=items, matched=items,
            extracted=items if extracted is None else extracted)

    def observations(self):
        result = reconcile(self.mentions, self.overrides)
        by_day = {}
        for article_id, (day, title, publisher, event, at, ids) in sorted(self.articles.items()):
            mentions = tuple(EntityMention(
                entity_key=result.assignments[i], type_group=result.keys[i].type_group,
                base_key=result.keys[i].base_key, role=self.mentions[i - 1].role,
                is_new=self.mentions[i - 1].is_new,
                novelty_quote=self.mentions[i - 1].novelty_quote) for i in ids)
            by_day.setdefault(day, []).append(ArticleObs(
                article_id=article_id, scope_day=day, title=title,
                url=f"https://{publisher}/{article_id}", publisher=publisher, published_at=at,
                event_type=event, mentions=mentions))
        return result, by_day

    def snapshot(self, day=D, thresholds=None, history=()):
        result, by_day = self.observations()
        coverage = dict(self.coverage)
        for d, articles in by_day.items():
            if d not in coverage:
                self.day(d, len(articles))
                coverage[d] = self.coverage[d]
        ids = {key: n for n, key in enumerate(sorted(result.entities), start=1)}
        return compute_snapshot(SnapshotInput(
            day=day, observations=by_day, coverage=coverage, entities=result.entities,
            entity_ids=ids, extraction_version="daily-signals-extract-5", generated_at=GENERATED,
            comparable_from=COMPARABLE_FROM, thresholds=thresholds or Thresholds(),
            history=LexicalHistory(history)))


def names(items):
    return [i["name"] for i in items]


# Clustering ----------------------------------------------------------------------------------

def fixture_days():
    mentions, raw = [], []
    for path in sorted(FIXTURES.glob("signals_*.json")):
        data = json.loads(path.read_text())
        day = date.fromisoformat(data["day"])
        for article in data["articles"]:
            ids = []
            for entity in article["entities"]:
                mentions.append(Mention(
                    mention_id=len(mentions) + 1, scope_day=day, article_id=article["article_id"],
                    publisher=article["publisher"], name=entity["name"],
                    canonical_name=entity["canonical"] or entity["name"],
                    entity_type=entity["type"], vendor=entity["vendor"], role=entity["role"]))
                ids.append(len(mentions))
            raw.append((day, article, ids))
    result = reconcile(mentions)
    days = {}
    for day, article, ids in raw:
        days.setdefault(day, []).append(ArticleObs(
            article_id=article["article_id"], scope_day=day, title=article["title"],
            url=article["url"], publisher=article["publisher"],
            published_at=datetime.fromisoformat(article["published_at"])
            if article["published_at"] else None,
            event_type=article["event_type"],
            mentions=tuple(EntityMention(result.assignments[i], result.keys[i].type_group,
                                         result.keys[i].base_key, mentions[i - 1].role)
                           for i in ids)))
    return days


def top(stories, limit=5):
    ranked = sorted(stories, key=lambda s: (-s.publishers, -len(s.members), s.earliest, s.label))
    return [s for s in ranked if s.publishers >= 2][:limit]


def test_fixture_stories():
    days = fixture_days()
    expected = {
        date(2026, 10, 12): ("auto:artifact:musewonder", 6, 6),
        date(2026, 10, 13): ("auto:artifact:gemini4argon", 7, 5),
        date(2026, 10, 15): ("auto:artifact:musesparkopen", 7, 7),
        date(2026, 10, 16): ("auto:artifact:beam", 4, 4),
    }
    for day, (entity_key, articles, publishers) in expected.items():
        story = top(cluster(days[day]))[0]
        assert entity_key in story.entity_keys
        assert (len(story.members), story.publishers) == (articles, publishers)
    for day, articles in days.items():
        labels = [s.label for s in top(cluster(articles))]
        assert len(labels) == len(set(labels)), day


def test_fixture_rtx_spark_and_surface_reviews_stay_separate():
    stories = cluster(fixture_days()[D])

    def story(publisher, word):
        found, = [s for s in stories for m in s.members
                  if m.publisher == publisher and word in m.title]
        return found

    rtx = story("theverge.com", "RTX Spark")
    assert rtx is story("extremetech.com", "RTX Spark")
    surface = story("wired.com", "Surface Laptop Ultra")
    assert surface is story("arstechnica.com", "Surface Laptop Ultra")
    assert rtx is not surface


def obs(article_id, title, *primary, event="model_release", publisher=None, at=None):
    return ArticleObs(
        article_id=article_id, scope_day=D, title=title, url=f"https://x/{article_id}",
        publisher=publisher or f"p{article_id}.com",
        published_at=at if at is not None else datetime(2026, 10, 16, article_id),
        event_type=event,
        mentions=tuple(EntityMention(f"auto:artifact:{k}", "artifact", k, "primary")
                       for k in primary))


def test_bridge_does_not_chain():
    a = obs(1, "Alpha ships things", "x")
    b = obs(2, "Bravo does stuff", "x", "y")
    c = obs(3, "Charlie wins prize", "y")
    stories = cluster([c, b, a])
    assert [[m.article_id for m in s.members] for s in stories] == [[1, 2], [3]]


def test_order_null_published_last_and_ties_by_id():
    at = datetime(2026, 10, 16, 9)
    first = obs(5, "Zeta one", "z", at=at)
    second = obs(4, "Zeta two", "z", at=at)
    late = ArticleObs(1, D, "Zeta three", "https://x/1", "p1.com", None, "model_release",
                      (EntityMention("auto:artifact:z", "artifact", "z", "primary"),))
    story = cluster([late, first, second])[0]
    assert [m.article_id for m in story.members] == [4, 5, 1]


def test_simhash_edges_only_within_event_family():
    title = "Acme raises money for robot hands in Berlin"
    funding = obs(1, title, event="funding")
    launch = obs(2, title, event="model_release")
    product = obs(3, title, event="product_launch")
    stories = cluster([funding, launch, product])
    assert sorted(len(s.members) for s in stories) == [1, 2]


def test_org_only_link_needs_title_overlap():
    org = (EntityMention("auto:org:acme", "org", "acme", "primary"),)
    a = replace(obs(1, "Acme quarterly revenue grows fast", event="funding"), mentions=org)
    b = replace(obs(2, "Acme quarterly revenue beats forecast", event="funding"), mentions=org)
    c = replace(obs(3, "Acme hires a chief scientist", event="funding"), mentions=org)
    stories = cluster([a, b, c])
    assert sorted(len(s.members) for s in stories) == [1, 2]


def test_us2_one_story_per_event_and_ordering():
    articles = [obs(i, f"Atlas model launch coverage part {i}", "atlas",
                    publisher="dup.com" if i == 6 else None) for i in range(1, 7)]
    articles += [obs(7, "Bravo raises money", "bravo", event="funding"),
                 obs(8, "Bravo funding round closes", "bravo", event="funding")]
    stories = top(cluster(articles))
    assert [(len(s.members), s.publishers) for s in stories] == [(6, 6), (2, 2)]
    articles[5] = replace(articles[5], publisher="p1.com")
    assert [(len(s.members), s.publishers) for s in top(cluster(articles))] == [(6, 5), (2, 2)]


def test_label_prefers_central_title_then_shorter():
    a = obs(1, "Atlas launches", "atlas")
    b = obs(2, "Acme Atlas robot model launches today", "atlas")
    c = obs(3, "Acme Atlas robot model", "atlas")
    assert cluster([a, b, c])[0].label == "Acme Atlas robot model"


def test_links_distinct_publishers_first():
    articles = [obs(1, "a", publisher="x.com"), obs(2, "b", publisher="x.com"),
                obs(3, "c", publisher="y.com"), obs(4, "d", publisher="z.com")]
    assert [link["url"] for link in links(articles, 3)] == \
        ["https://x/1", "https://x/3", "https://x/4"]
    assert [link["url"] for link in links(articles[:2], 3)] == ["https://x/1", "https://x/2"]


# New -----------------------------------------------------------------------------------------

def test_new_needs_primary_and_is_new_in_one_article():
    w = World()
    w.article(D, "a.com", e("Atlas", role="mentioned", new=True))
    w.article(D, "b.com", e("Atlas"))
    assert w.snapshot()["new"] == []
    w.article(D, "c.com", e("Atlas", new=True))
    item = w.snapshot()["new"][0]
    assert (item["name"], item["level"], item["publishers"], item["articles"]) == \
        ("Atlas", "confirmed", 3, 3)
    assert item["novelty_quote"] == "Today Acme launched Atlas"


def test_us1_confirmed_early_alias_and_history_note():
    w = World()
    w.day(date(2026, 10, 1), 5, kind="history")
    w.article(date(2026, 10, 1), "a.com", e("GPT-6"))
    w.article(D, "a.com", e("Beam", new=True, vendor="Reflection AI"))
    w.article(D, "b.com", e("Beam", new=True))
    w.article(D, "c.com", e("Orion-1", new=True))
    w.article(D, "c.com", e("GPT-6 Astra", new=True))
    snapshot = w.snapshot()
    assert [(i["name"], i["level"]) for i in snapshot["new"]] == [
        ("Beam", "confirmed"), ("GPT-6 Astra", "early"), ("Orion-1", "early")]
    assert snapshot["new"][0]["vendor"] == "Reflection AI"
    assert snapshot["sections"]["new"] == {"state": "building", "note": "History: 1 complete days."}
    assert snapshot["novelty_history_days"] == 1
    w.overrides = [Override(1, "alias", "artifact", "gpt6astra", "", "gpt6", "", "manual:1")]
    assert names(w.snapshot()["new"]) == ["Beam", "Orion-1"]


def test_glimpse_model_new_despite_older_company():
    w = World()
    w.article(date(2026, 10, 6), "a.com", e("Glimpse", "company"))
    w.article(D, "b.com", e("Glimpse", new=True, vendor="Elorian"))
    assert names(w.snapshot()["new"]) == ["Glimpse"]


def test_packaging_variant_of_known_model_not_new():
    w = World()
    w.article(date(2026, 10, 13), "a.com", e("NVIDIA", "company", role="mentioned"),
              e("NVIDIA Nemotron 3.5 Bolt 74B", new=True))
    w.article(D, "b.com", e("Nemotron 3.5 Bolt 74B-A9B 24GB", new=True, vendor="NVIDIA"))
    assert w.snapshot()["new"] == []


def test_same_day_family_grouped_and_variant_of():
    w = World()
    w.article(date(2026, 10, 12), "a.com", e("Muse Spark"))
    w.article(D, "b.com", e("Muse Spark Open", new=True), e("Muse Spark Open 8B", new=True))
    w.article(D, "c.com", e("Muse Spark Open", new=True))
    item, = w.snapshot()["new"]
    assert (item["name"], item["variant_of"], item["variants"]) == \
        ("Muse Spark Open", "Muse Spark", ["Muse Spark Open 8B"])


def test_person_other_and_question_entities_never_new():
    w = World()
    w.article(date(2026, 9, 1), "o.com", e("Acme", "company"), e("Zeta", "company"))
    w.article(D, "a.com", e("Jane Roe", "person", new=True), e("Thing", "other", new=True))
    for i in range(3):
        w.article(D, f"v{i}.com", e("Atlas", new=True, vendor="Acme"))
        w.article(D, f"z{i}.com", e("Atlas", new=True, vendor="Zeta"))
    w.article(D, "u.com", e("Atlas", new=True))
    assert names(w.snapshot()["new"]) == ["Atlas", "Atlas"]
    assert all(i["vendor"] in ("Acme", "Zeta") for i in w.snapshot()["new"])


def test_cp1_new_ordering_early_models_before_products():
    w = World()
    w.article(D, "a.com", e("Zeta Bench", "benchmark", new=True))
    w.article(D, "b.com", e("Alpha App", "product", new=True))
    w.article(D, "c.com", e("Mid Model", new=True))
    w.article(D, "d.com", e("Chip X1", "hardware", new=True))
    w.article(D, "e.com", e("Acme Labs", "company", new=True))
    w.article(D, "f.com", e("Big Launch", "product", new=True))
    w.article(D, "g.com", e("Big Launch", "product", new=True))
    w.article(D, "h.com", e("Data Set One", "dataset", new=True))
    w.article(D, "i.com", e("Neat Trick", "technology", new=True))
    w.article(D, "j.com", e("Act One", "policy", new=True))
    assert names(w.snapshot()["new"]) == ["Big Launch", "Mid Model", "Chip X1", "Zeta Bench",
                                          "Data Set One", "Neat Trick", "Acme Labs", "Alpha App"]
    capped = w.snapshot(thresholds=Thresholds(new_max=20))
    assert names(capped["new"])[-1] == "Act One"


# Top stories, events, status ---------------------------------------------------------------

def test_top_stories_events_and_status():
    w = World()
    w.article(D, "a.com", e("Atlas"), title="Acme launches Atlas robot model")
    w.article(D, "b.com", e("Atlas"), title="Atlas robot model from Acme")
    w.article(D, "c.com", e("Bravo", "company"), event="funding", title="Bravo raises $5M")
    snapshot = w.snapshot()
    story, = snapshot["top_stories"]
    assert (story["articles"], story["publishers"], story["entities"]) == (2, 2, ["Atlas"])
    assert snapshot["sections"]["top_stories"]["state"] == "ready"
    assert [(c["event_type"], c["stories"], c["articles"], len(c["links"]))
            for c in snapshot["event_counts"]] == [("model_release", 1, 2, 1), ("funding", 1, 1, 1)]
    assert snapshot["event_counts"][1]["label"] == "funding rounds"
    assert snapshot["article_event_types"]["https://c.com/3"] == "funding"
    assert snapshot["status"] == "building_history"
    assert snapshot["coverage"] == {"items": 3, "matched": 3, "extracted": 3, "failed": 0,
                                    "skipped": 0, "pending": 0, "unmatched": 0}


def test_status_precedence():
    w = World()
    w.article(D, "a.com", e("Atlas"))
    w.day(D, 0)
    empty = w.snapshot()
    assert (empty["status"], empty["notes"]) == ("unavailable", ["No digest items for this date."])
    w.day(D, 10, extracted=0)
    assert w.snapshot()["status"] == "unavailable"
    w.day(D, 10, extracted=8)
    partial = w.snapshot()
    assert (partial["status"], partial["notes"]) == ("partial", ["Extracted 8/10 digest items."])
    w.day(D, 10, extracted=9)
    complete = w.snapshot()
    assert complete["status"] == "building_history"
    assert complete["notes"] == ["Extracted 9/10 digest items."]
    assert w.snapshot()["sections"]["top_stories"] == {
        "state": "empty", "note": "No story was covered by more than one publisher."}


def test_payload_hash_and_determinism():
    w = World()
    w.article(D, "a.com", e("Atlas", new=True))
    first = w.snapshot()
    again = w.snapshot()
    assert first == again and payload_hash(first) == payload_hash(again)
    later = dict(first, generated_at="2030-01-01T00:00:00")
    assert payload_hash(later) == payload_hash(first)
    assert payload_hash(dict(first, status="ready")) != payload_hash(first)
    assert first["thresholds"]["spike_mean_floor"] == 0.333
    assert json.loads(json.dumps(first)) == first


# Spikes and windows --------------------------------------------------------------------------

def spike_world(trailing_items=10):
    w = World()
    for i in range(1, 4):
        w.day(D - timedelta(days=i), trailing_items)
    w.article(D - timedelta(days=1), "a.com", e("Atlas", role="mentioned"))
    for i in range(3):
        w.article(D, f"p{i}.com", e("Atlas", role="mentioned"), e("Orion", new=bool(i)))
    w.article(date(2026, 10, 1), "old.com", e("Orion"))
    return w


def test_spikes_from_complete_trailing_days():
    snapshot = spike_world().snapshot()
    rising = snapshot["rising"]
    assert snapshot["sections"]["rising"]["state"] == "spikes_only"
    assert snapshot["sections"]["cooling"] == {"state": "hidden", "note": None}
    assert [(r["name"], r["today"], r["trailing_mean"], r["spike"]) for r in rising] == [
        ("Atlas", 3, 0.333, True), ("Orion", 3, 0.0, True)]
    # Days with fewer than 10 digest items are not trailing days (10-10 with 7, 10-11 with 1).
    assert spike_world(trailing_items=7).snapshot()["rising"] == []


def test_new_entities_excluded_from_spikes():
    w = spike_world()
    for i in range(3):
        w.article(D, f"n{i}.com", e("Fresh", new=True))
    snapshot = w.snapshot()
    assert "Fresh" in names(snapshot["new"])
    assert "Fresh" not in names(snapshot["rising"])


def window_world(day=date(2026, 10, 24), per_day=10, skip=(), incomplete=(), empty=()):
    w = World()
    for i in range(14):
        d = day - timedelta(days=i)
        if d in skip:
            continue
        if d in empty:
            w.day(d, 0)
        else:
            w.day(d, per_day, extracted=per_day // 2 if d in incomplete else per_day)
    return w


def add(w, day, name, count, publishers=2):
    for i in range(count):
        w.article(day, f"pub{i % publishers}.com", e(name, role="mentioned"))


def test_rising_and_cooling_with_usable_windows():
    day = date(2026, 10, 24)
    w = window_world(day)
    add(w, day - timedelta(days=10), "Riser", 1)
    for i in range(3):
        add(w, day - timedelta(days=i), "Riser", 2)
    for i in range(7, 11):
        add(w, day - timedelta(days=i), "Cooler", 2)
    add(w, day - timedelta(days=1), "Cooler", 1)
    add(w, day - timedelta(days=9), "Flat", 3)
    add(w, day - timedelta(days=2), "Flat", 4)
    snapshot = w.snapshot(day)
    assert snapshot["sections"]["rising"] == {"state": "ready", "note": None}
    assert snapshot["sections"]["cooling"] == {"state": "ready", "note": None}
    riser, = snapshot["rising"]
    assert (riser["name"], riser["current_7d"], riser["previous_7d"], riser["expected_7d"],
            riser["today"], riser["spike"]) == ("Riser", 6, 1, 1.0, 2, False)
    cooler, = snapshot["cooling"]
    assert (cooler["name"], cooler["previous_7d"], cooler["current_7d"]) == ("Cooler", 8, 1)
    assert snapshot["comparable_complete_days"] == 14


def test_rising_boundaries_and_volume_adjustment():
    day = date(2026, 10, 24)
    w = window_world(day)
    # Current-window mentions three days back, so no spike is appended.
    current = day - timedelta(days=3)
    add(w, day - timedelta(days=8), "Exact", 1)
    add(w, current, "Exact", 4)
    add(w, day - timedelta(days=8), "Short", 2)
    add(w, current, "Short", 4)
    add(w, current, "Lonely", 5, publishers=1)
    assert names(w.snapshot(day)["rising"]) == ["Exact"]
    # Twice the extracted volume in the current window doubles the expectation.
    w2 = window_world(day)
    for i in range(7):
        w2.day(day - timedelta(days=i), 20)
    add(w2, day - timedelta(days=8), "Exact", 1)
    add(w2, current, "Exact", 4)
    assert w2.snapshot(day)["rising"] == []


def test_windows_need_six_complete_days_and_comparable_range():
    day = date(2026, 10, 24)
    missing_two = window_world(day, skip={day - timedelta(days=1), day - timedelta(days=2)})
    assert missing_two.snapshot(day)["sections"]["rising"]["state"] == "spikes_only"
    missing_one = window_world(day, skip={day - timedelta(days=1)})
    assert missing_one.snapshot(day)["sections"]["rising"]["state"] == "ready"
    incomplete = window_world(day, incomplete={day - timedelta(days=9), day - timedelta(days=10)})
    assert incomplete.snapshot(day)["sections"]["cooling"]["state"] == "hidden"
    early = window_world(date(2026, 10, 22))
    assert early.snapshot(date(2026, 10, 22))["sections"]["rising"]["state"] == "spikes_only"


def test_observed_empty_days_count_as_zero_but_zero_volume_is_unusable():
    day = date(2026, 10, 24)
    w = window_world(day, empty={day - timedelta(days=3)})
    assert w.snapshot(day)["sections"]["rising"]["state"] == "ready"
    no_prev = window_world(day, empty={day - timedelta(days=i) for i in range(7, 14)})
    snapshot = no_prev.snapshot(day)
    assert snapshot["sections"]["rising"]["state"] == "spikes_only"
    assert snapshot["sections"]["cooling"]["state"] == "hidden"


def test_fourteen_days_with_short_novelty_history():
    day = date(2026, 10, 24)
    snapshot = window_world(day).snapshot(day)
    assert snapshot["sections"]["rising"]["state"] == "ready"
    assert snapshot["sections"]["new"]["state"] == "building"
    assert snapshot["novelty_history_days"] == 13
    assert snapshot["status"] == "building_history"


def test_question_entities_excluded_from_trends():
    w = spike_world()
    w.article(date(2026, 9, 1), "o.com", e("Acme", "company"), e("Zeta", "company"))
    for i in range(2):
        w.article(D, f"v{i}.com", e("Atlas", role="mentioned", vendor="Acme"))
        w.article(D, f"z{i}.com", e("Atlas", role="mentioned", vendor="Zeta"))
    assert "Atlas" not in names(w.snapshot()["rising"])


def test_generic_lowercase_feature_names_are_not_new():
    # F22 (Phase 7): New needs a proper-name shape; such entities still count elsewhere.
    w = World()
    w.article(D, "a.com", e("dynamic workflows", "technology", new=True),
              e("on-demand capacity mode", "technology", new=True),
              e("agent-engineer", "product", new=True), e("d1-ultra", new=True),
              e("Priming", "technology", new=True))
    payload = w.snapshot()
    assert names(payload["new"]) == ["d1-ultra", "Priming", "agent-engineer"]
    assert [(i["name"], i["reason"]) for i in payload["new_suppressed"]] == [
        ("dynamic workflows", "generic_name"), ("on-demand capacity mode", "generic_name")]


def test_new_suppressed_by_title_or_summary_history():
    # F19 (Phase 7): a name already in an earlier in-scope title/summary is not New, even when
    # that article's extraction found nothing (title-only history).
    w = World()
    for publisher in ("a.com", "b.com", "c.com"):
        w.article(D, publisher, e("Surface Laptop Ultra", "hardware", new=True))
    w.article(D, "d.com", e("Maka", "product", new=True))
    w.article(D, "e.com", e("Reflection", "company"), e("Beam", new=True, vendor="Reflection"))
    history = [
        (date(2026, 10, 7), "The first Nvidia RTX Spark laptops cost up to $7,000. Microsoft "
                            "shows the Surface Laptop Ultra."),
        (date(2026, 10, 9), "a maka recipe"),  # lowercase common word: no match
        (date(2026, 10, 5), "Beam me up"),  # vendor known but absent: no match
        (D, "Maka streaming app"),  # the day itself never counts
    ]
    payload = w.snapshot(history=history)
    assert names(payload["new"]) == ["Beam", "Maka"]
    assert payload["new_suppressed"] == [{
        "name": "Surface Laptop Ultra", "entity_id": payload["new_suppressed"][0]["entity_id"],
        "reason": "lexical_history", "day": "2026-10-07", "match": "surface laptop ultra",
        "text": "The first Nvidia RTX Spark laptops cost up to $7,000. Microsoft shows the "
                "Surface Laptop Ultra."}]
    history.append((date(2026, 10, 6), "Reflection releases Beam"))
    assert names(w.snapshot(history=history)["new"]) == ["Maka"]
    # V02: a single common-word name without a vendor is never suppressed lexically.
    history.append((date(2026, 10, 8), "Maka raises money"))
    assert names(w.snapshot(history=history)["new"]) == ["Maka"]


def test_lexical_hit_in_not_yet_released_text_is_ignored():
    # F19 decision: "mentioned before" is not "released before" (previews, roadmaps, waitlists);
    # GA after a preview stays New (OD1). A later plain mention still suppresses.
    w = World()
    w.article(D, "a.com", e("Code Review for Claude Code", "product", new=True))
    w.article(D, "b.com", e("Muse Spark Open", new=True))
    w.article(D, "c.com", e("Atlas Pro", "product", new=True))
    history = [
        (date(2026, 9, 3), "Meta's roadmap includes the Muse Spark open weights release."),
        (date(2026, 3, 9), "Anthropic opens a research preview of Code Review for Claude Code."),
        (date(2026, 9, 1), "Acme Plans To ship Atlas Pro; join the waitlist."),
        (date(2026, 9, 2), "Atlas Pro: coming soon from Acme"),
    ]
    payload = w.snapshot(history=history)
    assert names(payload["new"]) == ["Muse Spark Open", "Atlas Pro", "Code Review for Claude Code"]
    assert payload["new_suppressed"] == []
    history.append((date(2026, 9, 20), "Acme ships Atlas Pro to all users."))
    payload = w.snapshot(history=history)
    assert [(i["name"], i["day"]) for i in payload["new_suppressed"]] == [
        ("Atlas Pro", "2026-09-20")]


@pytest.mark.parametrize("text", ["Acme announces Atlas Pro (preview).",
                                  "Acme shows Atlas Pro (early access; will launch next month)."])
def test_parenthetical_prerelease_does_not_suppress_ga(text):
    # V01: the not-released check and the snippet use the raw digest text (parentheses kept).
    w = World()
    w.article(D, "a.com", e("Atlas Pro", "product", new=True))
    payload = w.snapshot(history=[(date(2026, 9, 1), text)])
    assert names(payload["new"]) == ["Atlas Pro"]
    history = [(date(2026, 9, 1), "Acme ships Atlas Pro (GA) to everyone.")]
    suppressed = w.snapshot(history=history)["new_suppressed"]
    assert suppressed[0]["text"] == "Acme ships Atlas Pro (GA) to everyone."


def test_single_token_needs_the_vendor_name_in_the_same_item():
    # V02: "Beam search ..." is a homonym; a generic vendor word ("labs") is not the vendor.
    w = World()
    w.article(D, "a.com", e("Beam", new=True))
    assert names(w.snapshot(history=[(date(2026, 9, 1), "Beam search improves decoding.")])[
        "new"]) == ["Beam"]
    v = World()
    v.article(D, "a.com", e("Acme Labs", "company"), e("Beam", new=True, vendor="Acme Labs"))
    history = [(date(2026, 9, 1), "Beam search is used in research labs.")]
    assert names(v.snapshot(history=history)["new"]) == ["Beam"]
    history.append((date(2026, 9, 2), "Acme Labs previewed nothing; Acme Labs ships Beam."))
    assert names(v.snapshot(history=history)["new"]) == ["Beam"]  # "previewed": not released
    history.append((date(2026, 9, 3), "Acme Labs ships Beam to customers."))
    assert names(v.snapshot(history=history)["new"]) == []
