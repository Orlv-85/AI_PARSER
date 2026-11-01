import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import typer
import uvicorn
from sqlalchemy import select

from app.config.settings import get_settings
from app.config.sources import load_sources
from app.core.archive.capture import (
    ARCHIVE_CACHE_ROOT,
    DAILY_CACHE_ROOT,
    dedupe_page_cache,
)
from app.core.archive.capture import capture as archive_capture
from app.core.archive.capture import import_db as archive_import_db
from app.core.archive.capture import status as archive_status
from app.core.bulletin.builder import build_bulletin
from app.core.bulletin.phrases import load_phrases
from app.core.bulletin.render import render_text
from app.core.bulletin.world_change import (
    ASSESS_DEFAULT_MAX_USD,
    WORLD_CHANGE_MAX_USD_PER_DAY,
    open_assessor,
    run_assessment,
)
from app.core.daily.enrichment import publish_catch_up, publish_day
from app.core.daily.signals import (
    EntityCommandError,
    RunOptions,
    alias_entity,
    merge_entities,
    run_signals,
)
from app.core.ingestion.pipeline import run_fetch_cycle
from app.core.periodic.period_model import KINDS, MONTH, WEEK
from app.core.periodic.period_run import PeriodRunError, PeriodRunOptions, run_periods
from app.core.provider_costs import microdollars
from app.core.sources.onboarding import import_source_candidates
from app.core.sources.validation import run_source_validation_batch
from app.core.world.filter import load_own_domains
from app.core.world.gdelt import DayStats, make_client, scan_day
from app.core.world.screen import WORLD_JEV_MAX_USD_PER_DAY
from app.core.world_collect import collect_day, yesterday_utc
from app.core.world_report import build_report
from app.core.world_screen import open_world_assessor, run_screen, utc_today
from app.core.world_text import archive_text_source, run_texts
from app.observability import setup_json_logging
from app.storage import SessionLocal, create_all
from app.storage.archive import ArchiveRepo
from app.storage.article_repo import ArticleRepo
from app.storage.bulletin_input import load_day_input
from app.storage.daily_signals import DailySignalRepo, OverrideConflict
from app.storage.models_sql import AIEntityOverride
from app.storage.source_candidate_repo import SourceCandidateRepo, SourceImportBatchRepo
from app.storage.world_change import WorldChangeRepo

app = typer.Typer(help="AI News Collector CLI")
_WEEKLY_DATE_OPTION = typer.Option(None, "--report-date")
_VALIDATE_BATCH_ID_OPTION = typer.Option(None, "--batch-id", min=1)
_VALIDATE_CANDIDATE_ID_OPTION = typer.Option([], "--candidate-id", min=1)


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


@app.command("daily-publish")
def daily_publish(
    report_date: str | None = _WEEKLY_DATE_OPTION,
    cache_dir: str = typer.Option("data/daily-enrichment", "--cache-dir"),
    catch_up: bool = typer.Option(False, "--catch-up"),
) -> None:
    """Enrich the complete previous UTC day and atomically publish grounded summaries."""
    today = datetime.now(UTC).date()
    if catch_up and report_date:
        raise typer.BadParameter("--catch-up cannot be combined with --report-date")
    if catch_up:
        target = None
    else:
        try:
            target = date.fromisoformat(report_date) if report_date else today - timedelta(days=1)
        except ValueError as exc:
            raise typer.BadParameter("report-date must be YYYY-MM-DD") from exc
        if target >= today:
            raise typer.BadParameter("Only completed UTC days can be published")
    create_all()
    with SessionLocal() as session:
        settings = get_settings()
        if catch_up:
            results = publish_catch_up(session, settings, today, Path(cache_dir))
            result_states = [report["state"] for report in results]
            typer.echo(json.dumps({"reports": results}))
        else:
            result = publish_day(session, settings, target, Path(cache_dir))
            result_states = [result["state"]]
            typer.echo(json.dumps(result))
    if "failed_preserved_previous" in result_states:
        raise typer.Exit(1)
    if "held_collection_paused" in result_states:
        raise typer.Exit(2)


