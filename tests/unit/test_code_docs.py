import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _module():
    spec = importlib.util.spec_from_file_location("check_code_docs",
                                                  ROOT / "scripts/check_code_docs.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECK = _module()
SRC = "RENAMED_CONSTANT = 1\nclass KnownRepo:\n    pass\ndef known_function(): ...\n--known-flag\n"
SETTINGS = "class Settings:\n    known_setting: str = ''\n"


def _errors(tmp_path, body):
    doc = tmp_path / "feature.md"
    doc.write_text(body, encoding="utf-8")
    return CHECK.static_errors(CHECK.parse(doc), SRC, "", SETTINGS)


def test_repo_code_docs_are_in_sync():
    assert CHECK.main([]) == 0


def test_known_references_pass(tmp_path):
    body = ("`RENAMED_CONSTANT`, `KnownRepo`, `known_function`, `repo.known_function`, "
            "`--known-flag`, `AINEWS_KNOWN_SETTING`, `scripts/check_code_docs.py`, "
            "`check_code_docs.py`, plain words `ok` and `not a ref`.\n")
    assert _errors(tmp_path, body) == []


def test_stale_references_fail(tmp_path):
    body = ("`OLD_CONSTANT` `OldRepo` `old_function` `repo.old_method` `--old-flag` "
            "`AINEWS_OLD_SETTING` `src/app/core/removed.py`\n")
    errors = _errors(tmp_path, body)
    for name in ("OLD_CONSTANT", "OldRepo", "old_function", "repo.old_method", "--old-flag",
                 "AINEWS_OLD_SETTING", "src/app/core/removed.py"):
        assert any(f"`{name}`" in e for e in errors), name


def test_fenced_blocks_are_not_checked(tmp_path):
    assert _errors(tmp_path, "```text\n`OLD_CONSTANT`\n```\n") == []


def test_header_checks_module_docstring_covers_and_indexes(tmp_path):
    body = ("<!-- code-doc\nmodule: src/app/core/missing.py\ncovers:\n"
            "  - src/app/core/nothing_*.py\n-->\n# Doc\n")
    errors = _errors(tmp_path, body)
    assert any("module src/app/core/missing.py not found" in e for e in errors)
    assert any("covers `src/app/core/nothing_*.py` matches no file" in e for e in errors)
    assert any("not listed in docs/README.md" in e for e in errors)


def test_diff_requires_doc_change_or_docs_skip():
    doc = CHECK.Doc(ROOT / "src/app/core/feature.md", "src/app/core/feature.py",
                    ["src/app/core/feature*.py"])
    changed = ["src/app/core/feature_extra.py", "README.md"]
    errors = CHECK.diff_errors([doc], changed, "refactor\n")
    assert len(errors) == 1 and "src/app/core/feature_extra.py" in errors[0]
    assert CHECK.diff_errors([doc], [*changed, "src/app/core/feature.md"], "x") == []
    assert CHECK.diff_errors([doc], changed, "refactor\n\nDocs-Skip: rename only\n") == []
    assert CHECK.diff_errors([doc], ["src/app/core/other.py"], "x") == []
