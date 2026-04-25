"""
In-memory store for the control server.
Backed by a simple dict — swap for Redis/Postgres in production.
"""

import secrets
import time
from typing import Dict, List, Optional

NODE_TTL_SECS = 60   # node considered offline after this many seconds without heartbeat


class NodeStore:
    """Registry of all active nodes."""

    def __init__(self):
        self._nodes: Dict[str, dict] = {}   # node_id -> node_info

    def register(self, info: dict) -> None:
        info["registered_at"] = info.get("registered_at", int(time.time()))
        info["last_seen"]     = int(time.time())
        info["status"]        = "online"
        self._nodes[info["node_id"]] = info

    def heartbeat(self, node_id: str, network_id: str, metrics: dict) -> bool:
        node = self._nodes.get(node_id)
        if not node or node["network_id"] != network_id:
            return False
        node["last_seen"] = int(time.time())
        node["status"]    = "online"
        node.update(metrics)
        return True

    def deregister(self, node_id: str, network_id: str) -> None:
        node = self._nodes.get(node_id)
        if node and node["network_id"] == network_id:
            node["status"] = "offline"

    def get_nodes(self, network_id: str) -> List[dict]:
        now = int(time.time())
        result = []
        for node in self._nodes.values():
            if node["network_id"] != network_id:
                continue
            # Mark stale nodes offline
            if now - node.get("last_seen", 0) > NODE_TTL_SECS:
                node["status"] = "offline"
            else:
                node["status"] = "online"
            if node["status"] == "online":
                result.append(dict(node))
        return result


class AuthStore:
    """Manages device codes and pre-auth tokens."""

    def __init__(self):
        self._device_codes: Dict[str, dict] = {}   # device_code -> state
        self._preauth_tokens: Dict[str, dict] = {}  # token -> state
        self._sessions: Dict[str, dict] = {}        # access_token -> session

    # ------------------------------------------------------------------ #
    # Device code flow

    def create_device_code(self, node_id: str, base_url: str) -> dict:
        device_code = secrets.token_urlsafe(32)
        user_code   = _random_user_code()
        expire_at   = int(time.time()) + 300  # 5 min
        self._device_codes[device_code] = {
            "node_id":      node_id,
            "user_code":    user_code,
            "approved":     False,
            "network_id":   None,
            "expire_at":    expire_at,
        }
        return {
            "device_code":        device_code,
            "user_code":          user_code,
            "verification_uri":   f"{base_url}/connect/activate?code={user_code}",
            "expires_in":         300,
            "interval":           5,
        }

    def approve_device(self, user_code: str, network_id: str) -> bool:
        for state in self._device_codes.values():
            if state["user_code"] == user_code and not state["approved"]:
                state["approved"]   = True
                state["network_id"] = network_id
                return True
        return False

    def poll_device(self, device_code: str) -> Optional[dict]:
        """Returns access_token data if approved, None if pending."""
        state = self._device_codes.get(device_code)
        if not state:
            return None
        if int(time.time()) > state["expire_at"]:
            del self._device_codes[device_code]
            return None
        if not state["approved"]:
            return None
        # Issue access token
        access_token = secrets.token_urlsafe(32)
        session = {
            "node_id":    state["node_id"],
            "network_id": state["network_id"],
            "created_at": int(time.time()),
        }
        self._sessions[access_token] = session
        del self._device_codes[device_code]
        return {"access_token": access_token, "network_id": state["network_id"]}

    # ------------------------------------------------------------------ #
    # Pre-auth token flow

    def create_preauth_token(self, network_id: str, label: str, ttl_hours: int) -> dict:
        token     = "tk_" + secrets.token_urlsafe(24)
        expire_at = int(time.time()) + ttl_hours * 3600
        self._preauth_tokens[token] = {
            "network_id": network_id,
            "label":      label,
            "expire_at":  expire_at,
            "used":       False,
        }
        return {"token": token, "expires_at": expire_at, "label": label}

    def use_preauth_token(self, token: str, node_id: str) -> Optional[dict]:
        state = self._preauth_tokens.get(token)
        if not state:
            return None
        if int(time.time()) > state["expire_at"]:
            return None
        # Tokens can be reused (like Tailscale reusable keys)
        access_token = secrets.token_urlsafe(32)
        self._sessions[access_token] = {
            "node_id":    node_id,
            "network_id": state["network_id"],
            "created_at": int(time.time()),
        }
        return {"access_token": access_token, "network_id": state["network_id"]}

    # ------------------------------------------------------------------ #
    # Session validation

    def get_session(self, access_token: str) -> Optional[dict]:
        return self._sessions.get(access_token)


def _random_user_code() -> str:
    """Generate a short human-readable code like ABCD-1234."""
    import random, string
    letters = ''.join(random.choices(string.ascii_uppercase, k=4))
    digits  = ''.join(random.choices(string.digits, k=4))
    return f"{letters}-{digits}"
