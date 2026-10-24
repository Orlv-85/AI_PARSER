# Runbook: log in to the server by key as `deploy` (2026-10-24)

Run by the coordinator, after the owner's yes. Prepared from read-only checks of the server on
2026-10-24 (Ubuntu 24.04, sudo 1.9.15, sshd on `ssh.socket`, `/var/log/auth.log` present, docker
group GID 110, no `deploy` user, no fail2ban, root crontab empty, `/tmp/ai_news_*` absent).
Placeholders: `$HOST` = value of the repo variable `DEPLOY_HOST`; `$REPO` = `Orlv-85/AI_PARSER`.

The draft PR (workflows, scripts, docs) must not be merged before phase 1 is done and the two
secrets of phase 2 step 1 are set.

## Rules for the whole run

- Do phases 1-4 outside 01:00-04:00 UTC (daily timers 01/02/03 UTC, db-maintenance 02:20 UTC,
  nightly-health 03:00 UTC). Check `gh run list` for a running deploy first.
- Lockout guard: open **session R** (`ssh ai-news` as root, the current config) and keep it open
  until the end of phase 4. All checks of `deploy` run from a **second** terminal. Last resort: the
  time4vps console (root).
- Never print private keys. Keys live only in `~/.ssh/` and in the GitHub secret.

## Phase 0 - keys on this Mac

```bash
ssh-keygen -t ed25519 -N '' -C 'ai-news-ci'       -f ~/.ssh/ai_news_ci_ed25519
ssh-keygen -t ed25519 -N '' -C 'ai-news-operator' -f ~/.ssh/ai_news_deploy_ed25519
chmod 600 ~/.ssh/ai_news_ci_ed25519 ~/.ssh/ai_news_deploy_ed25519
ls -l ~/.ssh/ai_news_*          # four new files; do not cat the private ones
```

Check: both `.pub` files exist. Rollback: `rm ~/.ssh/ai_news_ci_ed25519* ~/.ssh/ai_news_deploy_ed25519*`.

## Phase 1 - server prep (session R, root; password and root login stay on)

1. User and group:

```bash
adduser --disabled-password --gecos '' deploy
usermod -aG docker deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
```

2. Keys (run on the Mac; the CI key is limited to what a batch job needs):

```bash
{ printf 'no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty '
  cat ~/.ssh/ai_news_ci_ed25519.pub
  cat ~/.ssh/ai_news_deploy_ed25519.pub; } | ssh ai-news 'cat > /home/deploy/.ssh/authorized_keys'
ssh ai-news 'chown deploy:deploy /home/deploy/.ssh/authorized_keys && chmod 600 /home/deploy/.ssh/authorized_keys && wc -l /home/deploy/.ssh/authorized_keys'
```

Check: `wc` prints 2.

3. Ownership of the app folder (containers and timers run as root and keep writing there; root
   ignores permissions):

```bash
chown -R deploy:deploy /opt/ai-news
ls -ld /opt/ai-news /opt/ai-news/.git /opt/ai-news/data /opt/ai-news/logs /opt/ai-news/backups
```

4. Git remote over https (the repo is public; the current SSH remote uses a root-only key):

```bash
sudo -u deploy git -C /opt/ai-news remote set-url origin https://github.com/Orlv-85/AI_PARSER.git
sudo -u deploy git -C /opt/ai-news fetch --force origin '+refs/tags/*:refs/tags/*' && echo fetch-ok
```

5. Sudoers (validated before it goes live):

```bash
cat > /root/ai-news-deploy.sudoers <<'SUDOERS'
# Root calls made by scripts/deploy_prod.sh and scripts/install_daily_timers.sh. Exact arguments only.
Cmnd_Alias AINEWS_UNITS = \
  /usr/bin/install -m 0644 /var/tmp/ai-news-units/ai-news-daily-archive.service /etc/systemd/system/ai-news-daily-archive.service, \
  /usr/bin/install -m 0644 /var/tmp/ai-news-units/ai-news-daily-archive.timer /etc/systemd/system/ai-news-daily-archive.timer, \
  /usr/bin/install -m 0644 /var/tmp/ai-news-units/ai-news-daily-digest.service /etc/systemd/system/ai-news-daily-digest.service, \
  /usr/bin/install -m 0644 /var/tmp/ai-news-units/ai-news-daily-digest.timer /etc/systemd/system/ai-news-daily-digest.timer, \
  /usr/bin/install -m 0644 /var/tmp/ai-news-units/ai-news-daily-fetch.service /etc/systemd/system/ai-news-daily-fetch.service, \
  /usr/bin/install -m 0644 /var/tmp/ai-news-units/ai-news-daily-fetch.timer /etc/systemd/system/ai-news-daily-fetch.timer
Cmnd_Alias AINEWS_SYSTEMD = \
  /usr/bin/systemctl daemon-reload, \
  /usr/bin/systemctl enable --now ai-news-daily-fetch.timer ai-news-daily-digest.timer, \
  /usr/bin/systemctl enable --now ai-news-daily-archive.timer, \
  /usr/bin/systemctl disable --now ai-news-daily-fetch.timer, \
  /usr/bin/systemctl disable --now ai-news-daily-digest.timer
deploy ALL=(root) NOPASSWD: AINEWS_UNITS, AINEWS_SYSTEMD
SUDOERS
visudo -cf /root/ai-news-deploy.sudoers && install -m 0440 -o root -g root /root/ai-news-deploy.sudoers /etc/sudoers.d/ai-news-deploy
visudo -c
sudo -l -U deploy
```

