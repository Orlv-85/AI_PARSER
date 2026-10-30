import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.storage.models_sql import Article, Base, Source


@pytest.fixture(name="registry")
def registry_fixture(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'registry.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        canonical = Source(source_key="deepmind_blog", name="DeepMind", type="rss",
                           url="https://deepmind.com/blog/feed/basic", enabled=True,
                           etag="old-etag", last_status_code=200)
        duplicate = Source(source_key="deepmind-google-blog-rss-xml", name="Duplicate",
                           type="rss", url="https://deepmind.google/blog/rss.xml", enabled=True)
        unrelated = Source(source_key="other", name="Other", type="rss",
                           url="https://example.com/feed", enabled=True)
        session.add_all([canonical, duplicate, unrelated])
        session.flush()
        session.add(Article(source_id=canonical.id, title="History", url="https://example.com/a",
                            url_canonical="https://example.com/a", url_canonical_hash="a" * 64,
                            published_at=datetime.now(UTC)))
        session.commit()
    yield engine, url, tmp_path / "backup.json"
    engine.dispose()


def _run(url: str, *arguments: str):
    root = Path(__file__).resolve().parents[2]
    # Run in the test's tmp dir: the script's Settings read .env from the working directory.
    return subprocess.run(
        [sys.executable, str(root / "scripts/repair_source_registry.py"), *arguments],
        cwd=Path(url.removeprefix("sqlite:///")).parent,
        env={**os.environ, "AINEWS_DATABASE_URL": url,
             "AINEWS_SOURCES_PATH": str(root / "sources.yaml")},
        capture_output=True, text=True, check=False,
    )


def _source(session: Session, key: str) -> Source:
    return session.scalars(select(Source).where(Source.source_key == key)).one()


def test_repair_is_dry_run_by_default(registry) -> None:
    engine, url, backup = registry
    result = _run(url)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["applied"] is False
    with Session(engine) as session:
        assert _source(session, "deepmind_blog").etag
        assert _source(session, "deepmind-google-blog-rss-xml").enabled
    assert not backup.exists()


def test_apply_preserves_history_and_is_idempotent(registry) -> None:
    engine, url, backup = registry
    result = _run(url, "--apply", "--backup", str(backup))
    assert result.returncode == 0, result.stderr
    assert backup.stat().st_mode & 0o777 == 0o600
    assert len(json.loads(backup.read_text())["sources"]) == 2
    with Session(engine) as session:
        canonical = _source(session, "deepmind_blog")
        assert canonical.url == "https://deepmind.google/blog/rss.xml"
        assert canonical.etag is None
        assert canonical.last_status_code is None
        assert session.scalars(select(Article)).one().source_id == canonical.id
        assert not _source(session, "deepmind-google-blog-rss-xml").enabled
        assert _source(session, "other").enabled
    second = _run(url, "--apply", "--backup", str(backup))
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["changes"] == []


@pytest.mark.parametrize("failure", ["changed_duplicate", "existing_backup"])
def test_unsafe_apply_refuses_before_any_mutation(registry, failure: str) -> None:
    engine, url, backup = registry
    if failure == "existing_backup":
        backup.write_text("existing backup")
    else:
        with Session(engine) as session:
            duplicate = _source(session, "deepmind-google-blog-rss-xml")
            duplicate.url = "https://example.com/different-feed"
            session.commit()
    result = _run(url, "--apply", "--backup", str(backup))
    assert result.returncode != 0
    with Session(engine) as session:
        canonical = _source(session, "deepmind_blog")
        assert canonical.url == "https://deepmind.com/blog/feed/basic"
        assert canonical.etag == "old-etag"
        assert _source(session, "deepmind-google-blog-rss-xml").enabled
