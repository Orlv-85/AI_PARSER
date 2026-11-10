"""Layer rule (src/app/README.md, "Layers"; spec 019): cli, web -> usecases -> storage -> core."""
import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "src" / "app"

# Known exceptions; both lists only shrink.
# storage files that still import a use case (spec 019, T009).
STORAGE_USING_USE_CASES = frozenset({"article_repo.py"})
# core files that load the provider journal from storage by name (spec 019, T014).
CORE_USING_STORAGE = frozenset({"jev.py", "bulletin/world_change.py"})
DYNAMIC_IMPORTERS = frozenset({"import_module", "__import__"})


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


@pytest.mark.parametrize("upper", ["usecases", "web", "cli"])
def test_core_imports_no_upper_layer(upper):
    assert importers("core", upper) == set()


def test_core_imports_storage_only_in_listed_files():
    assert importers("core", "storage") == CORE_USING_STORAGE


@pytest.mark.parametrize("upper", ["web", "cli"])
def test_storage_imports_no_entry_point(upper):
    assert importers("storage", upper) == set()


def test_storage_imports_use_cases_only_in_listed_files():
    assert importers("storage", "usecases") == STORAGE_USING_USE_CASES


@pytest.mark.parametrize("upper", ["web", "cli"])
def test_use_cases_import_no_entry_point(upper):
    assert importers("usecases", upper) == set()
