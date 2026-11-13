"""Daily bulletin commands: the `bulletin` group (src/app/cli/main.md)."""
import json
from datetime import timedelta

import typer

from app.cli import deps
from app.cli.common import day_within_cap, echo_json, parse_day
from app.core.bulletin.render import render_text
from app.core.bulletin.world_change import ASSESS_DEFAULT_MAX_USD, WORLD_CHANGE_MAX_USD_PER_DAY
from app.observability import setup_json_logging
from app.usecases.bulletin.assessor import open_assessor
from app.usecases.bulletin.daily import (
    BulletinEnv,
    assess_day,
    has_provider_key,
    prepare_bulletin,
    run_daily,
    write_prepared,
)
from app.usecases.bulletin.stored import store_bulletin
from app.usecases.bulletin.writer_run import WRITER_MAX_USD_PER_DAY, open_writer
from app.usecases.world_screen import utc_today

app = typer.Typer(help="Daily bulletin tools (spec 018).")


@app.command("assess")
def bulletin_assess(
    report_date: str = typer.Option(..., "--date", help="Digest day, YYYY-MM-DD."),
    max_usd: str = typer.Option(ASSESS_DEFAULT_MAX_USD, "--max-usd", help="Jev cap in USD."),
    dry_run: bool = typer.Option(False, "--dry-run", help="No request, nothing written."),
) -> None:
    """Ask Jev the world_change questions for the digest articles of a day."""
    target = day_within_cap(report_date, max_usd, WORLD_CHANGE_MAX_USD_PER_DAY, "ceiling")
    if not dry_run:
        deps.create_all()
    logger = setup_json_logging()
    with deps.SessionLocal() as session:
        try:
            env = BulletinEnv(deps.get_settings(), logger, assessor_factory=open_assessor)
            summary = assess_day(session, env, target, max_usd=max_usd, dry_run=dry_run)
        except ValueError as exc:
            typer.echo(f"bulletin assess: {exc}", err=True)
            raise typer.Exit(2) from exc
    if summary is None:
        typer.echo(f"bulletin assess: no digest for {target}", err=True)
        raise typer.Exit(2)
    echo_json(summary)


@app.command("daily")
def bulletin_daily(
    report_date: str | None = typer.Option(None, "--date", help="Day, default yesterday UTC."),
) -> None:
    """Assess, build, write when configured, and store the daily bulletin."""
    today = utc_today()
    target = parse_day(report_date) if report_date else today - timedelta(days=1)
    logger = setup_json_logging()
    try:
        deps.create_all()
        with deps.SessionLocal() as session:
            env = BulletinEnv(deps.get_settings(), logger, assessor_factory=open_assessor,
                              writer_factory=open_writer)
            summary = run_daily(session, env, target, utc_today)
    except Exception as exc:  # The unattended command reserves nonzero exits for usage errors.
        logger.exception("bulletin_daily_failed", extra={"event_fields": {
            "date": target.isoformat(), "error": type(exc).__name__, "detail": str(exc)[:200]}})
        summary = {"date": target.isoformat(), "status": "skipped", "reason": "daily_failed",
                   "assess": None, "writer": None, "stored": False, "refused": False}
    echo_json(summary)


@app.command("build")
def bulletin_build(
    report_date: str = typer.Option(..., "--date", help="Digest day, YYYY-MM-DD."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the bulletin, store nothing."),
    as_json: bool = typer.Option(False, "--json", help="Print the bulletin object as JSON."),
    write: bool = typer.Option(False, "--write", help="Call the model writer (paid, one call)."),
    max_usd: str = typer.Option(
        WRITER_MAX_USD_PER_DAY, "--max-usd", help="Writer cap in USD, at most the daily cap."),
) -> None:
    """Build the bulletin of a day from stored data; a model call only with --write."""
    target = day_within_cap(report_date, max_usd, WRITER_MAX_USD_PER_DAY, "cap")
    settings = deps.get_settings()
    if write and not has_provider_key(settings, "ds_api_key"):
        typer.echo("bulletin build: --write needs DS_API_KEY", err=True)
        raise typer.Exit(2)
    logger = setup_json_logging()
    with deps.SessionLocal() as session:
        prepared = prepare_bulletin(session, settings, logger, target, write=write)
        if prepared.reason == "no_digest":
            typer.echo(f"bulletin build: no digest for {target}", err=True)
            raise typer.Exit(2)
    if write:
        write_prepared(prepared, BulletinEnv(settings, logger, writer_factory=open_writer),
                       utc_today(), max_usd=max_usd)
    if not dry_run:
        deps.create_all()
        store_bulletin(deps.SessionLocal, target, bulletin=prepared.bulletin,
                       reason=prepared.reason, numbers=prepared.numbers)
    if prepared.bulletin is None:
        logger.info("bulletin_skipped", extra={"date": target.isoformat(),
                                               "reason": prepared.reason})
        typer.echo(f"bulletin build: skipped {target}: {prepared.reason}", err=True)
        return
    extra = prepared.numbers
    if as_json:
        typer.echo(json.dumps({**prepared.bulletin.as_dict(), **extra}, indent=2, sort_keys=True))
    else:
        typer.echo(render_text(prepared.bulletin, prepared.library), nl=False)
        if write:
            typer.echo(json.dumps(extra["writer"], sort_keys=True), err=True)
