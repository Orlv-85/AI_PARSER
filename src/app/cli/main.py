import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import typer
import uvicorn
from sqlalchemy import select

from app.config.settings import get_settings
from app.config.sources import load_sources
from app.core.daily.enrichment import publish_day
from app.core.daily.signals import (
    EntityCommandError,
    RunOptions,
    alias_entity,
    merge_entities,
    run_signals,
)
from app.core.ingestion.pipeline import run_fetch_cycle
from app.core.provider_costs import microdollars
from app.core.sources.onboarding import import_source_candidates, run_source_validation_batch
from app.core.weekly.audit import audit
from app.core.weekly.worker import drain
from app.observability import setup_json_logging
from app.storage import SessionLocal, create_all
from app.storage.article_repo import ArticleRepo
from app.storage.daily_signals import DailySignalRepo, OverrideConflict
from app.storage.models_sql import AIEntityOverride
from app.storage.source_candidate_repo import SourceCandidateRepo, SourceImportBatchRepo
from app.storage.weekly import WeeklyStore

app = typer.Typer(help="AI News Collector CLI")
_WEEKLY_DATE_OPTION = typer.Option(None, "--report-date")
_WEEKLY_AUDIT_OUTPUT_OPTION = typer.Option(..., "--output")
_VALIDATE_BATCH_ID_OPTION = typer.Option(None, "--batch-id", min=1)
_VALIDATE_CANDIDATE_ID_OPTION = typer.Option([], "--candidate-id", min=1)


@app.callback()
def main() -> None:
    """CLI entrypoint."""


@app.command("weekly-analytics")
def weekly_analytics(
    report_date: str | None = _WEEKLY_DATE_OPTION,
    limit: int = typer.Option(200, "--limit", min=1, help="Compatibility evidence/page-size hint."),
    max_jobs: int = typer.Option(1, "--max-jobs", min=1, max=20),
    enqueue_only: bool = typer.Option(False, "--enqueue-only"),
    drain_only: bool = typer.Option(False, "--drain-only"),
) -> None:
    """Freeze complete inputs and drain leased v2 jobs without changing legacy history."""
    del limit
    settings = get_settings()
    if not settings.weekly_v2_enabled:
        raise typer.BadParameter("Enable AINEWS_WEEKLY_V2_ENABLED for the v2 worker")
    today = datetime.now(UTC).date()
    try:
        target = date.fromisoformat(report_date) if report_date else (
            today - timedelta(days=(today.weekday() - 6) % 7))
    except ValueError as exc:
        raise typer.BadParameter("report-date must be YYYY-MM-DD") from exc
    if enqueue_only and drain_only:
        raise typer.BadParameter("Choose either enqueue-only or drain-only")
    setup_json_logging()
    create_all()
    with SessionLocal() as session:
        store = WeeklyStore(session)
        job_id = None if drain_only else store.enqueue(target, settings)
        session.commit()
        results = [] if enqueue_only else drain(store, settings, max_jobs=max_jobs)
    typer.echo(json.dumps({"job_id": job_id, "results": results}))


@app.command("weekly-analytics-audit")
def weekly_analytics_audit(
    report_date: str = typer.Option(..., "--report-date"),
    output: Path = _WEEKLY_AUDIT_OUTPUT_OPTION,
    weeks: int = typer.Option(8, "--weeks", min=1, max=52),
) -> None:
    """Export stored comparisons and review samples without calling providers."""
    try:
        target = date.fromisoformat(report_date)
    except ValueError as exc:
        raise typer.BadParameter("report-date must be YYYY-MM-DD") from exc
    create_all()
    with SessionLocal() as session:
        artifact = audit(WeeklyStore(session), target, weeks)
    output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    typer.echo(f"Weekly replay/review artifact written to {output}")


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
) -> None:
    """Enrich the complete previous UTC day and atomically publish grounded summaries."""
    try:
        target = date.fromisoformat(report_date) if report_date else (
            datetime.now(UTC).date() - timedelta(days=1))
    except ValueError as exc:
        raise typer.BadParameter("report-date must be YYYY-MM-DD") from exc
    if target >= datetime.now(UTC).date():
        raise typer.BadParameter("Only completed UTC days can be published")
    create_all()
    with SessionLocal() as session:
        result = publish_day(session, get_settings(), target, Path(cache_dir))
    typer.echo(json.dumps(result))
    if result["state"] == "failed_preserved_previous":
        raise typer.Exit(1)


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
