# Prompt: SSH by key and a `deploy` user instead of root password (2026-10-24)

Executor: background agent (Sonnet) of coordinator `ai-parser-ba`. Owner approved the plan on
2026-10-24. You plan and prepare a PR; **you never write to the server**. The coordinator runs every
server command himself after the owner's yes.

## Facts (checked by the coordinator, read-only, 2026-10-24)

- Repo is public. Server: `ssh ai-news` (root, key `~/.ssh/ai_news_prod_ed25519` on this Mac).
- sshd: `permitrootlogin yes`, `passwordauthentication yes`, `pubkeyauthentication yes`;
  `/etc/ssh/sshd_config.d/50-cloud-init.conf` exists. ~124 failed logins per 24 h from 24 IPs.
- No fail2ban, no ufw, `iptables INPUT ACCEPT`. Containers: `ai-news-app`, `ai-news-db`,
  `ai-news-caddy`, plus `amnezia-awg2` and `amnezia-wireguard` (owner's VPN, must keep working).
- `/opt/ai-news` owned by root; systemd units `ai-news-*.service` have no `User=` (run as root).
- GitHub Actions log in with `sshpass -p "${SERVER_PASSWORD}"` as `${DEPLOY_USER}@${DEPLOY_HOST}` in
  `.github/workflows/deploy-release.yml`, `deploy-by-tag.yml`, `nightly-health.yml`,
  `db-maintenance.yml`. `docs/deploy.md` lines ~55-70 and ~185-195 describe it.

## Target

1. A user `deploy` on the server: member of group `docker`, owns `/opt/ai-news` (or has write
   access to what deploy writes), login by key only, a narrow `sudoers.d` file (NOPASSWD) for only
   the root commands the deploy and nightly workflows really run (find them: `systemctl`,
   writes under `/etc/systemd/system/`, anything else in `scripts/deploy_prod.sh`,
   `scripts/db_maintenance.sh`, `scripts/db_backup.sh`, the health script, the remote commands in
   the four workflows).
2. Two separate keys: one for GitHub Actions (secret `SERVER_SSH_KEY`, plus `SERVER_KNOWN_HOSTS`
   with the pinned host key instead of `StrictHostKeyChecking=accept-new`), one for the coordinator
   and agents on this Mac (`ssh ai-news` then logs in as `deploy`).
3. Workflows use the key (`ssh -i`, `scp -i`, no `sshpass`, no `SERVER_PASSWORD`), `DEPLOY_USER`
   stays a variable/secret (its value becomes `deploy`).
4. After CI works with the key: `PasswordAuthentication no`, `PermitRootLogin no` (root only via
   the time4vps console), in a file `/etc/ssh/sshd_config.d/10-hardening.conf`; check
   `50-cloud-init.conf` does not override it (sshd uses the first value it reads).
5. fail2ban with the sshd jail (defaults are fine).
6. Firewall last and separate: only after listing the ports Amnezia uses (`docker ps`, `ss -lntup`);
   write the rule list, do not apply.

## Steps for you

1. Worktree: `cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER && git fetch -q && git worktree add -b ops/ssh-deploy-user-20261024 ../AI_PARSER-wt-ssh origin/master`. No git writes in the main folder.
2. Read the four workflows, `scripts/deploy_prod.sh` and every script they run on the server, the
   `deploy/` folder, `docs/deploy.md`, `docs/troubleshooting.md`. List each remote command and
   whether it needs root.
3. You may run read-only commands on the server to check facts: `ssh ai-news '<cmd>'` with only
   `cat`, `ls`, `stat`, `id`, `getent`, `systemctl cat|status|list-timers`, `ss -lntup`,
   `docker ps`, `sshd -T`. Nothing else; no edits, no installs, no restarts.
4. Write the runbook `docs/work/plan-ssh-deploy-user-2026-10-24.md` (in the main folder path
   `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/`, it is git-ignored only for `prompt-*`,
   so also put a copy in the worktree for the PR): for each phase (server prep / switch CI / verify /
   close password+root / fail2ban / firewall list) the exact commands the coordinator runs, the
   check after each, and the rollback. Include: how to generate the two keys locally (into
   `~/.ssh/`, never print private keys), the `gh secret set` commands (the coordinator runs them),
   the sudoers file content (validated with `visudo -cf`), and a lockout guard (keep a root session
   open; test `ssh -o PasswordAuthentication=no deploy@...` in a second session before closing).
5. In the worktree change the four workflows to keys (keep the existing `retry` helper and step
   structure; remove the sshpass install steps), any script that assumes root and needs `sudo`,
   and `docs/deploy.md` (secrets list, how CI logs in; no host passwords or login details beyond
   secret names). Add a case to `docs/troubleshooting.md` only if you hit a non-obvious failure.
6. Checks: `make lint PYTHON=../AI_PARSER/venv1/bin/python`, `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest`,
   `bash -n` on changed scripts, and a YAML parse of the four workflows
   (`../AI_PARSER/venv1/bin/python -c "import yaml,sys; [yaml.safe_load(open(f)) for f in sys.argv[1:]]" .github/workflows/*.yml`).
7. Commit `ops: log in to the server by key as deploy, drop sshpass` (end with
   `Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`), push, `gh pr create --base master --draft`
   with a body that says: do not merge before runbook phase 1 is done on the server (the workflows
   would fail). End the body with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
   Do not merge, do not tag, do not run `gh secret set`, do not run `gh workflow run`.

## Report (final answer)

Draft PR URL and SHA; runbook path; table of remote commands (command, file, needs root, how
covered: sudoers / deploy user / docker group); the sudoers content; ports Amnezia uses; check
results with exact commands; open questions (one line each, with your recommendation).
