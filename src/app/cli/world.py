"""World news stream commands: the `world` group (src/app/cli/main.md)."""
from datetime import timedelta

import typer

from app.cli import deps
from app.cli.common import day_within_cap, echo_json, parse_day
from app.core.world.filter import load_own_domains
from app.core.world.gdelt import DayStats, GdeltScan, make_client, scan_day
from app.core.world.screen import WORLD_JEV_MAX_USD_PER_DAY
from app.observability import setup_json_logging
from app.usecases.world_collect import collect_day, yesterday_utc
from app.usecases.world_report import build_report
from app.usecases.world_screen import (
    ScreenOptions,
    open_world_assessor,
    run_screen,
    utc_today,
)
from app.usecases.world_text import archive_text_source, run_texts

app = typer.Typer(help="World news stream (spec 018, item 5).")


@app.command("scan")
def world_scan(
    report_date: str = typer.Option(..., "--date", help="UTC day, YYYY-MM-DD."),
    max_files: int | None = typer.Option(None, "--max-files", min=1, help="Read only N files."),
) -> None:
    """Download the GDELT files of a day, filter titles, print counts. Writes nothing."""
    target = parse_day(report_date)
    own = load_own_domains(deps.get_settings().sources_path)
    stats = DayStats()
    with make_client() as client:
        for _candidate in scan_day(
            target, scan=GdeltScan(client, own_domains=own), stats=stats, max_files=max_files
        ):
            pass
    echo_json(stats.as_dict())


@app.command("collect")
def world_collect(
    report_date: str | None = typer.Option(None, "--date", help="UTC day, default yesterday."),
    max_files: int | None = typer.Option(None, "--max-files", min=1, help="Read only N files."),
) -> None:
    """Download the GDELT files of a day and store candidates; done files are skipped.

    Without --date: yesterday, then the day before (catch-up, no download when complete).
    """
    days = [parse_day(report_date)] if report_date else [
        yesterday_utc(), yesterday_utc() - timedelta(days=1)]
    deps.create_all()
    logger = setup_json_logging()
    own = load_own_domains(deps.get_settings().sources_path)
    with make_client() as client, deps.SessionLocal() as session:
        for day in days:
            summary = collect_day(
                session, day, scan=GdeltScan(client, own_domains=own), max_files=max_files,
                logger=logger,
            )
            echo_json(summary.as_dict())


@app.command("screen")
def world_screen(
    report_date: str = typer.Option(..., "--date", help="GDELT day, YYYY-MM-DD."),
    max_usd: str = typer.Option(
        WORLD_JEV_MAX_USD_PER_DAY, "--max-usd", help="Jev cap in USD, at most the daily cap."),
    dry_run: bool = typer.Option(False, "--dry-run", help="No request, nothing written."),
) -> None:
    """Jev title screen of stored world candidates, then FR-001 for the top ones with text."""
    target = day_within_cap(report_date, max_usd, WORLD_JEV_MAX_USD_PER_DAY, "cap")
    if not dry_run:
        deps.create_all()
    logger = setup_json_logging()
    with deps.SessionLocal() as session:
        try:
            if dry_run:
                summary = run_screen(session, None, target, ScreenOptions(dry_run=True))
            else:
                with open_world_assessor(deps.get_settings(), logger, utc_today()) as assessor:
                    summary = run_screen(session, assessor, target, ScreenOptions(
                        texts=archive_text_source(session), limit_usd=float(max_usd)))
        except ValueError as exc:
            typer.echo(f"world screen: {exc}", err=True)
            raise typer.Exit(2) from exc
    echo_json(summary)


@app.command("texts")
def world_texts(
    report_date: str = typer.Option(..., "--date", help="GDELT day, YYYY-MM-DD."),
    dry_run: bool = typer.Option(False, "--dry-run", help="No download, nothing written."),
) -> None:
    """Download the pages of the top screened-in world stories through the archive."""
    target = parse_day(report_date)
    if not dry_run:
        deps.create_all()
    setup_json_logging()
    with deps.SessionLocal() as session:
        summary = run_texts(session, target, dry_run=dry_run)
    echo_json(summary)


@app.command("report")
def world_report(
    report_date: str = typer.Option(..., "--date", help="GDELT day, YYYY-MM-DD."),
) -> None:
    """First days check: counts, answers, cost and a sample of the window. Read-only."""
    target = parse_day(report_date)
    with deps.SessionLocal() as session:
        report = build_report(session, target)
    echo_json(report)
