"""Loads sources.yaml into the sources table once (operator command `db-bootstrap`).

Flow and decisions: src/app/usecases/sources/onboarding.md.
"""
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.config.sources import load_sources
from app.storage.models_sql import Source


def bootstrap_sources_into_db(*, path: Path, repo: Any) -> list[Any]:
    upsert_source = getattr(repo, "upsert_source", None)
    session = getattr(repo, "session", None)
    if not callable(upsert_source) or session is None:
        raise ValueError("repo must provide upsert_source(...) and a SQLAlchemy session")

    imported_sources: list[Any] = []
    seen_urls: set[str] = set()

    for source_config in sorted(load_sources(path), key=lambda item: item.id):
        source_url = str(source_config.url)
        if source_url in seen_urls:
            continue

        existing_by_key = session.execute(
            select(Source).where(Source.source_key == source_config.id).limit(1)
        ).scalar_one_or_none()
        existing_by_url = session.execute(
            select(Source).where(Source.url == source_url).limit(1)
        ).scalar_one_or_none()

        if (
            existing_by_key is not None
            and existing_by_url is not None
            and getattr(existing_by_key, "id", None) != getattr(existing_by_url, "id", None)
        ):
            continue

        if existing_by_key is not None:
            imported_sources.append(upsert_source(source_config))
            seen_urls.add(source_url)
            continue

        if existing_by_url is not None:
            imported_sources.append(existing_by_url)
            seen_urls.add(source_url)
            continue

        imported_sources.append(upsert_source(source_config))
        seen_urls.add(source_url)

    return imported_sources
