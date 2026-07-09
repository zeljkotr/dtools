"""
modules/monitoring/core.py

Cista logika monitoring modula - BEZ print/input poziva.
Ovo koriste i CLI (modules/monitoring/cli.py) i Web (webapp/app.py),
tako da se pravila provere i baza pisu SAMO OVDE, na jednom mestu.
"""

import sqlite3
import json
import socket
import subprocess
import ssl
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
    "1": "Mreza",
    "2": "Web/API",
    "3": "Servisi (OS)",
    "4": "Kontejneri",
    "5": "Procesi",
    "6": "Disk",
}

CATEGORY_CHECK_TYPES = {
    "1": [("ping", "Ping (da li je host ziv)"),
          ("port", "Port open/closed check")],
    "2": [("http_status", "HTTP/HTTPS status kod"),
          ("ssl_expiry", "SSL sertifikat - dana do isteka")],
    "3": [("systemd_service", "systemd servis status (Linux)")],
    "4": [("docker_container", "Docker container status")],
    "5": [("process_running", "Da li proces radi (lokalno)")],
    "6": [("disk_space", "Slobodan disk prostor (prag u %)")],
}


# ----------------------------------------------------------------------
# Baza podataka
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
            last_checked TEXT DEFAULT ''
        )
    """)
    conn.commit()
    return conn


def _get_conn():
    return _ensure_db()


# ----------------------------------------------------------------------
# Check funkcije - svaka vraca (status, message) gde je status "ok"/"fail"
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
            return "ok", "Host odgovara"
        return "fail", "Host ne odgovara"
    except Exception as e:
        return "fail", f"Greska: {e}"


def check_port(address, params):
    port = params.get("port")
    if not port:
        return "fail", "Nije podesen port u params"
    try:
        with socket.create_connection((address, int(port)), timeout=config.PING_TIMEOUT_SEC):
            return "ok", f"Port {port} otvoren"
    except Exception as e:
        return "fail", f"Port {port} zatvoren/nedostupan ({e})"


def check_http_status(address, params):
    if requests is None:
        return "fail", "Modul 'requests' nije instaliran (pip install requests)"
    expected = params.get("expected_status", 200)
    try:
        resp = requests.get(address, timeout=config.HTTP_TIMEOUT_SEC)
        if resp.status_code == expected:
            return "ok", f"HTTP {resp.status_code} (ocekivano {expected})"
        return "fail", f"HTTP {resp.status_code} (ocekivano {expected})"
    except Exception as e:
        return "fail", f"Greska: {e}"


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
            return "fail", f"Sertifikat istice za {days_left} dana"
        return "ok", f"Sertifikat vazi jos {days_left} dana"
    except Exception as e:
        return "fail", f"Greska: {e}"


def check_systemd_service(address, params):
    service_name = params.get("service_name")
    if not service_name:
        return "fail", "Nije podesen service_name u params"
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5
        )
        status_out = result.stdout.strip()
        if status_out == "active":
            return "ok", "Servis aktivan"
        return "fail", f"Servis status: {status_out or 'nepoznato'}"
    except FileNotFoundError:
        return "fail", "systemctl nije dostupan (nije Linux ili nije u PATH-u)"
    except Exception as e:
        return "fail", f"Greska: {e}"


def check_docker_container(address, params):
    container_name = params.get("container_name", address)
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", container_name],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5
        )
        if result.returncode != 0:
            return "fail", "Container ne postoji ili docker nije dostupan"
        status_out = result.stdout.strip()
        if status_out == "running":
            return "ok", "Container running"
        return "fail", f"Container status: {status_out}"
    except FileNotFoundError:
        return "fail", "docker CLI nije instaliran/dostupan"
    except Exception as e:
        return "fail", f"Greska: {e}"


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
            return "ok", "Proces radi"
        return "fail", "Proces nije pronadjen"
    except Exception as e:
        return "fail", f"Greska: {e}"


def check_disk_space(address, params):
    path = address or "/"
    threshold_percent = params.get("threshold_percent", 90)
    try:
        total, used, free = shutil.disk_usage(path)
        used_percent = (used / total) * 100
        if used_percent >= threshold_percent:
            return "fail", f"Iskoriscenost {used_percent:.1f}% (prag {threshold_percent}%)"
        return "ok", f"Iskoriscenost {used_percent:.1f}% (prag {threshold_percent}%)"
    except Exception as e:
        return "fail", f"Greska: {e}"


CHECK_REGISTRY = {
    "ping": check_ping,
    "port": check_port,
    "http_status": check_http_status,
    "ssl_expiry": check_ssl_expiry,
    "systemd_service": check_systemd_service,
    "docker_container": check_docker_container,
    "process_running": check_process_running,
    "disk_space": check_disk_space,
}


def run_check(target_row):
    """target_row je sqlite3.Row ili dict sa istim kljucevima"""
    check_type = target_row["check_type"]
    address = target_row["address"]
    params = json.loads(target_row["params"] or "{}")
    func = CHECK_REGISTRY.get(check_type)
    if not func:
        return "fail", f"Nepoznat check_type: {check_type}"
    return func(address, params)


# ----------------------------------------------------------------------
# CRUD operacije
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


def delete_target(target_id):
    conn = _get_conn()
    conn.execute("DELETE FROM targets WHERE id = ?", (target_id,))
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


def check_all_targets():
    """Pokrece proveru za sve targete, azurira bazu, vraca listu rezultata."""
    results = []
    for t in list_targets():
        status, message = run_check(t)
        update_target_status(t["id"], status, message)
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
