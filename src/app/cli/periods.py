"""Period signals command: period-signals (src/app/cli/main.md)."""
from datetime import date
from pathlib import Path

import typer

from app.cli import deps
from app.cli.common import check_usd, echo_json, parse_day
from app.core.periodic.period_model import KINDS, WEEK
from app.usecases.periodic.period_run import (
    PeriodRunError,
    PeriodRunOptions,
    run_periods,
    run_week_and_month,
)

app = typer.Typer()


def _run_for(kind: str | None, target: date | None, backfill: int, recompute_all: bool):
    """The plain (nightly) command runs the week, then the month."""
    plain = kind is None and target is None and backfill == 1 and not recompute_all
    return run_week_and_month if plain else run_periods


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
    target = parse_day(period, "period") if period else None
    settings = deps.get_settings()
    usd = max_usd if max_usd is not None else settings.period_signals_max_usd
    check_usd(usd)
    if not settings.period_signals_enabled:
        echo_json({"state": "disabled", "kind": kind or WEEK, "periods": {}, "written": []})
        return
    run = _run_for(kind, target, backfill, recompute_all)
    deps.create_all()
    with deps.SessionLocal() as session:
        options = PeriodRunOptions(
            kind=kind or WEEK, period=target, backfill=backfill, recompute_all=recompute_all,
            with_brief=with_brief, max_usd=usd, cache_dir=Path(cache_dir))
        try:
            result = run(session, settings, options)
        except PeriodRunError as exc:
            raise typer.BadParameter(str(exc)) from exc
    echo_json(result)
