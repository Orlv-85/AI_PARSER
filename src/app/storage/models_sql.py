from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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


class AdmissionDecision(Base):
    __tablename__ = "admission_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    url_canonical_hash: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    payload: Mapped[str] = mapped_column(Text)
    evidence_hash: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_status: Mapped[str] = mapped_column(String(32), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class CollectionStatus(Base):
    __tablename__ = "collection_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
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
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    publication_day: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    publication_status: Mapped[str] = mapped_column(
        String(32), default="legacy_unverified", server_default="legacy_unverified"
    )
    publication_precision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    date_provenance: Mapped[str | None] = mapped_column(Text, nullable=True)
    enrichment_provenance: Mapped[str | None] = mapped_column(Text, nullable=True)
    material_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    compared_products: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    ai_relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    freshness_score: Mapped[float] = mapped_column(Float, default=0.0)
    rank_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

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


class NewsDigestReport(Base):
    __tablename__ = "news_digest_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    groups: Mapped[list[NewsDigestGroup]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="NewsDigestGroup.position",
    )


class NewsDigestGroup(Base):
    __tablename__ = "news_digest_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("news_digest_reports.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer, default=0)

    report: Mapped[NewsDigestReport] = relationship(back_populates="groups")
    items: Mapped[list[NewsDigestItem]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="NewsDigestItem.position",
    )


class NewsDigestItem(Base):
    __tablename__ = "news_digest_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("news_digest_groups.id"), index=True)
    title: Mapped[str] = mapped_column(String(512))
    summary: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(2048))
    position: Mapped[int] = mapped_column(Integer, default=0)

    group: Mapped[NewsDigestGroup] = relationship(back_populates="items")


class WeeklyAnalyticsStoredReport(Base):
    __tablename__ = "weekly_analytics_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    items: Mapped[list[WeeklyAnalyticsStoredItem]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="WeeklyAnalyticsStoredItem.position",
    )


class WeeklyAnalyticsStoredItem(Base):
    __tablename__ = "weekly_analytics_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("weekly_analytics_reports.id"),
        index=True,
    )
    section_name: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(512))
    summary: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(2048))
    position: Mapped[int] = mapped_column(Integer, default=0)

    report: Mapped[WeeklyAnalyticsStoredReport] = relationship(back_populates="items")


class WeeklySourceVersion(Base):
    __tablename__ = "weekly_source_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, index=True)
    publisher: Mapped[str] = mapped_column(String(255), index=True)
    configured_at: Mapped[datetime] = mapped_column(UTCDateTime())
    interval_minutes: Mapped[int] = mapped_column(Integer)
    configuration: Mapped[str] = mapped_column(Text)


class WeeklyCoverageAttempt(Base):
    __tablename__ = "weekly_coverage_attempts"
    __table_args__ = (UniqueConstraint("run_id", "source_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[int] = mapped_column(Integer, index=True)
    version_id: Mapped[str] = mapped_column(String(64), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    outcome: Mapped[str] = mapped_column(String(32))
    complete: Mapped[bool] = mapped_column(Boolean)
    expected_attempts: Mapped[int] = mapped_column(Integer)
    checked_at: Mapped[datetime] = mapped_column(UTCDateTime())


class WeeklyInputObservation(Base):
    __tablename__ = "weekly_input_observations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, index=True)
    canonical_hash: Mapped[str] = mapped_column(String(64), index=True)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
    discovered_at: Mapped[datetime] = mapped_column(UTCDateTime())
    payload: Mapped[str] = mapped_column(Text)


class WeeklyDecision(Base):
    __tablename__ = "weekly_decisions"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    task: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())


class WeeklyTopicVersion(Base):
    __tablename__ = "weekly_topic_versions"
    __table_args__ = (UniqueConstraint("taxonomy_version", "topic_id"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    taxonomy_version: Mapped[str] = mapped_column(String(64))
    topic_id: Mapped[str] = mapped_column(String(64))
    definition: Mapped[str] = mapped_column(Text)


class WeeklyJob(Base):
    __tablename__ = "weekly_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, index=True)
    methodology_version: Mapped[str] = mapped_column(String(64))
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    input_payload: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)


class WeeklySnapshot(Base):
    __tablename__ = "weekly_snapshots"
    __table_args__ = (UniqueConstraint("report_date", "revision"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, index=True)
    revision: Mapped[int] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime())
    data_cutoff: Mapped[datetime] = mapped_column(UTCDateTime())
    payload: Mapped[str] = mapped_column(Text)


class WeeklyPublication(Base):
    __tablename__ = "weekly_publications"

    report_date: Mapped[date] = mapped_column(Date, primary_key=True)
    snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("weekly_snapshots.id"), nullable=True,
    )



def _now() -> datetime:
    return datetime.now(UTC)


class ArticleSignal(Base):  # pylint: disable=too-many-instance-attributes
    """One extraction attempt result per article and extraction version (feature 006)."""
    __tablename__ = "article_signals"
    __table_args__ = (UniqueConstraint("article_id", "extraction_version",
                                       name="uq_article_signals_article_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"),
                                            index=True)
    extraction_version: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), index=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    retry_used: Mapped[bool] = mapped_column(Boolean, default=False)
    event_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    novelty_claim: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    provenance: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)


