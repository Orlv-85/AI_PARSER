# pylint: disable=protected-access

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.sources.candidate_fields import read_str
from app.storage.models_sql import Base, Source
from app.storage.source_repo import SourceRepo


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_disable_source_rejects_missing_source() -> None:
    repo = SourceRepo(_session())

    with pytest.raises(ValueError, match="source not found: 999"):
        repo.disable_source(999)


def test_create_from_candidate_allocates_unique_source_key_when_base_key_conflicts() -> None:
    session = _session()
    repo = SourceRepo(session)
    session.add(
        Source(
            source_key="example-com-blog",
            name="Existing",
            type="html",
            url="https://example.com/already-there",
            enabled=True,
            fetch_interval_minutes=30,
            source_weight=1.0,
        )
    )
    session.flush()

    created = repo.create_from_candidate(
        {
            "normalized_url": "https://example.com/blog",
            "candidate_type": "html",
        }
    )

    assert created.source_key == "example-com-blog-2"
    assert created.name == "example.com"
    assert created.url == "https://example.com/blog"


def test_source_repo_helper_methods_cover_missing_values_and_unknown_type_fallback() -> None:
    repo = SourceRepo(_session())

    with pytest.raises(ValueError, match="candidate field is required: normalized_url"):
        read_str({}, "normalized_url")

    assert repo._source_name_for_candidate(
        {"normalized_url": "http:///just-path-only"},
        default="Fallback Name",
    ) == "Fallback Name"
    assert repo._source_name_for_candidate(
        {"normalized_url": "http:///just-path-only"},
    ) == "http:///just-path-only"

    candidate = SimpleNamespace(
        normalized_url="https://example.com/feed.xml",
        candidate_type="unknown",
        validation_detected_type="rss",
    )
    assert repo._source_type_for_candidate(candidate, default="html") == "rss"