Check: `visudo -c` says "parsed OK"; `sudo -l -U deploy` lists only those commands.

6. Login test (second terminal on the Mac, before anything else changes):

```bash
ssh -i ~/.ssh/ai_news_deploy_ed25519 -o IdentitiesOnly=yes -o PasswordAuthentication=no deploy@$HOST 'id; docker ps --format "{{.Names}}"; cd /opt/ai-news && git status -sb | head -3'
ssh -i ~/.ssh/ai_news_ci_ed25519 -o IdentitiesOnly=yes -o PasswordAuthentication=no deploy@$HOST 'echo ci-key-ok'
```

Check: groups include `docker`; five container names; both succeed.

The sudo path of `scripts/install_daily_timers.sh` is exercised by the first deploy in phase 3
(`master` on the server still has the root-only version until a tag with the PR is deployed; the
first key-based deploy checks out the tag first, then runs the new script).

Rollback of phase 1: `rm /etc/sudoers.d/ai-news-deploy; chown -R root:root /opt/ai-news;
git -C /opt/ai-news remote set-url origin git@github.com:Orlv-85/AI_PARSER.git; userdel -r deploy`
(nothing else changed; CI still uses the root password).

## Phase 2 - switch CI

Order matters: the old workflows on `master` still log in with the password.

1. Secrets that do not affect the old workflows (the coordinator runs them):

```bash
gh secret set SERVER_SSH_KEY -R $REPO < ~/.ssh/ai_news_ci_ed25519
printf '%s %s\n' "$HOST" "$(ssh ai-news 'cut -d" " -f1,2 /etc/ssh/ssh_host_ed25519_key.pub')" | gh secret set SERVER_KNOWN_HOSTS -R $REPO
gh secret list -R $REPO | grep -E 'SERVER_'
```

The known-hosts line comes over the already trusted root session, not from `ssh-keyscan`.

