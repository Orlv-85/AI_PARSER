"""Layer rule (src/app/README.md, "Layers"; spec 019).

cli, web -> usecases -> storage -> ingest -> core; config and observability are leaves.
Spec 020 checks entry-point storage imports and web commit calls.
"""
import ast
import importlib
import inspect
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "src" / "app"
PACKAGES = ("core", "storage", "ingest", "usecases", "config", "observability", "web", "cli")

DYNAMIC_IMPORTERS = frozenset({"import_module", "__import__"})
ENTRY_POINT_STORAGE_MODULES = frozenset({"app.storage.models_sql", "app.storage:models_sql"})
COMPOSITION_ROOT = "web/app.py"
COMPOSITION_ROOT_NAMES = frozenset({"app.storage:SessionLocal", "app.storage:create_all"})
# Entry-point storage imports and web commits still in breach (spec 020); lists only shrink.
STORAGE_IN_ENTRY_POINTS = {
    "cli/main.py",
    "web/routes/bulletin.py",
    "web/routes/common.py",
    "web/routes/news.py",
    "web/routes/pages.py",
    "web/routes/period.py",
    "web/routes/signals.py",
    "web/routes/sources.py",
    "web/routes/weekly.py",
    "web/service.py",
    "web/source_intake.py",
    "web/source_onboarding.py",
}
COMMITS_IN_WEB = {
    "web/routes/pages.py",
    "web/routes/signals.py",
    "web/routes/sources.py",
    "web/routes/weekly.py",
    "web/source_intake.py",
}
# core functions a repository may call: they key, encode or read, not calculate.
HELPERS = frozenset({
    "canonical_url_hash",  # keys and hashes
    "encoded", "fingerprint",  # canonical JSON
    "microdollars", "is_overload",  # money units, provider error kind
    "period_days", "previous_start",  # period dates
    "read_str", "read_optional_str", "read_optional_int",  # field reading
    "request_key", "reservation", "parse_summary",  # payment journal keys
    "url_exclusion_reason",  # page rule of the page cache
})
# Calculations a repository still imports (spec 019, T013); the list only shrinks.
CALCULATION_EXCEPTIONS = {
    "bulletin_texts.py": {"all_stories"},
    "daily_signals.py": {"join", "name_tokens", "type_group"},
    "source_candidate_repo.py": {"group_candidate_overlaps"},
}
_MISSING = object()


def _loaded_by_name(node: ast.Call) -> str:
    """Module name of import_module("...") or __import__("..."); empty for any other call."""
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    keyword = next((k.value for k in node.keywords if k.arg == "name"), None)
    first = node.args[0] if node.args else keyword
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