def _completed_day(report_date: str | None) -> date:
    try:
        target = date.fromisoformat(report_date) if report_date else (
            datetime.now(UTC).date() - timedelta(days=1))
    except ValueError as exc:
        raise typer.BadParameter("report-date must be YYYY-MM-DD") from exc
    if target >= datetime.now(UTC).date():
        raise typer.BadParameter("Only completed UTC days can be used")
    return target


@app.command("daily-signals")
def daily_signals(
    *,
    report_date: str | None = _WEEKLY_DATE_OPTION,
    backfill_days: int = typer.Option(1, "--backfill-days", min=1, max=800),
    max_calls: int | None = typer.Option(None, "--max-calls", min=1),
    max_seconds: int | None = typer.Option(None, "--max-seconds", min=1),
    max_usd: str | None = typer.Option(None, "--max-usd"),
    cache_dir: str = typer.Option("data/daily-signals", "--cache-dir"),
    recompute_only: bool = typer.Option(False, "--recompute-only",
                                        help="No provider calls; works with the flag off."),
    recompute_all: bool = typer.Option(
        False, "--recompute-all",
        help="Recompute every comparable day, not only the last 400 days."),
    retry_skipped: bool = typer.Option(False, "--retry-skipped"),
) -> None:
    """Extract daily AI signals for a published digest day and recompute snapshots."""
    target = _completed_day(report_date)
    settings = get_settings()
    usd = max_usd if max_usd is not None else settings.daily_signals_max_usd
    try:
        microdollars(usd)
    except (ValueError, ArithmeticError) as exc:
        raise typer.BadParameter("max-usd must be a positive dollar amount") from exc
    options = RunOptions(
        report_date=target, backfill_days=backfill_days,
        max_calls=max_calls or settings.daily_signals_max_calls,
        max_seconds=max_seconds or settings.daily_signals_max_seconds, max_usd=usd,
        cache_dir=Path(cache_dir), recompute_only=recompute_only, recompute_all=recompute_all,
        retry_skipped=retry_skipped)
    create_all()
    with SessionLocal() as session:
        result = run_signals(session, settings, options)
    typer.echo(json.dumps(result, sort_keys=True))


@app.command("period-signals")
def period_signals(
    *,
    kind: str | None = typer.Option(
        None, "--kind",
        help="week or month. Without it: the latest completed week and, in a plain run, the "
        "latest completed month."),
    period: str | None = typer.Option(None, "--period", help="YYYY-MM-DD, any day of the period."),
    backfill: int = typer.Option(1, "--backfill", min=1, max=200,
                                 help="Number of periods ending at the target."),
    recompute_all: bool = typer.Option(
        False, "--recompute-all", help="Recompute every period from the first one."),
    with_brief: bool = typer.Option(
        False, "--with-brief",
        help="Paid: also write the brief of every period of the run; needs the brief flag."),
    max_usd: str | None = typer.Option(
        None, "--max-usd", help="Total USD cap of the brief step (default 0.10 from settings)."),
    cache_dir: str = typer.Option("data/period-signals", "--cache-dir"),
) -> None:
    """Compute weekly and monthly signals from stored daily data ($0); the brief is paid and
    flagged."""
    if kind is not None and kind not in KINDS:
        raise typer.BadParameter("kind must be week or month")
    try:
        target = date.fromisoformat(period) if period else None
    except ValueError as exc:
        raise typer.BadParameter("period must be YYYY-MM-DD") from exc
    settings = get_settings()
    usd = max_usd if max_usd is not None else settings.period_signals_max_usd
    try:
        microdollars(usd)
    except (ValueError, ArithmeticError) as exc:
        raise typer.BadParameter("max-usd must be a positive dollar amount") from exc
    if not settings.period_signals_enabled:
        typer.echo(json.dumps({"state": "disabled", "kind": kind or WEEK, "periods": {},
                               "written": []}, sort_keys=True))
        return
    create_all()
    with SessionLocal() as session:
        options = PeriodRunOptions(
            kind=kind or WEEK, period=target, backfill=backfill, recompute_all=recompute_all,
            with_brief=with_brief, max_usd=usd, cache_dir=Path(cache_dir))
        try:
            result = run_periods(session, settings, options)
        except PeriodRunError as exc:
            raise typer.BadParameter(str(exc)) from exc
        if kind is None and target is None and backfill == 1 and not recompute_all:
            # The plain (nightly) run: the latest completed month too; it does nothing until the
            # first month is complete, and a failure keeps the week report.
            try:
                result["month"] = run_periods(session, settings, replace(options, kind=MONTH))
            except Exception as exc:  # pylint: disable=broad-exception-caught
                session.rollback()
                result["month"] = {"state": "error", "error": type(exc).__name__}
    typer.echo(json.dumps(result, sort_keys=True))


