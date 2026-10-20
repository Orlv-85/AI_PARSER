import json
from contextlib import contextmanager
from datetime import UTC, datetime
from logging import getLogger
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.config.settings import Settings
from app.config.sources import SourceConfig
from app.core.canonicalize import canonical_url_hash
from app.core.jev import JevRelevanceScorer
from app.core.models import Article
from app.core.pipeline import HtmlLinkFetchResult, run_fetch_cycle
from app.ingest.html import fetch_html_article
from app.storage.admission import PAUSED_MESSAGE, set_collection_paused
from app.storage.models_sql import (
    AdmissionDecision,
    Base,
    CollectionStatus,
    Source,
    WeeklyCoverageAttempt,
    WeeklyInputObservation,
)
from app.storage.models_sql import Article as StoredArticle
from app.storage.reenrich_pilot_journal import PilotJournal


class Scenario:  # pylint: disable=too-many-instance-attributes
    def __init__(self, tmp_path, monkeypatch, source_type, batch):
        engine = create_engine(f"sqlite:///{tmp_path}/scenario.db")
        Base.metadata.create_all(engine)
        self.sessions = sessionmaker(bind=engine, autoflush=False)
        self.source_type = source_type
        self.settings = Settings(
            _env_file=None, jev_enabled=True, jev_api_key="test-key",
            semantic_admission_enabled=True, weekly_v2_enabled=False,
            auth_enabled=False, respect_robots_txt=False,
            rss_known_streak_stop=0, html_known_streak_stop=0,
            article_batch_upsert_enabled=batch,
        )
        self.configs = [SourceConfig(
            id="s1", name="s1", type="rss" if source_type == "rss" else "html",
            url="https://example.com/feed",
            html={} if source_type != "rss" else None,
        )]
        self.items = [Article(
            source_key="s1", title=f"AI research release {i}",
            url=f"https://example.com/story-{i}",
            published_at=datetime(2026, 10, 4, 12, tzinfo=UTC),
            summary=f"Study {i}", content=f"AI is central in research {i}.",
        ) for i in range(1, 4)]
        self.answers = {}
        self.requests = []
        self.fetches = []
        self.body_fetches = []
        self.fail_at = None
        self.not_modified = False
        monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: self.configs)
        monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
        monkeypatch.setattr("app.core.pipeline.SessionLocal", self.sessions)
        monkeypatch.setattr("app.core.pipeline.jev_relevance_scorer", self.scorer)
        monkeypatch.setattr("app.core.pipeline._collect_fetched_items", self.collect)
        monkeypatch.setattr("app.core.pipeline.fetch_html_article", self.fetch_body)
        monkeypatch.setattr(
            "app.core.pipeline.ai_relevance_score",
            lambda *_: pytest.fail("Keyword fallback is forbidden during admission"),
        )

    @contextmanager
    def scorer(self, *_args):
        def respond(request):
            payload = json.loads(request.content)
            self.requests.append(payload)
            if self.fail_at == len(self.requests):
                return httpx.Response(503)
            title = payload["state"].splitlines()[0][7:]
            answer = self.answers.get(title, {
                "ai_relevant": {"noul": 0.91},
                "category": {"choice": "AI Coding", "confidence": 0.9},
                "admission": {"choice": "accepted_ai_editorial"},
            })
            return httpx.Response(200, json={"answers": answer})

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            yield JevRelevanceScorer(
                client, self.settings.jev_model, getLogger("semantic-test"),
                semantic_admission_enabled=True,
            )

    def collect(self, **kwargs):
        sources = kwargs["enabled_sources"]
        assert len(sources) == 1, "Enabled admission must stop before fetching later sources"
        idx, config, *_ = sources[0]
        self.fetches.append(config.id)
        if self.not_modified:
            result = SimpleNamespace(not_modified=True, status_code=304, items=[])
        elif self.source_type == "two_stage_html":
            result = HtmlLinkFetchResult(
                links=[str(item.url) for item in self.items],
                status_code=200, etag="new-etag", last_modified="new-modified",
            )
        else:
            result = SimpleNamespace(
                items=self.items, status_code=200,
                etag="new-etag", last_modified="new-modified",
            )
        return {idx: result}, 0

    def fetch_body(self, *, url, **_kwargs):
        self.body_fetches.append(url)
        return next(item for item in self.items if str(item.url) == url)

    def run(self):
        return run_fetch_cycle(settings=self.settings, logger=getLogger("semantic-test"))

    def rows(self, model):
        with self.sessions() as session:
            return list(session.scalars(select(model)))


