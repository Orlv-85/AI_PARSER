"""`ai-news` entry point: the root Typer app gathers the command modules.

Behavior and decisions: src/app/cli/main.md.
"""
import typer

from app.cli import archive, articles, bulletin, candidates, daily, periods, site, world

app = typer.Typer(help="AI News Collector CLI")


@app.callback()
def main() -> None:
    """CLI entrypoint."""


# A module app without a name adds its commands at the top level; `--help` lists in this order.
for module in (articles, site, daily, periods, candidates):
    app.add_typer(module.app)
app.add_typer(daily.entities_app, name="daily-signals-entities")
app.add_typer(archive.app, name="archive")
app.add_typer(bulletin.app, name="bulletin")
app.add_typer(world.app, name="world")