entities_app = typer.Typer(help="Daily signals entity overrides (no provider calls).")
app.add_typer(entities_app, name="daily-signals-entities")


def _entity_command(action) -> None:
    settings = get_settings()
    create_all()
    with SessionLocal() as session:
        repo = DailySignalRepo(session, comparable_from=settings.daily_signals_comparable_from,
                               publisher_overrides=settings.weekly_publisher_overrides)
        try:
            output = action(repo)
        except (EntityCommandError, OverrideConflict, ValueError) as exc:
            session.rollback()
            typer.echo(json.dumps({"state": "refused", "error": str(exc)}))
            raise typer.Exit(1) from exc
        result = repo.recompute_reports(datetime.now(UTC).date() - timedelta(days=1))
        session.commit()
        output["reports_written"] = [d.isoformat() for d in result.written]
    typer.echo(json.dumps(output, sort_keys=True))


def _override_json(row) -> dict:
    return {"id": row.id, "kind": row.kind, "type_group": row.type_group,
            "match_key": row.match_key, "vendor_class": row.vendor_class,
            "target_base_key": row.target_base_key,
            "target_vendor_class": row.target_vendor_class,
            "target_entity_key": row.target_entity_key, "note": row.note}


@entities_app.command("merge")
def entities_merge(source: int = typer.Option(..., "--source", min=1),
                   target: int = typer.Option(..., "--target", min=1)) -> None:
    """Merge entity SOURCE into TARGET (ids from ai_entities), then recompute."""
    _entity_command(lambda repo: {"state": "ok", "override": _override_json(
        merge_entities(repo, source, target))})


@entities_app.command("alias")
def entities_alias(entity: int = typer.Option(..., "--entity", min=1),
                   name: str = typer.Option(..., "--name")) -> None:
    """Resolve mentions named NAME to ENTITY, then recompute."""
    _entity_command(lambda repo: {"state": "ok", "override": _override_json(
        alias_entity(repo, entity, name))})


@entities_app.command("overrides")
def entities_overrides(delete: int | None = typer.Option(None, "--delete", min=1)) -> None:
    """List overrides, or delete one (then recompute)."""
    if delete is None:
        create_all()
        with SessionLocal() as session:
            rows = [_override_json(o) for o in session.scalars(
                select(AIEntityOverride).order_by(AIEntityOverride.id))]
        typer.echo(json.dumps({"overrides": rows}, sort_keys=True))
        return

    def remove(repo):
        if not repo.delete_override(delete):
            raise EntityCommandError(f"override {delete} not found")
        return {"state": "ok", "deleted": delete}

    _entity_command(remove)


@entities_app.command("purge-evidence")
def entities_purge(article: int = typer.Option(..., "--article", min=1)) -> None:
    """Remove stored evidence of a deleted article (e.g. after non-news cleanup), then recompute."""
    _entity_command(lambda repo: {"state": "ok", "article": article,
                                  "purged": repo.purge_evidence(article)})


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
                f"{article.rank_score:.3f}\t"
                f"{article.published_at.isoformat() if article.published_at else 'unknown'}\t"
                f"{article.title}\t{article.url_canonical}"
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


archive_app = typer.Typer(help="Private article archive (no web access, no provider calls).")
app.add_typer(archive_app, name="archive")


@archive_app.command("capture")
def archive_capture_command(
    scope_all: bool = typer.Option(False, "--all", help="Sync every stored article."),
    no_download: bool = typer.Option(False, "--no-download", help="Never download pages."),
    max_seconds: int = typer.Option(1500, "--max-seconds", min=1),
) -> None:
    """Copy stored articles of the window (or all) into the archive."""
    create_all()
    logger = setup_json_logging()
    with SessionLocal() as session:
        summary = archive_capture(session, scope_all=scope_all, no_download=no_download,
                                  max_seconds=max_seconds, logger=logger)
    typer.echo(json.dumps(summary, sort_keys=True))


