from datetime import UTC, date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.storage import models_sql, repos


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    models_sql.Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _repo(session):
    return repos.NewsDigestRepo(session)


def _digest_models():
    return (
        models_sql.NewsDigestReport,
        models_sql.NewsDigestGroup,
        models_sql.NewsDigestItem,
    )


def _seed_weekly_analytics_articles(session) -> None:  # type: ignore[no-untyped-def]
    source = models_sql.Source(
        source_key="weekly-source",
        name="Weekly Source",
        type="rss",
        url="https://example.com/feed",
    )
    session.add(source)
    session.flush()
    session.add_all(
        [
            models_sql.Article(
                source_id=source.id,
                title="Coding Agents Expand",
                summary="The topic showed up last week at a lower intensity.",
                content=None,
                url="https://example.com/coding-agents-prior",
                url_canonical="https://example.com/coding-agents-prior",
                url_canonical_hash="coding-agents-prior",
                published_at=datetime(2026, 2, 25, 9, 0, tzinfo=UTC),
                ai_relevance_score=0.7,
                freshness_score=0.5,
                rank_score=0.35,
            ),
            models_sql.Article(
                source_id=source.id,
                title="Standalone Vector DBs Cool Off",
                summary="This topic mattered last week but does not recur this week.",
                content=None,
                url="https://example.com/vector-dbs-prior",
                url_canonical="https://example.com/vector-dbs-prior",
                url_canonical_hash="vector-dbs-prior",
                published_at=datetime(2026, 2, 27, 13, 0, tzinfo=UTC),
                ai_relevance_score=0.82,
                freshness_score=0.6,
                rank_score=0.88,
            ),
            models_sql.Article(
                source_id=source.id,
                title="Coding Agents Expand",
                summary="The same topic accelerated this week and should be trending up.",
                content=None,
                url="https://example.com/coding-agents-recent",
                url_canonical="https://example.com/coding-agents-recent",
                url_canonical_hash="coding-agents-recent",
                published_at=datetime(2026, 3, 5, 11, 0, tzinfo=UTC),
                ai_relevance_score=0.92,
                freshness_score=0.8,
                rank_score=0.97,
            ),
            models_sql.Article(
                source_id=source.id,
                title="AI Browser Launches",
                summary="This topic is net new in the selected seven-day report window.",
                content=None,
                url="https://example.com/ai-browser-recent",
                url_canonical="https://example.com/ai-browser-recent",
                url_canonical_hash="ai-browser-recent",
                published_at=datetime(2026, 3, 6, 10, 30, tzinfo=UTC),
                ai_relevance_score=0.9,
                freshness_score=0.82,
                rank_score=0.91,
            ),
        ]
    )
    session.commit()


def test_save_digest_creates_report_with_groups_and_items() -> None:
    session = _session()
    repo = _repo(session)
    NewsDigestReport, NewsDigestGroup, NewsDigestItem = _digest_models()
    target_date = date(2026, 3, 1)

    saved = repo.save_digest(
        report_date=target_date,
        groups=[
            {
                "title": "AI Coding",
                "items": [
                    {
                        "title": "Codex Ships New Workflow",
                        "summary": "Tooling now supports tighter tester and generator loops.",
                        "url": "https://example.com/codex-workflow",
                    },
                    {
                        "title": "Editor Agents Expand",
                        "summary": "Teams are adopting agent-assisted code review in production.",
                        "url": "https://example.com/editor-agents",
                    },
                ],
            },
            {
                "title": "Infrastructure",
                "items": [
                    {
                        "title": "Inference Costs Drop",
                        "summary": "GPU scheduling improvements reduce serving spend.",
                        "url": "https://example.com/inference-costs",
                    }
                ],
            },
        ],
    )
    session.commit()

    assert saved.report_date == target_date

    stored_reports = session.query(NewsDigestReport).all()
    stored_groups = session.query(NewsDigestGroup).order_by(NewsDigestGroup.id.asc()).all()
    stored_items = session.query(NewsDigestItem).order_by(NewsDigestItem.id.asc()).all()

    assert len(stored_reports) == 1
    assert [group.title for group in stored_groups] == ["AI Coding", "Infrastructure"]
    assert [(item.title, item.summary, item.url) for item in stored_items] == [
        (
            "Codex Ships New Workflow",
            "Tooling now supports tighter tester and generator loops.",
            "https://example.com/codex-workflow",
        ),
        (
            "Editor Agents Expand",
            "Teams are adopting agent-assisted code review in production.",
            "https://example.com/editor-agents",
        ),
        (
            "Inference Costs Drop",
            "GPU scheduling improvements reduce serving spend.",
            "https://example.com/inference-costs",
        ),
    ]


