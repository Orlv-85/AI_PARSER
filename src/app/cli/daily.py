"""Daily digest commands: daily-publish, daily-signals, daily-signals-entities
(src/app/cli/main.md)."""
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer

from app.cli import deps
from app.cli.common import check_usd, completed_day, echo_json
from app.usecases.daily.enrichment import publish_catch_up, publish_day
from app.usecases.daily.signals import (
    EntityCommandError,
    RunOptions,
    alias_entity,
    entity_overrides,
    merge_entities,
    run_entity_command,
    run_signals,
)

app = typer.Typer()
entities_app = typer.Typer(help="Daily signals entity overrides (no provider calls).")
_REPORT_DATE_OPTION = typer.Option(None, "--report-date")


@app.command("daily-publish")
def daily_publish(
    report_date: str | None = _REPORT_DATE_OPTION,
    cache_dir: str = typer.Option("data/daily-enrichment", "--cache-dir"),
    catch_up: bool = typer.Option(False, "--catch-up"),
) -> None:
    """Enrich the complete previous UTC day and atomically publish grounded summaries."""
    today = datetime.now(UTC).date()
    if catch_up and report_date:
        raise typer.BadParameter("--catch-up cannot be combined with --report-date")
    target = None if catch_up else completed_day(report_date, today, "published")
    deps.create_all()
    with deps.SessionLocal() as session:
        settings = deps.get_settings()
        if target is None:
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


@app.command("daily-signals")
def daily_signals(
    *,
    report_date: str | None = _REPORT_DATE_OPTION,
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
    target = completed_day(report_date, datetime.now(UTC).date(), "used")
    settings = deps.get_settings()
    usd = max_usd if max_usd is not None else settings.daily_signals_max_usd
    check_usd(usd)
    options = RunOptions(
        report_date=target, backfill_days=backfill_days,
        max_calls=max_calls or settings.daily_signals_max_calls,
        max_seconds=max_seconds or settings.daily_signals_max_seconds, max_usd=usd,
        cache_dir=Path(cache_dir), recompute_only=recompute_only, recompute_all=recompute_all,
        retry_skipped=retry_skipped)
    deps.create_all()
    with deps.SessionLocal() as session:
        result = run_signals(session, settings, options)
    echo_json(result)


def _entity_command(action) -> None:
    settings = deps.get_settings()
    deps.create_all()
    try:
        output = run_entity_command(deps.SessionLocal, settings, action,
                                    datetime.now(UTC).date() - timedelta(days=1))
    except EntityCommandError as exc:
        typer.echo(json.dumps({"state": "refused", "error": str(exc)}))
        raise typer.Exit(1) from exc
    echo_json(output)


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
        deps.create_all()
        echo_json({"overrides": [_override_json(o) for o in entity_overrides(deps.SessionLocal)]})
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
