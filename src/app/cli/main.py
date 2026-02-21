from datetime import UTC, datetime

import typer

from app.config.settings import get_settings
from app.config.sources import load_sources
from app.core.canonicalize import canonical_url_hash, canonicalize_url
from app.core.scoring import ai_relevance_score, freshness_score, rank_score
from app.ingest.fetcher import Fetcher
from app.ingest.html import fetch_html
from app.ingest.rss import fetch_rss
from app.observability import setup_json_logging
from app.storage import SessionLocal, create_all
from app.storage.repos import ArticleRepo, SourceRepo

app = typer.Typer(help="AI News Collector CLI")


@app.callback()
def main() -> None:
    """CLI entrypoint."""


@app.command()
def sources() -> None:
    settings = get_settings()
    configs = load_sources(settings.sources_path)
    for source in configs:
        status = "enabled" if source.enabled else "disabled"
        typer.echo(
            f"{source.id}\t{source.type}\t{status}\t{source.url}"
        )


@app.command()
def fetch(once: bool = typer.Option(True, "--once", help="Run a single fetch cycle.")) -> None:
    if not once:
        raise typer.BadParameter("Only --once mode is supported in MVP.")

    settings = get_settings()
    logger = setup_json_logging()
    configs = load_sources(settings.sources_path)
    create_all()

    run_id = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    fetched_count = 0
    new_count = 0
    duplicate_count = 0
    error_count = 0
    fetcher = Fetcher(
        timeout_seconds=settings.request_timeout_seconds,
        max_retries=settings.max_retries,
        per_source_min_interval_seconds=settings.per_source_min_interval_seconds,
    )

    with SessionLocal() as session:
        source_repo = SourceRepo(session)
        article_repo = ArticleRepo(session)

        for config in configs:
            db_source = source_repo.upsert_source(config)
            if not config.enabled:
                continue

            try:
                logger.info(
                    "source_fetch_started",
                    {
                        "run_id": run_id,
                        "source_id": config.id,
                        "stage": "fetch",
                        "url": str(config.url),
                    },
                )
                if config.type == "rss":
                    items = fetch_rss(
                        config.id,
                        str(config.url),
                        settings.request_timeout_seconds,
                        fetcher=fetcher,
                    )
                else:
                    items = fetch_html(
                        config,
                        settings.request_timeout_seconds,
                        fetcher=fetcher,
                    )
            except Exception as exc:
                error_count += 1
                cause = exc.__cause__
                logger.error(
                    "source_fetch_failed",
                    {
                        "run_id": run_id,
                        "source_id": config.id,
                        "stage": "fetch",
                        "url": str(config.url),
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "cause_type": type(cause).__name__ if cause is not None else None,
                        "cause_message": str(cause) if cause is not None else None,
                    },
                )
                continue

            fetched_count += len(items)
            for item in items:
                canonical = canonicalize_url(str(item.url))
                canonical_hash = canonical_url_hash(str(item.url))
                relevance = ai_relevance_score(item)
                freshness = freshness_score(item.published_at)
                rank = rank_score(
                    relevance=relevance,
                    freshness=freshness,
                    source_weight=config.source_weight,
                )
                _, is_new = article_repo.insert_article(
                    source_id=db_source.id,
                    title=item.title,
                    url=str(item.url),
                    url_canonical=canonical,
                    url_canonical_hash=canonical_hash,
                    published_at=item.published_at or datetime.now(UTC),
                    summary=item.summary,
                    content=item.content,
                    ai_relevance_score=relevance,
                    freshness_score=freshness,
                    rank_score=rank,
                )
                if is_new:
                    new_count += 1
                else:
                    duplicate_count += 1

        session.commit()

    logger.info(
        "fetch_run_finished",
        {
            "run_id": run_id,
            "fetched": fetched_count,
            "new": new_count,
            "duplicates": duplicate_count,
            "errors": error_count,
        },
    )
    summary = (
        f"fetch complete: fetched={fetched_count} new={new_count} "
        f"duplicates={duplicate_count} errors={error_count}"
    )
    typer.echo(
        summary
    )


@app.command()
def top(
    hours: int = typer.Option(24, "--hours", min=1),
    limit: int = typer.Option(30, "--limit", min=1, max=200),
) -> None:
    create_all()
    with SessionLocal() as session:
        repo = ArticleRepo(session)
        articles = repo.query_top(hours=hours, limit=limit)
        for article in articles:
            typer.echo(
                f"{article.rank_score:.3f}\t{article.published_at.isoformat()}\t{article.title}\t{article.url_canonical}"
            )


@app.command()
def search(
    query: str = typer.Option(..., "--query"),
    days: int = typer.Option(7, "--days", min=1),
) -> None:
    create_all()
    with SessionLocal() as session:
        repo = ArticleRepo(session)
        articles = repo.search(query=query, days=days)
        for article in articles:
            typer.echo(f"{article.published_at.isoformat()}\t{article.title}\t{article.url_canonical}")
