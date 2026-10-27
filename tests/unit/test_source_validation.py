from types import SimpleNamespace

from app.core.sources import candidates as source_candidates
from app.core.sources import onboarding as source_onboarding
from app.core.sources import validation as source_validation


def _require_api(name: str):
    assert hasattr(
        source_validation,
        name,
    ), f"Phase 2 validation API missing: app.core.sources.validation.{name}"
    return getattr(source_validation, name)


def _value(container, key: str):
    if isinstance(container, dict):
        return container[key]
    return getattr(container, key)


def test_validate_rss_candidate_marks_candidate_valid_when_feed_has_entries() -> None:
    validate_rss_candidate = _require_api("validate_rss_candidate")
    candidate = SimpleNamespace(
        id=1,
        normalized_url="https://example.com/feed.xml",
        candidate_type="rss",
    )

    result = validate_rss_candidate(
        candidate,
        fetch_feed=lambda url: {
            "url": url,
            "title": "Example Feed",
            "entries": [
                {"title": "Post 1", "link": "https://example.com/posts/1"},
                {"title": "Post 2", "link": "https://example.com/posts/2"},
            ],
        },
    )

    assert _value(result, "status") == "validated"
    assert _value(result, "detected_type") == "rss"
    assert _value(result, "entry_count") == 2
    assert _value(result, "validation_error") is None


def test_validate_rss_candidate_fails_when_feed_has_no_entries() -> None:
    validate_rss_candidate = _require_api("validate_rss_candidate")
    candidate = SimpleNamespace(
        id=2,
        normalized_url="https://example.com/empty.xml",
        candidate_type="rss",
    )

    result = validate_rss_candidate(
        candidate,
        fetch_feed=lambda url: {"url": url, "title": "Empty Feed", "entries": []},
    )

    assert _value(result, "status") == "failed"
    assert _value(result, "detected_type") == "rss"
    assert "entry" in _value(result, "validation_error").lower()


def test_validate_html_candidate_marks_candidate_valid_when_article_links_are_extractable(
) -> None:
    validate_html_candidate = _require_api("validate_html_candidate")
    candidate = SimpleNamespace(
        id=3,
        normalized_url="https://example.com/blog",
        candidate_type="html",
    )

    result = validate_html_candidate(
        candidate,
        fetch_html=lambda url: _ARTICLE,
        extract_links=lambda html, base_url: [
            f"{base_url}/posts/1",
            f"{base_url}/posts/2",
        ],
    )

    assert _value(result, "status") == "validated"
    assert _value(result, "detected_type") == "html"
    assert _value(result, "link_count") == 2
    assert _value(result, "sample_links") == [
        "https://example.com/blog/posts/1",
        "https://example.com/blog/posts/2",
    ]


def test_validate_html_candidate_warns_when_page_loads_but_has_no_article_links(
) -> None:
    validate_html_candidate = _require_api("validate_html_candidate")
    candidate = SimpleNamespace(
        id=4,
        normalized_url="https://example.com/category/testing",
        candidate_type="html",
    )

    result = validate_html_candidate(
        candidate,
        fetch_html=lambda url: "<html><body>empty</body></html>",
        extract_links=lambda html, base_url: [],
    )

    assert _value(result, "status") in {"warning", "failed"}
    assert _value(result, "detected_type") == "html"
    assert _value(result, "link_count") == 0
    assert "link" in _value(result, "validation_error").lower()


def test_run_source_validation_rejects_missing_candidate(monkeypatch) -> None:
    class _Repo:
        def __init__(self, _session) -> None:
            pass

        def get_candidate(self, _candidate_id: int):
            return None

    monkeypatch.setattr(source_validation, "SourceCandidateRepo", _Repo)

    try:
        source_validation.run_source_validation(candidate_id=77, session=object())
    except ValueError as exc:
        assert "source candidate not found: 77" in str(exc)
    else:  # pragma: no cover - exercised when the guard is implemented incorrectly
        raise AssertionError("run_source_validation should reject unknown candidate ids")


def test_run_source_validation_infers_unknown_candidate_type_and_records_result(
    monkeypatch,
) -> None:
    recorded: dict[str, object] = {}

    candidate = SimpleNamespace(
        id=9,
        candidate_type="unknown",
        normalized_url="https://example.com/feed.xml",
    )

    class _Repo:
        def __init__(self, _session) -> None:
            pass

        def get_candidate(self, candidate_id: int):
            assert candidate_id == 9
            return candidate

        def record_validation_result(self, *, candidate_id: int, result) -> None:
            recorded["candidate_id"] = candidate_id
            recorded["result"] = result

    monkeypatch.setattr(source_validation, "SourceCandidateRepo", _Repo)

    result = source_validation.run_source_validation(
        candidate_id=9,
        session=object(),
        fetch_feed=lambda _url: {"entries": [{"title": "Post"}]},
    )

    assert result.detected_type == "rss"
    assert result.status == "validated"
    assert recorded["candidate_id"] == 9
    assert recorded["result"] is result


def test_run_source_validation_returns_failed_result_for_unsupported_candidate_type(
    monkeypatch,
) -> None:
    recorded: dict[str, object] = {}

    candidate = SimpleNamespace(
        id=12,
        candidate_type="podcast",
        normalized_url="https://example.com/podcast",
    )

    class _Repo:
        def __init__(self, _session) -> None:
            pass

        def get_candidate(self, candidate_id: int):
            assert candidate_id == 12
            return candidate

        def record_validation_result(self, *, candidate_id: int, result) -> None:
            recorded["candidate_id"] = candidate_id
            recorded["result"] = result

    monkeypatch.setattr(source_validation, "SourceCandidateRepo", _Repo)

    result = source_validation.run_source_validation(candidate_id=12, session=object())

    assert result.status == "failed"
    assert result.detected_type == "unknown"
    assert "unsupported candidate type" in str(result.validation_error).lower()
    assert recorded["candidate_id"] == 12
    assert recorded["result"] is result


