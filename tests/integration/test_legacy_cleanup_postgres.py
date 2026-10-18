import json
import os
import threading
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, insert, select, text, update
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.config.sources import SourceConfig
from app.core.jev import JevAssessment
from app.core.legacy_cleanup import cleanup_verdict
from app.core.pipeline import AdmissionState, _screen_candidate
from app.storage.admission import list_pending, upsert_pending
from app.storage.legacy_cleanup import (
    apply_cleanup,
    build_manifest,
    cache_key,
    fingerprint,
    read_tables,
    restore_cleanup,
)
from app.storage.models_sql import Base
from app.storage.repos import ArticleRepo, SourceRepo

URL = os.getenv("AINEWS_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="AINEWS_TEST_POSTGRES_URL is not set")


@pytest.fixture(name="database")
def cleanup_database():
    admin = create_engine(str(URL))
    schema = "cleanup_" + uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(str(URL), connect_args={"options": "-csearch_path=" + schema})
    Base.metadata.create_all(engine)
    config = SourceConfig(id="example", name="Example", type="rss", url="https://example.com/rss")
    with Session(engine) as session:
        source = SourceRepo(session).upsert_source(config)
        article, _ = ArticleRepo(session).insert_article(
            source_id=source.id, title="About us", url="https://example.com/about",
            url_canonical="https://example.com/about", url_canonical_hash="h" * 64,
            published_at=datetime.now(UTC), content="Our company mission " * 30)
        ArticleRepo(session).add_alias(article_id=article.id, source_id=source.id,
                                       url="https://example.com/about-us")
        upsert_pending(session, key="older-pending", url_canonical_hash="h" * 64,
                       source_id=source.id, payload={"kind": "html_link", "url": article.url},
                       evidence_hash="", policy_version="old", model="jev-1.13.0")
        session.commit()
    with engine.connect() as connection:
        saved = {"tables": read_tables(connection), "screening": {
            "model": "jev-1.13.0", "policy_version": "p1", "prompt_version": "q1"}}
    row = saved["tables"]["articles"][0]
    verdict = cleanup_verdict(row, JevAssessment(0.01, admission_choice="non_editorial",
                                                admission_confidence=0.99))
    manifest = build_manifest(saved, {cache_key(row, saved["screening"]): verdict})
    yield engine, saved, manifest, config
    engine.dispose()
    with admin.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


def test_atomic_apply_targeted_restore_and_ordinary_screen_cache(database, tmp_path):
    from types import SimpleNamespace  # pylint: disable=import-outside-toplevel
    engine, saved, manifest, config = database
    result = apply_cleanup(engine, saved, manifest, tmp_path / "backup.json")
    assert result["deleted_ids"] == [1]
    with Session(engine) as session:
        assert not list_pending(session, source_id=1)
        state = AdmissionState(enabled=True)
        status, _ = _screen_candidate(
            item=SimpleNamespace(**saved["tables"]["articles"][0]), config=config,
            db_source_id=1, article_repo=ArticleRepo(session),
            settings=Settings(_env_file=None, semantic_admission_enabled=True,
                              semantic_admission_policy_version="p1",
                              semantic_admission_prompt_version="q1"),
            relevance_scorer=None, admission_state=state, canonical_hash="h" * 64)
        assert status == "reject" and state.cache_hits == 1 and not state.paused
    again = apply_cleanup(engine, saved, manifest, tmp_path / "again.json")
    assert again["deleted_ids"] == [] and again["already_absent_ids"] == [1]
    same = apply_cleanup(engine, saved, manifest, tmp_path / "backup.json")
    assert same["already_applied"] and same["already_absent_ids"] == [1]
    table = Base.metadata.tables["articles"]
    with engine.begin() as connection:
        newer = dict(saved["tables"]["articles"][0])
        newer.update(id=999, url_canonical_hash="n" * 64)
        connection.execute(insert(table).values(newer))
    restore_cleanup(engine, json.loads((tmp_path / "backup.json").read_text()))
    restore_cleanup(engine, json.loads((tmp_path / "backup.json").read_text()))
    with engine.connect() as connection:
        after = read_tables(connection)
        assert any(row["id"] == 999 for row in after["articles"])
        after["articles"] = [row for row in after["articles"] if row["id"] != 999]
        for name, rows in saved["tables"].items():
            assert sorted(map(fingerprint, rows)) == sorted(map(fingerprint, after[name]))


@pytest.mark.parametrize("change", ["content", "alias", "pending"])
def test_changed_rows_or_dependencies_are_skipped(database, tmp_path, change):
    engine, saved, manifest, _ = database
    with engine.begin() as connection:
        if change == "content":
            table = Base.metadata.tables["articles"]
            connection.execute(update(table).values(content="New AI evidence"))
        else:
            name = "article_aliases" if change == "alias" else "admission_decisions"
            table = Base.metadata.tables[name]
            values = {"url": "https://example.com/new-alias"} if change == "alias" else {
                "provider_status": "ok", "decision": "accept"}
            connection.execute(update(table).values(**values))
    result = apply_cleanup(engine, saved, manifest, tmp_path / "backup.json")
    assert result["deleted_ids"] == [] and result["skipped_changed_ids"] == [1]


def test_delete_failure_rolls_back_aliases_articles_and_cache(database, tmp_path):
    engine, saved, manifest, _ = database
    with engine.begin() as connection:
        connection.execute(text("CREATE FUNCTION reject_delete() RETURNS trigger AS $$ "
                                "BEGIN RAISE EXCEPTION 'test failure'; END; $$ LANGUAGE plpgsql"))
        connection.execute(text("CREATE TRIGGER refuse_delete BEFORE DELETE ON articles "
                                "FOR EACH ROW EXECUTE FUNCTION reject_delete()"))
    with pytest.raises(Exception, match="test failure"):
        apply_cleanup(engine, saved, manifest, tmp_path / "backup.json")
    with engine.connect() as connection:
        assert fingerprint(read_tables(connection)) == fingerprint(saved["tables"])


def test_restore_conflict_rolls_back_without_overwriting_new_data(database, tmp_path):
    engine, saved, manifest, _ = database
    apply_cleanup(engine, saved, manifest, tmp_path / "backup.json")
    table = Base.metadata.tables["admission_decisions"]
    with engine.begin() as connection:
        connection.execute(update(table).where(table.c.decision == "reject").values(reason="NEW"))
    with pytest.raises(ValueError, match="changed admission"):
        restore_cleanup(engine, json.loads((tmp_path / "backup.json").read_text()))
    with engine.connect() as connection:
        assert connection.execute(select(Base.metadata.tables["articles"])).first() is None
        assert connection.execute(select(Base.metadata.tables["article_aliases"])).first() is None


def test_concurrent_writer_finishes_before_locked_hash_recheck(database, tmp_path):
    engine, saved, manifest, _ = database
    table = Base.metadata.tables["articles"]
    writing, release = threading.Event(), threading.Event()

    def writer():
        with engine.begin() as connection:
            connection.execute(update(table).values(content="Concurrent AI evidence"))
            writing.set()
            assert release.wait(10)

    thread = threading.Thread(target=writer)
    thread.start()
    assert writing.wait(10)
    timer = threading.Timer(0.2, release.set)
    timer.start()
    try:
        result = apply_cleanup(engine, saved, manifest, tmp_path / "backup.json")
        assert result["skipped_changed_ids"] == [1]
        assert not result["deleted_ids"]
    finally:
        release.set()
        thread.join(10)
        timer.cancel()


def test_unknown_article_foreign_key_still_refuses_cleanup(database, tmp_path):
    engine, saved, manifest, _ = database
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE extra_refs (id INTEGER PRIMARY KEY, "
                                "article_id INTEGER REFERENCES articles(id))"))
    with pytest.raises(ValueError, match="Unknown article FK dependency: extra_refs"):
        apply_cleanup(engine, saved, manifest, tmp_path / "backup.json")
