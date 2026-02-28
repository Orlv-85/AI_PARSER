from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):  # pylint: disable=too-many-ancestors
    impl = DateTime(timezone=True)
    cache_ok = True

    @property
    def python_type(self) -> type[datetime]:
        return datetime

    def process_bind_param(self, value, dialect):  # type: ignore[no-untyped-def]
        del dialect
        return value

    def process_literal_param(self, value, dialect):  # type: ignore[no-untyped-def]
        del dialect
        return value

    def process_result_value(self, value, dialect):  # type: ignore[no-untyped-def]
        del dialect
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(16))
    url: Mapped[str] = mapped_column(String(1024))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    fetch_interval_minutes: Mapped[int] = mapped_column(Integer, default=30)
    source_weight: Mapped[float] = mapped_column(Float, default=1.0)
    etag: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(256), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    articles: Mapped[list[Article]] = relationship(back_populates="source")
    aliases: Mapped[list[ArticleAlias]] = relationship(back_populates="source")
    approved_candidates: Mapped[list[SourceCandidate]] = relationship(
        foreign_keys="SourceCandidate.approved_source_id",
        back_populates="approved_source",
    )


class SourceImportBatch(Base):
    __tablename__ = "source_import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_text: Mapped[str] = mapped_column(Text)
    parsed_count: Mapped[int] = mapped_column(Integer, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    candidates: Mapped[list[SourceCandidate]] = relationship(back_populates="batch")


class SourceCandidate(Base):
    __tablename__ = "source_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_import_batches.id"), nullable=True, index=True
    )
    raw_input: Mapped[str] = mapped_column(Text)
    normalized_url: Mapped[str] = mapped_column(String(2048), unique=True, index=True)
    candidate_type: Mapped[str] = mapped_column(String(16), default="unknown")
    status: Mapped[str] = mapped_column(String(16), default="draft")
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_of_candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_candidates.id"), nullable=True, index=True
    )
    approved_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id"), nullable=True, index=True
    )
    validation_status: Mapped[str] = mapped_column(String(16), default="pending")
    validation_detected_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    batch: Mapped[SourceImportBatch | None] = relationship(back_populates="candidates")
    duplicate_of: Mapped[SourceCandidate | None] = relationship(
        remote_side="SourceCandidate.id",
        foreign_keys=[duplicate_of_candidate_id],
    )
    approved_source: Mapped[Source | None] = relationship(
        foreign_keys=[approved_source_id],
        back_populates="approved_candidates",
    )


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(512))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(String(2048))
    url_canonical: Mapped[str] = mapped_column(String(2048))
    url_canonical_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    ai_relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    freshness_score: Mapped[float] = mapped_column(Float, default=0.0)
    rank_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    source: Mapped[Source | None] = relationship(back_populates="articles")
    aliases: Mapped[list[ArticleAlias]] = relationship(back_populates="article")


class ArticleAlias(Base):
    __tablename__ = "article_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    url: Mapped[str] = mapped_column(String(2048))
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    article: Mapped[Article] = relationship(back_populates="aliases")
    source: Mapped[Source] = relationship(back_populates="aliases")


class FetchRun(Base):
    __tablename__ = "fetch_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    parsed_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)


Index("ix_articles_published_at_desc", Article.published_at.desc())
Index("ix_articles_rank_score_desc", Article.rank_score.desc())
