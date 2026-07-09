"""
modules/monitoring/core.py

Cista logika monitoring modula - BEZ print/input poziva.
Ovo koriste i CLI (modules/monitoring/cli.py) i Web (webapp/app.py),
tako da se pravila provere i baza pisu SAMO OVDE, na jednom mestu.

# dtool — devops swiss army knife · by Zeljko Tripcevski

--------------------------------------------------------------------
DIZAJN: pull vs push, i zasto NEMA "port check"
--------------------------------------------------------------------
Namerno ne postoji generalni "da li je port otvoren" check koji bi dtool
aktivno gadjao ka udaljenom serveru. Na modernoj (zero-trust) infrastrukturi
serveri koje nadzires ne treba da imaju NIJEDAN otvoren inbound port zarad
monitoringa - ni SSH za "proveru", ni custom port za health check. To je
povrsina napada koja se ne otvara bez razloga.

Umesto pull modela (dtool -> gadja port na serveru), koristimo PUSH model:
malen agent (modules/monitoring/agent.py) se postavi NA server koji nadziremo,
tamo lokalno proveri sta treba (disk, systemd servis, docker container,
proces - sve to je vec lokalna provera, bez mreze), i sam POSTuje rezultat
ka centralnom dtool serveru preko HTTPS-a - iskljucivo OUTBOUND konekcija.
Server koji se nadzire ostaje potpuno "zatvoren" spolja.

Centralni dtool server i dalje ima jedan (1) otvoren port za sopstveni
web UI/API - to je "control plane" i to je ocekivano i uobicajeno (isto
kao sto Grafana/Prometheus server ima svoj port). Razlika je u tome sto
NIJEDNA monitorisana masina ne otvara nista zarad ovog alata.

Ako agent prestane da se javlja (mreza pukla, servis mrtav, masina ugasena),
check_agent_heartbeat prepoznaje "stale" stanje - to je "dead man's switch"
patern koji koriste Healthchecks.io, Cronitor, Prometheus Pushgateway.

Ping i HTTP/SSL provere ostaju kakve jesu jer proveravaju NAMERNO javne
servise (npr. javni web sajt MORA da ima port 443 otvoren - to mu je posao),
a ne administrativne/interne servere koje ti drzis.
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
    "1": "Mreza",
    "2": "Web/API",
    "3": "Servisi (OS)",
    "4": "Kontejneri",
    "5": "Procesi",
    "6": "Disk",
    "7": "Agent (push, bez otvorenih portova)",
}

CATEGORY_CHECK_TYPES = {
    "1": [("ping", "Ping (ICMP - da li je host ziv)")],
    "2": [("http_status", "HTTP/HTTPS status kod (za javne servise)"),
          ("ssl_expiry", "SSL sertifikat - dana do isteka (za javne servise)")],
    "3": [("systemd_service", "systemd servis status (lokalno, na ovom serveru)")],
    "4": [("docker_container", "Docker container status (lokalno, na ovom serveru)")],
    "5": [("process_running", "Da li proces radi (lokalno, na ovom serveru)")],
    "6": [("disk_space", "Slobodan disk prostor (lokalno, na ovom serveru)")],
    "7": [("agent_heartbeat", "Agent heartbeat - server sam javlja status (push, nema otvorenih portova)")],
}

DEFAULT_STALE_AFTER_SEC = 180  # ako agent ne javi status ovoliko sekundi, target je FAIL


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
            last_checked TEXT DEFAULT '',
            last_push_at TEXT DEFAULT '',
            last_push_status TEXT DEFAULT '',
            last_push_message TEXT DEFAULT ''
        )
    """)
    # Migracija za baze napravljene pre push kolona (ignorisi ako vec postoje)
    for col_def in [
        "ALTER TABLE targets ADD COLUMN last_push_at TEXT DEFAULT ''",
        "ALTER TABLE targets ADD COLUMN last_push_status TEXT DEFAULT ''",
        "ALTER TABLE targets ADD COLUMN last_push_message TEXT DEFAULT ''",
    ]:
        try:
            conn.execute(col_def)
        except sqlite3.OperationalError:
            pass  # kolona vec postoji
    conn.commit()
    return conn


def _get_conn():
    return _ensure_db()


# ----------------------------------------------------------------------
# Check funkcije (PULL) - svaka vraca (status, message), status je "ok"/"fail"
# Koriste se za: ping/http/ssl (javni servisi) i systemd/docker/proces/disk
# (provere koje dtool izvrsava LOKALNO, na istoj masini gde dtool radi).
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
    "http_status": check_http_status,
    "ssl_expiry": check_ssl_expiry,
    "systemd_service": check_systemd_service,
    "docker_container": check_docker_container,
    "process_running": check_process_running,
    "disk_space": check_disk_space,
}


def _check_agent_heartbeat(target_row):
    """
    PUSH provera - ne gadja mrezu. Cita samo kada je agent poslednji put
    javio status (last_push_at) i da li je taj status jos "svez".
    Ovo je "dead man's switch": ako agent cuti duze od stale_after_sec,
    smatramo da je server/servis pao (ili je mreza/agent mrtav) - sto je
    tacno ono sto zelimo da znamo, bez ijednog otvorenog porta na serveru.
    """
    params = json.loads(target_row["params"] or "{}")
    stale_after = params.get("stale_after_sec", DEFAULT_STALE_AFTER_SEC)

    last_push_at = target_row["last_push_at"]
    if not last_push_at:
        return "fail", "Agent se jos nije javio (nema push-a)"

    last_push_dt = datetime.datetime.strptime(last_push_at, "%Y-%m-%d %H:%M:%S")
    elapsed = (datetime.datetime.now() - last_push_dt).total_seconds()

    reported_status = target_row["last_push_status"] or "unknown"
    reported_message = target_row["last_push_message"] or ""

    if elapsed > stale_after:
        return "fail", f"Agent se nije javio {int(elapsed)}s (prag {stale_after}s) - poslednji izvestaj: {reported_message}"

    if reported_status == "fail":
        return "fail", f"Agent javlja problem: {reported_message}"

    return "ok", f"Poslednji javljanje pre {int(elapsed)}s: {reported_message}"


def run_check(target_row):
    """target_row je sqlite3.Row ili dict sa istim kljucevima"""
    check_type = target_row["check_type"]

    if check_type == "agent_heartbeat":
        return _check_agent_heartbeat(target_row)

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
    conn.commit()
    conn.close()


def update_target(target_id, name, address, params, interval_sec):
    """
    Izmena postojeceg targeta - menja se naziv, adresa, parametri i interval.
    Kategorija i check_type OSTAJU ISTI (namerno) - da bi se promenio tip
    provere, treba obrisati target i dodati novi, jer bi drugi tip trazio
    potpuno drugacije parametre.
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


def record_push(target_name, status, message):
    """
    Poziva se iz webapp/app.py kada agent (modules/monitoring/agent.py)
    posalje svoj heartbeat na /api/heartbeat. Cuva SAMO da je nesto stiglo
    i sta je agent lokalno izmerio - ne radi nikakvu mreznu proveru ovde,
    dtool server nikad ne "gadja" agenta.
    Vraca True ako je target pronadjen i azuriran, False ako ne postoji.
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
    return True


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
