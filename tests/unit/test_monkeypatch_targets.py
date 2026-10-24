"""Guard: a monkeypatch on an `app.` module must hit a module that reads the patched name.

A test that patches `module.NAME` only works when functions of `module` look NAME up at call time.
After a function moves to another module the patch silently stops applying; this test fails then.
Checked targets: `monkeypatch.setattr/delattr("app.x.y.NAME", ...)`, `setattr(<module object>,
"NAME", ...)` (aliases resolved from imports and `import_module`), and `f"app.x.y.{var}"` when
`var` is a `pytest.mark.parametrize` argument of the test.
"""
import ast
import importlib.util
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path

TESTS = Path(__file__).resolve().parent.parent
PATCH_METHODS = {"setattr", "delattr"}
# Patches that hit a module without a reader (module.NAME): none now. An entry means the patch
# does nothing; fix the test instead of adding one.
KNOWN_NO_READER: set[tuple[str, str]] = set()


@dataclass(frozen=True)
class Target:
    module: str
    name: str
    path: str
    line: int


@cache
def _module_source(module: str) -> tuple[ast.Module, str] | None:
    spec = importlib.util.find_spec(module)
    if spec is None or not spec.origin or not spec.origin.endswith(".py"):
        return None
    return ast.parse(Path(spec.origin).read_text(encoding="utf-8")), spec.origin


def _is_module(name: str) -> bool:
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return False
    return spec is not None and spec.origin is not None and spec.origin.endswith(".py")


def _split_dotted(dotted: str) -> tuple[str, str, bool] | None:
    """Longest module prefix, the next name, and whether more attributes follow."""
    parts = dotted.split(".")
    for end in range(len(parts) - 1, 0, -1):
        prefix = ".".join(parts[:end])
        if _is_module(prefix):
            return prefix, parts[end], end + 1 < len(parts)
    return None


def _imported_module_name(call: ast.Call) -> str | None:
    """`import_module("app...")` -> the module name, else None."""
    func = call.func
    called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
    if called != "import_module" or not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("app"):
        return arg.value
    return None


def _scope_nodes(tree: ast.Module, scope: ast.AST) -> Iterator[ast.AST]:
    """Nodes of one test function, or of the module level outside functions and classes."""
    if scope is not tree:
        yield from ast.walk(scope)
        return
    for stmt in tree.body:
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield from ast.walk(stmt)


def _aliases(tree: ast.Module, scope: ast.AST) -> dict[str, str]:
    """Names bound to `app.` modules: imports of the file, `import_module` calls of `scope`."""
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname and alias.name.startswith("app.") and _is_module(alias.name):
                    found[alias.asname] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app"):
            for alias in node.names:
                full = f"{node.module}.{alias.name}"
                if _is_module(full):
                    found[alias.asname or alias.name] = full
    for node in _scope_nodes(tree, scope):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            module = _imported_module_name(node.value)
            if module and isinstance(node.targets[0], ast.Name):
                found[node.targets[0].id] = module
    return found