def test_get_digest_returns_none_for_missing_date_and_nested_groups_for_existing_date() -> None:
    session = _session()
    repo = _repo(session)
    target_date = date(2026, 3, 1)

    repo.save_digest(
        report_date=target_date,
        groups=[
            {
                "title": "Agents",
                "items": [
                    {
                        "title": "Agent Platform Consolidates",
                        "summary": "Vendors are merging orchestration and eval tooling.",
                        "url": "https://example.com/agent-platform",
                    }
                ],
            }
        ],
    )
    session.commit()

    assert repo.get_digest(report_date=date(2026, 3, 2)) is None

    fetched = repo.get_digest(report_date=target_date)

    assert fetched is not None
    assert fetched.report_date == target_date
    assert [group.title for group in fetched.groups] == ["Agents"]
    assert [
        (item.title, item.summary, item.url)
        for item in fetched.groups[0].items
    ] == [
        (
            "Agent Platform Consolidates",
            "Vendors are merging orchestration and eval tooling.",
            "https://example.com/agent-platform",
        )
    ]


def test_save_digest_replaces_existing_report_for_same_date() -> None:
    session = _session()
    repo = _repo(session)
    NewsDigestReport, NewsDigestGroup, NewsDigestItem = _digest_models()
    target_date = date(2026, 3, 1)

    repo.save_digest(
        report_date=target_date,
        groups=[
            {
                "title": "Initial Batch",
                "items": [
                    {
                        "title": "Old Story",
                        "summary": "This summary should be replaced.",
                        "url": "https://example.com/old-story",
                    }
                ],
            },
            {
                "title": "Superseded Group",
                "items": [
                    {
                        "title": "Remove Me",
                        "summary": "This item should not survive replacement.",
                        "url": "https://example.com/remove-me",
                    }
                ],
            },
        ],
    )
    session.commit()

    repo.save_digest(
        report_date=target_date,
        groups=[
            {
                "title": "Fresh Outlook",
                "items": [
                    {
                        "title": "Replacement Story",
                        "summary": "A regenerated digest should become the canonical version.",
                        "url": "https://example.com/replacement-story",
                    }
                ],
            }
        ],
    )
    session.commit()

    stored_reports = session.query(NewsDigestReport).all()
    stored_groups = session.query(NewsDigestGroup).order_by(NewsDigestGroup.id.asc()).all()
    stored_items = session.query(NewsDigestItem).order_by(NewsDigestItem.id.asc()).all()
    fetched = repo.get_digest(report_date=target_date)

    assert len(stored_reports) == 1
    assert [group.title for group in stored_groups] == ["Fresh Outlook"]
    assert [(item.title, item.summary, item.url) for item in stored_items] == [
        (
            "Replacement Story",
            "A regenerated digest should become the canonical version.",
            "https://example.com/replacement-story",
        )
    ]
    assert fetched is not None
    assert fetched.report_date == target_date
    assert [group.title for group in fetched.groups] == ["Fresh Outlook"]


def test_save_digest_preserves_existing_report_when_replacement_fails() -> None:
    session = _session()
    repo = _repo(session)
    target_date = date(2026, 3, 1)

    repo.save_digest(
        report_date=target_date,
        groups=[
            {
                "title": "Stable Digest",
                "items": [
                    {
                        "title": "Keep Me",
                        "summary": "This digest should survive a failed replacement.",
                        "url": "https://example.com/keep-me",
                    }
                ],
            }
        ],
    )
    session.commit()

    try:
        repo.save_digest(
            report_date=target_date,
            groups=[
                {
                    "items": [
                        {
                            "title": "Broken Replacement",
                            "summary": "Missing group title should trigger failure.",
                            "url": "https://example.com/broken",
                        }
                    ]
                }
            ],
        )
    except KeyError:
        pass
    else:  # pragma: no cover - defensive guard
        raise AssertionError("save_digest should fail for malformed group payloads")

    fetched = repo.get_digest(report_date=target_date)

    assert fetched is not None
    assert [group.title for group in fetched.groups] == ["Stable Digest"]
    assert [item.title for item in fetched.groups[0].items] == ["Keep Me"]


