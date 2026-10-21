from types import SimpleNamespace

from app.core.sources import onboarding as source_onboarding


def _require_overlap_api():
    assert hasattr(
        source_onboarding,
        "group_candidate_overlaps",
    ), (
        "Phase 2 overlap grouping API missing: "
        "app.core.sources.onboarding.group_candidate_overlaps"
    )
    return source_onboarding.group_candidate_overlaps


def _value(container, key: str):
    if isinstance(container, dict):
        return container[key]
    return getattr(container, key)


def test_group_candidate_overlaps_flags_same_host_path_prefix_variants() -> None:
    group_candidate_overlaps = _require_overlap_api()
    candidates = [
        SimpleNamespace(
            id=101,
            normalized_url="https://vendor.example.com/blog",
            candidate_type="html",
        ),
        SimpleNamespace(
            id=102,
            normalized_url="https://vendor.example.com/blog/ai-test-automation",
            candidate_type="html",
        ),
    ]

    groups = group_candidate_overlaps(candidates)

    assert groups, "Expected same-host path-prefix candidates to be grouped for review"
    members = set(_value(groups[0], "candidate_ids"))
    assert members == {101, 102}
    assert _value(groups[0], "reason") in {"path_prefix", "same_host_path_prefix"}
    assert _value(groups[0], "preferred_candidate_id") == 101


def test_group_candidate_overlaps_flags_topic_page_variants_under_same_host() -> None:
    group_candidate_overlaps = _require_overlap_api()
    candidates = [
        SimpleNamespace(
            id=201,
            normalized_url="https://example.com/blog",
            candidate_type="html",
        ),
        SimpleNamespace(
            id=202,
            normalized_url="https://example.com/tag/ai-testing",
            candidate_type="html",
        ),
        SimpleNamespace(
            id=203,
            normalized_url="https://another.example.com/blog",
            candidate_type="html",
        ),
    ]

    groups = group_candidate_overlaps(candidates)

    assert len(groups) == 1, "Expected only same-host topic pages to be flagged"
    assert set(_value(groups[0], "candidate_ids")) == {201, 202}
    assert _value(groups[0], "reason") in {"topic_page", "same_host_topic_variant"}


def test_group_candidate_overlaps_keeps_distinct_same_host_families_separate() -> None:
    group_candidate_overlaps = _require_overlap_api()
    candidates = [
        SimpleNamespace(
            id=301,
            normalized_url="https://example.com/products/ai",
            candidate_type="html",
        ),
        SimpleNamespace(
            id=302,
            normalized_url="https://example.com/products/ai/announcements",
            candidate_type="html",
        ),
        SimpleNamespace(
            id=303,
            normalized_url="https://example.com/research/ml",
            candidate_type="html",
        ),
        SimpleNamespace(
            id=304,
            normalized_url="https://example.com/research/ml/weekly",
            candidate_type="html",
        ),
    ]

    groups = group_candidate_overlaps(candidates)

    assert len(groups) == 2, (
        "Expected disjoint same-host overlap families to stay separate"
    )
    grouped_members = {frozenset(_value(group, "candidate_ids")) for group in groups}
    assert grouped_members == {frozenset({301, 302}), frozenset({303, 304})}
    preferred_ids = {_value(group, "preferred_candidate_id") for group in groups}
    assert preferred_ids == {301, 303}
    assert {_value(group, "reason") for group in groups} <= {
        "path_prefix",
        "same_host_path_prefix",
    }
