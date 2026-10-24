# Prompt: add the tooling backlog with the spec pipeline idea (2026-10-24)

Executor: DeepSeek, run by coordinator `ai-parser-ba`; the coordinator reviews and merges. Docs
only. Do every step exactly; no other edits.

Repo: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (main folder). Never run `git add`, `git commit`,
`git checkout` or `rm -rf` in the main folder. Work only in the worktree from step 1.

## Step 1. Worktree

```bash
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch -q origin
git worktree add -b docs/tooling-todo-20261024 ../AI_PARSER-wt-tooling origin/master
cd ../AI_PARSER-wt-tooling
```

## Step 2. New file `docs/backlog/tooling-todo.json`

Create it with exactly this content (2-space indent, trailing newline):

```json
{
  "title": "Tooling backlog: how agents build this repo (not product features)",
  "created": "2026-10-24",
  "status": "backlog",
  "items": [
    {
      "id": "T1",
      "title": "Spec pipeline: tester -> coder -> reviewer loop driven by a script",
      "status": "deferred",
      "decided": "Owner 2026-10-24: good idea, later.",
      "idea": "A script takes a spec folder (specs/NNN-name/) and walks tasks.md. Per task: tester writes failing tests from the spec; a test reviewer checks them against the spec (optional); coder edits code until tests and linters are green; a code reviewer checks the code against the spec and sends findings back to the coder; the tester then strengthens the tests (edge cases) and red tests go back to the coder; commit, next task; one PR per spec, reviewed by the coordinator.",
      "design_notes": [
        "Location: scripts/agents/ (entry point scripts/agents/run_spec.sh specs/NNN-name/).",
        "Roles run as headless Claude Code (claude -p) with a model per role (e.g. coder DeepSeek, reviewer Sonnet); same mechanism as the DeepSeek runs of 2026-10-24.",
        "The script, not the model, enforces role limits by git diff: a coder change under tests/ or a tester change under src/ is rolled back.",
        "Tests before code need named interfaces: specs written for the pipeline list exact modules, functions and signatures.",
        "Hard caps per task (iterations) and per run (tokens or money; proposed $2 per spec for paid models); on a cap the script stops and reports.",
        "Prior art to reuse: .codex/skills/multi-agent-orchestration/scripts/run_executor_reviewer.sh (Codex executor/reviewer, not in use).",
        "First run: a small backlog item (F1 pipeline findings) to measure cost and how many findings the coordinator's review still finds."
      ],
      "open_questions": [
        "Budget per run (proposed $2 for DeepSeek) - owner.",
        "Spec number: next free under specs/ when started."
      ]
    }
  ]
}
```

## Step 3. Register it in `docs/README.md`

In the `## Backlog` list, after the line that starts with
`- [jev-novelty-second-opinion-todo.json]`, add the line:

```
- [tooling-todo.json](backlog/tooling-todo.json) - agent tooling (spec pipeline), not product
```

## Step 4. Checks

```bash
python3 -m json.tool docs/backlog/tooling-todo.json > /dev/null && echo json-ok
git status --short
git diff
```
Expected: `json-ok`; status shows `?? docs/backlog/tooling-todo.json` and ` M docs/README.md`; the diff
is the one added line.

## Step 5. Commit, push, PR

```bash
git add docs/backlog/tooling-todo.json docs/README.md
git commit -m "docs: tooling backlog with the spec pipeline idea (deferred)" -m "Co-Authored-By: DeepSeek V4-Pro <noreply@deepseek.com>"
git push -u origin docs/tooling-todo-20261024
gh pr create --base master --title "docs: tooling backlog with the spec pipeline idea (deferred)" --body "Docs-only; full gate skipped.

New docs/backlog/tooling-todo.json (agent tooling, not product) with T1 spec pipeline, deferred by the owner on 2026-10-24; registered in docs/README.md."
```
Do not merge.

## Step 6. Report (final answer)

PR URL, `git log --oneline -1`, outputs of step 4, anything that did not go as written.