def test_weekly_report_builds_local_summary_for_selected_seven_day_window() -> None:
    session = _session()
    _seed_weekly_analytics_articles(session)
    target_date = date(2026, 3, 7)

    report = repos.WeeklyAnalyticsRepo(session).get_weekly_report(report_date=target_date)

    assert report.report_date == target_date
    assert report.date_from == date(2026, 3, 1)
    assert report.date_to == target_date
    assert report.summary.startswith("Weekly summary for 2026-03-01 to 2026-03-07:")
    assert [item.title for item in report.new] == ["AI Browser Launches"]
    assert [item.title for item in report.trending_up] == ["Coding Agents Expand"]
    assert [item.title for item in report.trending_down] == ["Standalone Vector DBs Cool Off"]


def test_weekly_report_matches_topic_when_titles_vary_between_weeks() -> None:
    session = _session()
    source = models_sql.Source(
        source_key="weekly-variant-source",
        name="Weekly Variant Source",
        type="rss",
        url="https://example.com/weekly-variant",
    )
    session.add(source)
    session.flush()
    session.add_all(
        [
            models_sql.Article(
                source_id=source.id,
                title="Adaptive Inference in NVIDIA TensorRT for RTX optimization",
                summary="Prior week wording of the same topic.",
                content=None,
                url="https://example.com/prior-topic",
                url_canonical="https://example.com/prior-topic",
                url_canonical_hash="prior-topic",
                published_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
                ai_relevance_score=0.6,
                freshness_score=0.4,
                rank_score=0.31,
            ),
            models_sql.Article(
                source_id=source.id,
                title="NVIDIA TensorRT automatically optimizes inference for RTX",
                summary="Recent week variant with stronger momentum.",
                content=None,
                url="https://example.com/recent-topic",
                url_canonical="https://example.com/recent-topic",
                url_canonical_hash="recent-topic",
                published_at=datetime(2026, 3, 7, 11, 0, tzinfo=UTC),
                ai_relevance_score=0.92,
                freshness_score=0.9,
                rank_score=0.95,
            ),
        ]
    )
    session.commit()

    report = repos.WeeklyAnalyticsRepo(session).get_weekly_report(report_date=date(2026, 3, 8))

    assert not report.new
    assert [item.title for item in report.trending_up] == [
        "NVIDIA TensorRT automatically optimizes inference for RTX"
    ]


def test_get_weekly_report_returns_saved_published_report_for_matching_week() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    models_sql.Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    target_date = date(2026, 3, 8)

    with session_local() as write_session:
        _seed_weekly_analytics_articles(write_session)
        repos.WeeklyAnalyticsRepo(write_session).save_weekly_report(
            report_date=target_date,
            date_from=date(2026, 3, 2),
            date_to=target_date,
            summary="Published weekly management snapshot for the completed Monday-Sunday week.",
            new=[
                {
                    "title": "AI Browser Launches",
                    "summary": "Saved weekly section items should be served from storage.",
                    "url": "https://example.com/ai-browser-recent",
                }
            ],
            trending_up=[
                {
                    "title": "Coding Agents Expand",
                    "summary": "Published reports should preserve the reviewed trend narrative.",
                    "url": "https://example.com/coding-agents-recent",
                }
            ],
            trending_down=[
                {
                    "title": "Standalone Vector DBs Cool Off",
                    "summary": "Published reports should keep the stored comparison section.",
                    "url": "https://example.com/vector-dbs-prior",
                }
            ],
        )
        write_session.commit()

    with session_local() as read_session:
        report = repos.WeeklyAnalyticsRepo(read_session).get_weekly_report(report_date=target_date)

    assert report.report_date == target_date
    assert report.date_from == date(2026, 3, 2)
    assert report.date_to == target_date
    assert report.summary == (
        "Published weekly management snapshot for the completed Monday-Sunday week."
    )
    assert [item.title for item in report.new] == ["AI Browser Launches"]
    assert [item.title for item in report.trending_up] == ["Coding Agents Expand"]
    assert [item.title for item in report.trending_down] == ["Standalone Vector DBs Cool Off"]


def test_save_weekly_report_truncates_oversized_titles_for_storage_limits() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    models_sql.Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    target_date = date(2026, 3, 8)
    long_title = "A" * 700

    with session_local() as session:
        repo = repos.WeeklyAnalyticsRepo(session)
        report = repo.save_weekly_report(
            report_date=target_date,
            date_from=date(2026, 3, 2),
            date_to=target_date,
            summary="Stored report with oversized source title.",
            new=[
                {
                    "title": long_title,
                    "summary": "Long title should be truncated before persistence.",
                    "url": "https://example.com/very-long-title",
                }
            ],
            trending_up=[],
            trending_down=[],
        )
        session.commit()

    assert len(report.new) == 1
    assert len(report.new[0].title) == 512
