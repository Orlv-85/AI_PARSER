"""Fetch pipeline package; flow and code map: pipeline.md in the parent directory.

Only the entry point used by the CLI and the web service is re-exported. Everything else is
imported from its module, so a test patches the module that reads the name.
"""
from app.core.ingestion.pipeline.cycle import run_fetch_cycle

__all__ = ["run_fetch_cycle"]