def test_run_source_validation_batch_requires_scope() -> None:
    try:
        source_validation.run_source_validation_batch(session=object())
    except ValueError as exc:
        assert "batch_id or candidate_ids is required" in str(exc)
    else:  # pragma: no cover - exercised when the guard is implemented incorrectly
        raise AssertionError("run_source_validation_batch should require batch_id or candidate_ids")


def test_review_candidate_overlaps_filters_non_group_results(monkeypatch) -> None:
    expected_group = source_candidates.CandidateOverlapGroup(
        candidate_ids=[1, 2],
        reason="same_host_path_prefix",
        preferred_candidate_id=1,
    )

    class _Repo:
        def __init__(self, _session) -> None:
            pass

        def find_overlap_groups(self, *, batch_id, candidate_ids):
            assert batch_id == 5
            assert candidate_ids == [1, 2]
            return [expected_group, "ignored"]

    monkeypatch.setattr(source_onboarding, "SourceCandidateRepo", _Repo)

    groups = source_onboarding.review_candidate_overlaps(
        session=object(),
        batch_id=5,
        candidate_ids=[1, 2],
    )

    assert groups == [expected_group]


def test_run_source_validation_executes_html_path_and_batch_wrapper(monkeypatch) -> None:
    recorded: list[int] = []

    html_candidate = SimpleNamespace(
        id=21,
        candidate_type="html",
        normalized_url="https://example.com/blog",
    )
    batch_candidates = [SimpleNamespace(id=21), SimpleNamespace(id=22)]

    class _Repo:
        def __init__(self, _session) -> None:
            pass

        def get_candidate(self, candidate_id: int):
            assert candidate_id == 21
            return html_candidate

        def record_validation_result(self, *, candidate_id: int, result) -> None:
            _ = result
            recorded.append(candidate_id)

        def list_candidates(self, *, batch_id, candidate_ids):
            assert batch_id == 8
            assert candidate_ids is None
            return batch_candidates

    monkeypatch.setattr(source_validation, "SourceCandidateRepo", _Repo)

    html_result = source_validation.run_source_validation(
        candidate_id=21,
        session=object(),
        fetch_html=lambda _url: _ARTICLE,
        extract_links=lambda _html, base_url: [f"{base_url}/a", f"{base_url}/b"],
    )
    assert html_result.detected_type == "html"
    assert html_result.status == "validated"
    assert recorded == [21]

    calls: list[int] = []

    def _run_source_validation(**kwargs):
        calls.append(kwargs["candidate_id"])
        return SimpleNamespace(candidate_id=kwargs["candidate_id"], status="validated")

    monkeypatch.setattr(source_validation, "run_source_validation", _run_source_validation)

    results = source_validation.run_source_validation_batch(session=object(), batch_id=8)

    assert calls == [21, 22]
    assert [result.candidate_id for result in results] == [21, 22]


def _html_candidate():
    return SimpleNamespace(id=30, normalized_url="https://example.com/blog", candidate_type="html")


_ARTICLE = (
    '<html><head><script type="application/ld+json">{"@type":"NewsArticle"}</script>'
    "</head><body>post</body></html>"
)


def test_validate_html_candidate_checks_several_links_and_all_must_pass() -> None:
    fetched: list[str] = []

    def fetch(url: str) -> str:
        fetched.append(url)
        return _ARTICLE if url != "https://example.com/blog" else "<html/>"

    links = [f"https://example.com/blog/p{i}" for i in range(6)]
    result = source_validation.validate_html_candidate(
        _html_candidate(), fetch_html=fetch, extract_links=lambda _h, _b: links
    )
    assert result.status == "validated"
    assert fetched[1:] == links[: source_validation.HTML_SAMPLE_LINKS]
    assert result.link_count == 6


def test_validate_html_candidate_warns_when_a_sampled_link_is_not_an_article() -> None:
    links = ["https://example.com/blog/p1", "https://example.com/pricing", "https://example.com/blog/p3"]

    def fetch(url: str) -> str:
        if url.endswith("/pricing"):
            return "<html><body><h1>Pricing</h1></body></html>"
        return _ARTICLE if url in links else "<html/>"

    result = source_validation.validate_html_candidate(
        _html_candidate(), fetch_html=fetch, extract_links=lambda _h, _b: links
    )
    assert result.status == "warning"
    assert "pricing" in str(result.validation_error)


def test_validate_html_candidate_warns_when_a_sampled_link_cannot_be_fetched() -> None:
    links = ["https://example.com/blog/p1", "https://example.com/blog/p2"]

    def fetch(url: str) -> str:
        if url.endswith("/p2"):
            raise RuntimeError("boom")
        return _ARTICLE if url in links else "<html/>"

    result = source_validation.validate_html_candidate(
        _html_candidate(), fetch_html=fetch, extract_links=lambda _h, _b: links
    )
    assert result.status == "warning"
    assert "p2" in str(result.validation_error)


def test_validate_html_candidate_warns_when_listing_has_too_few_links() -> None:
    result = source_validation.validate_html_candidate(
        _html_candidate(),
        fetch_html=lambda _u: _ARTICLE,
        extract_links=lambda _h, _b: ["https://example.com/blog/p1"],
    )
    assert result.status == "warning"
    assert result.link_count == 1
