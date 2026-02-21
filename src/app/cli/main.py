import typer
import uvicorn

from app.config.settings import get_settings
from app.config.sources import load_sources
from app.core.pipeline import run_fetch_cycle
from app.observability import setup_json_logging
from app.storage import SessionLocal, create_all
from app.storage.repos import ArticleRepo

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
    summary_data = run_fetch_cycle(settings=settings, logger=logger)
    summary = (
        f"fetch complete: fetched={summary_data.fetched} new={summary_data.new} "
        f"duplicates={summary_data.duplicates} errors={summary_data.errors}"
    )
    typer.echo(
        summary
    )


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port", min=1, max=65535),
) -> None:
    uvicorn.run("app.web.app:app", host=host, port=port)


@app.command()
def top(
    hours: int = typer.Option(24, "--hours", min=1),
    limit: int = typer.Option(30, "--limit", min=1, max=200),
    min_ai_relevance: float = typer.Option(0.2, "--min-ai-relevance", min=0.0, max=1.0),
) -> None:
    create_all()
    with SessionLocal() as session:
        repo = ArticleRepo(session)
        articles = repo.query_top(hours=hours, limit=limit, min_ai_relevance=min_ai_relevance)
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


@app.command()
def prune(
    older_than_days: int = typer.Option(100, "--older-than-days", min=1),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Only show how many rows would be deleted.",
    ),
) -> None:
    create_all()
    with SessionLocal() as session:
        repo = ArticleRepo(session)
        if dry_run:
            old_articles = repo.count_older_than(older_than_days=older_than_days)
            typer.echo(
                "prune dry-run: "
                f"older_than_days={older_than_days} "
                f"articles_to_delete={old_articles}"
            )
            return

        deleted_articles, deleted_aliases = repo.prune_older_than(older_than_days=older_than_days)
        session.commit()
        typer.echo(
            f"prune complete: older_than_days={older_than_days} "
            f"deleted_articles={deleted_articles} deleted_aliases={deleted_aliases}"
        )
