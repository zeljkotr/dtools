"""
modules/monitoring/core.py

Pure monitoring module logic - NO print/input calls here.
Used by both CLI (modules/monitoring/cli.py) and Web (webapp/app.py),
so check rules and database writes live ONLY here, in one place.

# dtool — devops swiss army knife · by Zeljko Tripcevski

--------------------------------------------------------------------
DESIGN: pull vs push, and why there is NO "port check"
--------------------------------------------------------------------
There is intentionally no generic "is this port open" check that would
have dtool actively probe a remote server. On modern zero-trust
infrastructure, servers you monitor should not have ANY open inbound
port for monitoring purposes - not SSH "just to check", not a custom
health-check port. That's attack surface opened for no good reason.

Instead of a pull model (dtool -> probes a port on the server), we use
a PUSH model: a small agent (modules/monitoring/agent.py) is installed
ON the server being monitored. It checks things locally (disk, systemd
service, docker container, process - all local checks, no network),
and itself POSTs the result to the central dtool server over HTTPS -
an outbound-only connection. The monitored server stays fully "closed"
from the outside.

The central dtool server still has one (1) open port for its own web
UI/API - that's the "control plane" and is expected/normal (same as
a Grafana/Prometheus server having its own port). The difference is
that NO monitored machine opens anything for the sake of this tool.

If an agent stops checking in (network down, service dead, machine
off), check_agent_heartbeat recognizes the "stale" state - this is the
"dead man's switch" pattern used by Healthchecks.io, Cronitor, and
Prometheus Pushgateway.

Ping and HTTP/SSL checks remain pull-based because they check
INTENTIONALLY public services (e.g. a public website MUST have port
443 open - that's its job), not administrative/internal servers you
own.

--------------------------------------------------------------------
CHECK HISTORY AND UPTIME % (check_history table)
--------------------------------------------------------------------
Besides the "latest" status (last_status/last_message columns on the
targets table), every check is now ALSO logged into a separate
check_history table. This makes it possible to calculate Uptime %
(SLI - Service Level Indicator) for any period, instead of only
knowing the current state. This is the foundation for SRE concepts
like SLO (Service Level Objective) - e.g. "our target is 99.5% uptime
over the last 30 days" - which you can now actually measure.
"""

import sqlite3
import json
import subprocess
import ssl
import socket
import shutil
import datetime
import os
import sys

try:
    import requests
except ImportError:
    requests = None

import config

CATEGORIES = {
    "1": "Network",
    "2": "Web/API",
    "3": "Services (OS)",
    "4": "Containers",
    "5": "Processes",
    "6": "Disk",
    "7": "Agent (push, no open ports)",
}

CATEGORY_CHECK_TYPES = {
    "1": [("ping", "Ping (ICMP - is the host alive)")],
    "2": [("http_status", "HTTP/HTTPS status code (for public services)"),
          ("ssl_expiry", "SSL certificate - days until expiry (for public services)")],
    "3": [("systemd_service", "systemd service status (local, on this server)")],
    "4": [("docker_container", "Docker container status (local, on this server)")],
    "5": [("process_running", "Whether a process is running (local, on this server)")],
    "6": [("disk_space", "Free disk space (local, on this server)")],
    "7": [("agent_heartbeat", "Agent heartbeat - server reports its own status (push, no open ports)")],
}

DEFAULT_STALE_AFTER_SEC = 180  # if the agent hasn't reported in this many seconds, the target is FAIL


