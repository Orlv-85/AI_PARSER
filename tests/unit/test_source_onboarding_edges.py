# pylint: disable=protected-access

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.sources import candidates as source_candidates
from app.core.sources import onboarding as source_onboarding
from app.core.sources import validation as source_validation
from app.storage.models_sql import Base, Source


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_group_candidate_overlaps_skips_missing_host_and_singletons() -> None:
    groups = source_candidates.group_candidate_overlaps(
        [
            {"id": 1, "normalized_url": "http:///path-only", "candidate_type": "html"},
            {"id": 2, "normalized_url": "https://solo.example.com/blog", "candidate_type": "html"},
        ]
    )

    assert not groups


def test_group_candidate_overlaps_covers_no_overlap_hosts_and_revisited_pending_nodes() -> None:
    no_overlap = source_candidates.group_candidate_overlaps(
        [
            {"id": 1, "normalized_url": "https://example.com/alpha", "candidate_type": "html"},
            {"id": 2, "normalized_url": "https://example.com/beta", "candidate_type": "html"},
        ]
    )
    assert not no_overlap

    groups = source_candidates.group_candidate_overlaps(
        [
            {"id": 1, "normalized_url": "https://example.com/blog", "candidate_type": "html"},
            {"id": 2, "normalized_url": "https://example.com/blog/post", "candidate_type": "html"},
            {
                "id": 3,
                "normalized_url": "https://example.com/blog/post/deep",
                "candidate_type": "html",
            },
        ]
    )
    assert len(groups) == 1
    assert groups[0].candidate_ids == [1, 2, 3]


def test_review_source_candidate_guard_and_fallback_paths() -> None:
    with pytest.raises(ValueError, match="candidate_repo must provide get_candidate"):
        source_onboarding.review_source_candidate(
            candidate_id=1,
            action="approve",
            candidate_repo=object(),
            managed_source_repo=object(),
        )

    repo = SimpleNamespace(
        get_candidate=lambda _candidate_id: SimpleNamespace(id=1, status="draft")
    )
    with pytest.raises(ValueError, match="source candidate not found: 4"):
        source_onboarding.review_source_candidate(
            candidate_id=4,
            action="approve",
            candidate_repo=SimpleNamespace(get_candidate=lambda _candidate_id: None),
            managed_source_repo=object(),
        )

    with pytest.raises(ValueError, match="unsupported review action: archive"):
        source_onboarding.review_source_candidate(
            candidate_id=1,
            action="archive",
            candidate_repo=repo,
            managed_source_repo=object(),
        )

    candidate = SimpleNamespace(id=1, status="draft")
    returned = source_onboarding.review_source_candidate(
        candidate_id=1,
        action="reject",
        candidate_repo=SimpleNamespace(get_candidate=lambda _candidate_id: candidate),
        managed_source_repo=object(),
        review_note="manual reject",
    )
    assert returned is candidate
    assert candidate.status == "rejected"
    assert candidate.review_note == "manual reject"


def test_export_approved_sources_yaml_serializes_html_sources() -> None:
    session = _session()
    session.add(
        Source(
            source_key="managed-html",
            name="Managed HTML",
            type="html",
            url="https://example.com/html",
            enabled=True,
            fetch_interval_minutes=30,
            source_weight=1.0,
        )
    )
    session.flush()

    dumped = source_onboarding.export_approved_sources_yaml(session=session)
    assert "managed-html" in dumped
    assert "parser_options: {}" in dumped


def test_source_onboarding_review_helper_guards_and_edit_inference() -> None:
    candidate = SimpleNamespace(
        id=7,
        status="draft",
        validation_status="validated",
        approved_source_id=None,
        normalized_url="https://example.com/original",
        candidate_type="html",
        review_note=None,
        duplicate_of_candidate_id=None,
    )

    with pytest.raises(ValueError, match="managed_source_repo must provide create_from_candidate"):
        source_onboarding._approve_candidate(
            candidate=candidate,
            managed_source_repo=object(),
            review_note=None,
        )

    source_onboarding._approve_candidate(
        candidate=candidate,
        managed_source_repo=SimpleNamespace(create_from_candidate=lambda _candidate: object()),
        review_note="approved without managed source id",
    )
    assert candidate.status == "approved"
    assert candidate.review_note == "approved without managed source id"

    with pytest.raises(
        ValueError,
        match="Only approved candidates with a managed source can be disabled",
    ):
        source_onboarding._disable_candidate(
            candidate=candidate,
            managed_source_repo=object(),
            review_note=None,
        )

    candidate.approved_source_id = 11
    with pytest.raises(ValueError, match="managed_source_repo must provide disable_source"):
        source_onboarding._disable_candidate(
            candidate=candidate,
            managed_source_repo=object(),
            review_note=None,
        )

    disabled_calls: list[int] = []

    def _disable_source(source_id: int) -> None:
        disabled_calls.append(source_id)

    source_onboarding._disable_candidate(
        candidate=candidate,
        managed_source_repo=SimpleNamespace(disable_source=_disable_source),
        review_note="disabled now",
    )
    assert disabled_calls == [11]
    assert candidate.status == "disabled"
    assert candidate.review_note == "disabled now"

    with pytest.raises(ValueError, match="duplicate_of_candidate_id is required"):
        source_onboarding._mark_duplicate_candidate(
            candidate=candidate,
            candidate_repo=object(),
            duplicate_of_candidate_id=None,
            review_note=None,
        )

    candidate.status = "approved"
    with pytest.raises(ValueError, match="Approved candidates cannot be edited"):
        source_onboarding._edit_candidate(
            candidate=candidate,
            candidate_id=7,
            candidate_repo=object(),
            updates={"raw_input": "x"},
            review_note=None,
        )

    candidate.status = "draft"
    candidate.review_note = None
    source_onboarding._edit_candidate(
        candidate=candidate,
        candidate_id=7,
        candidate_repo=object(),
        updates={"normalized_url": "https://example.com/feed"},
        review_note="updated",
    )
    assert candidate.normalized_url == "https://example.com/feed"
    assert candidate.candidate_type == "rss"
    assert candidate.review_note == "updated"

    with pytest.raises(ValueError, match="normalized URL already exists for another candidate"):
        source_onboarding._edit_candidate(
            candidate=candidate,
            candidate_id=7,
            candidate_repo=SimpleNamespace(
                find_by_normalized_url=lambda _url: SimpleNamespace(id=99)
            ),
            updates={"normalized_url": "https://example.com/other"},
            review_note=None,
        )

    source_onboarding._edit_candidate(
        candidate=candidate,
        candidate_id=7,
        candidate_repo=object(),
        updates={"candidate_type": "HTML"},
        review_note=None,
    )
    assert candidate.candidate_type == "html"

    source_onboarding._edit_candidate(
        candidate=candidate,
        candidate_id=7,
        candidate_repo=object(),
        updates={"raw_input": "https://example.com/raw-only"},
        review_note=None,
    )
    assert candidate.raw_input == "https://example.com/raw-only"


