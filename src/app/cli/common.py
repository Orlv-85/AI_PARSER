"""Option checks and output shared by the CLI commands (src/app/cli/main.md)."""
import json
from datetime import date, timedelta

import typer

from app.core.provider_costs import microdollars


def echo_json(data: object) -> None:
    typer.echo(json.dumps(data, sort_keys=True))


def parse_day(value: str, name: str = "--date") -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"{name} must be YYYY-MM-DD") from exc


def completed_day(report_date: str | None, today: date, use: str) -> date:
    """`report_date` or yesterday; refuses today and later days."""
    target = parse_day(report_date, "report-date") if report_date else today - timedelta(days=1)
    if target >= today:
        raise typer.BadParameter(f"Only completed UTC days can be {use}")
    return target


def check_usd(max_usd: str) -> None:
    try:
        microdollars(max_usd)
    except (ValueError, ArithmeticError) as exc:
        raise typer.BadParameter("max-usd must be a positive dollar amount") from exc


def day_within_cap(report_date: str, max_usd: str, cap: str, label: str) -> date:
    try:
        target = date.fromisoformat(report_date)
        too_high = microdollars(max_usd) > microdollars(cap)
    except (ValueError, ArithmeticError) as exc:
        raise typer.BadParameter(
            "--date must be YYYY-MM-DD and --max-usd a positive amount") from exc
    if too_high:
        raise typer.BadParameter(f"--max-usd is above the {label} {cap}")
    return target
