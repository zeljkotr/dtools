"""
dtool — devops swiss army knife · by Zeljko Tripcevski
Module: home / config
Purpose: Lets the user pick which widgets appear on the customizable
"Moj Dashboard" home screen. Stored locally in data/home_widgets.json.
"""

import json
import os

_DTOOL_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA_DIR = os.path.join(_DTOOL_ROOT, "data")
_WIDGETS_FILE = os.path.join(_DATA_DIR, "home_widgets.json")

# Available widget types and their display names.
WIDGET_CATALOG = {
    "ec2_status": "EC2 — instance status",
    "s3_status": "S3 — bucket-i i zdravlje",
    "monitoring_summary": "Monitoring — ukupan pregled (ok/fail)",
    "disk_usage": "Disk — iskoriscenost (iz Monitoring disk_space targeta)",
    "ec2_cpu": "EC2 — CPU iskoriscenost (CloudWatch)",
}

_DEFAULT_ENABLED = ["ec2_status", "monitoring_summary", "disk_usage"]


def list_enabled_widgets() -> list:
    if not os.path.exists(_WIDGETS_FILE):
        return list(_DEFAULT_ENABLED)
    try:
        with open(_WIDGETS_FILE, "r") as f:
            data = json.load(f)
        return [w for w in data.get("enabled", []) if w in WIDGET_CATALOG]
    except (json.JSONDecodeError, OSError):
        return list(_DEFAULT_ENABLED)


def set_enabled_widgets(widget_ids: list) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    valid = [w for w in widget_ids if w in WIDGET_CATALOG]
    with open(_WIDGETS_FILE, "w") as f:
        json.dump({"enabled": valid}, f, indent=2)


def add_widget(widget_id: str) -> None:
    current = list_enabled_widgets()
    if widget_id in WIDGET_CATALOG and widget_id not in current:
        current.append(widget_id)
        set_enabled_widgets(current)


def remove_widget(widget_id: str) -> None:
    current = list_enabled_widgets()
    if widget_id in current:
        current.remove(widget_id)
        set_enabled_widgets(current)