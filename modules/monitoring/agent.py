#!/usr/bin/env python3
"""
modules/monitoring/agent.py

# dtool — devops swiss army knife · by Zeljko Tripcevski

STANDALONE agent skript - namerno je jedan samostalan fajl bez zavisnosti
od ostatka dtool projekta, jer se on KOPIRA na svaki server koji nadziremo,
odvojeno od centralnog dtool servera.

Sta radi:
    1. Lokalno proverava ono sto mu kazes (systemd servis, docker container,
       proces, disk prostor) - iskljucivo lokalnim komandama, bez mreze.
    2. POSTuje rezultat ka centralnom dtool serveru (webapp/app.py) na
       endpoint /api/heartbeat - JEDNA outbound HTTPS konekcija.

Zasto ovako (a ne da centralni server dodje i pita servera):
    Server koji se nadzire NE MORA da ima nijedan otvoren inbound port.
    On sam "javlja se" napolje, kao sto to rade Datadog agent, AWS SSM
    Agent, Wazuh agent i slicni alati u produkciji 2026. godine.

Deployment (preporuceno - systemd timer, ne beskonacna petlja):
    1. Kopiraj ovaj fajl na server: /opt/dtool-agent/agent.py
    2. Podesi promenljive ispod (DTOOL_SERVER_URL, TARGET_NAME, AGENT_TOKEN)
       ili ih izvezi kao environment varijable.
    3. Napravi systemd service + timer da se pokrece npr. na svakih 60s:

    /etc/systemd/system/dtool-agent.service:
        [Unit]
        Description=dtool monitoring agent (single-shot heartbeat)

        [Service]
        Type=oneshot
        ExecStart=/usr/bin/python3 /opt/dtool-agent/agent.py

    /etc/systemd/system/dtool-agent.timer:
        [Unit]
        Description=Run dtool-agent every 60 seconds

        [Timer]
        OnBootSec=15
        OnUnitActiveSec=60

        [Install]
        WantedBy=timers.target

    sudo systemctl enable --now dtool-agent.timer

    Alternativa (jednostavnije, ali manje elegantno): crontab
        * * * * * /usr/bin/python3 /opt/dtool-agent/agent.py
"""

import subprocess
import sys
import os
import json
import urllib.request
import urllib.error

# ----------------------------------------------------------------------
# KONFIGURACIJA - izmeni ovo za svaki server gde postavljas agenta
# (ili postavi kao environment varijable, isti nazivi)
# ----------------------------------------------------------------------
DTOOL_SERVER_URL = os.environ.get("DTOOL_SERVER_URL", "https://dtool.example.com")
TARGET_NAME = os.environ.get("DTOOL_TARGET_NAME", "prod-web-01")
AGENT_TOKEN = os.environ.get("DTOOL_AGENT_TOKEN", "change-me")

# Sta ovaj konkretan agent lokalno proverava - prilagodi listu po serveru
SYSTEMD_SERVICES_TO_CHECK = ["nginx"]            # npr. ["nginx", "docker"]
DOCKER_CONTAINERS_TO_CHECK = []                  # npr. ["my-app-container"]
PROCESSES_TO_CHECK = []                          # npr. ["python3 app.py"]
DISK_PATHS_TO_CHECK = [("/", 90)]                # (putanja, prag_procenat)

REQUEST_TIMEOUT_SEC = 5


# ----------------------------------------------------------------------
# Lokalne provere (identicna logika kao core.py, ali potpuno samostalno -
# ovaj fajl namerno ne importuje nista iz ostatka projekta)
# ----------------------------------------------------------------------
def check_systemd_service(service_name):
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5
        )
        status_out = result.stdout.strip()
        if status_out == "active":
            return True, f"{service_name}: aktivan"
        return False, f"{service_name}: {status_out or 'nepoznato'}"
    except Exception as e:
        return False, f"{service_name}: greska ({e})"


def check_docker_container(container_name):
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", container_name],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5
        )
        if result.returncode != 0:
            return False, f"{container_name}: ne postoji"
        status_out = result.stdout.strip()
        if status_out == "running":
            return True, f"{container_name}: running"
        return False, f"{container_name}: {status_out}"
    except Exception as e:
        return False, f"{container_name}: greska ({e})"


def check_process_running(process_name):
    try:
        result = subprocess.run(
            ["pgrep", "-f", process_name], stdout=subprocess.PIPE, text=True, timeout=5
        )
        if result.returncode == 0:
            return True, f"{process_name}: radi"
        return False, f"{process_name}: nije pronadjen"
    except Exception as e:
        return False, f"{process_name}: greska ({e})"


def check_disk_space(path, threshold_percent):
    try:
        import shutil
        total, used, free = shutil.disk_usage(path)
        used_percent = (used / total) * 100
        if used_percent >= threshold_percent:
            return False, f"{path}: {used_percent:.1f}% (prag {threshold_percent}%)"
        return True, f"{path}: {used_percent:.1f}%"
    except Exception as e:
        return False, f"{path}: greska ({e})"


def run_local_checks():
    """Vraca (overall_status, message) - 'fail' ako bilo koja provera padne."""
    lines = []
    overall_ok = True

    for svc in SYSTEMD_SERVICES_TO_CHECK:
        ok, msg = check_systemd_service(svc)
        overall_ok = overall_ok and ok
        lines.append(msg)

    for container in DOCKER_CONTAINERS_TO_CHECK:
        ok, msg = check_docker_container(container)
        overall_ok = overall_ok and ok
        lines.append(msg)

    for proc in PROCESSES_TO_CHECK:
        ok, msg = check_process_running(proc)
        overall_ok = overall_ok and ok
        lines.append(msg)

    for path, threshold in DISK_PATHS_TO_CHECK:
        ok, msg = check_disk_space(path, threshold)
        overall_ok = overall_ok and ok
        lines.append(msg)

    if not lines:
        lines.append("Nema podesenih lokalnih provera - agent samo javlja da je ziv")

    status = "ok" if overall_ok else "fail"
    message = "; ".join(lines)
    return status, message


def send_heartbeat(status, message):
    """Jedina mrezna aktivnost agenta - OUTBOUND POST ka centralnom serveru."""
    url = DTOOL_SERVER_URL.rstrip("/") + "/api/heartbeat"
    payload = json.dumps({
        "token": AGENT_TOKEN,
        "target": TARGET_NAME,
        "status": status,
        "message": message,
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.URLError as e:
        return None, f"Slanje heartbeat-a nije uspelo: {e}"


def main():
    status, message = run_local_checks()
    code, response_text = send_heartbeat(status, message)
    print(f"[dtool-agent] lokalni status={status} | server odgovor={code} {response_text}")
    sys.exit(0 if status == "ok" else 1)


if __name__ == "__main__":
    main()
