"""Operator merge/alias through the repo (review findings F2-F4): selectors cover whole entities."""
import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.canonicalize import canonical_url_hash
from app.core.daily.signals import EntityCommandError, alias_entity, merge_entities
from app.core.daily.signals_extract import ExtractedEntity, Extraction
from app.storage.daily_signals import DailySignalRepo, OverrideConflict
from app.storage.models_sql import AIEntity, Article, Base, SignalMention
from app.storage.repos import NewsDigestRepo

D = date(2026, 10, 16)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'overrides.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield DailySignalRepo(session, comparable_from=date(2026, 10, 10))
    engine.dispose()


def publish(repo, day, *articles):
    """articles: (slug, [(name, type, vendor, role, is_new)]); one article per slug and day."""
    rows = []
    for slug, _ in articles:
        url = f"https://{slug}.example/{day}"
        article = Article(title=slug, url=url, url_canonical=url,
                          url_canonical_hash=canonical_url_hash(url), content="Body",
                          published_at=datetime(day.year, day.month, day.day, 9, tzinfo=UTC))
        repo.session.add(article)
        rows.append(article)
    repo.session.flush()
    NewsDigestRepo(repo.session).save_digest(report_date=day, groups=[{
        "title": "Models & Research",
        "items": [{"title": a.title, "summary": "s", "url": a.url} for a in rows]}])
    repo.replace_membership(day)
    for article, (_, entities) in zip(rows, articles, strict=True):
        repo.save_extraction(article, Extraction("model_release", True, tuple(
            ExtractedEntity(name, name, kind, vendor, role, new,
                            f"Today we launch {name}" if new else None)
            for name, kind, vendor, role, new in entities)), content_hash="h")
    repo.session.flush()


def recompute(repo):
    repo.recompute_reports(D, now=datetime(2026, 10, 17, tzinfo=UTC))
    repo.session.flush()


def entity_id(repo, entity_key):
    return repo.session.scalar(select(AIEntity.id).where(AIEntity.entity_key == entity_key,
                                                          AIEntity.active))


def owners(repo, name):
    return sorted({(m.vendor or "", m.entity_key) for m in repo.session.scalars(
        select(SignalMention).where(SignalMention.canonical_name == name))})


def entity(repo, entity_key):
    return repo.session.scalar(select(AIEntity).where(AIEntity.entity_key == entity_key))


def reflection_beam(repo):
    publish(repo, D - timedelta(days=11), ("hist", [("Beam", "model", None, "primary", False)]))
    publish(repo, D, ("a", [("Reflection AI", "company", None, "mentioned", False),
                            ("Reflection Beam", "model", "Reflection AI", "primary", True)]),
            ("b", [("Beam", "model", None, "primary", False)]),
            ("c", [("Atlas", "model", None, "primary", False)]))
    recompute(repo)
    assert entity(repo, "auto:artifact:beam").vendor_class == "reflection"


def test_merge_of_vendor_class_entity_moves_its_vendorless_mentions(repo):
    # F2: the selector of a class-bearing entity must cover the vendorless mentions it holds.
    reflection_beam(repo)
    merge_entities(repo, entity_id(repo, "auto:artifact:beam"),
                   entity_id(repo, "auto:artifact:atlas"))
    recompute(repo)
    keys = {key for _, key in owners(repo, "Beam") + owners(repo, "Reflection Beam")}
    assert keys == {"manual:1"}
    assert entity(repo, "auto:artifact:beam").active is False


def test_alias_keeps_first_seen_of_the_whole_entity(repo):
    # F2: an alias must not split off the newest mention and make an old entity look New.
    reflection_beam(repo)
    alias_entity(repo, entity_id(repo, "auto:artifact:beam"), "Reflection Beam 501B")
    recompute(repo)
    assert {key for _, key in owners(repo, "Beam") + owners(repo, "Reflection Beam")} \
        == {"manual:1"}
    assert entity(repo, "manual:1").first_seen_day == D - timedelta(days=11)
    new = json.loads(repo.get_report(D).payload)["new"]
    assert [item["name"] for item in new] == []


