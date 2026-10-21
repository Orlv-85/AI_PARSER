import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.storage.article_evidence_cache import PageCache, private_bytes
from app.storage.journal_files import encoded, fingerprint
from app.storage.non_news_cleanup import EXPORT_TABLES


def _module():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("reenrich_script",
                                                root / "scripts/reenrich_articles.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(tmp_path):
    tables = {name: [] for name in EXPORT_TABLES}
    tables["articles"] = [{
        "id": i, "url": f"https://example.com/article/{i}", "title": "Synthetic AI title",
        "url_canonical": f"https://example.com/article/{i}", "url_canonical_hash": f"hash{i}",
        "summary": "Synthetic original summary", "content": "Synthetic original source text",
        "published_at": "2026-10-04T00:00:00+00:00", "source_id": None,
    } for i in range(1, 7)]
    review = {"entries": [{"article_id": i, "url_canonical_hash": f"hash{i}",
                           "row_hash": "origin", "evidence_hash": "original"} for i in (1, 99)]}
    snapshot = {"tables": tables}
    source = tmp_path / "source.json"
    source.write_text(encoded(snapshot))
    reviews = tmp_path / "review.json"
    reviews.write_text(encoded(review))
    args = SimpleNamespace(snapshot=source, review=reviews, run_dir=tmp_path / "run")
    module = _module()
    module.prepare(args)
    return module, args, snapshot


def test_prepare_freezes_only_existing_review_ids_and_rejects_changed_run(tmp_path, capsys):
    module, args, _ = _run(tmp_path)
    plan = module.read_plan(args.run_dir)
    assert [entry["article_id"] for entry in plan["targets"]] == [1]
    assert plan["missing_ids"] == [99]
    assert "Synthetic original source text" not in capsys.readouterr().out
    module.prepare(args)
    review = json.loads(args.review.read_text())
    review["entries"][0]["url_canonical_hash"] = "changed"
    args.review.write_text(encoded(review))
    with pytest.raises(ValueError, match="different snapshot/review"):
        module.prepare(args)


def test_plan_target_url_and_snapshot_hash_are_verified(tmp_path):
    module, args, _ = _run(tmp_path)
    path = args.run_dir / "plan.json"
    plan = json.loads(path.read_text())
    plan["targets"][0]["url"] = "https://example.com/unapproved"
    path.write_text(encoded(plan))
    with pytest.raises(ValueError, match="target identity/evidence"):
        module.read_plan(args.run_dir)


def test_offline_date_audit_excludes_cleanup_copies_updated_and_unknown(tmp_path, capsys):
    module, args, snapshot = _run(tmp_path)
    ledger = []
    for article_id, kind, cleanup in ((2, "published", False), (3, "published", True),
                                      (4, "updated", False)):
        ledger.append({"id": article_id, "key": f"key{article_id}",
                       "url_canonical_hash": f"hash{article_id}",
                       "payload": encoded({"candidate": {
                           "kind": "article", "publication_date_kind": kind,
                           "published_at": "2024-05-01T12:00:00+00:00"},
                           **({"cleanup_policy": "legacy-cleanup-1"} if cleanup else {})})})
    snapshot["tables"]["admission_decisions"] = ledger
    snapshot["tables"]["weekly_input_observations"] = [
        {"id": "observation", "canonical_hash": "hash5",
         "published_at": "2024-05-02T12:00:00+00:00",
         "payload": encoded({"publication_provenance": "source"})},
        {"id": "legacy", "canonical_hash": "hash6",
         "published_at": "2024-05-02T12:00:00+00:00",
         "payload": encoded({"publication_provenance": "legacy_unverified"})},
    ]
    args.snapshot.write_text(encoded(snapshot))
    fresh = SimpleNamespace(**{**vars(args), "run_dir": tmp_path / "fresh"})
    module.prepare(fresh)
    legacy = tmp_path / "legacy.json"
    legacy.write_text(encoded(snapshot))
    module.audit_dates(SimpleNamespace(run_dir=fresh.run_dir, legacy_snapshot=legacy))
    result = json.loads((fresh.run_dir / "offline-date-audit.json").read_text())
    by_id = {entry["article_id"]: entry for entry in result["entries"]}
    assert result["counts"] == {"confirmed": 2, "unknown": 3}
    assert by_id[2]["resolution"]["selected"]["value"] == "2024-05-01T12:00:00+00:00"
    assert by_id[3]["needs_date_only_fetch"]
    assert by_id[4]["needs_date_only_fetch"]
    assert by_id[6]["needs_date_only_fetch"]
    assert by_id[5]["resolution"]["status"] == "confirmed"
    assert "Synthetic original source text" not in capsys.readouterr().out
    frozen = json.loads((fresh.run_dir / "snapshot.json").read_text())
    assert result["snapshot_hash"] == fingerprint(frozen)


def test_verification_refuses_unfinished_or_tampered_cache(tmp_path, capsys):
    module, args, _ = _run(tmp_path)
    with pytest.raises(SystemExit, match="verification failed"):
        module.verify_cache(args)
    cache = PageCache(args.run_dir)
    url = "https://example.com/article/1"
    cache.begin(url)
    body = b"<article><h1>AI</h1><p>Synthetic article about AI models.</p></article>"
    directory = cache.page_dir(url)
    private_bytes(directory / "body.bin", body)
    response = {"final_url": url, "status_code": 200, "content_type": "text/html",
                "encoding": "utf-8", "body_sha256": hashlib.sha256(body).hexdigest(),
                "redirects": []}
    (directory / "response.json").write_text(encoded(response))
    cache.extract_saved(url)
    module.verify_cache(args)
    assert "Synthetic article" not in capsys.readouterr().out
    (directory / "text.txt").write_text("tampered")
    with pytest.raises(SystemExit, match="verification failed"):
        module.verify_cache(args)
