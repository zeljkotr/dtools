# dtool

*dtool — devops swiss army knife · by Zeljko Tripcevski*

A modular DevOps toolkit with both a **CLI** and a **web dashboard**, sharing the same core logic. Built incrementally, module by module, as I work through hands-on AWS, Kubernetes, and Terraform training.

## Why this exists

Most personal DevOps projects are one-off scripts. `dtool` is designed the opposite way: every capability (monitoring, backups, infra checks, CI/CD helpers) is added as an independent module, but each module works from **both** a terminal menu and a browser, without duplicating logic. The goal is a single toolkit that grows alongside real learning, and reflects how tools are actually built in production: separated business logic, a thin CLI layer, and a thin web layer.

## Architecture

```
dtool/
├── main.py                  # CLI entry point / menu router
├── config.py                # SMTP, DB path, timeouts, agent token, etc.
├── requirements.txt
├── modules/
│   └── monitoring/
│       ├── core.py          # pure logic: SQLite CRUD + all checks (no I/O with the user)
│       ├── cli.py           # terminal menu, calls core.py
│       └── agent.py         # standalone script deployed ON monitored servers (push heartbeats)
└── webapp/
    ├── app.py                # Flask app, imports modules.<name>.core directly, exposes /api/heartbeat
    ├── templates/
    └── static/style.css
```

Every future module (AWS EC2, Docker tools, backups, security scanning, git/CI-CD helpers) follows the same `core.py` / `cli.py` split, plus a route in `webapp/app.py`. The web dashboard and the CLI are two views onto the same data and the same checks — never two copies of the same logic.

## Current modules

### Monitoring
A generic "target" system for anything a DevOps engineer checks day to day — designed around a **zero-open-ports** principle: monitored instances never need an inbound port for this tool to work.

| Check type | What it verifies | Model |
|---|---|---|
| `ping` | Host is reachable (ICMP) | pull |
| `http_status` | A **public** HTTP/HTTPS endpoint returns the expected status code | pull |
| `ssl_expiry` | Days remaining before a TLS certificate expires (public endpoint) | pull |
| `systemd_service` | A systemd service is active — checked locally, on the same host dtool runs on | pull (local) |
| `docker_container` | A Docker container is running — checked locally | pull (local) |
| `process_running` | A named process is running — checked locally | pull (local) |
| `disk_space` | Disk usage is below a configured threshold — checked locally | pull (local) |
| `agent_heartbeat` | A remote server reports its own health via outbound HTTPS push | **push** |

**Why no generic port scan:** actively probing a port on a remote server means that server has to keep an inbound port open just so this tool can poll it — an unnecessary attack surface on modern, zero-trust infrastructure. Instead, remote servers run a small standalone agent (`modules/monitoring/agent.py`) that performs its checks locally and **pushes** the result to dtool's `/api/heartbeat` endpoint over an outbound-only HTTPS call — the same pattern used by tools like the AWS SSM Agent, Datadog Agent, or Wazuh. If an agent goes quiet longer than its configured threshold, dtool treats it as failing (a "dead man's switch", the same idea behind Healthchecks.io / Cronitor / Prometheus Pushgateway staleness detection).

Targets are stored in SQLite (`category`, `check_type`, `address`, `params` as JSON), so adding a new check type only means adding one function and one registry entry — nothing else changes.

Targets can be added, edited (name, address, thresholds, interval), and removed from both the CLI and the web dashboard. The check type itself is fixed once a target is created — changing it means deleting and re-adding, since different check types need entirely different parameters.

**Coming soon:** AWS EC2 management, Docker tools, backup manager, security scanner, git/CI-CD helpers.

## Setup

```bash
git clone https://github.com/zeljkotr/dtools.git
cd dtools
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

**CLI:**
```bash
python3 main.py
```

**Web dashboard:**
```bash
python3 webapp/app.py
```
Then open `http://localhost:5000` (or `http://<server-ip>:5000` if running remotely — the app binds to `0.0.0.0`).

The CLI also has a shortcut (option 7) to launch the web dashboard directly from the terminal menu.

### Deploying the monitoring agent on a remote server

1. Add a target in dtool with category **Agent (push)** / check type `agent_heartbeat`. Its name (e.g. `prod-web-01`) is what the agent must send back.
2. Copy `modules/monitoring/agent.py` to the remote server (e.g. `/opt/dtool-agent/agent.py`).
3. Set `DTOOL_SERVER_URL`, `DTOOL_TARGET_NAME`, and `DTOOL_AGENT_TOKEN` (env vars, or edit the constants at the top of the file), and adjust which local checks it should run (systemd services, Docker containers, processes, disk paths).
4. Run it on a schedule — a systemd timer (every 60s, `oneshot` service type) is preferred over a long-running loop; a crontab entry works just as well. Full unit file examples are in the docstring at the top of `agent.py`.

No inbound port is opened on the remote server at any point — the agent only makes outbound HTTPS calls to dtool's existing web port.

## Stack

Python 3, Flask, SQLite, vanilla JS (dynamic form fields), no frontend framework.

## Roadmap

- [ ] AWS EC2 management module (boto3 — start/stop/status, Elastic IP tracking)
- [ ] Docker tools module (container lifecycle, image cleanup)
- [ ] Backup manager module (rotation, email notifications)
- [ ] Security scanner module (security group / IAM audit)
- [ ] Git / CI-CD helper module
- [ ] Kubernetes checks (once past the K8s stage of the learning plan)
- [ ] Terraform helpers (once past the Terraform stage)

## Author

**Zeljko Tripcevski**
GitHub: [@zeljkotr](https://github.com/zeljkotr)
