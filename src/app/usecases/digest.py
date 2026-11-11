"""Stored daily digest of the web: save and read, one session each."""

from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.storage.digest_repo import NewsDigestRepo
from app.storage.models_sql import NewsDigestReport


def stored_digest(session_factory: Callable[[], Session], report_date: date
                  ) -> NewsDigestReport | None:
    """The digest of a day with its groups and items loaded; None when none is stored."""
    with session_factory() as session:
        digest: NewsDigestReport | None = NewsDigestRepo(session).get_digest(
            report_date=report_date)
        return digest


def save_digest(session_factory: Callable[[], Session], report_date: date,
                groups: list[dict[str, Any]]) -> NewsDigestReport | None:
    """Replaces the digest of a day, commits, and returns it as stored."""
    with session_factory() as session:
        repo = NewsDigestRepo(session)
        repo.save_digest(report_date=report_date, groups=groups)
        session.commit()
        digest: NewsDigestReport | None = repo.get_digest(report_date=report_date)
        return digest
