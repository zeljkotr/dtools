"""
config.py - Centralna konfiguracija za dtool

VAŽNO: Ovaj fajl ne sme da sadrži prave lozinke/tokene u produkciji.
Za sada koristi environment varijable (export u shell-u ili .env fajl).
Kasnije možemo dodati python-dotenv da automatski učitava .env.

# dtool — devops swiss army knife · by Zeljko Tripcevski
"""

import os

# --- Baza podataka ---
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "multitool.db")

# --- SMTP / Email alerti (reuse iz tvog ping monitor projekta) ---
SMTP_SERVER = os.environ.get("DTOOL_SMTP_SERVER", "smtp.mts.rs")
SMTP_PORT = int(os.environ.get("DTOOL_SMTP_PORT", 587))
SMTP_USER = os.environ.get("DTOOL_SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("DTOOL_SMTP_PASSWORD", "")
ALERT_EMAIL_TO = os.environ.get("DTOOL_ALERT_EMAIL", "")

# --- Agent push autentifikacija ---
# Agenti (modules/monitoring/agent.py) salju ovaj token u svakom heartbeat-u
# da server zna da je push legitiman. Promeni u produkciji (env varijabla)!
AGENT_TOKEN = os.environ.get("DTOOL_AGENT_TOKEN", "change-me")

# --- Opšta podešavanja ---
DEFAULT_CHECK_INTERVAL_SEC = 60
PING_TIMEOUT_SEC = 2
HTTP_TIMEOUT_SEC = 5