def test_oversized_journal_input_stays_pending_without_pausing_other_articles(
    tmp_path, monkeypatch,
):
    scenario = Scenario(tmp_path, monkeypatch, "rss", False)
    scenario.settings.daily_enrichment_enabled = True
    scenario.items[0].content = "Long non-ASCII source: " + "\u00e9" * 16000
    requests = []

    @contextmanager
    def scorer(*_args):
        def respond(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={"model": "jev-1.13.0",
                "usage": {"input_tokens": 100}, "answers": {
                    "ai_relevant": {"noul": 0.99},
                    "admission": {"choice": "accepted_ai_editorial", "confidence": 0.99},
                    "category": {"choice": "AI Coding", "confidence": 0.99},
                    "comparison": {"choice": "NotComparison", "confidence": 0.99}}})

        journal = PilotJournal(tmp_path / "journal.sqlite3", {"version": "test"},
                               {"total": "2", "jev": "1", "deepseek": "1"})
        with httpx.Client(transport=httpx.MockTransport(respond),
                          headers={"Authorization": "Bearer test-key"}) as client:
            yield JevRelevanceScorer(client, "jev-1.13.0", getLogger("semantic-test"),
                semantic_admission_enabled=True, daily_enrichment_enabled=True,
                payment_journal=journal)
        assert journal.report()["providers"]["jev"]["calls"] == 2
        journal.close()

    monkeypatch.setattr("app.core.pipeline.jev_relevance_scorer", scorer)
    first = scenario.run()
    assert first.new == 2 and first.screening_paused == 0
    assert first.semantic_unresolved == 1
    pending = [row for row in scenario.rows(AdmissionDecision) if row.provider_status == "pending"]
    assert len(pending) == 1
    assert json.loads(pending[0].payload)["candidate"]["url"] == str(scenario.items[0].url)
    assert not any(row.paused for row in scenario.rows(CollectionStatus))
    scenario.run()
    assert len(requests) == 2


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("source_type", ["rss", "legacy_html", "two_stage_html"])
def test_admission_and_cache_all_ingestion_paths(monkeypatch, tmp_path, batch, source_type):
    scenario = Scenario(tmp_path, monkeypatch, source_type, batch)
    scenario.items[0].published_at = None
    for item, choice in zip(scenario.items[1:], ["non_ai", "non_editorial"], strict=True):
        scenario.answers[item.title] = {
            "ai_relevant": {"noul": 1.0},
            "category": {"choice": "AI Coding", "confidence": 0.99},
            "admission": {"choice": choice},
        }
    first = scenario.run()
    assert (first.new, first.semantic_rejected, first.screening_paused) == (1, 2, 0)
    assert len(scenario.rows(WeeklyInputObservation)) == 3
    assert len(scenario.requests) == 3
    second = scenario.run()
    assert (second.new, second.semantic_rejected, second.semantic_cache_hits) == (0, 2, 2)
    assert len(scenario.requests) == 3
    assert len(scenario.rows(StoredArticle)) == 1


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("source_type", ["rss", "legacy_html", "two_stage_html"])
@pytest.mark.parametrize("not_modified", [False, True])
def test_outage_preserves_verified_and_replays_after_list_rotation(
    monkeypatch, tmp_path, batch, source_type, not_modified,
):
    scenario = Scenario(tmp_path, monkeypatch, source_type, batch)
    scenario.configs.append(SourceConfig(
        id="s2", name="s2", type="rss", url="https://other.example/feed",
    ))
    scenario.fail_at = 2
    first = scenario.run()
    assert (first.new, first.screening_paused) == (1, 1)
    assert scenario.fetches == ["s1"]
    assert len(scenario.requests) == 2
    pending = [r for r in scenario.rows(AdmissionDecision) if r.provider_status == "pending"]
    assert len(pending) == 2
    assert len(scenario.rows(StoredArticle)) == 1
    source = next(r for r in scenario.rows(Source) if r.source_key == "s1")
    assert source.etag is None and source.last_modified is None
    status = scenario.rows(CollectionStatus)[0]
    assert status.paused and status.message == PAUSED_MESSAGE
    expected_observed = 2 if source_type == "two_stage_html" else 3
    assert len(scenario.rows(WeeklyInputObservation)) == expected_observed
    attempt = scenario.rows(WeeklyCoverageAttempt)[0]
    # Weekly coverage describes raw acquisition, independently of articles admission.
    assert attempt.complete is (source_type != "two_stage_html")
    assert attempt.outcome == "success"
    scenario.fail_at = None
    scenario.not_modified = not_modified
    old_items = scenario.items
    scenario.items = []
    monkeypatch.setattr("app.core.pipeline.fetch_html_article", lambda *, url, **_: next(
        item for item in old_items if str(item.url) == url
    ))
    scenario.configs = scenario.configs[:1]
    second = scenario.run()
    assert (second.new, second.screening_paused) == (2, 0)
    assert len(scenario.rows(StoredArticle)) == 3
    assert len(scenario.requests) == 4
    assert not [r for r in scenario.rows(AdmissionDecision) if r.provider_status == "pending"]
    assert not scenario.rows(CollectionStatus)[0].paused
    assert len(scenario.rows(WeeklyInputObservation)) == 3


