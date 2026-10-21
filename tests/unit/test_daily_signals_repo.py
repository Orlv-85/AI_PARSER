import json
import random
import time
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.core.canonicalize import canonical_url_hash
from app.core.daily.signals_extract import ExtractedEntity, Extraction
from app.storage import daily_signals as module
from app.storage.daily_signals import DailySignalRepo, OverrideConflict
from app.storage.models_sql import (
    AIEntity,
    Article,
    ArticleSignal,
    Base,
    DailySignalReport,
    DailySignalScope,
    NewsDigestItem,
    SignalMention,
)
from app.storage.repos import ArticleRepo, NewsDigestRepo

COMPARABLE_FROM = date(2026, 10, 10)
D = date(2026, 10, 16)
NOW = datetime(2026, 10, 17, 3, tzinfo=UTC)


@pytest.fixture(name="session")
def session_fixture(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'signals.db'}")

    @event.listens_for(engine, "connect")
    def _fk(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    engine.dispose()


@pytest.fixture(name="repo")
def repo_fixture(session):
    return DailySignalRepo(session, comparable_from=COMPARABLE_FROM)


def add_article(session, url, *, title=None, published=None):
    article = Article(title=title or f"Title {url}", url=url, url_canonical=url,
                      url_canonical_hash=canonical_url_hash(url), content="Body",
                      published_at=published or datetime(2026, 10, 16, 9, tzinfo=UTC))
    session.add(article)
    session.flush()
    return article


def digest(session, day, *urls):
    NewsDigestRepo(session).save_digest(report_date=day, groups=[{
        "title": "Models & Research",
        "items": [{"title": f"Item {u}", "summary": "s", "url": u} for u in urls]}])


def extraction(*entities, event_type="model_release"):
    return Extraction(event_type=event_type, novelty_claim=True, entities=tuple(
        ExtractedEntity(name=n, canonical_name=n, entity_type=t, vendor=None, role=r,
                        is_new=new, novelty_quote=f"Today we launch {n}" if new else None)
        for n, t, r, new in entities))


def model(name, new=False, role="primary"):
    return (name, "model", role, new)


def mentions(session, article_id=None):
    stmt = select(SignalMention).order_by(SignalMention.scope_day, SignalMention.name_key)
    if article_id is not None:
        stmt = stmt.where(SignalMention.article_id == article_id)
    return [(m.scope_day, m.name_key, m.extraction_version) for m in session.scalars(stmt)]


# Membership and coverage ---------------------------------------------------------------------

def test_membership_exact_canonical_and_unmatched(session, repo):
    a = add_article(session, "https://a.com/1")
    b = add_article(session, "https://b.org/2")
    c = add_article(session, "https://c.net/3?x=1")
    digest(session, D, "https://a.com/1", "https://b.org/2", "https://c.net/3?utm_source=z&x=1",
           "https://nowhere.example/4")
    assert repo.replace_membership(D)
    rows = {r.article_id: r for r in session.scalars(select(DailySignalScope))}
    assert set(rows) == {a.id, b.id, c.id}
    assert rows[a.id].publisher == "a.com" and rows[a.id].kind == "signals"
    assert rows[c.id].item_url == "https://c.net/3?utm_source=z&x=1"
    coverage = repo.coverage()[D]
    assert (coverage.items, coverage.matched, coverage.extracted) == (4, 3, 0)


def test_missing_and_empty_days(session, repo):
    assert not repo.replace_membership(D)
    assert D not in repo.coverage()
    digest(session, D)
    assert repo.replace_membership(D)
    coverage = repo.coverage()[D]
    assert coverage.published and coverage.items == 0 and coverage.complete()


def test_kind_by_comparable_from(session, repo):
    article = add_article(session, "https://a.com/1")
    old = date(2026, 10, 5)
    digest(session, old, article.url)
    digest(session, D, article.url)
    repo.replace_membership(old)
    repo.replace_membership(D)
    kinds = dict(session.execute(select(DailySignalScope.scope_day, DailySignalScope.kind)).all())
    assert kinds == {old: "history", D: "signals"}
    assert repo.coverage()[old].kind == "history"


def test_republished_digest_drops_article_from_that_day_only(session, repo):
    a = add_article(session, "https://a.com/1")
    b = add_article(session, "https://b.com/2")
    other = D - timedelta(days=1)
    digest(session, other, a.url)
    digest(session, D, a.url, b.url)
    repo.replace_membership(other)
    repo.replace_membership(D)
    repo.save_extraction(a, extraction(model("Atlas")), content_hash="h1")
    assert mentions(session, a.id) == [(other, "atlas", module.EXTRACTION_VERSION),
                                       (D, "atlas", module.EXTRACTION_VERSION)]
    digest(session, D, b.url)
    repo.replace_membership(D)
    assert mentions(session, a.id) == [(other, "atlas", module.EXTRACTION_VERSION)]
    assert session.scalar(select(func.count(NewsDigestItem.id))) == 2
    digest(session, D, a.url, b.url)
    repo.replace_membership(D)
    assert len(mentions(session, a.id)) == 2


# Extractions and evidence --------------------------------------------------------------------

def test_cache_by_content_hash_and_failures(session, repo):
    article = add_article(session, "https://a.com/1")
    digest(session, D, article.url)
    repo.replace_membership(D)
    assert repo.get_cached(article, "h1") is None
    repo.save_failure(article, content_hash="h1", status="failed", reason="unknown")
    assert repo.coverage()[D].failed == 1
    repo.save_extraction(article, extraction(model("Atlas")), content_hash="h1")
    assert repo.get_cached(article, "h1") is not None
    assert repo.get_cached(article, "h2") is None
    row = repo.get_signal(article)
    assert (row.attempts, row.status, row.event_type) == (2, "ok", "model_release")
    assert json.loads(row.payload)["entities"][0]["name"] == "Atlas"
    assert repo.coverage()[D].extracted == 1
    with pytest.raises(ValueError):
        repo.save_failure(article, content_hash="h1", status="ok", reason="x")


def test_reextraction_replaces_all_days_of_that_version(session, repo):
    article = add_article(session, "https://a.com/1")
    for day in (D - timedelta(days=1), D):
        digest(session, day, article.url)
        repo.replace_membership(day)
    repo.save_extraction(article, extraction(model("Atlas"), model("Bravo")), content_hash="h1")
    repo.save_extraction(article, extraction(model("Charlie")), content_hash="h2")
    assert [k for _, k, _ in mentions(session, article.id)] == ["charlie", "charlie"]


def test_reused_article_id_leaves_old_evidence(session, repo):
    old = add_article(session, "https://a.com/old")
    digest(session, D, old.url)
    repo.replace_membership(D)
    repo.save_extraction(old, extraction(model("Atlas")), content_hash="h1")
    old_id, old_hash = old.id, old.url_canonical_hash
    session.delete(old)
    session.flush()
    reused = Article(id=old_id, title="New", url="https://b.com/new", url_canonical="https://b.com/new",
                     url_canonical_hash=canonical_url_hash("https://b.com/new"), content="x")
    session.add(reused)
    session.flush()
    digest(session, D, reused.url)
    repo.replace_membership(D)
    repo.save_extraction(reused, extraction(model("Bravo")), content_hash="h2")
    rows = {(m.url_canonical_hash, m.name_key) for m in session.scalars(select(SignalMention))}
    assert rows == {(old_hash, "atlas"), (reused.url_canonical_hash, "bravo")}
    with pytest.raises(ValueError):
        repo.purge_evidence(old_id)


def test_evidence_uses_newest_ok_version_with_fallback(session, repo, monkeypatch):
    monkeypatch.setattr(module, "EXTRACTION_VERSIONS", ("v-old", "v-new"))
    a = add_article(session, "https://a.com/1")
    b = add_article(session, "https://b.com/2")
    digest(session, D, a.url, b.url)
    repo.replace_membership(D)
    for article in (a, b):
        repo.save_extraction(article, extraction(model("Old Name")), content_hash="h",
                             version="v-old")
    repo.save_extraction(a, extraction(model("New Name")), content_hash="h", version="v-new")
    evidence, _ = repo.load_evidence()
    assert sorted((m.article_id, m.canonical_name) for m in evidence) == [
        (a.id, "New Name"), (b.id, "Old Name")]


def test_reconciliation_persists_stable_ids_and_inactive(session, repo):
    a = add_article(session, "https://a.com/1")
    digest(session, D, a.url)
    repo.replace_membership(D)
    repo.save_extraction(a, extraction(model("Atlas"), model("Bravo")), content_hash="h1")
    repo.recompute_reports(D, now=NOW)
    ids = dict(session.execute(select(AIEntity.entity_key, AIEntity.id)).all())
    repo.save_extraction(a, extraction(model("Atlas")), content_hash="h2")
    repo.recompute_reports(D, now=NOW)
    rows = {e.entity_key: e for e in session.scalars(select(AIEntity))}
    assert rows["auto:artifact:atlas"].id == ids["auto:artifact:atlas"]
    assert rows["auto:artifact:atlas"].active and not rows["auto:artifact:bravo"].active
    assert {m.entity_key for m in session.scalars(select(SignalMention))} == {"auto:artifact:atlas"}


def test_overrides_stored_applied_refused_and_deleted(session, repo):
    a = add_article(session, "https://a.com/1")
    b = add_article(session, "https://b.com/2")
    digest(session, D - timedelta(days=3), a.url)
    digest(session, D, b.url)
    repo.replace_membership(D - timedelta(days=3))
    repo.replace_membership(D)
    repo.save_extraction(a, extraction(model("GPT-6")), content_hash="h")
    repo.save_extraction(b, extraction(model("GPT-6 Astra", new=True)), content_hash="h")
    repo.recompute_reports(D, now=NOW)
    assert [i["name"] for i in json.loads(repo.get_report(D).payload)["new"]] == ["GPT-6 Astra"]
    row = repo.add_override(kind="alias", type_group_="artifact", match_key="gpt6astra",
                            target_base_key="gpt6")
    assert row.target_entity_key == f"manual:{row.id}"
    repo.recompute_reports(D, now=NOW)
    assert json.loads(repo.get_report(D).payload)["new"] == []
    assert {m.entity_key for m in session.scalars(select(SignalMention))} == {row.target_entity_key}
    with pytest.raises(OverrideConflict):
        repo.add_override(kind="merge", type_group_="artifact", match_key="gpt6",
                          target_base_key="gpt7")
    with pytest.raises(OverrideConflict):
        repo.add_override(kind="alias", type_group_="artifact", match_key="gpt6astra",
                          target_base_key="gpt6")
    second = repo.add_override(kind="merge", type_group_="artifact", match_key="gpt6sol",
                               target_base_key="gpt6")
    assert second.target_entity_key == row.target_entity_key
    assert repo.delete_override(row.id) and not repo.delete_override(row.id)
    repo.recompute_reports(D, now=NOW)
    assert [i["name"] for i in json.loads(repo.get_report(D).payload)["new"]] == ["GPT-6 Astra"]


# first_seen and retention --------------------------------------------------------------------

def first_seen(session):
    return dict(session.execute(select(AIEntity.entity_key, AIEntity.first_seen_day)
                                .where(AIEntity.active)).all())


def test_first_seen_independent_of_insertion_order(tmp_path):
    results = []
    for seed in range(3):
        engine = create_engine(f"sqlite:///{tmp_path / f'order{seed}.db'}")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            repo = DailySignalRepo(session, comparable_from=COMPARABLE_FROM)
            days = [D - timedelta(days=i) for i in range(4)]
            random.Random(seed).shuffle(days)
            for i, day in enumerate(days):
                article = add_article(session, f"https://p{i}.com/{day}")
                digest(session, day, article.url)
                repo.replace_membership(day)
                repo.save_extraction(article, extraction(model("Atlas"), model(f"Only {day}")),
                                     content_hash="h")
            repo.recompute_reports(D, now=NOW)
            results.append(first_seen(session))
        engine.dispose()
    assert results[0] == results[1] == results[2]
    assert results[0]["auto:artifact:atlas"] == D - timedelta(days=3)


def test_correction_moves_first_seen_later(session, repo):
    a = add_article(session, "https://a.com/1")
    b = add_article(session, "https://b.com/2")
    early = D - timedelta(days=2)
    digest(session, early, a.url)
    digest(session, D, b.url)
    repo.replace_membership(early)
    repo.replace_membership(D)
    repo.save_extraction(a, extraction(model("Atlas")), content_hash="h")
    repo.save_extraction(b, extraction(model("Atlas")), content_hash="h")
    repo.recompute_reports(D, now=NOW)
    assert first_seen(session)["auto:artifact:atlas"] == early
    repo.save_extraction(a, extraction(model("Bravo")), content_hash="h2")
    repo.recompute_reports(D, now=NOW)
    assert first_seen(session)["auto:artifact:atlas"] == D


def test_prune_keeps_evidence_and_first_seen_then_purge(session, repo):
    old = add_article(session, "https://a.com/old", published=datetime(2020, 1, 1, tzinfo=UTC))
    new = add_article(session, "https://b.com/new")
    early = D - timedelta(days=2)
    digest(session, early, old.url)
    digest(session, D, new.url)
    repo.replace_membership(early)
    repo.replace_membership(D)
    repo.save_extraction(old, extraction(model("Atlas")), content_hash="h")
    repo.save_extraction(new, extraction(model("Atlas", new=True)), content_hash="h")
    repo.recompute_reports(D, now=NOW)
    old_id = old.id
    deleted, _ = ArticleRepo(session).prune_older_than(older_than_days=365)
    session.flush()
    session.expire_all()
    assert deleted == 1
    assert session.scalar(select(func.count(ArticleSignal.id))) == 1
    assert session.scalar(select(func.count(DailySignalScope.id))) == 1
    assert len(mentions(session, old_id)) == 1
    repo.recompute_reports(D, now=NOW)
    assert first_seen(session)["auto:artifact:atlas"] == early
    assert json.loads(repo.get_report(D).payload)["new"] == []
    assert repo.purge_evidence(old_id) == 1
    repo.recompute_reports(D, now=NOW)
    assert first_seen(session)["auto:artifact:atlas"] == D
    assert [i["name"] for i in json.loads(repo.get_report(D).payload)["new"]] == ["Atlas"]


def test_version_bump_of_one_day_keeps_other_reports(session, repo, monkeypatch):
    monkeypatch.setattr(module, "EXTRACTION_VERSIONS", ("v1", "v2"))
    days = [D - timedelta(days=i) for i in range(3)]
    articles = {}
    for day in days:
        articles[day] = add_article(session, f"https://p.com/{day}")
        digest(session, day, articles[day].url)
        repo.replace_membership(day)
        repo.save_extraction(articles[day], extraction(model("Atlas"), model(f"Solo {day.day}")),
                             content_hash="h", version="v1")
    repo.recompute_reports(D, now=NOW)
    before = {r.report_date: r.payload_hash for r in session.scalars(select(DailySignalReport))}
    seen = first_seen(session)
    repo.save_extraction(articles[D], extraction(model("Atlas"), model("Solo 16")),
                         content_hash="h", version="v2")
    result = repo.recompute_reports(D, now=NOW)
    assert result.written == [] and first_seen(session) == seen
    after = {r.report_date: r.payload_hash for r in session.scalars(select(DailySignalReport))}
    assert after == before


# Reports and recompute -----------------------------------------------------------------------

def test_recompute_creates_missing_and_rewrites_only_changed(session, repo):
    legacy = date(2026, 10, 5)
    articles = []
    for day in (legacy, D - timedelta(days=1), D):
        article = add_article(session, f"https://p.com/{day}")
        articles.append(article)
        digest(session, day, article.url)
        repo.replace_membership(day)
        repo.save_extraction(article, extraction(model("Atlas")), content_hash="h")
    first = repo.recompute_reports(D, now=NOW)
    assert first.written == [D - timedelta(days=1), D]
    assert repo.get_report(legacy) is None
    second = repo.recompute_reports(D, now=NOW + timedelta(hours=1))
    assert second.written == [] and second.unchanged == 2
    stored = repo.get_report(D)
    payload = json.loads(stored.payload)
    assert stored.status == payload["status"] == "building_history"
    assert payload["novelty_history_days"] == 2
    assert json.loads(stored.coverage) == payload["coverage"]


def test_coverage_only_change_updates_history_note(session, repo):
    old_day = date(2026, 10, 1)
    old = add_article(session, "https://p.com/old")
    other = add_article(session, "https://p.com/other")
    digest(session, old_day, old.url, other.url)
    repo.replace_membership(old_day)
    repo.save_extraction(old, extraction(model("Bravo")), content_hash="h")
    today = add_article(session, "https://p.com/today")
    digest(session, D, today.url)
    repo.replace_membership(D)
    repo.save_extraction(today, extraction(model("Atlas")), content_hash="h")
    repo.recompute_reports(D, now=NOW)
    assert json.loads(repo.get_report(D).payload)["novelty_history_days"] == 0
    repo.save_extraction(other, extraction(model("Charlie")), content_hash="h")
    assert repo.recompute_reports(D, now=NOW).written == [D]
    assert json.loads(repo.get_report(D).payload)["novelty_history_days"] == 1


def test_family_only_change_removes_new_item(session, repo):
    today = add_article(session, "https://p.com/today")
    digest(session, D, today.url)
    repo.replace_membership(D)
    repo.save_extraction(today, extraction(model("Nemotron 3.5 Bolt 74B-A9B", new=True)),
                         content_hash="h")
    repo.recompute_reports(D, now=NOW)
    assert len(json.loads(repo.get_report(D).payload)["new"]) == 1
    early = D - timedelta(days=3)
    old = add_article(session, "https://p.com/old")
    digest(session, early, old.url)
    repo.replace_membership(early)
    repo.save_extraction(old, extraction(model("Nemotron 3.5 Bolt 74B")), content_hash="h")
    assert D in repo.recompute_reports(D, now=NOW).written
    assert json.loads(repo.get_report(D).payload)["new"] == []


def test_recompute_bound_and_all_days(session, repo):
    days = [date(2026, 10, 10), date(2027, 11, 20)]
    for day in days:
        article = add_article(session, f"https://p.com/{day}")
        digest(session, day, article.url)
        repo.replace_membership(day)
        repo.save_extraction(article, extraction(model("Atlas")), content_hash="h")
    assert repo.recompute_reports(days[1], now=NOW).written == [days[1]]
    assert repo.recompute_reports(days[1], now=NOW, all_days=True).written == [days[0]]


def test_save_report_integrity_error_path(session, repo, monkeypatch):
    payload = {"methodology_version": "m", "extraction_version": "e", "status": "ready",
               "thresholds": {}, "coverage": {}}
    repo.save_report(D, payload, "a" * 64)
    real = repo.get_report
    calls = []

    def stale_then_real(day):
        calls.append(day)
        return None if len(calls) == 1 else real(day)

    monkeypatch.setattr(repo, "get_report", stale_then_real)
    row = repo.save_report(D, dict(payload, status="partial"), "b" * 64)
    assert (row.status, row.payload_hash) == ("partial", "b" * 64)
    assert session.scalar(select(func.count(DailySignalReport.id))) == 1


def test_synthetic_year_recompute_time(session, repo, capsys):
    rng = random.Random(7)
    start = date(2026, 10, 10)
    names = [f"Entity {i}" for i in range(400)]
    for offset in range(60):
        day = start + timedelta(days=offset)
        urls = []
        for n in range(20):
            article = add_article(session, f"https://p{n % 9}.com/{day}/{n}")
            urls.append(article.url)
        digest(session, day, *urls)
        repo.replace_membership(day)
        for article in repo.scope_articles(day):
            repo.save_extraction(article, extraction(*[model(n) for n in rng.sample(names, 4)]),
                                 content_hash="h")
    began = time.perf_counter()
    first = repo.recompute_reports(start + timedelta(days=59), now=NOW)
    elapsed = time.perf_counter() - began
    began = time.perf_counter()
    second = repo.recompute_reports(start + timedelta(days=59), now=NOW)
    again = time.perf_counter() - began
    assert len(first.written) == 60 and second.written == []
    with capsys.disabled():
        print(f"\n60 days x 20 articles x 4 mentions: first recompute {elapsed:.2f}s, "
              f"unchanged recompute {again:.2f}s")


def test_reused_article_id_without_fk_enforcement_inherits_nothing(tmp_path):
    # F9: the app does not enable SQLite foreign keys, so an article's scope and extraction rows
    # survive its deletion; a new article that reuses the id must not inherit them.
    engine = create_engine(f"sqlite:///{tmp_path / 'nofk.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = DailySignalRepo(session, comparable_from=COMPARABLE_FROM)
        d1 = D - timedelta(days=2)
        old = add_article(session, "https://a.com/old")
        digest(session, d1, old.url)
        repo.replace_membership(d1)
        repo.save_extraction(old, extraction(model("Atlas")), content_hash="h1")
        old_id = old.id
        session.delete(old)
        session.flush()
        reused = Article(id=old_id, title="New", url="https://b.com/new",
                         url_canonical="https://b.com/new",
                         url_canonical_hash=canonical_url_hash("https://b.com/new"), content="x")
        session.add(reused)
        session.flush()
        digest(session, D, reused.url)
        repo.replace_membership(D)
        assert (repo.coverage()[D].extracted, repo.coverage()[D].pending) == (0, 1)
        assert repo.get_signal(reused) is None
        assert repo.get_cached(reused, "h1") is None
        assert not repo.scope_articles(d1)
        evidence, rows = repo.load_evidence()
        assert {(rows[m.mention_id].url_canonical_hash, m.scope_day) for m in evidence} == {
            (canonical_url_hash("https://a.com/old"), d1)}
        result = repo.recompute_reports(D, now=NOW)
        observed = repo.observations(result.reconciliation, rows, [d1, D])
        assert observed.get(d1, []) == [] and observed.get(D, []) == []
        repo.save_extraction(reused, extraction(model("Bravo")), content_hash="h2")
        assert repo.get_signal(reused).attempts == 1
        assert {(m.scope_day, m.name_key) for m in session.scalars(select(SignalMention).where(
            SignalMention.url_canonical_hash == reused.url_canonical_hash))} == {(D, "bravo")}
    engine.dispose()


def test_newer_ok_extraction_without_entities_supersedes_old_mentions(session, repo,
                                                                     monkeypatch):
    # F10: the newest `ok` extraction decides, even when it has no entities (no mention rows).
    monkeypatch.setattr(module, "EXTRACTION_VERSIONS", ("v-old", "v-new"))
    a = add_article(session, "https://a.com/1")
    digest(session, D, a.url)
    repo.replace_membership(D)
    repo.save_extraction(a, extraction(model("Old Name")), content_hash="h", version="v-old")
    repo.save_extraction(a, extraction(), content_hash="h", version="v-new")
    evidence, _ = repo.load_evidence()
    assert evidence == []


def test_title_only_history_suppresses_new_through_digest_text(session, repo):
    # F19: the history article was extracted to nothing, but its digest title names the laptop.
    hist = add_article(session, "https://h.com/1", title="RTX Spark laptops")
    digest(session, date(2026, 10, 7), hist.url)
    item = session.scalar(select(NewsDigestItem).where(NewsDigestItem.url == hist.url))
    item.summary = "Microsoft shows the Surface Laptop Ultra."
    repo.replace_membership(date(2026, 10, 7))
    repo.save_extraction(hist, extraction(), content_hash="h")
    a = add_article(session, "https://a.com/1")
    digest(session, D, a.url)
    repo.replace_membership(D)
    repo.save_extraction(a, extraction(("Surface Laptop Ultra", "hardware", "primary", True)),
                         content_hash="h")
    repo.recompute_reports(D, now=NOW)
    payload = json.loads(repo.get_report(D).payload)
    assert payload["new"] == []
    assert payload["new_suppressed"][0]["day"] == "2026-10-07"



def test_lexical_history_reads_digest_text_not_article_summaries(session, repo):
    # F19 decision: only what we published (digest item title and summary) counts; an RSS summary
    # of an in-scope article that names the entity does not suppress New.
    hist = add_article(session, "https://h.com/1", title="Meta roadmap")
    hist.summary = "Meta says the Muse Spark Open release ships soon."
    digest(session, date(2026, 9, 3), hist.url)
    repo.replace_membership(date(2026, 9, 3))
    repo.save_extraction(hist, extraction(), content_hash="h")
    a = add_article(session, "https://a.com/1")
    digest(session, D, a.url)
    repo.replace_membership(D)
    repo.save_extraction(a, extraction(model("Muse Spark Open", True)), content_hash="h")
    repo.recompute_reports(D, now=NOW)
    payload = json.loads(repo.get_report(D).payload)
    assert [i["name"] for i in payload["new"]] == ["Muse Spark Open"]


# 007 ----------------------------------------------------------------------------------------

def test_observations_carry_the_digest_summary_of_that_day(session, repo):
    shared = add_article(session, "https://a.com/1")
    other = add_article(session, "https://b.com/2")
    for day, summary in ((D - timedelta(days=1), "Day one text."), (D, "Day two text.")):
        NewsDigestRepo(session).save_digest(report_date=day, groups=[{"title": "Models", "items": [
            {"title": "A", "summary": summary, "url": shared.url},
            {"title": "B", "summary": None if day == D else "", "url": other.url}]}])
        repo.replace_membership(day)
    for article in (shared, other):
        repo.save_extraction(article, extraction(model("Atlas")), content_hash="h")
    evidence, rows = repo.load_evidence()
    result = module.reconcile(evidence, repo.overrides())
    repo.apply_reconciliation(result, rows)
    obs = repo.observations(result, rows, [D - timedelta(days=1), D])
    summaries = {(d, o.url): o.summary for d, items in obs.items() for o in items}
    # N1: save_digest stores a None summary as the string "None"; 007 reads it as "".
    assert session.scalar(select(NewsDigestItem.summary).where(
        NewsDigestItem.url == other.url).order_by(NewsDigestItem.id.desc())) == "None"
    assert summaries == {(D - timedelta(days=1), shared.url): "Day one text.",
                         (D - timedelta(days=1), other.url): "",
                         (D, shared.url): "Day two text.", (D, other.url): ""}
    items = repo.digest_items(D)
    assert [(i["url"], i["summary"], i["publisher"]) for i in items] == [
        (shared.url, "Day two text.", "a.com"), (other.url, "", "b.com")]
    assert repo.digest_items(D + timedelta(days=1)) == []


def test_save_brief_upserts_by_day(session, repo):
    assert repo.get_brief(D) is None
    first = repo.save_brief(D, brief_version="v", model="m", input_hash="h1", status="invalid",
                            payload={}, reason="schema,schema")
    session.commit()
    second = repo.save_brief(D, brief_version="v", model="m", input_hash="h2", status="ok",
                             payload={"sentences": [{"text": "x", "links": [], "quote": "q"}]})
    session.commit()
    assert first.id == second.id
    row = repo.get_brief(D)
    assert (row.input_hash, row.status, row.reason) == ("h2", "ok", None)
    assert json.loads(row.payload)["sentences"][0]["quote"] == "q"
    with pytest.raises(ValueError):
        repo.save_brief(D, brief_version="v", model="m", input_hash="h", status="bad", payload={})
