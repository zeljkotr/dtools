"""
dtool — devops swiss army knife · by Zeljko Tripcevski
Module: alerting / core
Purpose: Send notifications through configured channels (email, Telegram)
when a monitored target changes status.

Zero-trust note: sending an alert is always an OUTBOUND connection
(SMTP submission, or an HTTPS call to the Telegram Bot API) - dtool
never opens an inbound port for this.
"""

import smtplib
from email.mime.text import MIMEText

try:
    import requests
except ImportError:
    requests = None

from modules.alerting import config as alert_config


class AlertingError(Exception):
    pass


def send_email(channel_config: dict, subject: str, body: str) -> None:
    smtp_server = channel_config["smtp_server"]
    smtp_port = int(channel_config.get("smtp_port", 587))
    smtp_user = channel_config["smtp_user"]
    smtp_password = channel_config["smtp_password"]
    from_addr = channel_config.get("from_addr") or smtp_user
    to_addr = channel_config["to_addr"]

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr

    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
    except Exception as e:
        raise AlertingError(f"Email send failed: {e}")


def send_telegram(channel_config: dict, message: str) -> None:
    if requests is None:
        raise AlertingError("The 'requests' module is not installed (pip install requests)")
    bot_token = channel_config["bot_token"]
    chat_id = channel_config["chat_id"]
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
        if resp.status_code != 200:
            raise AlertingError(f"Telegram API error: {resp.status_code} {resp.text}")
    except AlertingError:
        raise
    except Exception as e:
        raise AlertingError(f"Telegram send failed: {e}")


def send_to_channel(channel: dict, subject: str, message: str):
    """Returns (success: bool, error_message: str)."""
    try:
        if channel["type"] == "email":
            send_email(channel["config"], subject, message)
        elif channel["type"] == "telegram":
            send_telegram(channel["config"], message)
        else:
            return False, f"Unknown channel type: {channel['type']}"
        return True, ""
    except AlertingError as e:
        return False, str(e)


def notify_all(subject: str, message: str) -> list:
    """
    Sends the given alert to every ENABLED channel. Does not raise on
    individual channel failure - one broken channel (e.g. wrong SMTP
    password) should not block notifications on other channels.
    Returns a list of {"channel": name, "success": bool, "error": str}.
    """
    results = []
    for channel in alert_config.list_channels():
        if not channel.get("enabled", True):
            continue
        success, error = send_to_channel(channel, subject, message)
        results.append({"channel": channel["name"], "success": success, "error": error})
    return results