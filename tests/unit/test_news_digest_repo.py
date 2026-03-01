from datetime import date

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
