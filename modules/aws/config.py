"""
dtool — devops swiss army knife · by Zeljko Tripcevski
Module: aws / config
Purpose: Optional, locally-stored AWS credentials for when no IAM role is
available (e.g. running dtool from a laptop instead of from an EC2 instance
that already has a role attached).

Credentials are stored in data/aws_credentials.json (NEVER in code, NEVER
committed to git — add data/aws_credentials.json to .gitignore).

If no credentials are saved here, every AWS module automatically falls back
to boto3's default credential chain (IAM role, environment variables, or
~/.aws/credentials) — nothing breaks if this file is empty/missing.
"""

import json
import os
import stat

_DTOOL_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA_DIR = os.path.join(_DTOOL_ROOT, "data")
_CRED_FILE = os.path.join(_DATA_DIR, "aws_credentials.json")


def load_credentials() -> dict | None:
    """Return saved credentials dict, or None if none are saved / file is invalid."""
    if not os.path.exists(_CRED_FILE):
        return None
    try:
        with open(_CRED_FILE, "r") as f:
            data = json.load(f)
        if data.get("access_key") and data.get("secret_key"):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def save_credentials(access_key: str, secret_key: str, region: str = "us-east-1",
                      session_token: str = "") -> None:
    """Create or overwrite (edit) the saved credentials."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    data = {
        "access_key": access_key.strip(),
        "secret_key": secret_key.strip(),
        "region": (region.strip() or "us-east-1"),
        "session_token": session_token.strip(),
    }
    with open(_CRED_FILE, "w") as f:
        json.dump(data, f)
    # restrict file permissions to owner read/write only (chmod 600)
    os.chmod(_CRED_FILE, stat.S_IRUSR | stat.S_IWUSR)


def clear_credentials() -> None:
    """Delete saved credentials — module falls back to IAM role / env vars again."""
    if os.path.exists(_CRED_FILE):
        os.remove(_CRED_FILE)


def has_saved_credentials() -> bool:
    return load_credentials() is not None