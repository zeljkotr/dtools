"""
dtool — devops swiss army knife · by Zeljko Tripcevski
Module: scheduler
Purpose: Install/manage a systemd --user timer that runs monitoring
checks (and therefore alerting) on a schedule, independent of whether
anyone has the web dashboard open.

Uses systemd --user units (NOT /etc/systemd/system) - no root/sudo
required, since dtool runs as a regular user. Unit files are generated
dynamically (correct python interpreter + repo path baked in), not
copied from a static template, so install() works regardless of where
dtool is checked out or which venv it runs in.

Note: for the timer to keep running after you log out of SSH, the
user needs "lingering" enabled once:
    sudo loginctl enable-linger <username>
This is a one-time, one-line setup step outside dtool's control (it
requires sudo), mentioned here for completeness.
"""

import os
import subprocess
import sys

_DTOOL_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_USER_SYSTEMD_DIR = os.path.expanduser("~/.config/systemd/user")
_SERVICE_NAME = "dtool-checks.service"
_TIMER_NAME = "dtool-checks.timer"


class SchedulerError(Exception):
    pass


def _run(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise SchedulerError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def is_installed() -> bool:
    return os.path.exists(os.path.join(_USER_SYSTEMD_DIR, _TIMER_NAME))


def get_status() -> str:
    if not is_installed():
        return "not installed"
    try:
        return _run(["systemctl", "--user", "is-active", _TIMER_NAME])
    except SchedulerError as e:
        return f"error: {e}"


def get_next_run() -> str:
    if not is_installed():
        return "-"
    try:
        return _run(["systemctl", "--user", "list-timers", _TIMER_NAME, "--no-pager"])
    except SchedulerError:
        return "-"


def install(interval_sec: int = 60) -> None:
    """Add — writes the systemd user unit files and enables the timer."""
    os.makedirs(_USER_SYSTEMD_DIR, exist_ok=True)

    python_bin = sys.executable
    script_path = os.path.join(_DTOOL_ROOT, "scripts", "run_checks.py")

    service_content = f"""[Unit]
Description=dtool monitoring check cycle

[Service]
Type=oneshot
ExecStart={python_bin} {script_path}
WorkingDirectory={_DTOOL_ROOT}
"""

    timer_content = f"""[Unit]
Description=Run dtool monitoring checks every {interval_sec}s

[Timer]
OnBootSec=30
OnUnitActiveSec={interval_sec}
Persistent=true

[Install]
WantedBy=timers.target
"""

    with open(os.path.join(_USER_SYSTEMD_DIR, _SERVICE_NAME), "w") as f:
        f.write(service_content)
    with open(os.path.join(_USER_SYSTEMD_DIR, _TIMER_NAME), "w") as f:
        f.write(timer_content)

    try:
        _run(["systemctl", "--user", "daemon-reload"])
        _run(["systemctl", "--user", "enable", "--now", _TIMER_NAME])
    except SchedulerError as e:
        raise SchedulerError(f"Failed to enable timer: {e}")


def uninstall() -> None:
    """Delete — disables and removes the systemd user unit files."""
    try:
        _run(["systemctl", "--user", "disable", "--now", _TIMER_NAME])
    except SchedulerError:
        pass  # may already be disabled/not running

    for name in (_SERVICE_NAME, _TIMER_NAME):
        path = os.path.join(_USER_SYSTEMD_DIR, name)
        if os.path.exists(path):
            os.remove(path)

    try:
        _run(["systemctl", "--user", "daemon-reload"])
    except SchedulerError:
        pass


def update_interval(interval_sec: int) -> None:
    """Edit — reinstalls with a new interval (simplest reliable approach)."""
    install(interval_sec)