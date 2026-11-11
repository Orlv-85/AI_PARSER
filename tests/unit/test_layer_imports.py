"""Layer rule (src/app/README.md, "Layers"; spec 019).

cli, web -> usecases -> storage -> ingest -> core; config and observability are leaves.
"""
import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "src" / "app"
PACKAGES = ("core", "storage", "ingest", "usecases", "config", "observability", "web", "cli")

DYNAMIC_IMPORTERS = frozenset({"import_module", "__import__"})
# core functions that calculate; a repository returns rows and the use case calls these.
CALCULATIONS = frozenset({"reconcile", "digest_title", "digest_summary"})


def _loaded_by_name(node: ast.Call) -> str:
    """Module name of import_module("...") or __import__("..."); empty for any other call."""
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    first = node.args[0] if node.args else None
    if name not in DYNAMIC_IMPORTERS or not isinstance(first, ast.Constant):
        return ""
    return first.value if isinstance(first.value, str) else ""


def _names_package(node: ast.AST, package: str) -> bool:
    full = "app." + package
    if isinstance(node, ast.Import):
        return any(a.name == full or a.name.startswith(full + ".") for a in node.names)
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if module == full or module.startswith(full + "."):
            return True
        return module == "app" and any(a.name == package for a in node.names)
    if isinstance(node, ast.Call):
        module = _loaded_by_name(node)
        return module == full or module.startswith(full + ".")
    return False


def imports_package(source: str, package: str) -> bool:
    """True for any import of app.<package>: also inside functions and by a literal module name."""
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
    assert imports_package('x = import_module("app.storage.provider_journal").Y', "storage")
    assert imports_package('importlib.import_module("app.storage")', "storage")
    assert imports_package('__import__("app.storage.db")', "storage")
    assert not imports_package('import_module("app.core.provider_costs")', "storage")
    assert not imports_package("import_module(name)", "storage")


def test_app_has_no_relative_imports():
    """The scan reads absolute names only, so relative imports are not used in src/app."""
    relative = [path.relative_to(APP).as_posix() for path in APP.rglob("*.py")
                for node in ast.walk(ast.parse(path.read_text()))
                if isinstance(node, ast.ImportFrom) and node.level]
    assert relative == []


@pytest.mark.parametrize("other", ["storage", "ingest", "usecases", "web", "cli"])
def test_core_imports_no_lower_or_upper_layer(other):
    assert importers("core", other) == set()


@pytest.mark.parametrize("upper", ["usecases", "web", "cli"])
def test_storage_imports_no_upper_layer(upper):
    assert importers("storage", upper) == set()


@pytest.mark.parametrize("upper", ["web", "cli"])
def test_use_cases_import_no_entry_point(upper):
    assert importers("usecases", upper) == set()


@pytest.mark.parametrize("other", ["storage", "usecases", "web", "cli"])
def test_ingest_imports_no_storage_or_upper_layer(other):
    assert importers("ingest", other) == set()


@pytest.mark.parametrize("leaf", ["config", "observability"])
def test_leaf_packages_import_no_app_package(leaf):
    assert {other: importers(leaf, other) for other in PACKAGES
            if other != leaf and importers(leaf, other)} == {}


def calculations_imported(source: str) -> set[str]:
    return {alias.name for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app.core")
            for alias in node.names if alias.name in CALCULATIONS}


def test_storage_imports_no_calculations():
    root = APP / "storage"
    found = {path.relative_to(root).as_posix(): calculations_imported(path.read_text())
             for path in root.rglob("*.py")}
    assert {name: names for name, names in found.items() if names} == {}