def test_source_onboarding_lookup_and_value_helpers() -> None:
    assert source_onboarding._lookup_candidate(object(), 1) is None
    assert source_onboarding._find_by_normalized_url(object(), "https://example.com") is None
    assert source_onboarding._candidate_int_value({}, "approved_source_id") is None
    assert (
        source_onboarding._candidate_int_value(
            SimpleNamespace(approved_source_id="9"),
            "approved_source_id",
        )
        == 9
    )

    with pytest.raises(ValueError, match="candidate field is required: normalized_url"):
        source_candidates._candidate_value({}, "normalized_url")


def test_source_onboarding_path_and_reason_helpers() -> None:
    assert source_candidates._is_search_wrapper(
        hostname="bing.com",
        path="/url",
        query="q=https://example.com",
    ) is False
    assert source_candidates._is_search_wrapper(
        hostname="google.com",
        path="/other",
        query="q=https://example.com",
    ) is True
    assert source_candidates._normalized_path("https://example.com/blog/") == "/blog"
    assert source_candidates._normalized_path("https://example.com") == "/"
    assert source_candidates._path_segments("https://example.com") == []
    assert source_candidates._path_segments("https://example.com/a/b") == ["a", "b"]

    assert source_candidates._is_strict_path_prefix("/blog", "/blog") is False
    assert source_candidates._is_strict_path_prefix("/", "/blog") is False
    assert source_candidates._is_root_family_path("/") is True
    assert (
        source_candidates._overlap_reason(
            {"normalized_url": "https://example.com/blog", "candidate_type": "html"},
            {"normalized_url": "https://example.com/news", "candidate_type": "html"},
        )
        == "same_host_family"
    )

    assert source_candidates._prefer_reason("same_host_family", "same_host_path_prefix") == (
        "same_host_path_prefix"
    )
    assert source_candidates._prefer_reason("same_host_path_prefix", "same_host_family") == (
        "same_host_path_prefix"
    )


def test_source_onboarding_picker_and_ingest_helpers(monkeypatch) -> None:
    chosen = source_candidates._pick_preferred_candidate(
        [
            {
                "id": 2,
                "normalized_url": "https://example.com/blog/deep/post",
                "candidate_type": "html",
            },
            {"id": 1, "normalized_url": "https://example.com/feed.xml", "candidate_type": "rss"},
        ]
    )
    assert source_candidates._candidate_value(chosen, "id") == "1"

    calls: dict[str, object] = {}

    class _Fetcher:
        def __enter__(self):
            calls["entered"] = True
            return self

        def __exit__(self, exc_type, exc, tb):
            calls["exited"] = True
            return False

        def fetch_text(self, *, source_id: str, url: str):
            calls["fetch_text"] = (source_id, url)
            return "<html>body</html>"

    monkeypatch.setattr(source_validation, "Fetcher", _Fetcher)
    monkeypatch.setattr(
        source_validation,
        "fetch_rss_with_metadata",
        lambda **kwargs: {"entries": [kwargs["url"]]},
    )
    monkeypatch.setattr(
        source_validation,
        "extract_links_from_html",
        lambda **kwargs: [kwargs["base_url"]],
    )

    feed_payload = source_validation._fetch_feed_with_ingest("https://example.com/feed.xml")
    assert feed_payload == {"entries": ["https://example.com/feed.xml"]}

    html_payload = source_validation._fetch_html_with_ingest("https://example.com/html")
    assert html_payload == "<html>body</html>"
    assert calls["fetch_text"] == ("source-onboarding-validation", "https://example.com/html")

    links = source_validation._extract_links_with_ingest("<html/>", "https://example.com/html")
    assert links == ["https://example.com/html"]

    assert source_validation._extract_feed_entries({"entries": [1, 2]}) == [1, 2]
    assert source_validation._extract_feed_entries([1, 2]) == [1, 2]
    assert source_validation._extract_feed_entries(SimpleNamespace(entries=[3, 4])) == [3, 4]
    assert source_validation._extract_feed_entries(SimpleNamespace(items=[5, 6])) == [5, 6]
    assert source_validation._extract_feed_entries(SimpleNamespace(items=lambda: [7])) == []

    assert source_validation._format_validation_error(RuntimeError("boom")) == "RuntimeError: boom"
    assert source_validation._format_validation_error(RuntimeError()) == "RuntimeError"