def _parametrized(function: ast.AST) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for decorator in getattr(function, "decorator_list", []):
        if not (isinstance(decorator, ast.Call) and decorator.args
                and getattr(decorator.func, "attr", "") == "parametrize"):
            continue
        names, options = decorator.args[0], decorator.args[1:2]
        if (isinstance(names, ast.Constant) and isinstance(names.value, str)
                and options and isinstance(options[0], (ast.List, ast.Tuple))):
            consts = [e.value for e in options[0].elts
                      if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            if len(consts) == len(options[0].elts):
                values[names.value] = consts
    return values


def _string_targets(first: ast.expr, params: dict[str, list[str]]) -> list[str]:
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return [first.value]
    if isinstance(first, ast.JoinedStr) and len(first.values) == 2:
        head, tail = first.values
        if (isinstance(head, ast.Constant) and isinstance(tail, ast.FormattedValue)
                and isinstance(tail.value, ast.Name) and tail.value.id in params):
            return [f"{head.value!s}{value}" for value in params[tail.value.id]]
    return []


def _unique(items: list[Target]) -> list[Target]:
    return sorted(set(items), key=lambda t: (t.path, t.line, t.module, t.name))


def _targets_in_file(path: Path) -> tuple[list[Target], list[Target]]:
    """(module-attribute targets, object-attribute targets) patched by one test file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    shown = path.relative_to(TESTS.parent).as_posix()
    module_targets: list[Target] = []
    object_targets: list[Target] = []
    functions = [n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for function in [tree, *functions]:
        params = _parametrized(function)
        aliases = _aliases(tree, function)
        for node in _scope_nodes(tree, function):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in PATCH_METHODS and node.args):
                continue
            first = node.args[0]
            if isinstance(first, ast.Name) and first.id in aliases and len(node.args) >= 2:
                second = node.args[1]
                if isinstance(second, ast.Constant) and isinstance(second.value, str):
                    module_targets.append(
                        Target(aliases[first.id], second.value, shown, node.lineno))
                continue
            for dotted in _string_targets(first, params):
                if not dotted.startswith("app."):
                    continue
                split = _split_dotted(dotted)
                if split is None:
                    continue
                module, name, deeper = split
                (object_targets if deeper else module_targets).append(
                    Target(module, name, shown, node.lineno))
    return _unique(module_targets), _unique(object_targets)


def _defines(tree: ast.Module, name: str) -> bool:
    def walk(statements: list[ast.stmt]) -> bool:
        for stmt in statements:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if stmt.name == name:
                    return True
            elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
                if any((a.asname or a.name.split(".")[0]) == name for a in stmt.names):
                    return True
            elif isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.TypeAlias)):
                targets = (stmt.targets if isinstance(stmt, ast.Assign)
                           else [stmt.name] if isinstance(stmt, ast.TypeAlias) else [stmt.target])
                if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                    return True
            else:
                for field in ("body", "orelse", "finalbody", "handlers"):
                    inner = getattr(stmt, field, [])
                    if inner and walk([s for s in inner if isinstance(s, ast.stmt)]
                                      + [b for h in inner if isinstance(h, ast.ExceptHandler)
                                         for b in h.body]):
                        return True
        return False

    return walk(tree.body)


def _read_in_function(tree: ast.Module, name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            for inner in ast.walk(node):
                if (isinstance(inner, ast.Name) and inner.id == name
                        and isinstance(inner.ctx, ast.Load)):
                    return True
                if isinstance(inner, ast.Attribute) and inner.attr == name:
                    return True
    return False


def _all_targets() -> tuple[list[Target], list[Target]]:
    module_targets: list[Target] = []
    object_targets: list[Target] = []
    for path in sorted(TESTS.rglob("test_*.py")):
        if path.name == Path(__file__).name:
            continue
        modules, objects = _targets_in_file(path)
        module_targets += modules
        object_targets += objects
    return module_targets, object_targets


def _problems() -> list[str]:
    modules, objects = _all_targets()
    problems: list[str] = []
    for target in modules + objects:
        source = _module_source(target.module)
        where = f"{target.path}:{target.line}"
        if source is None:
            problems.append(f"{where}: {target.module} is not a Python module")
            continue
        tree, _ = source
        if not _defines(tree, target.name):
            problems.append(f"{where}: {target.module} has no name {target.name}")
    for target in modules:
        source = _module_source(target.module)
        if source is None or not _defines(source[0], target.name):
            continue
        if (target.module, target.name) in KNOWN_NO_READER:
            continue
        if not _read_in_function(source[0], target.name):
            problems.append(
                f"{target.path}:{target.line}: patch on {target.module}.{target.name} has no "
                "effect: no reader in this module"
            )
    return problems


def test_every_monkeypatch_hits_a_module_that_reads_the_name() -> None:
    problems = _problems()
    assert not problems, "\n" + "\n".join(problems)


def test_known_no_reader_entries_are_still_needed() -> None:
    modules, _ = _all_targets()
    patched = {(t.module, t.name) for t in modules}
    stale = sorted(KNOWN_NO_READER - patched)
    assert not stale, f"remove from KNOWN_NO_READER: {stale}"


def test_guard_reader_check() -> None:
    tree = ast.parse("from os import sep\n\ndef read():\n    return 1\n")
    assert _defines(tree, "sep")
    assert not _read_in_function(tree, "sep")
    assert _read_in_function(ast.parse("def f():\n    return sep\n"), "sep")
