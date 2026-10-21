#!/usr/bin/env python3
"""Keep code docs (Markdown next to the code) in sync with the code.

A code doc is a `*.md` file under `src/` with a header comment:

    <!-- code-doc
    module: src/app/core/daily/signals.py
    covers:
      - src/app/core/daily/signals*.py
    -->

Static checks (every doc under `src/`, header or not):
- every backticked file reference exists;
- every backticked UPPER_CASE constant, CamelCase class, snake_case name and `--flag` occurs
  in `src/`; a backticked `test_*` name is a test function under `tests/`;
- every backticked `AINEWS_*` variable is a settings field (or occurs in `src/`, scripts,
  deploy files).
Header checks: `module` exists and its docstring names the doc; every `covers` glob matches a file;
the doc is listed in `docs/README.md` and `README.md`.

Diff check (`--diff BASE`): a change to a covered file needs a change to its doc, or a commit
message line `Docs-Skip: <reason>` in BASE..HEAD. Warn only, unless `--strict`.

Stdlib only; run from the repo root. Exit 1 on any static error (and on diff errors with --strict).
"""
import argparse
import fnmatch
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADER = re.compile(r"<!--\s*code-doc\s*(.*?)-->", re.DOTALL)
FENCE = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)
TICK = re.compile(r"`([^`\n]+)`")
FILE_REF = re.compile(r"^[\w./*-]+\.(py|md|html|sh|json|yml|yaml|toml|txt)$")
CONST = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")
CLASS = re.compile(r"^[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+$")
SNAKE = re.compile(r"^_?[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")
DOTTED = re.compile(r"^[a-z_][a-z0-9_]*\.([a-z_][a-z0-9_]*)$")
FLAG = re.compile(r"^--[a-z][a-z0-9-]+$")
SKIP_LINE = re.compile(r"^Docs-Skip:\s*\S", re.MULTILINE)
TEXT_SUFFIXES = frozenset({".py", ".html", ".sh", ".yml", ".yaml", ".toml", ".txt", ".ini", ""})
SEARCH_EXTRA = ("scripts", "deploy", "docker-compose.prod.yml", ".github")


@dataclass
class Doc:
    path: Path
    module: str | None = None
    covers: list[str] = field(default_factory=list)


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def parse(path: Path) -> Doc:
    doc = Doc(path)
    match = HEADER.search(path.read_text(encoding="utf-8"))
    if match:
        for line in match.group(1).splitlines():
            line = line.strip()
            if line.startswith("module:"):
                doc.module = line.split(":", 1)[1].strip()
            elif line.startswith("- "):
                doc.covers.append(line[2:].strip())
    return doc


def code_docs() -> list[Doc]:
    return [parse(p) for p in sorted((ROOT / "src").rglob("*.md"))]


def _corpus(paths: list[Path]) -> str:
    parts = []
    for base in paths:
        files = [base] if base.is_file() else [p for p in base.rglob("*") if p.is_file()]
        for path in files:
            if path.suffix in TEXT_SUFFIXES and "__pycache__" not in path.parts:
                try:
                    parts.append(path.read_text(encoding="utf-8"))
                except (UnicodeDecodeError, OSError):
                    continue
    return "\n".join(parts)


def _file_exists(ref: str, doc_dir: Path) -> bool:
    if "*" in ref:
        return any(ROOT.glob(ref)) or any(doc_dir.glob(ref))
    candidates = [ROOT / ref, doc_dir / ref, ROOT / "src/app" / ref, ROOT / "tests/unit" / ref,
                  ROOT / "docs" / ref]
    if any(c.exists() for c in candidates):
        return True
    # A bare file name may live anywhere under src/, tests/ or scripts/.
    return "/" not in ref and any(any((ROOT / base).rglob(ref))
                                  for base in ("src", "tests", "scripts"))


def _word(name: str, text: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text) is not None


