import re
from pathlib import Path

SAMPLE = Path("deploy/sudoers.d/ai-news-deploy")
STAGE_DIR = "/var/tmp/ai-news-units"  # install_daily_timers.sh sets it for a non-root user
FINAL_DIR = "/etc/systemd/system"  # default UNIT_DIR of install_daily_timers.sh


def _sample_commands():
    text = SAMPLE.read_text(encoding="utf-8").replace("\\\n", " ")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    aliases = {}
    allowed = []
    for ln in lines:
        alias = re.match(r"Cmnd_Alias\s+(\w+)\s*=\s*(.*)", ln)
        if alias:
            aliases[alias[1]] = [c.strip() for c in alias[2].split(",")]
        elif ln.startswith("deploy ALL="):
            allowed += [a.strip() for a in ln.split("NOPASSWD:", 1)[1].split(",")]
    return {cmd for name in allowed for cmd in aliases[name]}


def _script_commands():
    install = Path("scripts/install_daily_timers.sh").read_text(encoding="utf-8")
    deploy = Path("scripts/deploy_prod.sh").read_text(encoding="utf-8")
    jobs = re.search(r"^for job in ([\w ]+); do$", install, re.M)[1].split()
    units = set()
    for name in re.findall(r'"\$UNIT_DIR/(ai-news-[\w${}-]+\.(?:service|timer))"', install):
        units |= {name.replace("${job}", job) for job in jobs} if "${job}" in name else {name}
    commands = set()
    for text in (install, deploy):
        for call in re.findall(r"^\s*\$SUDO (.+)$", text, re.M):
            if call.startswith("install "):
                assert call == 'install -m 0644 "$unit" "$FINAL_DIR/$(basename "$unit")"'
                commands |= {f"/usr/bin/install -m 0644 {STAGE_DIR}/{u} {FINAL_DIR}/{u}"
                             for u in units}
            else:
                commands.add(f"/usr/bin/{call}")
    return commands


def test_sudoers_sample_matches_the_sudo_calls_of_the_scripts():
    sample = _sample_commands()
    calls = _script_commands()
    assert calls - sample == set(), "script sudo call missing from the sample"
    assert sample - calls == set(), "stale sample line no script makes"
