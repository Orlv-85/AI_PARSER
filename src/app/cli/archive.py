"""Archive commands: the `archive` group (src/app/cli/main.md)."""
import typer

from app.cli import deps
from app.cli.common import echo_json
from app.observability import setup_json_logging
from app.usecases.archive.capture import (
    ARCHIVE_CACHE_ROOT,
    DAILY_CACHE_ROOT,
    dedupe_page_cache,
    purge_archive,
)
from app.usecases.archive.capture import capture as archive_capture
from app.usecases.archive.capture import import_db as archive_import_db
from app.usecases.archive.capture import status as archive_status

app = typer.Typer(help="Private article archive (no web access, no provider calls).")


@app.command("capture")
def archive_capture_command(
    scope_all: bool = typer.Option(False, "--all", help="Sync every stored article."),
    no_download: bool = typer.Option(False, "--no-download", help="Never download pages."),
    max_seconds: int = typer.Option(1500, "--max-seconds", min=1),
) -> None:
    """Copy stored articles of the window (or all) into the archive."""
    deps.create_all()
    logger = setup_json_logging()
    with deps.SessionLocal() as session:
        summary = archive_capture(session, scope_all=scope_all, no_download=no_download,
                                  max_seconds=max_seconds, logger=logger)
    echo_json(summary)


@app.command("status")
def archive_status_command() -> None:
    """Archive counts, coverage and size (read-only)."""
    deps.create_all()
    with deps.SessionLocal() as session:
        echo_json(archive_status(session))


@app.command("purge")
def archive_purge(
    url: str | None = typer.Option(None, "--url"),
    source: str | None = typer.Option(None, "--source"),
    host: str | None = typer.Option(None, "--host"),
    apply: bool = typer.Option(False, "--apply", help="Delete; without it only counts."),
) -> None:
    """Remove archived documents of one URL, source or host (dry run by default)."""
    if sum(value is not None for value in (url, source, host)) != 1:
        typer.echo("archive purge needs exactly one of --url, --source, --host", err=True)
        raise typer.Exit(2)
    deps.create_all()
    documents, versions = purge_archive(deps.SessionLocal, url=url, source_key=source, host=host,
                                        apply=apply)
    echo_json({"state": "deleted" if apply else "dry_run", "documents": documents,
               "versions": versions})


@app.command("dedupe-cache")
def archive_dedupe_cache(
    apply: bool = typer.Option(False, "--apply", help="Delete; without it only counts."),
) -> None:
    """Remove duplicate page.html files from the source-page caches (dry run by default)."""
    result = dedupe_page_cache([ARCHIVE_CACHE_ROOT, DAILY_CACHE_ROOT], apply=apply)
    echo_json({"state": "deleted" if apply else "dry_run", **result})


@app.command("import-db")
def archive_import_db_command(
    source_url: str = typer.Option(..., "--source-url",
                                   help="SQLAlchemy URL of the database to read (never written)."),
    apply: bool = typer.Option(False, "--apply", help="Write; without it only counts."),
) -> None:
    """Archive articles of another database (a restored dump) missing here."""
    deps.create_all()
    with deps.SessionLocal() as session:
        try:
            result = archive_import_db(session, source_url, apply=apply)
        except ValueError as exc:
            typer.echo(f"archive import-db: {exc}", err=True)
            raise typer.Exit(2) from exc
    echo_json(result)