def test_ambiguity_cached_category_independent_and_policy_invalidates(monkeypatch, tmp_path):
    scenario = Scenario(tmp_path, monkeypatch, "rss", False)
    scenario.items = scenario.items[:1]
    item = scenario.items[0]
    scenario.answers[item.title] = {
        "ai_relevant": {"noul": 0.8}, "category": "malformed",
        "admission": {"choice": "insufficient_evidence"},
    }
    assert scenario.run().semantic_unresolved == 1
    assert scenario.run().semantic_cache_hits == 1
    assert len(scenario.requests) == 1
    assert not scenario.rows(StoredArticle)
    assert all(row.outcome == "success" for row in scenario.rows(WeeklyCoverageAttempt))
    scenario.settings.semantic_admission_prompt_version = "changed"
    scenario.answers[item.title]["admission"]["choice"] = "accepted_ai_editorial"
    assert scenario.run().new == 1
    assert scenario.rows(StoredArticle)[0].category is None


@pytest.mark.parametrize("corruption", ["score", "missing_choice", "wrong_choice"])
def test_corrupt_accept_cache_requires_new_assessment(monkeypatch, tmp_path, corruption):
    scenario = Scenario(tmp_path, monkeypatch, "rss", False)
    scenario.items = scenario.items[:1]
    scenario.answers[scenario.items[0].title] = {
        "ai_relevant": {"noul": 0.99},
        "admission": {"choice": "non_editorial"},
    }
    scenario.run()
    with scenario.sessions() as session:
        row = session.scalar(select(AdmissionDecision))
        row.decision = "accept"
        payload = json.loads(row.payload)
        if corruption == "score":
            payload["assessment"]["relevance_score"] = "bad"
        elif corruption == "missing_choice":
            payload["assessment"].pop("admission_choice")
        else:
            payload["assessment"]["admission_choice"] = "non_ai"
        row.payload = json.dumps(payload)
        session.commit()
    assert scenario.run().new == 0
    assert len(scenario.requests) == 2
    assert scenario.rows(AdmissionDecision)[0].decision == "reject"


def test_source_rollback_does_not_clear_prior_notice(monkeypatch, tmp_path):
    scenario = Scenario(tmp_path, monkeypatch, "rss", False)
    with scenario.sessions() as session:
        set_collection_paused(session)
        session.execute(text("CREATE TRIGGER fail_article BEFORE INSERT ON articles "
                             "BEGIN SELECT RAISE(ABORT, 'test rollback'); END"))
        session.commit()
    result = scenario.run()
    assert result.errors == 1 and result.new == 0
    assert not scenario.rows(StoredArticle)
    assert not scenario.rows(AdmissionDecision)
    assert scenario.rows(CollectionStatus)[0].paused
    source = scenario.rows(Source)[0]
    assert source.etag is None and source.last_modified is None


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("failure", ["exception", "parser"])
def test_html_article_failure_retains_retry_and_continues(
    monkeypatch, tmp_path, batch, failure,
):
    scenario = Scenario(tmp_path, monkeypatch, "two_stage_html", batch)
    original_fetch = scenario.fetch_body
    first_url = str(scenario.items[0].url)

    def fetch_body(*, url, **kwargs):
        if url == first_url:
            if failure == "exception":
                raise httpx.ReadTimeout("offline acquisition failure")
            return None
        return original_fetch(url=url, **kwargs)

    monkeypatch.setattr("app.core.pipeline.fetch_html_article", fetch_body)
    result = scenario.run()
    assert result.new == 2 and result.screening_paused == 0
    assert len(scenario.requests) == 2
    pending = [r for r in scenario.rows(AdmissionDecision) if r.provider_status == "pending"]
    assert len(pending) == 1
    assert json.loads(pending[0].payload)["candidate"]["url"] == first_url
    monkeypatch.setattr("app.core.pipeline.fetch_html_article", original_fetch)
    scenario.not_modified = True
    assert scenario.run().new == 1
    assert not [r for r in scenario.rows(AdmissionDecision) if r.provider_status == "pending"]


