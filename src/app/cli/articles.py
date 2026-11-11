"""Collection commands: sources, fetch, top, search, prune (src/app/cli/main.md)."""
import typer

from app.cli import deps
from app.config.sources import load_sources
from app.observability import setup_json_logging
from app.usecases.archive.capture import count_old_articles, prune_old_articles
from app.usecases.ingestion.pipeline import run_fetch_cycle
from app.usecases.news_reads import search_articles, top_articles

app = typer.Typer()


@app.command()
def sources() -> None:
    settings = deps.get_settings()
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

    settings = deps.get_settings()
    logger = setup_json_logging()
    summary_data = run_fetch_cycle(settings=settings, logger=logger)
    summary = (
        f"fetch complete: fetched={summary_data.fetched} new={summary_data.new} "
        f"duplicates={summary_data.duplicates} errors={summary_data.errors}"
    )
    typer.echo(
        summary
    )


@app.command()
def top(
    hours: int = typer.Option(24, "--hours", min=1),
    limit: int = typer.Option(30, "--limit", min=1, max=200),
    min_ai_relevance: float = typer.Option(0.2, "--min-ai-relevance", min=0.0, max=1.0),
) -> None:
    deps.create_all()
    articles = top_articles(deps.SessionLocal, hours=hours, limit=limit,
                            min_ai_relevance=min_ai_relevance)
    for article in articles:
        typer.echo(
            f"{article.rank_score:.3f}\t"
            f"{article.published_at.isoformat() if article.published_at else 'unknown'}\t"
            f"{article.title}\t{article.url_canonical}"
        )


@app.command()
def search(
    query: str = typer.Option(..., "--query"),
    days: int = typer.Option(7, "--days", min=1),
) -> None:
    deps.create_all()
    for article in search_articles(deps.SessionLocal, query=query, days=days):
        published = article.published_at.isoformat() if article.published_at else "unknown"
        typer.echo(f"{published}\t{article.title}\t{article.url_canonical}")


@app.command()
def prune(
    older_than_days: int = typer.Option(800, "--older-than-days", min=1),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Only show how many rows would be deleted.",
    ),
) -> None:
    deps.create_all()
    if dry_run:
        old_articles = count_old_articles(deps.SessionLocal, older_than_days)
        typer.echo(
            "prune dry-run: "
            f"older_than_days={older_than_days} "
            f"articles_to_delete={old_articles}"
        )
        return

    deleted_articles, deleted_aliases = prune_old_articles(deps.SessionLocal, older_than_days)
    typer.echo(
        f"prune complete: older_than_days={older_than_days} "
        f"deleted_articles={deleted_articles} deleted_aliases={deleted_aliases}"
    )
