"""Web site commands: serve, page-views (src/app/cli/main.md)."""
from datetime import UTC, datetime, timedelta

import typer
import uvicorn

from app.cli import deps
from app.cli.common import echo_json
from app.usecases.page_views import PAGE_VIEWS_DEFAULT_DAYS, page_view_totals

app = typer.Typer()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port", min=1, max=65535),
) -> None:
    uvicorn.run("app.web.app:app", host=host, port=port)


@app.command("page-views")
def page_views(days: int = typer.Option(PAGE_VIEWS_DEFAULT_DAYS, "--days", min=1)) -> None:
    """Read anonymous UTC day/route totals (src/app/web/pages.md)."""
    today = datetime.now(UTC).date()
    echo_json(page_view_totals(deps.SessionLocal, today - timedelta(days=days - 1), today))
