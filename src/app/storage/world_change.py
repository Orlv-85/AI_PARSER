"""Storage of Jev world_change answers and the digest scope they are asked for."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.bulletin.world_change import WorldChange
from app.core.canonicalize import canonical_url_hash
from app.storage.models_sql import (
    Article,
    NewsDigestGroup,
    NewsDigestItem,
    NewsDigestReport,
    WorldChangeAssessment,
)


class WorldChangeRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def digest_articles(self, day: date) -> tuple[list[Article], int] | None:
        """Stored articles of the day's published digest (by URL, then canonical hash) and the
        number of digest URLs without one; None when the day has no digest."""
        report_id = self.session.scalar(
            select(NewsDigestReport.id).where(NewsDigestReport.report_date == day))
        if report_id is None:
            return None
        urls = list(dict.fromkeys(self.session.scalars(
            select(NewsDigestItem.url).join(NewsDigestGroup)
            .where(NewsDigestGroup.report_id == report_id)
            .order_by(NewsDigestGroup.position, NewsDigestItem.position))))
        found = {a.url: a for a in self.session.scalars(
            select(Article).where(Article.url.in_(urls)))}
        missing = {canonical_url_hash(u): u for u in urls if u not in found}
        if missing:
            for article in self.session.scalars(
                    select(Article).where(Article.url_canonical_hash.in_(list(missing)))):
                found[missing[article.url_canonical_hash]] = article
        articles = {a.id: a for a in found.values()}
        return sorted(articles.values(), key=lambda a: a.id), len(urls) - len(found)

    def answered(self, hashes: list[str], version: str) -> set[str]:
        return set(self.session.scalars(select(WorldChangeAssessment.url_canonical_hash).where(
            WorldChangeAssessment.url_canonical_hash.in_(hashes),
            WorldChangeAssessment.question_version == version)))

    def get(self, url_hash: str, version: str) -> WorldChangeAssessment | None:
        return self.session.scalar(select(WorldChangeAssessment).where(
            WorldChangeAssessment.url_canonical_hash == url_hash,
            WorldChangeAssessment.question_version == version))

    def save(self, article: Article, answer: WorldChange, *, version: str, model: str) -> bool:
        """Store the answers; False (nothing changed) when the pair already has a row."""
        if self.get(article.url_canonical_hash, version) is not None:
            return False
        self.session.add(WorldChangeAssessment(
            url_canonical_hash=article.url_canonical_hash, article_id=article.id,
            world_change=answer.world_change,
            world_change_confidence=answer.world_change_confidence,
            area=answer.area, area_confidence=answer.area_confidence,
            actor=answer.actor, actor_confidence=answer.actor_confidence,
            harm_to_people=answer.harm_to_people, question_version=version, model=model))
        self.session.flush()
        return True
