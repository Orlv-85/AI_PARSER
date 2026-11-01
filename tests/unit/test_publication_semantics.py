import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from app.config.sources import SourceConfig
from app.core.ingestion.pipeline.models import COMPARISON_MIN_CONFIDENCE
from app.core.ingestion.pipeline.rows import _build_article_row, _candidate_payload
from app.core.jev import JevAssessment
from app.ingest.html import fetch_html_article
from app.ingest.rss import parse_rss


def test_atom_updated_only_does_not_become_publication():
    items = parse_rss(
        "test",
        b"""<feed xmlns="http://www.w3.org/2005/Atom">
      <title>AI feed</title><id>urn:test</id><updated>2026-10-01T12:00:00Z</updated>
      <entry><id>urn:item</id><title>AI research</title>
      <link href="https://example.com/research"/><updated>2026-10-01T12:00:00Z</updated>
      </entry></feed>""",
    )
    assert len(items) == 1
    assert items[0].published_at is None
    assert items[0].modified_at == datetime(2026, 10, 1, 12, tzinfo=UTC)


def test_unknown_or_conflicting_publication_has_zero_freshness():
    source = SourceConfig(id="test", name="Test", type="rss", url="https://example.com/feed")
    for evidence in (None, {"published": {"status": "conflict", "selected": None}}):
        item = SimpleNamespace(
            title="AI research",
            url="https://example.com/research",
            published_at=None,
            date_evidence=evidence,
            summary=None,
            content=None,
        )
        row = _build_article_row(
            item=item,
            config=source,
            db_source_id=1,
            canonical=str(item.url),
            canonical_hash="a" * 64,
            assessment=None,
            admission_enabled=False,
        )
        assert row["published_at"] is None
        assert row["freshness_score"] == 0
        assert row["publication_status"] == ("conflict" if evidence else "unknown")


def test_day_precision_evidence_sets_publication_day_not_published_at():
    source = SourceConfig(id="test", name="Test", type="html", url="https://example.com/news",
                          html={})
    page = ('<html><head><meta property="article:published_time" content="2026-10-01">'
            "</head><body><h1>AI research</h1><p>AI research results.</p></body></html>")
    fetcher = SimpleNamespace(fetch_text=lambda **_kwargs: page)
    item = fetch_html_article(source=source, url="https://example.com/news/ai-research",
                              fetcher=fetcher)
    assert item is not None
    row = _build_article_row(
        item=item,
        config=source,
        db_source_id=1,
        canonical=str(item.url),
        canonical_hash="b" * 64,
        assessment=None,
        admission_enabled=False,
    )
    assert row["published_at"] is None
    assert row["publication_day"] == date(2026, 10, 1)
    assert row["publication_precision"] == "day"
    assert row["freshness_score"] == 0


def _future_row(published_at):
    source = SourceConfig(id="test", name="Test", type="rss", url="https://example.com/feed")
    item = SimpleNamespace(title="AI research", url="https://example.com/research",
                           published_at=published_at, publication_date_kind="published",
                           date_evidence=None, summary=None, content=None)
    return _build_article_row(item=item, config=source, db_source_id=1,
                              canonical=str(item.url), canonical_hash="a" * 64,
                              assessment=None, admission_enabled=False)


def test_future_publication_becomes_collection_time():
    before = datetime.now(UTC)
    row = _future_row(before + timedelta(days=8))
    assert before <= row["published_at"] <= datetime.now(UTC)
    assert row["publication_status"] == "confirmed"
    assert "future_date_replaced" in row["date_provenance"]


def test_future_date_within_tolerance_is_kept():
    stamp = datetime.now(UTC) + timedelta(hours=3)
    assert _future_row(stamp)["published_at"] == stamp


def test_candidate_payload_replaces_future_date():
    source = SourceConfig(id="test", name="Test", type="rss", url="https://example.com/feed")
    far = datetime.now(UTC) + timedelta(days=8)
    item = SimpleNamespace(title="t", url="https://example.com/a", published_at=far,
                           publication_evidence_at=far)
    payload = _candidate_payload(item, source)
    assert datetime.fromisoformat(payload["published_at"]) < far - timedelta(days=7)
    assert datetime.fromisoformat(payload["publication_evidence_at"]) < far - timedelta(days=7)


def _row(item, assessment=None, admission_enabled=False):
    source = SourceConfig(id="test", name="Test", type="rss", url="https://example.com/feed")
    return _build_article_row(item=item, config=source, db_source_id=7,
                              canonical="https://example.com/a", canonical_hash="c" * 64,
                              assessment=assessment, admission_enabled=admission_enabled)


def _item(**fields):
    base = {"title": "AI research", "url": "https://example.com/a", "summary": "s",
            "content": "c", "published_at": None, "date_evidence": None}
    return SimpleNamespace(**{**base, **fields})


def test_admission_without_assessment_builds_no_row():
    assert _row(_item(), assessment=None, admission_enabled=True) is None


def test_non_published_kind_uses_evidence_time_not_published_at():
    evidence = datetime(2026, 9, 1, 8, tzinfo=UTC)
    row = _row(_item(published_at=datetime(2026, 10, 1, tzinfo=UTC),
                     publication_date_kind="updated", publication_evidence_at=evidence))
    assert row["published_at"] == evidence
    assert row["publication_status"] == "confirmed"
    assert row["publication_precision"] == "normalized_source_timestamp"
    assert row["date_provenance"] == "null"


def test_row_fields_and_assessment_extras_are_pinned():
    stamp = datetime(2026, 9, 1, 8, tzinfo=UTC)
    assessment = JevAssessment(
        relevance_score=0.8, category="Models", category_confidence=0.7,
        admission_choice="Admit", admission_confidence=0.9,
        comparison_choice="Comparison", comparison_confidence=COMPARISON_MIN_CONFIDENCE)
    row = _row(_item(published_at=stamp), assessment, admission_enabled=True)
    assert row["source_id"] == 7
    assert row["url_canonical"] == "https://example.com/a"
    assert row["url_canonical_hash"] == "c" * 64
    assert row["ai_relevance_score"] == 0.8
    assert row["category"] == "Models"
    assert row["category_confidence"] == 0.7
    assert row["material_type"] == "Comparison"
    assert row["publication_day"] is None
    assert set(row) >= {"enrichment_provenance", "rank_score", "freshness_score"}
    prov = json.loads(row["enrichment_provenance"])
    assert prov["admission_assessment"]["comparison_choice"] == "Comparison"
    assert len(prov["admission_source_hash"]) == 64


def test_low_confidence_comparison_has_no_material_type_and_no_category():
    assessment = JevAssessment(relevance_score=0.5, comparison_choice="Comparison",
                               comparison_confidence=0.0)
    row = _row(_item(), assessment)
    assert "material_type" not in row
    assert "category" not in row
    assert "enrichment_provenance" in row
    plain = _row(_item(), JevAssessment(relevance_score=0.5))
    assert "enrichment_provenance" not in plain
