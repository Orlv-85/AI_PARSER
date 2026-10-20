import hashlib
import json
from datetime import UTC, datetime
from logging import getLogger

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config.settings import Settings
from app.config.sources import SourceConfig
from app.core.admission import bounded_evidence, evidence_hash
from app.core.categories import CATEGORY_CRITERIA
from app.core.jev import JevAssessment, JevRelevanceScorer, jev_relevance_scorer
from app.core.models import Article
from app.core.pipeline import _build_article_row, run_fetch_cycle
from app.core.reenrich_pilot import source_state
from app.core.scoring import ai_relevance_score
from app.ingest.html import HtmlListPageResult
from app.ingest.rss import RssFetchResult, _with_rss_metadata
from app.storage.models_sql import Article as StoredArticle
from app.storage.models_sql import Base
from app.storage.weekly import fingerprint


def _article(index: int = 1) -> Article:
    return Article(
        source_key="test", title=f"AI model release {index}",
        url=f"https://example.com/{index}", published_at=datetime.now(UTC),
        summary="New language model weights", content="A new model is available.",
    )


def test_jev_request_scores_zero_and_reuses_bounded_text() -> None:
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"answers": {"ai_relevant": {"noul": 0.0}}})

    article = _article().model_copy(update={
        "title": "t" * 2000, "summary": "s" * 5000, "content": "c" * 20000,
    })
    with httpx.Client(
        transport=httpx.MockTransport(respond), headers={"Authorization": "Bearer test-key"},
    ) as client:
        scorer = JevRelevanceScorer(client, "jev-1.13.0", getLogger("jev-test"))
        assert scorer.score(article) == 0.0
        assert scorer.score(article.model_copy(update={"url": "https://example.com/alias"})) == 0.0
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://api.typesafe.ai/v1/systemone"
    assert request.headers["Authorization"] == "Bearer test-key"
    payload = json.loads(request.content)
    assert payload["model"] == "jev-1.13.0"
    assert payload["questions"]["ai_relevant"]["type"] == "noul"
    assert payload["questions"]["category"]["type"] == "choice"
    assert set(payload["questions"]["category"]["criteria"]) == {*CATEGORY_CRITERIA, "Other"}
    assert payload["state"] == "Title: " + "t" * 1024 + "\nSummary: " + "s" * 4000 + (
        "\nContent: " + "c" * 16000
    )


