from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.storage.article_repo import ArticleRepo
from app.storage.models_sql import Base
from app.web.app import create_app


def _row(key: str, rank: float = 0.5, category: str | None = None) -> dict:
    row = {
        "source_id": None, "title": "AI release " + key,
        "url": f"https://example.com/{key}", "url_canonical": f"https://example.com/{key}",
        "url_canonical_hash": key, "published_at": datetime.now(UTC),
        "ai_relevance_score": 0.9, "freshness_score": 0.5, "rank_score": rank,
    }
    if category is not None:
        row.update(category=category, category_confidence=0.98)
    return row


@pytest.mark.parametrize("batch", [False, True])
def test_category_updates_preserve_accepted_values_on_fallback(batch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        repo = ArticleRepo(session)
        original, _ = repo.insert_article(**_row("existing", category="Security"))
        if batch:
            assert repo.upsert_articles_batch([
                _row("existing", 0.7, "AI Coding"),
                _row("new", 0.4),
                _row("duplicate", 0.6, "Infrastructure"),
                _row("duplicate", 0.8),
            ]) == (2, 2)
        else:
            repo.insert_article(**_row("existing", 0.7, "AI Coding"))
            repo.insert_article(**_row("new", 0.4))
            repo.insert_article(**_row("duplicate", 0.6, "Infrastructure"))
            repo.insert_article(**_row("duplicate", 0.8))
        session.flush()
        session.expire_all()
        assert original.category == "AI Coding"
        assert original.category_confidence == 0.98

        if batch:
            repo.upsert_articles_batch([_row("existing", 0.3)])
        else:
            repo.insert_article(**_row("existing", 0.3))
        session.flush()
        session.expire_all()
        assert original.category == "AI Coding"
        assert original.category_confidence == 0.98
        assert original.rank_score == 0.3
        rows = repo.list_for_view(hours=24, limit=10, query=None, days=1, sort="rank")
        stored = {article.url_canonical_hash: article for article, _, _ in rows}
        assert stored["new"].category is None
        assert stored["duplicate"].category == "Infrastructure"
        assert stored["duplicate"].category_confidence == 0.98
        assert stored["duplicate"].rank_score == 0.8


def test_category_filter_and_sort_apply_before_limit() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        repo = ArticleRepo(session)
        for row in (
            _row("unknown", 1.0), _row("security", 0.9, "Security"),
            _row("coding-low", 0.3, "AI Coding"), _row("coding-high", 0.8, "AI Coding"),
        ):
            repo.insert_article(**row)
        kwargs = {"hours": 24, "limit": 3, "query": None, "days": 1, "sort": "category"}
        rows = repo.list_for_view(**kwargs)
        assert [article.url_canonical_hash for article, _, _ in rows] == [
            "coding-high", "coding-low", "security",
        ]
        filtered = repo.list_for_view(**{**kwargs, "category": "Security", "limit": 1})
        assert [article.url_canonical_hash for article, _, _ in filtered] == ["security"]
        assert not repo.list_for_view(**{**kwargs, "category": "missing"})


def test_category_metadata_reaches_news_links_and_exports(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    engine = create_engine(f"sqlite:///{tmp_path}/web.db")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    with sessions() as session:
        repo = ArticleRepo(session)
        repo.insert_article(**_row("coding", 0.8, "AI Coding"))
        repo.insert_article(**_row("security", 0.9, "Security"))
        repo.insert_article(**_row("unknown", 1.0))
        session.commit()
    web_module = import_module("app.web.app")
    monkeypatch.setattr(web_module, "create_all", lambda: None)
    monkeypatch.setattr(web_module, "SessionLocal", sessions)
    try:
        with TestClient(create_app()) as client:
            response = client.get("/api/news?sort=category")
            assert response.status_code == 200
            rows = response.json()
            assert [row.get("category") for row in rows] == ["AI Coding", "Security", None]
            assert rows[0]["category_confidence"] == 0.98
            assert "category_confidence" not in rows[2]
            filtered = client.get("/api/news", params={"category": "Security"}).json()
            assert len(filtered) == 1
            assert filtered[0]["category"] == "Security"
            exported = client.get("/api/news/export", params={"category": "AI Coding"}).json()
            assert len(exported) == 1
            assert exported[0]["category"] == "AI Coding"
            assert exported[0]["category_confidence"] == 0.98
            feed = client.get("/api/news/links", params={
                "date": datetime.now(UTC).date().isoformat(), "include_content": "true",
            }).json()
            by_url = {row["url"]: row for row in feed}
            assert by_url["https://example.com/coding"]["category"] == "AI Coding"
            assert by_url["https://example.com/coding"]["rank_score"] == 0.8
            assert "category" not in by_url["https://example.com/unknown"]
    finally:
        get_settings.cache_clear()


def test_category_migration_preserves_existing_rows_and_downgrades(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "migration.db"
    monkeypatch.setenv("AINEWS_DATABASE_URL", f"sqlite:///{db_path}")
    config = Config()
    config.set_main_option("script_location", str(
        Path(__file__).resolve().parents[2] / "src/app/storage/migrations",
    ))
    command.upgrade(config, "8b3a2d4e9f10")
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO articles (title, url, url_canonical, url_canonical_hash, "
            "published_at, discovered_at, ai_relevance_score, freshness_score, rank_score) "
            "VALUES ('Existing AI news', 'https://example.com/old', 'https://example.com/old', "
            "'old-hash', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0.5, 0.5, 0.5)"
        ))
    command.upgrade(config, "c9e71b82a640")
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT title, category, category_confidence FROM articles"
        )).one() == ("Existing AI news", None, None)
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
            "c9e71b82a640"
        )
    command.downgrade(config, "8b3a2d4e9f10")
    with engine.connect() as connection:
        assert "category" not in {column["name"] for column in inspect(connection).get_columns(
            "articles",
        )}
        assert connection.execute(text("SELECT title FROM articles")).scalar() == "Existing AI news"