class DailySignalScope(Base):
    """Digest membership: which articles belong to which digest day."""
    __tablename__ = "daily_signal_scope"
    __table_args__ = (UniqueConstraint("scope_day", "article_id",
                                       name="uq_daily_signal_scope_day_article"),
                      Index("ix_daily_signal_scope_kind_day", "kind", "scope_day"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope_day: Mapped[date] = mapped_column(Date)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"),
                                            index=True)
    kind: Mapped[str] = mapped_column(String(16))
    publisher: Mapped[str] = mapped_column(String(255))
    item_url: Mapped[str] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)


class SignalMention(Base):  # pylint: disable=too-many-instance-attributes
    """Mention evidence; no FK to articles so it survives retention (plan Decision 4)."""
    __tablename__ = "signal_mentions"
    __table_args__ = (
        UniqueConstraint("scope_day", "article_id", "url_canonical_hash", "extraction_version",
                         "name_key", "type_group", name="uq_signal_mentions_identity"),
        Index("ix_signal_mentions_article_hash", "article_id", "url_canonical_hash"),
        Index("ix_signal_mentions_group_base", "type_group", "base_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(Integer)
    url_canonical_hash: Mapped[str] = mapped_column(String(64))
    scope_day: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(16))
    extraction_version: Mapped[str] = mapped_column(String(64))
    publisher: Mapped[str] = mapped_column(String(255))
    surface_name: Mapped[str] = mapped_column(String(255))
    canonical_name: Mapped[str] = mapped_column(String(255))
    name_key: Mapped[str] = mapped_column(String(255))
    base_key: Mapped[str] = mapped_column(String(255))
    family_key: Mapped[str] = mapped_column(String(255))
    type_group: Mapped[str] = mapped_column(String(16))
    entity_type: Mapped[str] = mapped_column(String(32))
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vendor_key: Mapped[str] = mapped_column(String(255), default="")
    vendor_inferred: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(16))
    is_new: Mapped[bool] = mapped_column(Boolean)
    novelty_quote: Mapped[str | None] = mapped_column(String(400), nullable=True)
    entity_key: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)


class AIEntity(Base):  # pylint: disable=too-many-instance-attributes
    """Derived entity with a stable id per entity_key."""
    __tablename__ = "ai_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_key: Mapped[str] = mapped_column(String(300), unique=True)
    display_name: Mapped[str] = mapped_column(String(255))
    type_group: Mapped[str] = mapped_column(String(16))
    type: Mapped[str] = mapped_column(String(32))
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vendor_class: Mapped[str] = mapped_column(String(255), default="")
    base_key: Mapped[str] = mapped_column(String(255))
    family_key: Mapped[str] = mapped_column(String(255))
    first_seen_day: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)


class AIEntityOverride(Base):  # pylint: disable=too-many-instance-attributes
    """Operator alias/merge override selecting mentions by stable selectors."""
    __tablename__ = "ai_entity_overrides"
    __table_args__ = (UniqueConstraint("kind", "type_group", "match_key", "vendor_class",
                                       name="uq_ai_entity_overrides_selector"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    type_group: Mapped[str] = mapped_column(String(16))
    match_key: Mapped[str] = mapped_column(String(255))
    vendor_class: Mapped[str] = mapped_column(String(255), default="")
    target_base_key: Mapped[str] = mapped_column(String(255))
    target_vendor_class: Mapped[str] = mapped_column(String(255), default="")
    target_entity_key: Mapped[str] = mapped_column(String(300))
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)


class DailySignalReport(Base):  # pylint: disable=too-many-instance-attributes
    """Stored daily signals snapshot (one per comparable published day)."""
    __tablename__ = "daily_signal_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    methodology_version: Mapped[str] = mapped_column(String(64))
    extraction_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    payload_hash: Mapped[str] = mapped_column(String(64))
    thresholds: Mapped[str] = mapped_column(Text)
    payload: Mapped[str] = mapped_column(Text)
    coverage: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)

Index("ix_articles_published_at_desc", Article.published_at.desc())
Index("ix_articles_rank_score_desc", Article.rank_score.desc())