@pytest.mark.parametrize("batch", [False, True])
def test_confirmed_html_exclusion_settles_before_304(monkeypatch, tmp_path, batch):
    scenario = Scenario(tmp_path, monkeypatch, "two_stage_html", batch)
    url = "https://example.com/products/ai-tool"
    scenario.items = [Article(source_key="s1", title="AI Platform", url=url)]
    downloads = []

    def fetch_text(_fetcher, *, source_id, url):
        assert source_id == "s1"
        downloads.append(url)
        return "<h1>AI Platform</h1><h2>Features</h2><a>Request a demo</a>"

    monkeypatch.setattr("app.core.pipeline.fetch_html_article", fetch_html_article)
    monkeypatch.setattr("app.ingest.fetcher.Fetcher.fetch_text", fetch_text)
    first = scenario.run()
    assert first.new == 0 and first.screening_paused == 0
    assert not [r for r in scenario.rows(AdmissionDecision) if r.provider_status == "pending"]
    attempt = scenario.rows(WeeklyCoverageAttempt)[0]
    assert attempt.outcome == "empty" and attempt.complete
    scenario.not_modified = True
    second = scenario.run()
    assert second.not_modified_sources == 1
    assert downloads == [url]
    assert not scenario.requests
    assert not scenario.rows(StoredArticle)


def test_cache_only_retry_does_not_claim_provider_recovery(monkeypatch, tmp_path):
    scenario = Scenario(tmp_path, monkeypatch, "rss", False)
    scenario.items = scenario.items[:1]
    scenario.answers[scenario.items[0].title] = {
        "ai_relevant": {"noul": 0.9}, "admission": {"choice": "non_ai"},
    }
    scenario.run()
    with scenario.sessions() as session:
        set_collection_paused(session)
        session.commit()
    result = scenario.run()
    assert result.semantic_cache_hits == 1 and result.new == 0
    assert scenario.rows(CollectionStatus)[0].paused
    scenario.not_modified = True
    scenario.run()
    assert scenario.rows(CollectionStatus)[0].paused
    assert len(scenario.requests) == 1


def test_canonical_aliases_share_decision(monkeypatch, tmp_path):
    scenario = Scenario(tmp_path, monkeypatch, "rss", True)
    item = scenario.items[0]
    scenario.items = [item, item.model_copy(update={
        "url": "https://example.com/story-1?utm_source=feed#top",
    })]
    result = scenario.run()
    assert result.new == 1 and result.duplicates == 1
    assert len(scenario.requests) == 1
    assert len(scenario.rows(StoredArticle)) == 1


def test_redirect_identity_survives_pending_body_replay(monkeypatch, tmp_path):
    scenario = Scenario(tmp_path, monkeypatch, "two_stage_html", False)
    scenario.items = scenario.items[:1]
    original = scenario.items[0]
    redirected = original.model_copy(update={"url": "https://example.com/final-story"})
    monkeypatch.setattr("app.core.pipeline.fetch_html_article", lambda **_: redirected)
    scenario.fail_at = 1
    assert scenario.run().screening_paused == 1
    scenario.fail_at = None
    scenario.not_modified = True
    assert scenario.run().new == 1
    stored = scenario.rows(StoredArticle)[0]
    assert stored.url == str(redirected.url)
    assert stored.url_canonical == str(original.url)
    assert len(scenario.rows(WeeklyInputObservation)) == 1


def test_replay_and_fresh_fetch_share_source_savepoint(monkeypatch, tmp_path):
    scenario = Scenario(tmp_path, monkeypatch, "rss", False)
    original = scenario.items[0]
    scenario.items = [original]
    scenario.fail_at = 1
    assert scenario.run().screening_paused == 1
    scenario.fail_at = None
    scenario.items = [original.model_copy(update={
        "title": "AI fresh research", "url": "https://example.com/fresh-failure",
    })]
    with scenario.sessions() as session:
        session.execute(text(
            "CREATE TRIGGER fail_fresh BEFORE INSERT ON articles "
            "WHEN NEW.url LIKE '%fresh-failure' "
            "BEGIN SELECT RAISE(ABORT, 'test rollback'); END"
        ))
        session.commit()
    result = scenario.run()
    assert result.errors == 1 and result.new == 0
    assert not scenario.rows(StoredArticle)
    assert len([r for r in scenario.rows(AdmissionDecision)
                if r.provider_status == "pending"]) == 1
    assert scenario.rows(CollectionStatus)[0].paused
    source = scenario.rows(Source)[0]
    assert source.etag is None and source.last_modified is None


