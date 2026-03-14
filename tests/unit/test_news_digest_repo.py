from datetime import UTC, date, datetime
from typing import Any

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


def test_weekly_report_uses_antigravity_output_for_selected_seven_day_window(
    monkeypatch,
) -> None:
    session = _session()
    _seed_weekly_analytics_articles(session)
    target_date = date(2026, 3, 7)
    captured: dict[str, Any] = {}

    def fake_generate(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        del self, args
        captured.update(kwargs)
        return {
            "summary": "Antigravity management summary for the selected week.",
            "new": [
                {
                    "title": "AI Browser Launches",
                    "summary": "A net-new browser launch stood out in the selected week.",
                    "url": "https://example.com/ai-browser-recent",
                }
            ],
            "trending_up": [
                {
                    "title": "Coding Agents Expand",
                    "summary": "Coding agents accelerated week over week.",
                    "url": "https://example.com/coding-agents-recent",
                }
            ],
            "trending_down": [
                {
                    "title": "Standalone Vector DBs Cool Off",
                    "summary": "The prior-week topic lost momentum in the selected week.",
                    "url": "https://example.com/vector-dbs-prior",
                }
            ],
        }

    monkeypatch.setattr(
        repos.WeeklyAnalyticsRepo,
        "_generate_antigravity_report",
        fake_generate,
        raising=False,
    )

    report = repos.WeeklyAnalyticsRepo(session).get_weekly_report(report_date=target_date)

    assert captured["report_date"] == target_date
    assert captured["date_from"] == date(2026, 3, 1)
    assert captured["date_to"] == target_date
    assert {row.title for row in captured["recent_rows"]} == {
        "AI Browser Launches",
        "Coding Agents Expand",
    }
    assert {row.title for row in captured["prior_rows"]} == {
        "Coding Agents Expand",
        "Standalone Vector DBs Cool Off",
    }
    assert report.summary == "Antigravity management summary for the selected week."
    assert [item.title for item in report.new] == ["AI Browser Launches"]
    assert [item.title for item in report.trending_up] == ["Coding Agents Expand"]
    assert [item.title for item in report.trending_down] == ["Standalone Vector DBs Cool Off"]


def test_weekly_report_falls_back_when_antigravity_times_out(monkeypatch) -> None:
    session = _session()
    _seed_weekly_analytics_articles(session)
    target_date = date(2026, 3, 7)
    attempts = {"count": 0}

    def fake_generate(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        del self, args, kwargs
        attempts["count"] += 1
        raise TimeoutError("Antigravity timed out after 60 seconds")

    monkeypatch.setattr(
        repos.WeeklyAnalyticsRepo,
        "_generate_antigravity_report",
        fake_generate,
        raising=False,
    )

    repo = repos.WeeklyAnalyticsRepo(session)
    report = repo.get_weekly_report(report_date=target_date)
    recent_rows = repo._list_articles(date_from=date(2026, 3, 1), date_to=target_date)  # pylint: disable=protected-access
    prior_rows = repo._list_articles(  # pylint: disable=protected-access
        date_from=date(2026, 2, 22), date_to=date(2026, 2, 28)
    )

    assert attempts["count"] == 1
    assert report.summary == repo._build_summary(  # pylint: disable=protected-access
        date_from=date(2026, 3, 1),
        date_to=target_date,
        recent_rows=recent_rows,
        prior_rows=prior_rows,
    )
    assert [item.title for item in report.new] == ["AI Browser Launches"]
    assert [item.title for item in report.trending_up] == ["Coding Agents Expand"]
    assert [item.title for item in report.trending_down] == ["Standalone Vector DBs Cool Off"]


def test_weekly_report_falls_back_when_antigravity_payload_is_invalid(monkeypatch) -> None:
    session = _session()
    _seed_weekly_analytics_articles(session)
    target_date = date(2026, 3, 7)
    attempts = {"count": 0}

    def fake_generate(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        del self, args, kwargs
        attempts["count"] += 1
        return {
            "summary": "Broken payload",
            "new": "not-a-list",
            "trending_up": [],
            "trending_down": [],
        }

    monkeypatch.setattr(
        repos.WeeklyAnalyticsRepo,
        "_generate_antigravity_report",
        fake_generate,
        raising=False,
    )

    repo = repos.WeeklyAnalyticsRepo(session)
    report = repo.get_weekly_report(report_date=target_date)

    assert attempts["count"] == 1
    assert report.summary.startswith("Antigravity summary for 2026-03-01 to 2026-03-07:")
    assert [item.title for item in report.new] == ["AI Browser Launches"]
    assert [item.title for item in report.trending_up] == ["Coding Agents Expand"]
    assert [item.title for item in report.trending_down] == ["Standalone Vector DBs Cool Off"]


def test_weekly_report_logs_timeout_warning_before_fallback(
    monkeypatch, caplog
) -> None:
    session = _session()
    _seed_weekly_analytics_articles(session)
    target_date = date(2026, 3, 7)

    def fake_generate(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        del self, args, kwargs
        raise TimeoutError("Antigravity timed out after 60 seconds")

    monkeypatch.setattr(
        repos.WeeklyAnalyticsRepo,
        "_generate_antigravity_report",
        fake_generate,
        raising=False,
    )

    caplog.set_level("WARNING", logger="app.storage.repos")

    report = repos.WeeklyAnalyticsRepo(session).get_weekly_report(report_date=target_date)

    assert report.summary.startswith("Antigravity summary for 2026-03-01 to 2026-03-07:")
    assert "weekly_analytics_antigravity_timeout" in caplog.text
    assert "Antigravity timed out after 60 seconds" in caplog.text


def test_weekly_report_falls_back_when_antigravity_item_is_invalid(
    monkeypatch, caplog
) -> None:
    session = _session()
    _seed_weekly_analytics_articles(session)
    target_date = date(2026, 3, 7)

    def fake_generate(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        del self, args, kwargs
        return {
            "summary": "Broken payload",
            "new": [
                {
                    "title": "AI Browser Launches",
                    "summary": "A section item without a URL must be rejected.",
                }
            ],
            "trending_up": [],
            "trending_down": [],
        }

    monkeypatch.setattr(
        repos.WeeklyAnalyticsRepo,
        "_generate_antigravity_report",
        fake_generate,
        raising=False,
    )

    caplog.set_level("WARNING", logger="app.storage.repos")

    report = repos.WeeklyAnalyticsRepo(session).get_weekly_report(report_date=target_date)

    assert report.summary.startswith("Antigravity summary for 2026-03-01 to 2026-03-07:")
    assert [item.title for item in report.new] == ["AI Browser Launches"]
    assert [item.title for item in report.trending_up] == ["Coding Agents Expand"]
    assert [item.title for item in report.trending_down] == ["Standalone Vector DBs Cool Off"]
    assert "weekly_analytics_antigravity_fallback" in caplog.text
    assert "new[0] is missing url" in caplog.text
