# Prompt (Codex, gpt-6-astra high): review of PR #197, bulletin outlet names (2026-11-01)

Read-only review. Directory: `/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/codex-outlet` (git worktree of branch
`fix/018-bulletin-outlet-name`, PR #197). Do not edit, commit or push anything; no network.

1. Read `AGENTS.md`, then the change: `git -C /private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/codex-outlet diff origin/master...HEAD`.
2. Check: `outlet_name` strips only a trailing parenthesised label and a leading `www.`; inputs
   where it does harm (a real name ending in parentheses, nested parentheses, "WWW.", an IP, a name
   that is only a label); both call sites use it; `/daily` and the digest are untouched; the doc rule
   in `builder.md` matches the code and names the test.
3. Test strength: would the test fail if a call site stopped using `outlet_name`? Say so if not and
   give the smallest extra assertion that would catch it.
4. Run `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/pytest -q -o addopts="" tests/unit/test_bulletin_builder.py | tail -1`.

Report: verdict (merge / merge after fixes), findings with file:line and a one-line fix, the test output.
