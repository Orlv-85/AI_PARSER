import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from app.config.settings import Settings
from app.core.weekly_enrichment import BudgetExhausted
from app.core.weekly_topics import TAXONOMY_VERSION, topic_registry


def module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "weekly_historical_preview.py"
    spec = importlib.util.spec_from_file_location("weekly_historical_preview", path)
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def export():
    rows = [{"id": str(i), "article_id": i, "source_id": i, "canonical_hash": str(i),
             "published_at": day, "title": f"AI coding assistant release {i}",
             "summary": "A software development assistant for writing and testing code.",
             "content": None, "publisher": "example.com", "url": f"https://example.com/{i}",
             "publication_provenance": "legacy_unverified"}
            for i, day in enumerate(("2026-09-28T00:00:00+00:00",
                                     "2026-09-21T00:00:00+00:00",
                                     "2026-09-20T23:59:59+00:00"))]
    return {"packets": [{"report_date": "2026-10-04", "observations": rows,
                         "data_cutoff": "2026-10-05T00:00:00+00:00", "input_complete": True,
                         "provider_configuration": {}, "taxonomy_version": TAXONOMY_VERSION,
                         "topics": topic_registry(), "quality_counters": {}}],
            "legacy_reports": [{"report_date": "2026-10-04", "summary": "Original"}]}


def test_prepare_filters_pilot_but_preserves_original_history_and_legacy(tmp_path):
    script = module()
    result = script.prepare(export(), tmp_path, 2)
    assert result["unique_observations"] == 2
    assert result["paid_calls"] == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert len(manifest["packets"][0]["observations"]) == 3
    assert manifest["original_legacy_reports"][0]["summary"] == "Original"
    assert script.prepare(export(), tmp_path, 2) == result
    with pytest.raises(ValueError, match="differs"):
        script.prepare(export(), tmp_path, 3)


def test_total_budget_survives_new_store_and_unknown_usage(tmp_path):
    script = module()
    path = tmp_path / "state.sqlite"
    store = script.PreviewStore(path)
    store.reserve("jev", 672, 1000)
    store.close()
    store = script.PreviewStore(path)
    with pytest.raises(BudgetExhausted, match="total_backfill_budget"):
        store.reserve("jev", 672, 1000)
    assert store.usage()["unknown_usage_attempts"] == 1
    assert store.usage()["reserved_cost_usd"] == 0.000672
    store.close()


def test_each_http_retry_reserves_budget_and_stops_before_request(tmp_path, monkeypatch):
    script = module()
    store = script.PreviewStore(tmp_path / "state.sqlite")
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(503)

    monkeypatch.setattr("app.core.weekly_enrichment.time.sleep", lambda _: None)
    settings = Settings(_env_file=None, auth_secret=None, jev_api_key="test")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        enricher = script.BudgetedEnricher(settings, store, client, topic_registry(),
                                          TAXONOMY_VERSION, total_limit=1000)
        with pytest.raises(BudgetExhausted, match="total_backfill_budget"):
            enricher.jev({}, {"supported": enricher.support_question("Supported?")})
    assert len(requests) == 1
    assert store.usage()["calls"] == {"jev": 1}
    store.close()


def test_resume_reuses_assignments_and_keeps_preview_separate(tmp_path, monkeypatch):
    script = module()
    script.prepare(export(), tmp_path, 2)
    requests = []

    def handler(request):
        requests.append(request)
        questions = json.loads(request.content)["questions"]
        answers = ({"same_event": {"noul": 0.05}} if "same_event" in questions else
                   {"relevant": {"noul": 0.95}, "topic": {"choice": "coding-agents",
                                                            "confidence": 0.95}})
        return httpx.Response(200, json={"answers": answers, "usage": {"input_tokens": 100}})

    real_client = httpx.Client
    monkeypatch.setattr(script.httpx, "Client", lambda **_: real_client(
        transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(script, "explain", lambda *_: False)
    settings = Settings(_env_file=None, auth_secret=None, jev_api_key="test",
                        weekly_jev_decision_budget=1)
    first = script.run(tmp_path, settings)
    assert first["jobs"][0][1] == "retry"
    assert len(requests) == 1
    settings.weekly_jev_decision_budget = 100
    second = script.run(tmp_path, settings)
    assert second["jobs"][0][1] == "complete"
    assert len(requests) == 2  # Seven-day separation needs no same-event call.
    script.run(tmp_path, settings)
    assert len(requests) == 2
    payload = json.loads((tmp_path / "2026-10-04.r1.json").read_text())
    assert payload["coverage_confirmed"] is False
    assert not any(payload[s] for s in ("new", "trending_up", "trending_down"))
    assert payload["topics"][0]["observed_articles_current"] == 1
    assert payload["topics"][0]["observed_articles_previous"] == 1
    store = script.PreviewStore(tmp_path / "preview.sqlite")
    assert store.progress("classified:0")["publication_provenance"] == "legacy_unverified"
    assert store.usage()["usage_priced_cost_usd"] < 2
    store.close()