def test_confident_comparison_answer_sets_material_type(monkeypatch, tmp_path):
    scenario = Scenario(tmp_path, monkeypatch, "rss", False)
    scenario.settings.daily_enrichment_enabled = True
    comparisons = dict(zip(
        (item.title for item in scenario.items),
        [("Comparison", 0.9), ("Comparison", 0.5), ("NotComparison", 0.95)],
        strict=True,
    ))

    @contextmanager
    def scorer(*_args):
        def respond(request):
            title = json.loads(request.content)["state"].splitlines()[0][7:]
            choice, confidence = comparisons[title]
            return httpx.Response(200, json={"answers": {
                "ai_relevant": {"noul": 0.9},
                "admission": {"choice": "accepted_ai_editorial", "confidence": 0.9},
                "category": {"choice": "AI Coding", "confidence": 0.9},
                "comparison": {"choice": choice, "confidence": confidence}}})

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            yield JevRelevanceScorer(client, "jev-1.13.0", getLogger("semantic-test"),
                semantic_admission_enabled=True, daily_enrichment_enabled=True)

    monkeypatch.setattr("app.core.pipeline.jev_relevance_scorer", scorer)
    assert scenario.run().new == 3
    material = {row.title: row.material_type for row in scenario.rows(StoredArticle)}
    assert material == {
        scenario.items[0].title: "Comparison",
        scenario.items[1].title: None,
        scenario.items[2].title: None,
    }


def test_pending_replay_is_bounded_by_list_pending_limit(monkeypatch, tmp_path):
    scenario = Scenario(tmp_path, monkeypatch, "rss", False)
    scenario.items = [Article(
        source_key="s1", title=f"AI research release {i}",
        url=f"https://example.com/story-{i}",
        published_at=datetime(2026, 10, 4, 12, tzinfo=UTC),
        summary=f"Study {i}", content=f"AI is central in research {i}.",
    ) for i in range(1, 53)]
    scenario.fail_at = 1
    assert scenario.run().screening_paused == 1
    pending = [r for r in scenario.rows(AdmissionDecision) if r.provider_status == "pending"]
    assert len(pending) == 52
    scenario.fail_at = None
    scenario.items = []
    scenario.not_modified = True
    assert scenario.run().new == 50
    assert len(scenario.requests) == 1 + 50
    pending = [r for r in scenario.rows(AdmissionDecision) if r.provider_status == "pending"]
    assert len(pending) == 2
    assert scenario.run().new == 2
    assert not [r for r in scenario.rows(AdmissionDecision) if r.provider_status == "pending"]


def test_rss_records_known_items_as_weekly_observations(monkeypatch, tmp_path):
    scenario = Scenario(tmp_path, monkeypatch, "rss", False)
    known = scenario.items[0]
    with scenario.sessions() as session:
        session.add(StoredArticle(
            title=known.title, url=str(known.url), url_canonical=str(known.url),
            url_canonical_hash=canonical_url_hash(str(known.url)),
            published_at=known.published_at, ai_relevance_score=0.9,
            freshness_score=0.5, rank_score=0.7,
        ))
        session.commit()
    result = scenario.run()
    assert (result.new, result.duplicates) == (2, 1)
    assert len(scenario.requests) == 2
    observed = {row.canonical_hash for row in scenario.rows(WeeklyInputObservation)}
    assert observed == {canonical_url_hash(str(item.url)) for item in scenario.items}


@pytest.mark.parametrize("failure", ["fetch", "persist"])
def test_admission_coverage_attempt_records_fetch_and_persist_failures(
    monkeypatch, tmp_path, failure,
):
    scenario = Scenario(tmp_path, monkeypatch, "rss", False)
    if failure == "fetch":
        monkeypatch.setattr(
            "app.core.pipeline._collect_fetched_items", lambda **_kwargs: ({}, 1),
        )
    else:
        with scenario.sessions() as session:
            session.execute(text("CREATE TRIGGER fail_article BEFORE INSERT ON articles "
                                 "BEGIN SELECT RAISE(ABORT, 'test rollback'); END"))
            session.commit()
    result = scenario.run()
    assert result.errors == 1 and result.new == 0
    attempts = scenario.rows(WeeklyCoverageAttempt)
    assert [row.outcome for row in attempts] == [f"{failure}_failure"]
    assert attempts[0].complete is (failure == "fetch")
