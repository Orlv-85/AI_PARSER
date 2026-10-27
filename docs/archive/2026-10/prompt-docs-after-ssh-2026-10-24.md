# Prompt: docs PR after the SSH switch (2026-10-24)

Executor: DeepSeek, run by coordinator `ai-parser-ba`; the coordinator reviews and merges. Docs
only. Do every step exactly; no other edits.

Repo: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (main folder). Never run `git add`, `git commit`,
`git checkout` or `rm -rf` in the main folder. Work only in the worktree from step 1.

## Step 1. Worktree

```bash
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch -q origin
git worktree add -b docs/after-ssh-20261024 ../AI_PARSER-wt-after-ssh origin/master
cd ../AI_PARSER-wt-after-ssh
```

## Step 2. Run the edit script

Save as `/tmp/after_ssh.py`, run `python3 /tmp/after_ssh.py` from the worktree root. It must print
`ok`. If an assert fails, stop and report; do not edit by hand.

```python
import json
import pathlib
import shutil
import subprocess

MAIN = pathlib.Path("/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work")
ARCH = pathlib.Path("docs/archive/2026-10")

# 1. Archive the finished prompts (git-ignored copies in the main folder).
for name in [
    "prompt-docs-after-127-2026-10-24.md",
    "prompt-scrub-access-details-2026-10-24.md",
    "prompt-ssh-deploy-user-2026-10-24.md",
    "prompt-tooling-todo-2026-10-24.md",
]:
    shutil.copyfile(MAIN / name, ARCH / name)

# 2. The SSH runbook is done: move it to the archive.
subprocess.run(["git", "mv", "docs/work/plan-ssh-deploy-user-2026-10-24.md",
                str(ARCH / "plan-ssh-deploy-user-2026-10-24.md")], check=True)

# 3. Troubleshooting case.
tp = pathlib.Path("docs/troubleshooting.md")
t = tp.read_text(encoding="utf-8")
tail = "\n  ]\n}\n```"
assert t.count(tail) == 1
case = {
    "id": "fail2ban-sshd-jail-sees-nothing",
    "date": "2026-10-24",
    "area": "prod server (fail2ban)",
    "symptom": "After `apt-get install fail2ban` on the prod server (Ubuntu 24.04) the sshd jail reports `Total failed: 0` while /var/log/auth.log has hundreds of failed SSH logins.",
    "evidence": [
        "fail2ban-client status sshd: Journal matches _SYSTEMD_UNIT=sshd.service + _COMM=sshd",
        "journalctl has no sshd failure lines on this server; /var/log/auth.log has them"
    ],
    "cause": "The Debian default (jail.d/defaults-debian.conf) sets backend = systemd and matches the sshd.service unit; on this server sshd runs as ssh.service and its lines reach only /var/log/auth.log.",
    "fix": "/etc/fail2ban/jail.d/ai-news-sshd.local: [sshd] backend = auto, logpath = /var/log/auth.log; then fail2ban-client -t and systemctl restart fail2ban.",
    "verification": "fail2ban-client status sshd shows File list: /var/log/auth.log. Bans not yet observed at the time of writing (the jail reads only new lines).",
    "if_it_recurs": "Check `fail2ban-client status sshd` (File list vs Journal matches) and where sshd writes: `grep -c 'Invalid user' /var/log/auth.log` vs `journalctl -g 'Invalid user'`."
}
body = json.dumps(case, indent=2, ensure_ascii=False)
body = "\n".join("    " + line for line in body.split("\n"))
t = t.replace(tail, ",\n" + body + tail)
start = t.index("```json\n") + len("```json\n")
end = t.index("\n```", start)
json.loads(t[start:end])
tp.write_text(t, encoding="utf-8")

# 4. Coordinator state.
sp = pathlib.Path("docs/work/coordinator-state-2026-10-24.json")
s = sp.read_text(encoding="utf-8")


def sub(old, new):
    global s
    assert s.count(old) == 1, ("not found once", old[:70])
    s = s.replace(old, new)


sub('"master": "3d38930 (PR #110)"', '"master": "d789ede (PR #114)"')
a = s.index('"prod": "v0.1.127 tagged')
b = s.index("\n", a)
s = (s[:a]
     + '"prod": "v0.1.128 (2026-10-24 14:24 UTC, first deploy by key as user deploy, green). '
       'SSH since 2026-10-24: password login off, root by key only (owner chose to keep root '
       'by key), CI and operators as deploy (docker group, narrow sudoers), SERVER_PASSWORD '
       'secret deleted, fail2ban sshd jail on /var/log/auth.log. Owner to change the root '
       'password in the time4vps panel (console only).",'
     + s[b:])
sub("code doc src/app/web/pages.md (#110). Docs: docs/ root holds guides only, docs/work/ for open process files (#109).\",",
    "code doc src/app/web/pages.md (#110). Docs: docs/ root holds guides only, docs/work/ for open "
    "process files (#109); access details removed from the archive (#112); tooling backlog "
    "docs/backlog/tooling-todo.json with T1 spec pipeline, deferred (#114). v0.1.128: CI logs in "
    "by key as deploy, sshpass removed (#113); runbook docs/archive/2026-10/plan-ssh-deploy-user-2026-10-24.md.\",")
sub("or external models (DeepSeek) run by the owner;",
    "or DeepSeek run by the coordinator itself (headless claude -p with DS_API_KEY, simple docs "
    "tasks by default); Z.ai/GLM dropped by the owner;")
sub('"status": "todo"},\n    {"id": "OPENAI-check"',
    '"status": "todo"},\n'
    '    {"id": "SSH-check", "title": "2026-10-25: fail2ban bans appear (fail2ban-client status sshd), '
    'nightly-health and db-maintenance green by key; owner changed the root password", "status": "todo"},\n'
    '    {"id": "FIREWALL", "title": "Firewall (runbook phase 6, rules listed, not applied): only 22, 80, 443 '
    'and the Amnezia UDP ports; test the VPN before enabling; owner yes", "status": "backlog"},\n'
    '    {"id": "OPENAI-check"')
json.loads(s)
sp.write_text(s, encoding="utf-8")
print("ok")
```

## Step 3. Checks

```bash
git add -A
git status --short
PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest tests -k code_docs -p no:cacheprovider 2>&1 | tail -1
```
Expected status: four `A docs/archive/2026-10/prompt-*-2026-10-24.md`, one
`R docs/work/plan-ssh-deploy-user-2026-10-24.md -> docs/archive/2026-10/plan-ssh-deploy-user-2026-10-24.md`,
` M`/`M` for `docs/troubleshooting.md` and `docs/work/coordinator-state-2026-10-24.json`. Nothing
else. The pytest line shows `passed` (run without `-q`).

## Step 4. Commit, push, PR

```bash
git commit -m "docs: state after the SSH switch, fail2ban case, archive SSH records" -m "Co-Authored-By: DeepSeek V4-Pro <noreply@deepseek.com>"
git push -u origin docs/after-ssh-20261024
gh pr create --base master --title "docs: state after the SSH switch, fail2ban case, archive SSH records" --body "Docs-only; full gate skipped.

- Archive four finished prompts and the SSH runbook.
- docs/troubleshooting.md: fail2ban sshd jail read the journal, sshd logs only to auth.log.
- Coordinator state: master d789ede, prod v0.1.128 and the new SSH access, release line, executor rule, SSH-check and FIREWALL items."
```
Do not merge.

## Step 5. Report (final answer)

PR URL, `git log --oneline -1`, outputs of steps 2 and 3, anything that did not go as written.
