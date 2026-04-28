"""
Persistent store for the control server.
State is saved to /data/state.json on every change and loaded on startup.
"""

import json
import secrets
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional

NODE_TTL_SECS  = 90    # node considered offline after this many seconds without heartbeat
STATE_FILE     = Path("/data/state.json")


def _now() -> int:
    return int(time.time())


def _save_state(nodes: dict, tokens: dict, sessions: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "nodes":    nodes,
            "tokens":   tokens,
            "sessions": sessions,
            "saved_at": _now(),
        }, indent=2))
        tmp.replace(STATE_FILE)
    except Exception:
        pass


def _load_state() -> tuple:
    try:
        if STATE_FILE.exists():
            d = json.loads(STATE_FILE.read_text())
            return d.get("nodes", {}), d.get("tokens", {}), d.get("sessions", {})
    except Exception:
        pass
    return {}, {}, {}


class NodeStore:

    def __init__(self, _auth_ref=None):
        self._lock   = threading.Lock()
        self._auth   = _auth_ref   # set after AuthStore is created
        nodes, _, _  = _load_state()
        self._nodes: Dict[str, dict] = nodes

    def _save(self, auth: "AuthStore") -> None:
        _save_state(self._nodes, auth._preauth_tokens, auth._sessions)

    def register(self, info: dict, auth: "AuthStore") -> None:
        with self._lock:
            info["registered_at"] = info.get("registered_at", _now())
            info["last_seen"]     = _now()
            info["status"]        = "online"
            info.setdefault("cpu_pct",     0.0)
            info.setdefault("mem_pct",     0.0)
            info.setdefault("disk_pct",    0.0)
            info.setdefault("agents",      [])
            info.setdefault("models",      [])
            info.setdefault("services",    [])
            info.setdefault("ai_model",    "")
            info.setdefault("ai_provider", "")
            self._nodes[info["node_id"]] = info
            self._save(auth)

    def heartbeat(self, node_id: str, network_id: str, metrics: dict, auth: "AuthStore") -> bool:
        with self._lock:
            node = self._nodes.get(node_id)
            if not node or node["network_id"] != network_id:
                return False
            node["last_seen"] = _now()
            node["status"]    = "online"
            for key in ("cpu_pct", "mem_pct", "disk_pct", "agents", "models", "services", "ai_model", "ai_provider", "tools", "channels"):
                if key in metrics:
                    node[key] = metrics[key]
            self._save(auth)
            return True

    def deregister(self, node_id: str, network_id: str, auth: "AuthStore") -> None:
        with self._lock:
            node = self._nodes.get(node_id)
            if node and node["network_id"] == network_id:
                node["status"] = "offline"
                self._save(auth)

    def _mark_stale(self) -> None:
        now = _now()
        for node in self._nodes.values():
            if node["status"] == "online" and now - node.get("last_seen", 0) > NODE_TTL_SECS:
                node["status"] = "offline"

    def get_nodes(self, network_id: str) -> List[dict]:
        with self._lock:
            self._mark_stale()
            return [dict(n) for n in self._nodes.values()
                    if n["network_id"] == network_id and n["status"] == "online"]

    def get_all_nodes(self) -> List[dict]:
        with self._lock:
            self._mark_stale()
            return [dict(n) for n in self._nodes.values()]

    def summary(self) -> dict:
        with self._lock:
            self._mark_stale()
            nodes   = list(self._nodes.values())
            online  = [n for n in nodes if n["status"] == "online"]
            offline = [n for n in nodes if n["status"] == "offline"]
            return {
                "total_nodes":   len(nodes),
                "online_nodes":  len(online),
                "offline_nodes": len(offline),
                "networks":      len({n["network_id"] for n in nodes}),
                "total_agents":  sum(len(n.get("agents", [])) for n in online),
            }


class AuthStore:

    def __init__(self):
        self._lock = threading.Lock()
        _, tokens, sessions = _load_state()
        self._device_codes:   Dict[str, dict] = {}          # never persisted (short-lived)
        self._preauth_tokens: Dict[str, dict] = tokens
        self._sessions:       Dict[str, dict] = sessions

    def _save(self, nodes: dict) -> None:
        _save_state(nodes, self._preauth_tokens, self._sessions)

    # --- device code flow ---

    def create_device_code(self, node_id: str, base_url: str) -> dict:
        device_code = secrets.token_urlsafe(32)
        user_code   = _random_user_code()
        self._device_codes[device_code] = {
            "node_id":    node_id,
            "user_code":  user_code,
            "approved":   False,
            "network_id": None,
            "expire_at":  _now() + 300,
        }
        return {
            "device_code":      device_code,
            "user_code":        user_code,
            "verification_uri": f"{base_url}/connect/activate?code={user_code}",
            "expires_in":       300,
            "interval":         5,
        }

    def approve_device(self, user_code: str, network_id: str) -> bool:
        for state in self._device_codes.values():
            if state["user_code"] == user_code and not state["approved"]:
                state["approved"]   = True
                state["network_id"] = network_id
                return True
        return False

    def poll_device(self, device_code: str) -> Optional[dict]:
        state = self._device_codes.get(device_code)
        if not state or _now() > state["expire_at"]:
            self._device_codes.pop(device_code, None)
            return None
        if not state["approved"]:
            return None
        access_token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[access_token] = {
                "node_id":    state["node_id"],
                "network_id": state["network_id"],
                "created_at": _now(),
            }
        del self._device_codes[device_code]
        return {"access_token": access_token, "network_id": state["network_id"]}

    # --- pre-auth tokens ---

    def create_preauth_token(self, network_id: str, label: str, ttl_hours: int) -> dict:
        token = "tk_" + secrets.token_urlsafe(24)
        with self._lock:
            self._preauth_tokens[token] = {
                "network_id": network_id,
                "label":      label,
                "expire_at":  _now() + ttl_hours * 3600,
            }
        return {"token": token, "expires_at": self._preauth_tokens[token]["expire_at"], "label": label}

    def use_preauth_token(self, token: str, node_id: str) -> Optional[dict]:
        with self._lock:
            state = self._preauth_tokens.get(token)
            if not state or _now() > state["expire_at"]:
                return None
            access_token = secrets.token_urlsafe(32)
            self._sessions[access_token] = {
                "node_id":    node_id,
                "network_id": state["network_id"],
                "created_at": _now(),
            }
            return {"access_token": access_token, "network_id": state["network_id"]}

    def get_session(self, access_token: str) -> Optional[dict]:
        return self._sessions.get(access_token)


def _random_user_code() -> str:
    import random, string
    return (''.join(random.choices(string.ascii_uppercase, k=4)) + '-' +
            ''.join(random.choices(string.digits, k=4)))
