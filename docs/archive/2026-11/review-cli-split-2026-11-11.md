- **P3 — incorrect command location:** [src/app/usecases/archive/capture.md:224](/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/6f385967-2d04-4991-99fc-95f037a741dd/scratchpad/wt-cli/src/app/usecases/archive/capture.md:224) places `prune` in `cli/archive.py`. Concrete case: tracing `ai-news prune --dry-run` through this map leads to the wrong module; its handler is `cli/articles.py:71`. Fix: give `prune` a separate `cli/articles.py` entry.

No findings for command options/defaults, output ordering and streams, exit codes, initialization order, or dry-run behavior.

No findings for shared validation messages, week-error propagation, month rollback/error reporting, or migrated monkeypatch targets. No ineffective migrated patch found hidden by the guard change.

No findings for `main.md` or the remaining current documentation references.

The exact requested four-file pytest run passed (exit 0). Other tests were not run, as instructed. No files edited.