2. Merge the PR (owner's yes), then **immediately**:

```bash
gh variable set DEPLOY_USER -R $REPO --body deploy
gh variable list -R $REPO | grep DEPLOY_
```

A scheduled run between merge and this command fails (harmless). Do not do it near 02:20 or 03:00 UTC.

Rollback: `gh variable set DEPLOY_USER -R $REPO --body root`, then revert the PR merge (the
`SERVER_PASSWORD` secret stays set until phase 4 is done).

## Phase 3 - verify CI by key

```bash
gh workflow run nightly-health.yml -R $REPO ; sleep 20; gh run list -R $REPO --workflow nightly-health.yml -L 1
gh workflow run db-maintenance.yml -R $REPO ; sleep 5; gh run list -R $REPO --workflow db-maintenance.yml -L 1
```

(db-maintenance prunes, backs up and uploads off-site: the work it does every night.)
Then a deploy by key that exercises sudo, git and docker login: `deploy-by-tag` with a tag that
contains the PR (the next release), or the current tag if the PR was merged before it (the app
restarts for a few seconds):

```bash
gh workflow run deploy-by-tag.yml -R $REPO -f deploy_tag=<tag containing the PR>
gh run watch -R $REPO
```

Checks on the server (as `deploy`):

```bash
ssh -i ~/.ssh/ai_news_deploy_ed25519 deploy@$HOST 'systemctl list-timers "ai-news-daily-*" --no-pager; cat /opt/ai-news/.last_deploy_image; ls -l /etc/systemd/system/ai-news-daily-*; ls /tmp/ai_news_* 2>&1 | head -2'
```

Expected: three timers with next run times, the new image tag, unit files owned by root, no
leftover `/tmp/ai_news_*`.

Switch this Mac to `deploy` (keep a root alias until phase 4 ends). In `~/.ssh/config`:

```
Host ai-news
  HostName 5kzt.l.time4vps.cloud
  User deploy
  IdentityFile ~/.ssh/ai_news_deploy_ed25519
  IdentitiesOnly yes

Host ai-news-root
  HostName 5kzt.l.time4vps.cloud
  User root
  IdentityFile ~/.ssh/ai_news_prod_ed25519
  IdentitiesOnly yes
```

Agents that run `ssh ai-news '<read-only cmd>'` then act as `deploy`: root-only paths
(`/root/...`, root's crontab, `/etc/ssh/sshd_config` is readable) are not readable; `docker ps`,
`systemctl status|list-timers`, `ss -lntup`, `cat` of world-readable files work. `sshd -T` needs
root: use `ai-news-root` until phase 4, afterwards read `/etc/ssh/sshd_config.d/*.conf` instead.

Failure: any failing run -> set `DEPLOY_USER` back to `root` and revert the PR (password still valid).

## Phase 4 - close password and root login

Only after phase 3 is green, with session R still open.

```bash
# in session R
cat > /etc/ssh/sshd_config.d/10-hardening.conf <<'CONF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
CONF
sshd -t && systemctl reload ssh
sshd -T | grep -iE '^(passwordauthentication|permitrootlogin|kbdinteractiveauthentication)'
```

`sshd` uses the first value it reads and `Include /etc/ssh/sshd_config.d/*.conf` is at the top of
`sshd_config`; `10-hardening.conf` sorts before `50-cloud-init.conf` (`PasswordAuthentication yes`),
so it wins. Check: the three lines read `no`.

Test from a second terminal **before** closing session R:

```bash
ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password deploy@$HOST true   # must fail
ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password root@$HOST true     # must fail
ssh -i ~/.ssh/ai_news_prod_ed25519 -o IdentitiesOnly=yes root@$HOST true                # must fail: root off
ssh ai-news 'echo deploy-key-ok'                                                        # must work
gh workflow run nightly-health.yml -R $REPO                                              # must be green
```

Then remove the password secret:

```bash
gh secret delete SERVER_PASSWORD -R $REPO
```

Rollback (session R or the time4vps console):
`rm /etc/ssh/sshd_config.d/10-hardening.conf && sshd -t && systemctl reload ssh`.
Follow-up for the owner: change the root password in the time4vps panel (it was a CI secret),
drop the `ai-news-root` alias.

## Phase 5 - fail2ban (sshd jail)

`deploy` has no sudo for apt: do it in session R, before phase 4, or via the console.

```bash
apt-get update && apt-get install -y fail2ban
systemctl enable --now fail2ban
fail2ban-client status sshd
```

Debian/Ubuntu ship the `sshd` jail enabled (`jail.d/defaults-debian.conf`); defaults are fine
(5 failures in 10 min, 10 min ban). Check: `Status for the jail: sshd`; `Currently banned` grows
within hours (about 5 failed logins per hour are seen today). Key logins of CI do not fail, so
runner IPs are not at risk. Rollback: `systemctl disable --now fail2ban; fail2ban-client unban --all`.

## Phase 6 - firewall: rule list only, NOT applied

Listening ports found on 2026-10-24 (`ss -lntup`, `docker ps`):

| Port | Proto | Owner | Public |
| --- | --- | --- | --- |
| 22 | tcp | sshd (ssh.socket) | yes |
| 80 | tcp | `ai-news-caddy` (docker-proxy) | yes |
| 443 | tcp | `ai-news-caddy` | yes |
| 33488 | udp | `amnezia-awg2` (docker-proxy) | yes |
| 33218 | udp | `amnezia-wireguard` (docker-proxy) | yes |
| 53 | tcp/udp | systemd-resolved on 127.0.0.53 / 127.0.0.54 | no |
| 40179 | tcp | containerd on 127.0.0.1 | no |

`ai-news-app` (8010) and `ai-news-db` (5432) are not published to the host. 443/udp (HTTP/3) is
not published.

Proposed rules (ufw), for review and a separate later step:

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 33488/udp
ufw allow 33218/udp
# do not touch DEFAULT_FORWARD_POLICY or before.rules: the VPN containers forward client traffic
```

Cautions: Docker publishes ports through its own iptables chains (`DOCKER`, `FORWARD`), which ufw
`INPUT` rules do not govern, and a ufw forward policy can break VPN forwarding. Before applying,
read `iptables -S` and `iptables -t nat -S`, keep session R open, run a timed rollback
(`( sleep 300; ufw disable ) &`) while testing, and have the owner test the VPN from a phone.

## Remote commands

The table of every remote command, with the file, the need for root and how it is covered, is in
the PR description. Summary: all commands of the four workflows and of `scripts/deploy_prod.sh`,
`db_maintenance.sh`, `db_backup.sh` run as `deploy` (docker group or file ownership); only the
`ai-news-daily-*` unit install and the `systemctl` calls use sudo (the sudoers file above).