def _ref_errors(doc: Doc, src: str, extra: str, settings: str, tests: str) -> list[str]:
    errors = []
    name = rel(doc.path)
    body = FENCE.sub("", doc.path.read_text(encoding="utf-8"))
    for token in sorted(set(TICK.findall(body))):
        ref = token.strip()
        if FILE_REF.match(ref):
            if not _file_exists(ref, doc.path.parent):
                errors.append(f"{name}: file `{ref}` not found")
        elif ref.startswith("AINEWS_") and CONST.match(ref):
            field_name = ref.removeprefix("AINEWS_").lower()
            if not re.search(rf"^\s+{field_name}\s*:", settings, re.MULTILINE) \
                    and not _word(ref, src + extra):
                errors.append(f"{name}: setting `{ref}` not found")
        elif ref.startswith("test_") and SNAKE.match(ref):
            if not re.search(rf"\bdef {re.escape(ref)}\(", tests):
                errors.append(f"{name}: test `{ref}` not found in tests/")
        elif CONST.match(ref) or CLASS.match(ref) or SNAKE.match(ref) or FLAG.match(ref):
            if not _word(ref, src):
                errors.append(f"{name}: name `{ref}` not found in src/")
        elif (dotted := DOTTED.match(ref)) and not _word(dotted.group(1), src):
            errors.append(f"{name}: name `{ref}` not found in src/")
    return errors


def _header_errors(doc: Doc) -> list[str]:
    if doc.module is None:
        return []
    errors = []
    name = rel(doc.path)
    module = ROOT / doc.module
    if not module.is_file():
        errors.append(f"{name}: module {doc.module} not found")
    else:
        text = module.read_text(encoding="utf-8")
        docstring = re.match(r'\s*(?:#[^\n]*\n\s*)*"""(.*?)"""', text, re.DOTALL)
        if not docstring or doc.path.name not in docstring.group(1):
            errors.append(f"{name}: docstring of {doc.module} does not name {doc.path.name}")
    if not doc.covers:
        errors.append(f"{name}: header has no covers")
    for pattern in doc.covers:
        if not any(ROOT.glob(pattern)):
            errors.append(f"{name}: covers `{pattern}` matches no file")
    for index in ("docs/README.md", "README.md"):
        if rel(doc.path) not in (ROOT / index).read_text(encoding="utf-8"):
            errors.append(f"{name}: not listed in {index}")
    return errors


def static_errors(doc: Doc, src: str, extra: str, settings: str, tests: str = "") -> list[str]:
    return _ref_errors(doc, src, extra, settings, tests) + _header_errors(doc)


def diff_errors(docs: list[Doc], changed: list[str], messages: str) -> list[str]:
    """Covered files changed without their doc; empty when a Docs-Skip line is present."""
    if SKIP_LINE.search(messages):
        return []
    errors = []
    for doc in docs:
        if not doc.covers:
            continue
        touched = sorted(f for f in changed
                         if any(fnmatch.fnmatch(f, p) for p in doc.covers))
        if touched and rel(doc.path) not in changed:
            errors.append(f"{rel(doc.path)}: covered files changed without the doc: "
                          + ", ".join(touched)
                          + " (update the doc or add 'Docs-Skip: <reason>' to a commit message)")
    return errors


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--diff", metavar="BASE", help="also check changes in BASE...HEAD")
    parser.add_argument("--strict", action="store_true", help="fail on diff findings")
    args = parser.parse_args(argv)
    docs = code_docs()
    src = _corpus([ROOT / "src"])
    extra = _corpus([ROOT / p for p in SEARCH_EXTRA if (ROOT / p).exists()])
    settings = (ROOT / "src/app/config/settings.py").read_text(encoding="utf-8")
    tests = _corpus([ROOT / "tests"])
    errors = [e for d in docs for e in static_errors(d, src, extra, settings, tests)]
    for error in errors:
        print(f"ERROR {error}")
    failed = bool(errors)
    if args.diff:
        changed = _git("diff", "--name-only", f"{args.diff}...HEAD").split()
        messages = _git("log", "--format=%B", f"{args.diff}..HEAD")
        level = "error" if args.strict else "warning"
        for finding in diff_errors(docs, changed, messages):
            # GitHub Actions shows ::warning:: / ::error:: lines as annotations on the run.
            prefix = f"::{level}::" if os.environ.get("GITHUB_ACTIONS") else f"{level.upper()} "
            print(f"{prefix}{finding}")
            failed = failed or args.strict
    print(f"code docs: {len(docs)} checked, {'FAILED' if failed else 'ok'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