@archive_app.command("status")
def archive_status_command() -> None:
    """Archive counts, coverage and size (read-only)."""
    create_all()
    with SessionLocal() as session:
        typer.echo(json.dumps(archive_status(session), sort_keys=True))


@archive_app.command("purge")
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
    create_all()
    with SessionLocal() as session:
        documents, versions = ArchiveRepo(session).purge(url=url, source_key=source, host=host,
                                                         apply=apply)
        session.commit()
    typer.echo(json.dumps({"state": "deleted" if apply else "dry_run", "documents": documents,
                           "versions": versions}, sort_keys=True))


@archive_app.command("dedupe-cache")
def archive_dedupe_cache(
    apply: bool = typer.Option(False, "--apply", help="Delete; without it only counts."),
) -> None:
    """Remove duplicate page.html files from the source-page caches (dry run by default)."""
    result = dedupe_page_cache([ARCHIVE_CACHE_ROOT, DAILY_CACHE_ROOT], apply=apply)
    typer.echo(json.dumps({"state": "deleted" if apply else "dry_run", **result}, sort_keys=True))


@archive_app.command("import-db")
def archive_import_db_command(
    source_url: str = typer.Option(..., "--source-url",
                                   help="SQLAlchemy URL of the database to read (never written)."),
    apply: bool = typer.Option(False, "--apply", help="Write; without it only counts."),
) -> None:
    """Archive articles of another database (a restored dump) missing here."""
    create_all()
    with SessionLocal() as session:
        try:
            result = archive_import_db(session, source_url, apply=apply)
        except ValueError as exc:
            typer.echo(f"archive import-db: {exc}", err=True)
            raise typer.Exit(2) from exc
    typer.echo(json.dumps(result, sort_keys=True))


bulletin_app = typer.Typer(help="Daily bulletin tools (spec 018).")
app.add_typer(bulletin_app, name="bulletin")


@bulletin_app.command("assess")
def bulletin_assess(
    report_date: str = typer.Option(..., "--date", help="Digest day, YYYY-MM-DD."),
    max_usd: str = typer.Option(ASSESS_DEFAULT_MAX_USD, "--max-usd", help="Jev cap in USD."),
    dry_run: bool = typer.Option(False, "--dry-run", help="No request, nothing written."),
) -> None:
    """Ask Jev the world_change questions for the digest articles of a day."""
    try:
        target = date.fromisoformat(report_date)
        too_high = microdollars(max_usd) > microdollars(WORLD_CHANGE_MAX_USD_PER_DAY)
    except (ValueError, ArithmeticError) as exc:
        raise typer.BadParameter(
            "--date must be YYYY-MM-DD and --max-usd a positive amount") from exc
    if too_high:
        raise typer.BadParameter(f"--max-usd is above the ceiling {WORLD_CHANGE_MAX_USD_PER_DAY}")
    if not dry_run:
        create_all()
    logger = setup_json_logging()
    with SessionLocal() as session:
        repo = WorldChangeRepo(session)
        try:
            if dry_run:
                summary = run_assessment(session, repo, None, target, dry_run=True)
            else:
                with open_assessor(get_settings(), logger, target, max_usd) as assessor:
                    summary = run_assessment(session, repo, assessor, target)
        except ValueError as exc:
            typer.echo(f"bulletin assess: {exc}", err=True)
            raise typer.Exit(2) from exc
    if summary is None:
        typer.echo(f"bulletin assess: no digest for {target}", err=True)
        raise typer.Exit(2)
    typer.echo(json.dumps(summary, sort_keys=True))


