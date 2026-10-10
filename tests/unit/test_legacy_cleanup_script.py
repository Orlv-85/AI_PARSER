import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx

from app.storage.legacy_cleanup import build_manifest, encoded
from app.storage.non_news_cleanup import EXPORT_TABLES


def test_parallel_screening_resumes_without_paid_repetition(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("cleanup_script",
                                                root / "scripts/legacy_articles_cleanup.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    tables = {name: [] for name in EXPORT_TABLES}
    tables["articles"] = [{"id": i, "url": f"https://example.com/about/{i}",
                           "url_canonical": f"https://example.com/about/{i}",
                           "url_canonical_hash": str(i), "title": "Company", "summary": None,
                           "content": "Company history", "published_at": None, "source_id": None}
                          for i in range(1, 9)]
    snapshot = {"tables": tables, "screening": {
        "model": "jev-1.13.0", "policy_version": "p1", "prompt_version": "q1"}}
    (run / "snapshot.json").write_text(encoded(snapshot))
    (run / "manifest.json").write_text(encoded(build_manifest(snapshot, {})))
    calls = []

    def transport(request):
        calls.append(request)
        return httpx.Response(200, json={"answers": {
            "ai_relevant": {"noul": 0},
            "category": {"choice": "Other", "confidence": 1},
            "admission": {"choice": "non_editorial", "confidence": 0.99}},
            "usage": {"input_tokens": 100}})

    original_client = httpx.Client
    monkeypatch.setattr(module.httpx, "Client", lambda **kwargs: original_client(
        **{**kwargs, "transport": httpx.MockTransport(transport)}))
    from app.config.settings import Settings  # pylint: disable=import-outside-toplevel
    monkeypatch.setattr(module, "Settings", lambda: Settings(_env_file=None, jev_api_key="test"))
    args = SimpleNamespace(run_dir=run, budget_usd=2, max_requests=8, concurrency=4)
    module.screen(args)
    module.screen(args)
    assert len(calls) == 8
    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["counts"] == {"unresolved": 8}
    assert json.loads((run / "usage.json").read_text())["requests"] == 8