@pytest.mark.parametrize("failure", [
    "timeout", "401", "429", "500", "invalid_json", "missing_answer",
    "wrong_type", "string", "bool", "negative", "above_one", "nan",
])
def test_jev_failure_stops_requests_and_does_not_log_secrets(failure, caplog) -> None:
    calls = []

    def respond(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("test-secret", request=request)
        if failure.isdigit():
            return httpx.Response(int(failure), text="test-secret")
        if failure == "invalid_json":
            return httpx.Response(200, text="test-secret")
        if failure == "missing_answer":
            return httpx.Response(200, json={"answers": {}})
        if failure == "wrong_type":
            return httpx.Response(200, json=[])
        values = {"string": "0.9", "bool": True, "negative": -0.1, "above_one": 1.1}
        if failure == "nan":
            return httpx.Response(200, text='{"answers":{"ai_relevant":{"noul":NaN}}}')
        return httpx.Response(200, json={"answers": {"ai_relevant": {"noul": values[failure]}}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        scorer = JevRelevanceScorer(client, "jev-1.13.0", getLogger("jev-test"))
        assert scorer.score(_article()) is None
        assert scorer.score(_article(2)) is None
    assert len(calls) == 1
    assert "jev_relevance_fallback" in caplog.text
    assert "test-secret" not in caplog.text


@pytest.mark.parametrize("enabled,key", [(False, "unused-key"), (True, None), (True, " ")])
def test_jev_disabled_or_missing_key_never_opens_client(enabled, key, monkeypatch) -> None:
    def unexpected_client(**_kwargs):
        pytest.fail("HTTP client must not be created")

    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("AINEWS_JEV_API_KEY", raising=False)
    settings = Settings(jev_enabled=enabled, jev_api_key=key, _env_file=None)
    monkeypatch.setattr("app.core.jev.httpx.Client", unexpected_client)
    with jev_relevance_scorer(settings, getLogger("jev-test")) as scorer:
        assert scorer is None


@pytest.mark.parametrize("category,confidence,accepted", [
    ("AI Coding", 0.99, True),
    ("Agent Frameworks", 0.7, True),
    ("RAG & Data Systems", 1.0, True),
    ("Security", 0.69, False),
    ("QA & Observability", 0.0, False),
    ("Infrastructure", 0.95, True),
    ("Business & Product", 0.9, True),
    ("Other", 1.0, False),
    ("Invented category", 1.0, False),
    ("AI Coding", "0.99", False),
    ("AI Coding", True, False),
    ("AI Coding", -0.1, False),
    ("AI Coding", 1.1, False),
])
def test_jev_category_confidence_gate_keeps_valid_relevance(category, confidence, accepted) -> None:
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"answers": {
            "ai_relevant": {"noul": 0.8},
            "category": {"choice": category, "confidence": confidence},
        }})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        scorer = JevRelevanceScorer(client, "jev-1.13.0", getLogger("jev-test"))
        result = scorer.classify(_article())
        assert result is not None
        assert result.relevance_score == 0.8
        assert result.category == (category if accepted else None)
        assert result.category_confidence == (confidence if accepted else None)
        assert scorer.classify(_article().model_copy(update={"published_at": None})) == result
        assert scorer.score(_article()) == 0.8
        assert not scorer.failed
    assert len(requests) == 1


def test_jev_category_threshold_is_configurable() -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(
        200, json={"answers": {
            "ai_relevant": {"noul": 0.8},
            "category": {"choice": "AI Coding", "confidence": 0.9},
        }},
    ))) as client:
        scorer = JevRelevanceScorer(client, "jev-1.13.0", getLogger("jev-test"), 0.95)
        result = scorer.classify(_article())
        assert result is not None
        assert result.category is None


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("source_type", ["rss", "html"])
@pytest.mark.parametrize("api_failure", [False, True])
def test_ingestion_persists_jev_score_or_heuristic_on_failure(
    tmp_path, monkeypatch, batch, source_type, api_failure,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path}/jev.db")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    config = SourceConfig(
        id="test", name="Test", type=source_type, url="https://example.com/feed",
        html={} if source_type == "html" else None,
    )
    articles = [_article(), _article(2)]
    result = (
        HtmlListPageResult(links=[str(item.url) for item in articles])
        if source_type == "html" else _with_rss_metadata(articles, RssFetchResult(
            items=articles, not_modified=False, status_code=200, etag=None, last_modified=None,
        ))
    )
    requests = []
    clients = []
    real_client = httpx.Client

    def respond(request):
        requests.append(request)
        if api_failure:
            return httpx.Response(503)
        return httpx.Response(200, json={"answers": {
            "ai_relevant": {"noul": 0.0},
            "category": {"choice": "AI Coding", "confidence": 0.98},
        }})

    def create_client(**kwargs):
        clients.append(real_client(transport=httpx.MockTransport(respond), **kwargs))
        return clients[-1]

    def fetch_article(*, url, **_kwargs):
        return next(item for item in articles if str(item.url) == url)

    monkeypatch.setattr("app.core.jev.httpx.Client", create_client)
    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: [config])
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", sessions)
    monkeypatch.setattr(
        "app.core.pipeline._collect_fetched_items", lambda **_kwargs: ({0: result}, 0),
    )
    monkeypatch.setattr("app.core.pipeline.fetch_html_article", fetch_article)
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("AINEWS_JEV_API_KEY", raising=False)
    settings = Settings(
        jev_enabled=True, jev_api_key="test-key", article_batch_upsert_enabled=batch,
        _env_file=None,
    )
    summary = run_fetch_cycle(settings=settings, logger=getLogger("jev-pipeline-test"))
    assert summary.new == 2
    assert summary.errors == 0
    assert len(requests) == (1 if api_failure else 2)
    assert len(clients) == 1
    assert clients[0].is_closed
    with sessions() as session:
        stored = list(session.scalars(select(StoredArticle).order_by(StoredArticle.url)))
        assert len(stored) == 2
        for item, article in zip(stored, articles, strict=True):
            expected = ai_relevance_score(article) if api_failure else 0.0
            assert item.ai_relevance_score == expected
            assert item.category == (None if api_failure else "AI Coding")
            assert item.category_confidence == (None if api_failure else 0.98)
            assert item.rank_score == pytest.approx(
                0.6 * item.freshness_score + 0.3 * expected + 0.1 * config.source_weight,
            )
    # Already stored RSS/HTML items must not trigger another paid request.
    requests.clear()
    repeated = run_fetch_cycle(settings=settings, logger=getLogger("jev-pipeline-test"))
    assert repeated.new == 0
    assert repeated.duplicates == 2
    assert not requests


