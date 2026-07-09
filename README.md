# dtool

A modular DevOps toolkit with both a **CLI** and a **web dashboard**, sharing the same core logic. Built incrementally, module by module, as I work through hands-on AWS, Kubernetes, and Terraform training.

## Why this exists

Most personal DevOps projects are one-off scripts. `dtool` is designed the opposite way: every capability (monitoring, backups, infra checks, CI/CD helpers) is added as an independent module, but each module works from **both** a terminal menu and a browser, without duplicating logic. The goal is a single toolkit that grows alongside real learning, and reflects how tools are actually built in production: separated business logic, a thin CLI layer, and a thin web layer.

## Architecture

```
dtool/
├── main.py                  # CLI entry point / menu router
├── config.py                # SMTP, DB path, timeouts, etc.
├── requirements.txt
├── modules/
│   └── monitoring/
│       ├── core.py          # pure logic: SQLite CRUD + all checks (no I/O with the user)
│       └── cli.py           # terminal menu, calls core.py
└── webapp/
    ├── app.py                # Flask app, imports modules.<name>.core directly
    ├── templates/
    └── static/style.css
```

Every future module (AWS EC2, Docker tools, backups, security scanning, git/CI-CD helpers) follows the same `core.py` / `cli.py` split, plus a route in `webapp/app.py`. The web dashboard and the CLI are two views onto the same data and the same checks — never two copies of the same logic.

## Current modules

### Monitoring
A generic "target" system for anything a DevOps engineer checks day to day:

| Check type | What it verifies |
|---|---|
| `ping` | Host is reachable |
| `port` | TCP port is open |
| `http_status` | HTTP/HTTPS endpoint returns the expected status code |
| `ssl_expiry` | Days remaining before a TLS certificate expires |
| `systemd_service` | A systemd service is active |
| `docker_container` | A Docker container is running |
| `process_running` | A named process is running |
| `disk_space` | Disk usage is below a configured threshold |

Targets are stored in SQLite (`category`, `check_type`, `address`, `params` as JSON), so adding a new check type only means adding one function and one registry entry — nothing else changes.

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
