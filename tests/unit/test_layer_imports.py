"""Layer rule (src/app/README.md, "Layers"; spec 019): cli, web -> usecases -> storage -> core."""
import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "src" / "app"

# storage files that still import a use case. The list only shrinks (spec 019, T009).
STORAGE_USING_USE_CASES = frozenset({"article_repo.py"})


def _names_package(node: ast.AST, package: str) -> bool:
    full = "app." + package
    if isinstance(node, ast.Import):
        return any(a.name == full or a.name.startswith(full + ".") for a in node.names)
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if module == full or module.startswith(full + "."):
            return True
        return module == "app" and any(a.name == package for a in node.names)
    return False


def imports_package(source: str, package: str) -> bool:
    """True for any import of app.<package>, including imports inside functions."""
    return any(_names_package(node, package) for node in ast.walk(ast.parse(source)))


def importers(layer: str, package: str) -> set[str]:
    root = APP / layer
    return {path.relative_to(root).as_posix() for path in root.rglob("*.py")
            if imports_package(path.read_text(), package)}


def test_imports_package_sees_every_import_form():
    assert imports_package("from app.storage.article_repo import ArticleRepo", "storage")
    assert imports_package("from app.storage import SessionLocal", "storage")
    assert imports_package("import app.storage.db", "storage")
    assert imports_package("from app import storage", "storage")
    assert imports_package("def f():\n    from app.storage.world import WorldRepo\n", "storage")
    assert not imports_package("from app.core.canonicalize import canonical_url_hash", "storage")
    assert not imports_package("from app.storage_tools import x\nimport app.storagex", "storage")
    assert not imports_package("from app.storage import SessionLocal", "usecases")


@pytest.mark.parametrize("upper", ["storage", "usecases", "web", "cli"])
def test_core_imports_no_upper_layer(upper):
    assert importers("core", upper) == set()


@pytest.mark.parametrize("upper", ["web", "cli"])
def test_storage_imports_no_entry_point(upper):
    assert importers("storage", upper) == set()


def test_storage_imports_use_cases_only_in_listed_files():
    assert importers("storage", "usecases") == STORAGE_USING_USE_CASES


@pytest.mark.parametrize("upper", ["web", "cli"])
def test_use_cases_import_no_entry_point(upper):
    assert importers("usecases", upper) == set()
