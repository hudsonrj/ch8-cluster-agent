"""
Authentication management for CH8 Connect.

Supports two flows:
  1. Login flow  — ch8 login  (interactive, opens browser or device code)
  2. Token flow  — ch8 up --token <TOKEN>  (headless, CI, embedded)
"""

import json
import os
import secrets
import hashlib
import time
from pathlib import Path
from typing import Optional
import httpx

CONFIG_DIR  = Path(os.environ.get("CH8_CONFIG_DIR", Path.home() / ".config" / "ch8"))
AUTH_FILE   = CONFIG_DIR / "auth.json"
CONTROL_URL = os.environ.get("CH8_CONTROL_URL", "https://control.ch8ai.com.br")


def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_auth() -> Optional[dict]:
    """Load saved auth state from disk."""
    if not AUTH_FILE.exists():
        return None
    try:
        return json.loads(AUTH_FILE.read_text())
    except Exception:
        return None


def save_auth(data: dict) -> None:
    """Persist auth state to disk (chmod 600)."""
    _ensure_config_dir()
    AUTH_FILE.write_text(json.dumps(data, indent=2))
    AUTH_FILE.chmod(0o600)


def clear_auth() -> None:
    """Remove saved credentials (logout)."""
    if AUTH_FILE.exists():
        AUTH_FILE.unlink()


def get_node_id() -> str:
    """Stable node ID derived from machine-id or generated once."""
    node_id_file = CONFIG_DIR / "node_id"
    _ensure_config_dir()
    if node_id_file.exists():
        return node_id_file.read_text().strip()
    # generate deterministic ID from hostname + machine-id
    machine_id = ""
    for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
        try:
            machine_id = Path(path).read_text().strip()
            break
        except Exception:
            pass
    if not machine_id:
        machine_id = secrets.token_hex(16)
    import socket
    raw = f"{socket.gethostname()}:{machine_id}"
    node_id = "node_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
    node_id_file.write_text(node_id)
    return node_id


def login_interactive() -> dict:
    """
    Device-code login flow.
    Prints a URL the user opens in a browser to authenticate.
    Polls until approved or timed out.
    """
    client = httpx.Client(base_url=CONTROL_URL, timeout=30)

    # Request device code
    resp = client.post("/auth/device", json={"node_id": get_node_id()})
    resp.raise_for_status()
    data = resp.json()

    device_code  = data["device_code"]
    user_code    = data["user_code"]
    verify_url   = data["verification_uri"]
    expires_in   = data.get("expires_in", 300)
    poll_interval = data.get("interval", 5)

    print(f"\n  Open this URL in your browser:\n")
    print(f"    {verify_url}")
    print(f"\n  Enter code:  {user_code}\n")

    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(poll_interval)
        poll = client.post("/auth/token", json={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
        })
        if poll.status_code == 200:
            token_data = poll.json()
            auth = {
                "access_token":  token_data["access_token"],
                "network_id":    token_data["network_id"],
                "node_id":       get_node_id(),
                "created_at":    int(time.time()),
            }
            save_auth(auth)
            return auth
        # 428 = authorization_pending, keep polling
        if poll.status_code not in (428, 400):
            poll.raise_for_status()

    raise TimeoutError("Login timed out. Please try again.")


def login_with_token(token: str) -> dict:
    """
    Authenticate using a pre-auth token (headless mode).
    Token can be created via `ch8 token create` on an already-authenticated node.
    """
    client = httpx.Client(base_url=CONTROL_URL, timeout=30)
    resp = client.post("/auth/preauth", json={
        "token":   token,
        "node_id": get_node_id(),
    })
    resp.raise_for_status()
    token_data = resp.json()
    auth = {
        "access_token": token_data["access_token"],
        "network_id":   token_data["network_id"],
        "node_id":      get_node_id(),
        "created_at":   int(time.time()),
    }
    save_auth(auth)
    return auth


def get_access_token() -> Optional[str]:
    auth = load_auth()
    return auth.get("access_token") if auth else None


def get_network_id() -> Optional[str]:
    auth = load_auth()
    return auth.get("network_id") if auth else None


def is_authenticated() -> bool:
    return load_auth() is not None
