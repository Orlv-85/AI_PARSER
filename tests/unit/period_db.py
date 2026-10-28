"""Database helpers for the period signals tests: a few digest days with extracted entities."""
from datetime import date, datetime, timedelta

from app.core.canonicalize import canonical_url_hash
from app.core.daily.signals_extract import ExtractedEntity, Extraction
from app.storage.daily_signals import DailySignalRepo
from app.storage.digest_repo import NewsDigestRepo
from app.storage.models_sql import Article

COMPARABLE_FROM = date(2026, 10, 10)
NOW = datetime(2026, 10, 28, 3, 0)  # a Wednesday: the latest completed week starts 2026-10-19
NAMES = ("Alpha", "Bravo", "Charlie")


def seed_day(maker, day: date, *, comparable_from: date = COMPARABLE_FROM, names=NAMES) -> None:
    """One digest for `day` with one article per name, each mentioning one model."""
    with maker() as session:
        articles = []
        for i, name in enumerate(names):
            url = f"https://p{i}.com/{day}/{name}"
            article = Article(title=f"Story {day} {i}", url=url, url_canonical=url,
                              url_canonical_hash=canonical_url_hash(url), content=name)
            session.add(article)
            articles.append((name, article))
        session.flush()
        NewsDigestRepo(session).save_digest(report_date=day, groups=[{
            "title": "Models", "items": [{"title": a.title, "summary": "s", "url": a.url}
                                         for _, a in articles]}])
        repo = DailySignalRepo(session, comparable_from=comparable_from)
        repo.replace_membership(day)
        for name, article in articles:
            repo.save_extraction(article, Extraction("model_release", False, (ExtractedEntity(
                name, name, "model", None, "primary", False, None),)), content_hash="h")
        session.commit()


def seed_weeks(maker, *starts: date, comparable_from: date = COMPARABLE_FROM) -> None:
    """Digests and daily snapshots for every day of the weeks that start on `starts`."""
    last = max(starts) + timedelta(days=6)
    for start in starts:
        for offset in range(7):
            seed_day(maker, start + timedelta(days=offset), comparable_from=comparable_from)
    with maker() as session:
        DailySignalRepo(session, comparable_from=comparable_from).recompute_reports(
            last, now=NOW)
        session.commit()
