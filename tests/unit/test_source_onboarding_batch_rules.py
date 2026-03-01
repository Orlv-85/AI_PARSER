from pathlib import Path

from app.core import source_onboarding


def _fixture_text() -> str:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "source_batches"
        / "qa_ai_sources.txt"
    )
    return fixture_path.read_text(encoding="utf-8")


def _fixture_urls() -> list[str]:
    return [line for line in _fixture_text().splitlines() if line.strip()]


def _require_batch_rule_api():
    assert hasattr(
        source_onboarding,
        "classify_candidate_batch",
    ), (
        "Phase 5 batch classification API missing: "
        "app.core.source_onboarding.classify_candidate_batch"
    )
    return source_onboarding.classify_candidate_batch


def _lookup(container, key: str):
    if isinstance(container, dict):
        return container[key]
    return getattr(container, key)


def _reasons_by_url(items) -> dict[str, str]:
    return {
        _lookup(item, "normalized_url"): _lookup(item, "reason")
        for item in items
    }


def test_classify_candidate_batch_rejects_search_wrappers_and_flags_broad_candidates() -> None:
    classify_candidate_batch = _require_batch_rule_api()
    google_wrapper_url = (
        "https://www.google.com/url?q=https%3A%2F%2Ftestrigor.com%2Fblog%2F"
        "&sa=D&source=editors"
    )

    fixture_text = _fixture_text()
    assert len(_fixture_urls()) == 50
    review = classify_candidate_batch(fixture_text)

    rejected_by_url = _reasons_by_url(_lookup(review, "rejected_candidates"))
    assert rejected_by_url == {
        google_wrapper_url: "search_wrapper",
        "https://muuktest.com/blog": "duplicate_url",
    }

    flagged_by_url = _reasons_by_url(_lookup(review, "flagged_candidates"))
    assert (
        flagged_by_url["https://www.infoq.com/ai-ml-data-eng/"]
        == "broad_media_page"
    )
    assert flagged_by_url["https://testguild.com/category/ai-in-testing/"] == "topic_page"
    assert flagged_by_url["https://www.ministryoftesting.com/topics/ai"] == "topic_page"
    assert "broad_media" not in set(flagged_by_url.values())


def test_classify_candidate_batch_groups_same_vendor_overlaps_for_review() -> None:
    classify_candidate_batch = _require_batch_rule_api()

    fixture_text = _fixture_text()
    assert len(_fixture_urls()) == 50
    review = classify_candidate_batch(fixture_text)

    overlap_groups = _lookup(review, "overlap_groups")
    matched_group = next(
        (
            group
            for group in overlap_groups
            if set(_lookup(group, "candidate_urls"))
            == {
                "https://muuktest.com/blog",
                "https://muuktest.com/blog/ai-in-software-testing",
            }
        ),
        None,
    )

    assert matched_group is not None, "Expected same-vendor overlaps to be grouped"
    assert _lookup(matched_group, "reason") == "same_host_path_prefix"
    assert _lookup(matched_group, "preferred_url") == "https://muuktest.com/blog"
    assert {
        _lookup(group, "reason")
        for group in overlap_groups
    }.isdisjoint({"path_prefix"})
