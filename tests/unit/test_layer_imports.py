"""Layer rule (src/app/README.md, "Layers"; spec 019): core does not import storage."""
import ast
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "src" / "app" / "core"

# Use cases that still live in core. The list only shrinks: spec 019 step 2 moves them out.
USE_CASES_IN_CORE = frozenset({
    "archive/capture.py",
    "bulletin/daily.py",
    "bulletin/writer_run.py",
    "daily/enrichment.py",
    "daily/signals.py",
    "ingestion/pipeline/cycle.py",
    "ingestion/pipeline/html_links.py",
    "ingestion/pipeline/replay.py",
    "ingestion/pipeline/rows.py",
    "ingestion/pipeline/rss.py",
    "ingestion/pipeline/screening.py",
    "ingestion/pipeline/source_result.py",
    "ingestion/pipeline/sources.py",
    "periodic/period_brief_run.py",
    "periodic/period_run.py",
    "sources/onboarding.py",
    "sources/validation.py",
    "world_collect.py",
    "world_report.py",
    "world_screen.py",
    "world_text.py",
})


def _names_storage(node: ast.AST) -> bool:
    if isinstance(node, ast.Import):
        return any(a.name == "app.storage" or a.name.startswith("app.storage.") for a in node.names)
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if module == "app.storage" or module.startswith("app.storage."):
            return True
        return module == "app" and any(a.name == "storage" for a in node.names)
    return False


def imports_storage(source: str) -> bool:
    """True for any import of app.storage, including imports inside functions."""
    return any(_names_storage(node) for node in ast.walk(ast.parse(source)))


def test_imports_storage_sees_every_import_form():
    assert imports_storage("from app.storage.article_repo import ArticleRepo")
    assert imports_storage("from app.storage import SessionLocal")
    assert imports_storage("import app.storage.db")
    assert imports_storage("from app import storage")
    assert imports_storage("def f():\n    from app.storage.world import WorldRepo\n")
    assert not imports_storage("from app.core.canonicalize import canonical_url_hash")
    assert not imports_storage("from app.storage_tools import x\nimport app.storagex")


def test_core_imports_storage_only_in_listed_use_cases():
    found = {path.relative_to(CORE).as_posix() for path in CORE.rglob("*.py")
             if imports_storage(path.read_text())}
    assert found == USE_CASES_IN_CORE