def storage_imports(source: str) -> set[str]:
    """Storage modules imported anywhere; imports from app.storage retain individual names."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not _names_package(node, "storage"):
            continue
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names
                         if alias.name == "app.storage" or alias.name.startswith("app.storage."))
        elif isinstance(node, ast.ImportFrom):
            if node.module == "app.storage":
                found.update(f"app.storage:{alias.name}" for alias in node.names)
            else:
                found.add("app.storage" if node.module == "app" else node.module or "")
        elif isinstance(node, ast.Call):
            found.add(_loaded_by_name(node))
    return found


def calls_commit(source: str) -> bool:
    """True for any attribute call named commit, including inside functions."""
    return any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and node.func.attr == "commit" for node in ast.walk(ast.parse(source)))


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
    assert imports_package('import_module(name="app.storage.db")', "storage")
    assert not imports_package('import_module("app.core.provider_costs")', "storage")
    assert not imports_package("import_module(name)", "storage")


def test_app_has_no_relative_imports():
    """The scan reads absolute names only, so relative imports are not used in src/app."""
    relative = [path.relative_to(APP).as_posix() for path in APP.rglob("*.py")
                for node in ast.walk(ast.parse(path.read_text()))
                if isinstance(node, ast.ImportFrom) and node.level]
    assert relative == []


def test_storage_imports_sees_every_import_form():
    assert storage_imports("from app.storage.x import A") == {"app.storage.x"}
    assert storage_imports("import app.storage.x") == {"app.storage.x"}
    assert storage_imports("from app.storage import A, B") == {"app.storage:A", "app.storage:B"}
    assert storage_imports("from app.storage import *") == {"app.storage:*"}
    assert storage_imports("from app import storage") == {"app.storage"}
    assert storage_imports("import app.storage") == {"app.storage"}
    assert storage_imports('import_module("app.storage.x")') == {"app.storage.x"}
    assert storage_imports('__import__("app.storage.x")') == {"app.storage.x"}
    assert storage_imports('importlib.import_module(name="app.storage.x")') == {"app.storage.x"}
    assert storage_imports('__import__(name="app.storage.x")') == {"app.storage.x"}
    assert storage_imports("from app.storage import models_sql") <= ENTRY_POINT_STORAGE_MODULES
    assert storage_imports("from app.storage.x import A as B") == {"app.storage.x"}
    assert storage_imports("def f():\n    from app.storage.x import A\n") == {"app.storage.x"}
    assert storage_imports("from app.storage import A\nimport app.storage.x") == {
        "app.storage:A", "app.storage.x"}
    assert storage_imports('importlib.import_module("app.storage")') == {"app.storage"}
    assert storage_imports("import app.storage.models_sql as rows") == {"app.storage.models_sql"}
    assert storage_imports("from app.storage import SessionLocal as session") == {
        "app.storage:SessionLocal"}
    assert storage_imports("from app.storage_tools import x") == set()
    assert storage_imports("import app.storagex") == set()
    assert storage_imports("from app.core.x import A") == set()
    assert storage_imports('import_module("app.core.x")') == set()
    assert storage_imports('import_module("app.storage_tools")') == set()
    assert storage_imports('__import__("app.storagex")') == set()
    assert storage_imports("import_module(name)") == set()


def test_entry_points_import_storage_only_in_listed_files():
    found = set()
    for layer in ("cli", "web"):
        for path in (APP / layer).rglob("*.py"):
            name = path.relative_to(APP).as_posix()
            allowed = ENTRY_POINT_STORAGE_MODULES
            if name == COMPOSITION_ROOT:
                allowed |= COMPOSITION_ROOT_NAMES
            if storage_imports(path.read_text()) - allowed:
                found.add(name)
    assert found == STORAGE_IN_ENTRY_POINTS


def test_composition_root_imports_only_session_and_create_all():
    assert storage_imports((APP / COMPOSITION_ROOT).read_text()) <= (
        ENTRY_POINT_STORAGE_MODULES | COMPOSITION_ROOT_NAMES)


def test_commit_scan_sees_attribute_calls():
    assert calls_commit("session.commit()")
    assert calls_commit("def f():\n    session.commit()\n")
    assert not calls_commit("commit()")
    assert not calls_commit("x.commit")


def test_web_commits_only_in_listed_files():
    found = {path.relative_to(APP).as_posix() for path in (APP / "web").rglob("*.py")
             if calls_commit(path.read_text())}
    assert found == COMMITS_IN_WEB


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


def _in_core(module: str) -> bool:
    return module == "app.core" or module.startswith("app.core.")


def _function_or_module(module: str, name: str) -> str:
    """The name of a function, the path of a module; empty for a type or a constant."""
    value = getattr(importlib.import_module(module), name, _MISSING)
    if value is _MISSING or inspect.ismodule(value):
        return f"{module}.{name}"
    return name if callable(value) and not inspect.isclass(value) else ""


def _core_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.name for alias in node.names if _in_core(alias.name)}
    if isinstance(node, ast.Call):
        module = _loaded_by_name(node)
        return {module} if _in_core(module) else set()
    if not isinstance(node, ast.ImportFrom):
        return set()
    module = node.module or ""
    if module == "app":
        return {"app.core"} if any(alias.name == "core" for alias in node.names) else set()
    if not _in_core(module):
        return set()
    return {_function_or_module(module, alias.name) for alias in node.names} - {""}


def names_from_core(source: str) -> set[str]:
    """Functions and modules of app.core the source imports; types and constants are left out."""
    return set().union(*(_core_names(node) for node in ast.walk(ast.parse(source))))


def storage_core_names() -> dict[str, set[str]]:
    root = APP / "storage"
    return {path.relative_to(root).as_posix(): names_from_core(path.read_text())
            for path in root.rglob("*.py")}


def test_names_from_core_sees_functions_and_modules():
    assert names_from_core("from app.core.canonicalize import canonical_url_hash") == {
        "canonical_url_hash"}
    assert names_from_core("def f():\n    from app.core.daily.titles import digest_title\n") == {
        "digest_title"}
    assert names_from_core("from app.core.bulletin.builder import Bulletin") == set()
    assert names_from_core("from app.core.provider_costs import PRICES") == set()
    assert names_from_core("import app.core.canonical_json") == {"app.core.canonical_json"}
    assert names_from_core("from app.core import canonical_json") == {"app.core.canonical_json"}
    assert names_from_core("from app import core") == {"app.core"}
    assert names_from_core('import_module("app.core.provider_costs")') == {
        "app.core.provider_costs"}
    assert names_from_core("from app.storage.db import SessionLocal") == set()


def test_storage_imports_from_core_only_types_constants_and_helpers():
    found = {name: names - HELPERS for name, names in storage_core_names().items()}
    assert {name: names for name, names in found.items() if names} == CALCULATION_EXCEPTIONS


def test_helpers_are_all_still_used_by_storage():
    assert HELPERS - set().union(*storage_core_names().values()) == set()
