from datetime import UTC, datetime

import pytest

from app.storage.journal_files import fingerprint
from app.storage.reenrich_apply import article_with_defaults, verify_manifest


def manifest_for(after, *, delete=False):
    row = article_with_defaults(
        {
            "id": 1,
            "title": "Ordinary article",
            "url": "https://example.com/a",
            "url_canonical": "https://example.com/a",
            "url_canonical_hash": "a" * 64,
            "source_id": 1,
            "discovered_at": datetime(2026, 10, 1, tzinfo=UTC),
            "published_at": datetime(2026, 9, 1, tzinfo=UTC),
        }
    )
    entry = {
        "article_id": 1,
        "before": row,
        "after": None if delete else {**row, **after},
        "row_hash": fingerprint(row),
        "dependencies": [],
    }
    if delete:
        entry.update(
            source_row={"url": row["url"], "title": row["title"], "content": "Short"},
            assessment={
                "relevance_score": 0.01,
                "admission_choice": "non_ai",
                "admission_confidence": 0.99,
            },
        )
    value = {"entries": [entry]}
    value["manifest_hash"] = fingerprint(value)
    return value


def test_manifest_allows_unknown_date_without_changing_discovery():
    verify_manifest(manifest_for({"published_at": None, "publication_status": "unknown"}))


def test_manifest_refuses_identity_change_even_with_recomputed_hash():
    with pytest.raises(ValueError, match="identity or discovery"):
        verify_manifest(manifest_for({"url": "https://example.com/other"}))


def test_manifest_refuses_confident_deletion_without_source_corroboration():
    with pytest.raises(ValueError, match="Unsafe or disputed"):
        verify_manifest(manifest_for({}, delete=True))


def test_manifest_refuses_mutated_payload_without_matching_hash():
    value = manifest_for({"published_at": None})
    value["entries"][0]["after"]["title"] = "Altered"
    with pytest.raises(ValueError, match="hash differs"):
        verify_manifest(value)


def test_manifest_refuses_precision_description_that_exceeds_column_limit():
    with pytest.raises(ValueError, match="schema limit: publication_precision"):
        verify_manifest(manifest_for({"publication_precision": "x" * 33}))
