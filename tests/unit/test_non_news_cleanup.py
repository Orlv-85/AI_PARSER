import json
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config.sources import SourceConfig
from app.core.canonicalize import canonical_url_hash, canonicalize_url
from app.storage.models_sql import ArticleAlias, Base
from app.storage.non_news_cleanup import (
    EXPORT_TABLES,
    build_cleanup_plan,
    export_database,
    restoration_sql,
)
from app.storage.repos import ArticleRepo, SourceRepo


def test_dry_run_dependencies_and_restore_roundtrip(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'news.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source = SourceRepo(session).upsert_source(SourceConfig(
            id="example", name="Example", type="rss", url="https://example.com/feed"))
        repo = ArticleRepo(session)
        for path, title, content in (
            ("about", "About", "Company's mission"),
            ("products/tool", "AI Tool", "Features. Request a demo"),
            ("news/tool-release", "Introducing AI Tool", "Features. Request a demo"),
        ):
            url = f"https://example.com/{path}"
            article, _ = repo.insert_article(source_id=source.id, title=title, url=url,
                                             url_canonical=canonicalize_url(url),
                                             url_canonical_hash=canonical_url_hash(url),
                                             published_at=datetime.now(UTC), content=content)
            if path == "about":
                session.add(ArticleAlias(article_id=article.id, source_id=source.id, url=url,
                                         discovered_at=datetime.now(UTC)))
        session.commit()
    export = json.loads(json.dumps(export_database(database_url), default=str))
    # Frozen payloads refer to articles by URL, prefixed ID or canonical hash.
    export["tables"]["weekly_snapshots"] = [{"id": "snap", "payload": json.dumps(
        {"evidence": [{"id": "article-1", "url": "https://example.com/about/"}]})}]
    export["tables"]["weekly_publications"] = [{"report_date": "2026-10-04",
                                               "snapshot_id": "snap"}]
    plan = build_cleanup_plan(export)
    assert plan["confident_count"] == 1
    assert plan["uncertain_count"] == 1
    assert plan["proposed_deletions"] == {"articles": [1], "article_aliases": [1]}
    assert plan["dependency_counts"]["article_aliases"] == 1
    assert plan["dependency_counts"]["weekly_snapshots"] == 1
    assert plan["dependency_counts"]["weekly_publications"] == 1
    sql = restoration_sql(export, plan)
    assert "Company''s mission" in sql
    assert sql.index("INSERT INTO articles") < sql.index("INSERT INTO article_aliases")
    with engine.begin() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM articles")).scalar() == 3
        connection.execute(text("DELETE FROM article_aliases WHERE article_id=1"))
        connection.execute(text("DELETE FROM articles WHERE id=1"))
    with engine.connect() as connection:
        driver = connection.connection.driver_connection
        assert driver is not None
        driver.executescript(sql)
        assert connection.execute(text("SELECT COUNT(*) FROM articles")).scalar() == 3
        assert connection.execute(text("SELECT COUNT(*) FROM article_aliases")).scalar() == 1
    assert build_cleanup_plan(export)["candidate_sha256"] == plan["candidate_sha256"]


def test_incomplete_export_cannot_be_presented_as_a_cleanup_plan() -> None:
    with pytest.raises(ValueError, match="Incomplete dependency export"):
        build_cleanup_plan({"tables": {"articles": []}})


def test_missing_dates_are_not_a_cleanup_reason() -> None:
    tables: dict[str, list[dict[str, Any]]] = {name: [] for name in EXPORT_TABLES}
    tables["articles"] = [{"id": 1, "source_id": None, "url": "https://example.com/article",
                           "title": "AI system update", "content": "Full article without a date",
                           "published_at": None, "url_canonical_hash": "hash"}]
    assert build_cleanup_plan({"tables": tables})["confident_count"] == 0
    assert build_cleanup_plan({"tables": tables})["uncertain_count"] == 0