# ----------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------
def _ensure_db():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            check_type TEXT NOT NULL,
            address TEXT,
            params TEXT,
            interval_sec INTEGER DEFAULT 60,
            enabled INTEGER DEFAULT 1,
            last_status TEXT DEFAULT 'unknown',
            last_message TEXT DEFAULT '',
            last_checked TEXT DEFAULT '',
            last_push_at TEXT DEFAULT '',
            last_push_status TEXT DEFAULT '',
            last_push_message TEXT DEFAULT ''
        )
    """)
    # Migration for databases created before the push columns existed (ignore if they already exist)
    for col_def in [
        "ALTER TABLE targets ADD COLUMN last_push_at TEXT DEFAULT ''",
        "ALTER TABLE targets ADD COLUMN last_push_status TEXT DEFAULT ''",
        "ALTER TABLE targets ADD COLUMN last_push_message TEXT DEFAULT ''",
    ]:
        try:
            conn.execute(col_def)
        except sqlite3.OperationalError:
            pass  # column already exists

    # Check history - for Uptime % calculation (SLI/SLO)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS check_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            checked_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_history_target ON check_history(target_id, checked_at)")

    conn.commit()
    return conn


def _get_conn():
    return _ensure_db()


# ----------------------------------------------------------------------
# Check functions (PULL) - each returns (status, message), status is "ok"/"fail"
# Used for: ping/http/ssl (public services) and systemd/docker/process/disk
# (checks that dtool runs LOCALLY, on the same machine dtool runs on).
# ----------------------------------------------------------------------
def check_ping(address, params):
    try:
        count_flag = "-n" if sys.platform.startswith("win") else "-c"
        timeout_flag = "-w" if sys.platform.startswith("win") else "-W"
        timeout_val = str(int(config.PING_TIMEOUT_SEC * (1000 if sys.platform.startswith("win") else 1)))
        result = subprocess.run(
            ["ping", count_flag, "1", timeout_flag, timeout_val, address],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=config.PING_TIMEOUT_SEC + 2
        )
        if result.returncode == 0:
            return "ok", "Host is responding"
        return "fail", "Host is not responding"
    except Exception as e:
        return "fail", f"Error: {e}"


def check_http_status(address, params):
    if requests is None:
        return "fail", "The 'requests' module is not installed (pip install requests)"
    expected = params.get("expected_status", 200)
    try:
        resp = requests.get(address, timeout=config.HTTP_TIMEOUT_SEC)
        if resp.status_code == expected:
            return "ok", f"HTTP {resp.status_code} (expected {expected})"
        return "fail", f"HTTP {resp.status_code} (expected {expected})"
    except Exception as e:
        return "fail", f"Error: {e}"


def check_ssl_expiry(address, params):
    warn_days = params.get("warn_days", 14)
    host = address.replace("https://", "").replace("http://", "").split("/")[0]
    port = params.get("port", 443)
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, int(port)), timeout=config.HTTP_TIMEOUT_SEC) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
        expire_str = cert["notAfter"]
        expire_date = datetime.datetime.strptime(expire_str, "%b %d %H:%M:%S %Y %Z")
        days_left = (expire_date - datetime.datetime.utcnow()).days
        if days_left <= warn_days:
            return "fail", f"Certificate expires in {days_left} days"
        return "ok", f"Certificate valid for {days_left} more days"
    except Exception as e:
        return "fail", f"Error: {e}"


def check_systemd_service(address, params):
    service_name = params.get("service_name")
    if not service_name:
        return "fail", "service_name is not set in params"
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5
        )
        status_out = result.stdout.strip()
        if status_out == "active":
            return "ok", "Service is active"
        return "fail", f"Service status: {status_out or 'unknown'}"
    except FileNotFoundError:
        return "fail", "systemctl is not available (not Linux, or not in PATH)"
    except Exception as e:
        return "fail", f"Error: {e}"


def check_docker_container(address, params):
    container_name = params.get("container_name", address)
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", container_name],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5
        )
        if result.returncode != 0:
            return "fail", "Container does not exist or docker is not available"
        status_out = result.stdout.strip()
        if status_out == "running":
            return "ok", "Container running"
        return "fail", f"Container status: {status_out}"
    except FileNotFoundError:
        return "fail", "docker CLI is not installed/available"
    except Exception as e:
        return "fail", f"Error: {e}"


def check_process_running(address, params):
    process_name = params.get("process_name", address)
    try:
        if sys.platform.startswith("win"):
            result = subprocess.run(
                ["tasklist"], stdout=subprocess.PIPE, text=True, timeout=5
            )
            found = process_name.lower() in result.stdout.lower()
        else:
            result = subprocess.run(
                ["pgrep", "-f", process_name], stdout=subprocess.PIPE, text=True, timeout=5
            )
            found = result.returncode == 0
        if found:
            return "ok", "Process is running"
        return "fail", "Process not found"
    except Exception as e:
        return "fail", f"Error: {e}"


def check_disk_space(address, params):
    path = address or "/"
    threshold_percent = params.get("threshold_percent", 90)
    try:
        total, used, free = shutil.disk_usage(path)
        used_percent = (used / total) * 100
        if used_percent >= threshold_percent:
            return "fail", f"Usage {used_percent:.1f}% (threshold {threshold_percent}%)"
        return "ok", f"Usage {used_percent:.1f}% (threshold {threshold_percent}%)"
    except Exception as e:
        return "fail", f"Error: {e}"


CHECK_REGISTRY = {
    "ping": check_ping,
    "http_status": check_http_status,
    "ssl_expiry": check_ssl_expiry,
    "systemd_service": check_systemd_service,
    "docker_container": check_docker_container,
    "process_running": check_process_running,
    "disk_space": check_disk_space,
}


def _check_agent_heartbeat(target_row):
    """
    PUSH check - does not touch the network. Only reads when the agent
    last reported a status (last_push_at) and whether that status is
    still "fresh". This is a "dead man's switch": if the agent stays
    silent longer than stale_after_sec, we consider the server/service
    down (or the network/agent is dead) - which is exactly what we want
    to know, without a single open port on the server.
    """
    params = json.loads(target_row["params"] or "{}")
    stale_after = params.get("stale_after_sec", DEFAULT_STALE_AFTER_SEC)

    last_push_at = target_row["last_push_at"]
    if not last_push_at:
        return "fail", "Agent has not checked in yet (no push received)"

    last_push_dt = datetime.datetime.strptime(last_push_at, "%Y-%m-%d %H:%M:%S")
    elapsed = (datetime.datetime.now() - last_push_dt).total_seconds()

    reported_status = target_row["last_push_status"] or "unknown"
    reported_message = target_row["last_push_message"] or ""

    if elapsed > stale_after:
        return "fail", f"Agent hasn't checked in for {int(elapsed)}s (threshold {stale_after}s) - last report: {reported_message}"

    if reported_status == "fail":
        return "fail", f"Agent reports a problem: {reported_message}"

    return "ok", f"Last check-in {int(elapsed)}s ago: {reported_message}"


def run_check(target_row):
    """target_row is a sqlite3.Row or dict with the same keys"""
    check_type = target_row["check_type"]

    if check_type == "agent_heartbeat":
        return _check_agent_heartbeat(target_row)

    address = target_row["address"]
    params = json.loads(target_row["params"] or "{}")
    func = CHECK_REGISTRY.get(check_type)
    if not func:
        return "fail", f"Unknown check_type: {check_type}"
    return func(address, params)


# ----------------------------------------------------------------------
# CRUD operations
# ----------------------------------------------------------------------
def add_target(name, category, check_type, address, params, interval_sec=60):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO targets (name, category, check_type, address, params, interval_sec) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, category, check_type, address, json.dumps(params), interval_sec)
    )
    conn.commit()
    conn.close()


def list_targets():
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM targets ORDER BY id").fetchall()
    conn.close()
    return rows


def get_target(target_id):
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM targets WHERE id = ?", (target_id,)).fetchone()
    conn.close()
    return row


def get_target_by_name(name):
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM targets WHERE name = ? AND check_type = 'agent_heartbeat'", (name,)
    ).fetchone()
    conn.close()
    return row


def delete_target(target_id):
    conn = _get_conn()
    conn.execute("DELETE FROM targets WHERE id = ?", (target_id,))
    conn.execute("DELETE FROM check_history WHERE target_id = ?", (target_id,))
    conn.commit()
    conn.close()


def update_target(target_id, name, address, params, interval_sec):
    """
    Edits an existing target - name, address, params, and interval change.
    Category and check_type stay THE SAME (on purpose) - to change the
    check type, delete the target and add a new one, since a different
    type would need completely different params.
    """
    conn = _get_conn()
    conn.execute(
        "UPDATE targets SET name = ?, address = ?, params = ?, interval_sec = ? WHERE id = ?",
        (name, address, json.dumps(params), interval_sec, target_id)
    )
    conn.commit()
    conn.close()


def update_target_status(target_id, status, message):
    conn = _get_conn()
    conn.execute(
        "UPDATE targets SET last_status = ?, last_message = ?, last_checked = ? WHERE id = ?",
        (status, message, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), target_id)
    )
    conn.commit()
    conn.close()


def _record_history(target_id, status, message):
    """Logs EVERY check result - the foundation for Uptime % calculation."""
    conn = _get_conn()
    conn.execute(
        "INSERT INTO check_history (target_id, status, message, checked_at) VALUES (?, ?, ?, ?)",
        (target_id, status, message, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()


def get_history(target_id, limit=50):
    """Last N checks for this target, newest first."""
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM check_history WHERE target_id = ? ORDER BY checked_at DESC LIMIT ?",
        (target_id, limit)
    ).fetchall()
    conn.close()
    return rows


def get_uptime_percent(target_id, days=7):
    """
    Calculates the % of checks with status 'ok' over the last N days.
    Returns None if there's no data for that period (target just added,
    or the dashboard hasn't been loaded since the target was added).
    """
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute(
        "SELECT status FROM check_history WHERE target_id = ? AND checked_at >= ?",
        (target_id, cutoff)
    ).fetchall()
    conn.close()

    if not rows:
        return None

    ok_count = sum(1 for r in rows if r["status"] == "ok")
    return round((ok_count / len(rows)) * 100, 1)


def prune_history(keep_days=90):
    """
    Optional cleanup so the history table doesn't grow forever. Not
    called automatically - can be called manually or hooked up to a
    systemd timer/cron job later if needed.
    """
    conn = _get_conn()
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=keep_days)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("DELETE FROM check_history WHERE checked_at < ?", (cutoff,))
    conn.commit()
    conn.close()


def record_push(target_name, status, message):
    """
    Called from webapp/app.py when an agent (modules/monitoring/agent.py)
    sends its heartbeat to /api/heartbeat. Only stores that something
    arrived and what the agent measured locally - no network check
    happens here, the dtool server never "reaches out" to the agent.
    Returns True if the target was found and updated, False otherwise.
    """
    target = get_target_by_name(target_name)
    if not target:
        return False
    conn = _get_conn()
    conn.execute(
        "UPDATE targets SET last_push_at = ?, last_push_status = ?, last_push_message = ? WHERE id = ?",
        (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status, message, target["id"])
    )
    conn.commit()
    conn.close()
    _record_history(target["id"], status, message)
    return True


def _send_transition_alert(target_name, previous_status, new_status, message):
    """
    Fires a notification through modules/alerting/core.py when a target's
    status genuinely changes (ok -> fail, or fail -> ok). Never raises -
    a broken alert channel should never break the monitoring check itself.
    Imported locally so monitoring keeps working even if the alerting
    module (or its 'requests' dependency) has a problem.
    """
    try:
        from modules.alerting import core as alerting_core
    except ImportError:
        return

    if new_status == "fail":
        subject = f"dtool ALERT: {target_name} is DOWN"
        body = f"Target '{target_name}' changed from '{previous_status}' to 'fail'.\n\nMessage: {message}"
    else:
        subject = f"dtool RECOVERY: {target_name} is back UP"
        body = f"Target '{target_name}' changed from '{previous_status}' to 'ok'.\n\nMessage: {message}"

    try:
        results = alerting_core.notify_all(subject, body)
        print(f"[ALERT DEBUG] {results}")
    except Exception as e:
        print(f"[ALERT DEBUG] Exception: {e}")


def check_all_targets():
    """
    Runs the check for every target, updates the database (status + history),
    fires an alert on genuine status transitions, and returns a list of results.
    """
    results = []
    for t in list_targets():
        previous_status = t["last_status"]
        status, message = run_check(t)
        update_target_status(t["id"], status, message)
        _record_history(t["id"], status, message)

        if previous_status not in ("unknown", status):
            _send_transition_alert(t["name"], previous_status, status, message)

        results.append({
            "id": t["id"],
            "name": t["name"],
            "category": t["category"],
            "check_type": t["check_type"],
            "address": t["address"],
            "status": status,
            "message": message,
        })
    return results