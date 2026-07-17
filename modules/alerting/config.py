"""
dtool — devops swiss army knife · by Zeljko Tripcevski
Module: alerting / config
Purpose: Add/Edit/Delete alert channels (email, Telegram) - stored locally,
never hardcoded. Channels are used by modules/alerting/core.py to notify
when a monitored target changes status (ok -> fail, or fail -> ok).

Stored in data/alert_channels.json - add this file to .gitignore, since
it may contain SMTP passwords / bot tokens.
"""

import json
import os
import stat

_DTOOL_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA_DIR = os.path.join(_DTOOL_ROOT, "data")
_CHANNELS_FILE = os.path.join(_DATA_DIR, "alert_channels.json")


def _load_all() -> list:
    if not os.path.exists(_CHANNELS_FILE):
        return []
    try:
        with open(_CHANNELS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_all(channels: list) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_CHANNELS_FILE, "w") as f:
        json.dump(channels, f, indent=2)
    os.chmod(_CHANNELS_FILE, stat.S_IRUSR | stat.S_IWUSR)


def list_channels() -> list:
    return _load_all()


def get_channel(channel_id: int):
    for c in _load_all():
        if c["id"] == channel_id:
            return c
    return None


def add_channel(channel_type: str, name: str, config: dict) -> int:
    channels = _load_all()
    new_id = (max((c["id"] for c in channels), default=0)) + 1
    channels.append({
        "id": new_id,
        "type": channel_type,
        "name": name,
        "enabled": True,
        "config": config,
    })
    _save_all(channels)
    return new_id


def update_channel(channel_id: int, name: str, config: dict, enabled: bool = True) -> bool:
    channels = _load_all()
    for c in channels:
        if c["id"] == channel_id:
            c["name"] = name
            c["config"] = config
            c["enabled"] = enabled
            _save_all(channels)
            return True
    return False


def delete_channel(channel_id: int) -> bool:
    channels = _load_all()
    new_channels = [c for c in channels if c["id"] != channel_id]
    if len(new_channels) == len(channels):
        return False
    _save_all(new_channels)
    return True


def toggle_channel(channel_id: int, enabled: bool) -> bool:
    channels = _load_all()
    for c in channels:
        if c["id"] == channel_id:
            c["enabled"] = enabled
            _save_all(channels)
            return True
    return False