@bulletin_app.command("build")
def bulletin_build(
    report_date: str = typer.Option(..., "--date", help="Digest day, YYYY-MM-DD."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the bulletin, store nothing."),
    as_json: bool = typer.Option(False, "--json", help="Print the bulletin object as JSON."),
) -> None:
    """Build the bulletin of a day from stored data (no model call; dry run only for now)."""
    try:
        target = date.fromisoformat(report_date)
    except ValueError as exc:
        raise typer.BadParameter("--date must be YYYY-MM-DD") from exc
    if not dry_run:
        typer.echo("bulletin build: only --dry-run is available", err=True)
        raise typer.Exit(2)
    logger = setup_json_logging()
    with SessionLocal() as session:
        data = load_day_input(
            session, target, include_world=get_settings().world_stream_in_bulletin)
    if data is None:
        typer.echo(f"bulletin build: no digest for {target}", err=True)
        raise typer.Exit(2)
    library = load_phrases()
    result = build_bulletin(data, library)
    assessed = sum(1 for c in data.candidates if c.origin == "digest")
    logger.info("bulletin_assessed_share", extra={
        "date": target.isoformat(), "assessed": assessed, "digest_articles": data.digest_articles})
    if result.bulletin is None:
        logger.info("bulletin_skipped", extra={"date": target.isoformat(), "reason": result.reason})
        typer.echo(f"bulletin build: skipped {target}: {result.reason}", err=True)
    elif as_json:
        counts = {"assessed": assessed, "digest_articles": data.digest_articles}
        typer.echo(json.dumps({**result.bulletin.as_dict(), **counts}, indent=2, sort_keys=True))
    else:
        typer.echo(render_text(result.bulletin, library), nl=False)


world_app = typer.Typer(help="World news stream (spec 018, item 5).")
app.add_typer(world_app, name="world")


@world_app.command("scan")
def world_scan(
    report_date: str = typer.Option(..., "--date", help="UTC day, YYYY-MM-DD."),
    max_files: int | None = typer.Option(None, "--max-files", min=1, help="Read only N files."),
) -> None:
    """Download the GDELT files of a day, filter titles, print counts. Writes nothing."""
    try:
        target = date.fromisoformat(report_date)
    except ValueError as exc:
        raise typer.BadParameter("--date must be YYYY-MM-DD") from exc
    own = load_own_domains(get_settings().sources_path)
    stats = DayStats()
    with make_client() as client:
        for _candidate in scan_day(
            target, client=client, stats=stats, own_domains=own, max_files=max_files
        ):
            pass
    typer.echo(json.dumps(stats.as_dict(), sort_keys=True))


@world_app.command("collect")
def world_collect(
    report_date: str | None = typer.Option(None, "--date", help="UTC day, default yesterday."),
    max_files: int | None = typer.Option(None, "--max-files", min=1, help="Read only N files."),
) -> None:
    """Download the GDELT files of a day and store candidates; done files are skipped.

    Without --date: yesterday, then the day before (catch-up, no download when complete).
    """
    try:
        days = [date.fromisoformat(report_date)] if report_date else [
            yesterday_utc(), yesterday_utc() - timedelta(days=1)]
    except ValueError as exc:
        raise typer.BadParameter("--date must be YYYY-MM-DD") from exc
    create_all()
    logger = setup_json_logging()
    own = load_own_domains(get_settings().sources_path)
    with make_client() as client, SessionLocal() as session:
        for day in days:
            summary = collect_day(
                session, day, client=client, own_domains=own, max_files=max_files, logger=logger
            )
            typer.echo(json.dumps(summary.as_dict(), sort_keys=True))


@world_app.command("screen")
def world_screen(
    report_date: str = typer.Option(..., "--date", help="GDELT day, YYYY-MM-DD."),
    max_usd: str = typer.Option(
        WORLD_JEV_MAX_USD_PER_DAY, "--max-usd", help="Jev cap in USD, at most the daily cap."),
    dry_run: bool = typer.Option(False, "--dry-run", help="No request, nothing written."),
) -> None:
    """Jev title screen of stored world candidates, then FR-001 for the top ones with text."""
    try:
        target = date.fromisoformat(report_date)
        too_high = microdollars(max_usd) > microdollars(WORLD_JEV_MAX_USD_PER_DAY)
    except (ValueError, ArithmeticError) as exc:
        raise typer.BadParameter(
            "--date must be YYYY-MM-DD and --max-usd a positive amount") from exc
    if too_high:
        raise typer.BadParameter(f"--max-usd is above the cap {WORLD_JEV_MAX_USD_PER_DAY}")
    if not dry_run:
        create_all()
    logger = setup_json_logging()
    with SessionLocal() as session:
        try:
            if dry_run:
                summary = run_screen(session, None, target, dry_run=True)
            else:
                with open_world_assessor(get_settings(), logger, utc_today()) as assessor:
                    summary = run_screen(session, assessor, target, limit_usd=float(max_usd),
                                         texts=archive_text_source(session))
        except ValueError as exc:
            typer.echo(f"world screen: {exc}", err=True)
            raise typer.Exit(2) from exc
    typer.echo(json.dumps(summary, sort_keys=True))


@world_app.command("texts")
def world_texts(
    report_date: str = typer.Option(..., "--date", help="GDELT day, YYYY-MM-DD."),
    dry_run: bool = typer.Option(False, "--dry-run", help="No download, nothing written."),
) -> None:
    """Download the pages of the top screened-in world stories through the archive."""
    try:
        target = date.fromisoformat(report_date)
    except ValueError as exc:
        raise typer.BadParameter("--date must be YYYY-MM-DD") from exc
    if not dry_run:
        create_all()
    setup_json_logging()
    with SessionLocal() as session:
        summary = run_texts(session, target, dry_run=dry_run)
    typer.echo(json.dumps(summary, sort_keys=True))


@world_app.command("report")
def world_report(
    report_date: str = typer.Option(..., "--date", help="GDELT day, YYYY-MM-DD."),
) -> None:
    """First days check: counts, answers, cost and a sample of the window. Read-only."""
    try:
        target = date.fromisoformat(report_date)
    except ValueError as exc:
        raise typer.BadParameter("--date must be YYYY-MM-DD") from exc
    with SessionLocal() as session:
        report = build_report(session, target)
    typer.echo(json.dumps(report, sort_keys=True))


@app.command("import-candidates")
def import_candidates(
    raw_text: str = typer.Argument(
        ...,
        help="Raw text containing candidate URLs or markdown links.",
    ),
) -> None:
    create_all()
    with SessionLocal() as session:
        result = import_source_candidates(
            raw_text=raw_text,
            batch_repo=SourceImportBatchRepo(session),
            candidate_repo=SourceCandidateRepo(session),
        )
        session.commit()
        batch_id = result.batch.id
        parsed_count = result.parsed_count
        accepted_count = result.accepted_count
        rejected_count = result.rejected_count
    typer.echo(
        "source import complete: "
        f"batch_id={batch_id} "
        f"parsed={parsed_count} "
        f"accepted={accepted_count} "
        f"rejected={rejected_count}"
    )


@app.command("validate-candidates")
def validate_candidates(
    batch_id: int | None = _VALIDATE_BATCH_ID_OPTION,
    candidate_id: list[int] = _VALIDATE_CANDIDATE_ID_OPTION,
) -> None:
    candidate_ids = list(candidate_id)
    if batch_id is None and not candidate_ids:
        raise typer.BadParameter("Provide --batch-id or at least one --candidate-id.")

    create_all()
    with SessionLocal() as session:
        results = run_source_validation_batch(
            session=session,
            batch_id=batch_id,
            candidate_ids=candidate_ids or None,
        )
        session.commit()

    typer.echo(f"source validation complete: validated={len(results)}")
    for result in results:
        detail = result.validation_error or "ok"
        typer.echo(
            f"{result.candidate_id}\t{result.detected_type}\t{result.status}\t{detail}"
        )


@app.command("review-batch-outcomes")
def review_batch_outcomes(
    batch_id: int = typer.Option(..., "--batch-id", min=1),
) -> None:
    create_all()
    with SessionLocal() as session:
        batch_repo = SourceImportBatchRepo(session)
        batch = batch_repo.get_batch(batch_id)
        if batch is None:
            raise typer.BadParameter(f"source import batch not found: {batch_id}")
        summary = SourceCandidateRepo(session).summarize_batch(batch_id=batch.id)

    typer.echo(
        "batch review outcomes: "
        f"batch_id={summary['batch_id']} "
        f"total={summary['total_candidates']} "
        f"pending_review={summary['pending_review_count']} "
        f"validated={summary['validated_count']} "
        f"approved={summary['approved_count']} "
        f"rejected={summary['rejected_count']} "
        f"duplicates={summary['duplicate_count']}"
    )
