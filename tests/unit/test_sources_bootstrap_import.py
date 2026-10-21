from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import sources as sources_config
from app.storage.models_sql import Base, Source
from app.storage.source_repo import SourceRepo


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_bootstrap_sources_into_db_imports_yaml_once_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
version: 1
sources:
  - id: zebra_feed
    name: Zebra Feed
    type: rss
    url: https://example.com/zebra.xml
    enabled: true
    fetch_interval_minutes: 15
    source_weight: 0.8
  - id: alpha_blog
    name: Alpha Blog
    type: html
    url: https://example.com/alpha
    enabled: true
    fetch_interval_minutes: 45
    source_weight: 1.2
    html:
      list_selector: main
      link_selector: a
""".strip(),
        encoding="utf-8",
    )

    session = _session()
    repo = SourceRepo(session)

    sources_config.bootstrap_sources_into_db(path=path, repo=repo)
    sources_config.bootstrap_sources_into_db(path=path, repo=repo)
    session.commit()

    rows = session.query(Source).order_by(Source.source_key.asc()).all()

    assert [row.source_key for row in rows] == ["alpha_blog", "zebra_feed"]
    assert [row.url for row in rows] == [
        "https://example.com/alpha",
        "https://example.com/zebra.xml",
    ]
    assert [row.fetch_interval_minutes for row in rows] == [45, 15]
    assert [row.source_weight for row in rows] == [1.2, 0.8]
    assert all(row.enabled is True for row in rows)
    assert len(rows) == 2


def test_bootstrap_sources_into_db_keeps_existing_url_owner_when_repoint_would_duplicate(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
version: 1
sources:
  - id: alpha_feed
    name: Alpha Feed Repointed
    type: rss
    url: https://example.com/beta.xml
    enabled: true
    fetch_interval_minutes: 15
    source_weight: 0.7
  - id: beta_feed
    name: Beta Feed
    type: rss
    url: https://example.com/beta.xml
    enabled: true
    fetch_interval_minutes: 20
    source_weight: 1.1
""".strip(),
        encoding="utf-8",
    )

    session = _session()
    repo = SourceRepo(session)
    session.add_all(
        [
            Source(
                source_key="alpha_feed",
                name="Alpha Feed",
                type="rss",
                url="https://example.com/alpha.xml",
                enabled=True,
                fetch_interval_minutes=10,
                source_weight=0.5,
            ),
            Source(
                source_key="beta_feed",
                name="Beta Feed",
                type="rss",
                url="https://example.com/beta.xml",
                enabled=True,
                fetch_interval_minutes=20,
                source_weight=1.1,
            ),
        ]
    )
    session.commit()

    sources_config.bootstrap_sources_into_db(path=path, repo=repo)
    sources_config.bootstrap_sources_into_db(path=path, repo=repo)
    session.commit()

    rows = session.query(Source).order_by(Source.source_key.asc()).all()

    assert len(rows) == 2
    assert {row.url for row in rows} == {
        "https://example.com/alpha.xml",
        "https://example.com/beta.xml",
    }
    assert rows[0].source_key == "alpha_feed"
    assert rows[0].url == "https://example.com/alpha.xml"
    assert rows[0].name == "Alpha Feed"
    assert rows[1].source_key == "beta_feed"
    assert rows[1].url == "https://example.com/beta.xml"
