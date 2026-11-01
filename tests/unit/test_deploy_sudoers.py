import re
from pathlib import Path

SAMPLE = Path("deploy/sudoers.d/ai-news-deploy")
# Lines with "sudo" that are not a call: the SUDO assignments of both scripts.
NOT_A_CALL = (r'\s*SUDO=""', r'\s*SUDO="sudo -n"', r"\s*#.*")


def _sample_commands():
    text = SAMPLE.read_text(encoding="utf-8").replace("\\\n", " ")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    aliases = {}
    allowed = []
    assert any(ln.startswith("deploy ALL=") for ln in lines), "no `deploy ALL=` line parsed"
    for ln in lines:
        alias = re.match(r"Cmnd_Alias\s+(\w+)\s*=\s*(.*)", ln)
        if alias:
            aliases[alias[1]] = [c.strip() for c in alias[2].split(",")]
        elif ln.startswith("deploy ALL="):
            allowed += [a.strip() for a in ln.split("NOPASSWD:", 1)[1].split(",")]
    assert allowed, "`deploy ALL=` line has no NOPASSWD: list"
    unknown = [name for name in allowed if name not in aliases]
    assert not unknown, f"alias used but not defined (dropped trailing backslash?): {unknown}"
    return {cmd for name in allowed for cmd in aliases[name]}


def _assert_no_unparsed_sudo(name, text):
    for line in text.splitlines():
        if "sudo" not in line.lower() or re.match(r"\s*\$SUDO ", line):
            continue
        assert any(re.fullmatch(p, line) for p in NOT_A_CALL), f"{name}: unparsed sudo line: {line}"


def _script_commands():
    install = Path("scripts/install_daily_timers.sh").read_text(encoding="utf-8")
    deploy = Path("scripts/deploy_prod.sh").read_text(encoding="utf-8")
    stage_dir = re.search(r"^\s+STAGE_DIR=(/\S+)$", install, re.M)[1]
    final_dir = re.search(r'^UNIT_DIR="\$\{AINEWS_SYSTEMD_UNIT_DIR:-(/[^}]+)\}"$', install, re.M)[1]
    jobs = re.search(r"^for job in ([\w ]+); do$", install, re.M)[1].split()
    units = set()
    for name in re.findall(r'"\$UNIT_DIR/(ai-news-[\w${}-]+\.(?:service|timer))"', install):
        units |= {name.replace("${job}", job) for job in jobs} if "${job}" in name else {name}
    commands = set()
    for name, text in (("install_daily_timers.sh", install), ("deploy_prod.sh", deploy)):
        _assert_no_unparsed_sudo(name, text)
        for call in re.findall(r"^\s*\$SUDO (.+)$", text, re.M):
            if call.startswith("install "):
                assert call == 'install -m 0644 "$unit" "$FINAL_DIR/$(basename "$unit")"'
                commands |= {f"/usr/bin/install -m 0644 {stage_dir}/{u} {final_dir}/{u}"
                             for u in units}
            else:
                commands.add(f"/usr/bin/{call}")
    return commands


def test_sudoers_sample_matches_the_sudo_calls_of_the_scripts():
    sample = _sample_commands()
    calls = _script_commands()
    assert calls - sample == set(), "script sudo call missing from the sample"
    assert sample - calls == set(), "stale sample line no script makes"