def atlas_three_vendors(repo):
    publish(repo, D, ("o", [("OpenAI", "company", None, "mentioned", False),
                            ("Atlas", "product", "OpenAI", "primary", False)]),
            ("g", [("Google", "company", None, "mentioned", False),
                   ("Atlas", "product", "Google", "primary", False)]),
            ("x", [("Atlas", "product", None, "primary", False)]),
            ("y", [("Atlas", "product", None, "primary", False)]),
            ("p", [("Atlas Pro", "product", None, "primary", False)]))
    recompute(repo)
    assert entity(repo, "auto:artifact:atlas:?").needs_review


def test_merge_of_needs_review_entity_takes_only_vendorless_mentions(repo):
    # F3: an empty vendor selector was a wildcard and swallowed both companies' Atlas.
    atlas_three_vendors(repo)
    merge_entities(repo, entity_id(repo, "auto:artifact:atlas:?"),
                   entity_id(repo, "auto:artifact:atlaspro"))
    recompute(repo)
    assert owners(repo, "Atlas") == [("", "manual:1"), ("Google", "auto:artifact:atlas:google"),
                                     ("OpenAI", "auto:artifact:atlas:openai")]


def test_overlapping_selectors_refused(repo):
    # F3: conflict detection compared exact tuples; "" (vendorless or unclassed entity) overlaps
    # a class selector of the same base, so a different target is refused.
    atlas_three_vendors(repo)
    merge_entities(repo, entity_id(repo, "auto:artifact:atlas:openai"),
                   entity_id(repo, "auto:artifact:atlaspro"))
    with pytest.raises(OverrideConflict):
        repo.add_override(kind="merge", type_group_="artifact", match_key="atlas",
                          vendor_class="", target_base_key="orion")
    # The vendorless-only selector does not overlap the OpenAI class and joins the same target.
    merge_entities(repo, entity_id(repo, "auto:artifact:atlas:?"),
                   entity_id(repo, "auto:artifact:atlaspro"))
    with pytest.raises(EntityCommandError):
        merge_entities(repo, 10_000, entity_id(repo, "auto:artifact:atlaspro"))


def test_merge_survives_vendor_class_growth(repo):
    # F4: the class "googledeepmind" becomes "google" once a shorter member appears.
    publish(repo, D - timedelta(days=1),
            ("a", [("Google DeepMind", "company", None, "mentioned", False),
                   ("Gemini Robotics", "model", "Google DeepMind", "primary", False)]),
            ("b", [("Gemini Robotics ER", "model", "Google DeepMind", "primary", False)]))
    recompute(repo)
    source = entity(repo, "auto:artifact:geminiroboticser")
    assert source.vendor_class == "googledeepmind"
    merge_entities(repo, source.id, entity_id(repo, "auto:artifact:geminirobotics"))
    recompute(repo)
    publish(repo, D, ("c", [("Google", "company", None, "mentioned", False),
                            ("Gemini Robotics ER", "model", "Google", "primary", False)]))
    recompute(repo)
    assert entity(repo, "auto:artifact:geminiroboticser").active is False
    assert {key for _, key in owners(repo, "Gemini Robotics ER")} == {"manual:1"}


def test_merge_survives_later_singular_evidence(repo):
    # V04: a stored selector keeps matching after the plural fold changes the base keys.
    publish(repo, D - timedelta(days=2),
            ("a", [("Gemini Agents", "product", None, "primary", False)]),
            ("b", [("Gemini Studio", "product", None, "primary", False)]),
            ("c", [("Orion Tools", "product", None, "primary", False)]),
            ("d", [("Helix", "product", None, "primary", False)]))
    recompute(repo)
    merge_entities(repo, entity_id(repo, "auto:artifact:geminiagents"),
                   entity_id(repo, "auto:artifact:geministudio"))
    merge_entities(repo, entity_id(repo, "auto:artifact:helix"),
                   entity_id(repo, "auto:artifact:oriontools"))
    recompute(repo)
    publish(repo, D, ("e", [("Gemini agent", "product", None, "primary", False)]),
            ("f", [("Orion Tool", "product", None, "primary", False)]))
    recompute(repo)
    assert {key for _, key in owners(repo, "Gemini Agents") + owners(repo, "Gemini agent")
            + owners(repo, "Gemini Studio")} == {"manual:1"}
    assert {key for _, key in owners(repo, "Orion Tools") + owners(repo, "Orion Tool")
            + owners(repo, "Helix")} == {"manual:2"}
    with pytest.raises(OverrideConflict):
        repo.add_override(kind="merge", type_group_="artifact", match_key="geminiagent",
                          target_base_key="helix")