# Bounded text sent to Jev, pinned byte for byte (sha256 of the UTF-8 text) per mode.
PINNED_ARTICLE = {
    "title": "AI été " * 150,
    "summary": "Summary line. " * 300,
    "content": "Contenu étendu. " * 1100,
}
PINNED_TEXT = {
    "admission": "1d5da0677f4673412268c107ea26c5bebb1a0e9c961b04a1122372d7c014b236",
    "daily_enrichment": "d9dab80771cb3908a45b5094fce3a4de5fbc7866652f22bfcacca685a9085bea",
    "plain": "1d5da0677f4673412268c107ea26c5bebb1a0e9c961b04a1122372d7c014b236",
    "admission_empty": "73358b694ace7d401bc6f09c3f381a9cadf964c985785ff927cfa0f210d3ba93",
}


def _pinned_article(**update) -> Article:
    return _article().model_copy(update={**PINNED_ARTICLE, **update})


def _sent_state(article: Article, *, admission: bool, daily: bool) -> str:
    states: list[str] = []

    def respond(request):
        states.append(json.loads(request.content)["state"])
        return httpx.Response(200, json={"answers": {
            "ai_relevant": {"noul": 0.9},
            "admission": {"choice": "accepted_ai_editorial", "confidence": 0.9},
        }})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        JevRelevanceScorer(
            client, "jev-1.13.0", getLogger("jev-test"), semantic_admission_enabled=admission,
            daily_enrichment_enabled=daily,
        ).classify(article)
    assert len(states) == 1
    return states[0]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.mark.parametrize("mode", ["admission", "daily_enrichment", "plain", "admission_empty"])
def test_bounded_jev_text_is_pinned_per_mode(mode) -> None:
    article = (_pinned_article(summary=None, content=None) if mode == "admission_empty"
               else _pinned_article())
    if mode.startswith("admission"):
        sent = _sent_state(article, admission=True, daily=False)
        # The admission cache key hashes the same text that is sent.
        assert bounded_evidence(article) == sent
        assert evidence_hash(bounded_evidence(article)) == _sha(sent)
    elif mode == "daily_enrichment":
        sent = _sent_state(article, admission=True, daily=True)
        # Evidence for the cache key keeps the summary in every mode.
        assert _sha(bounded_evidence(article)) == PINNED_TEXT["admission"]
        row = _build_article_row(
            item=article, config=SourceConfig(id="test", name="Test", type="rss",
                                              url="https://example.com/feed"),
            db_source_id=1, canonical="c", canonical_hash="h", admission_enabled=True,
            assessment=JevAssessment(0.9, None, None, "accepted_ai_editorial", 0.9,
                                     "NotComparison", 0.9),
        )
        assert row is not None
        provenance = json.loads(str(row["enrichment_provenance"]))
        assert provenance["admission_source_hash"] == fingerprint(sent)
        assert sent == source_state({"title": article.title, "content": article.content})
    else:
        sent = _sent_state(article, admission=False, daily=False)
    assert _sha(sent) == PINNED_TEXT[mode]
