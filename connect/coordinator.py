"""
Client for the CH8 Control Server.

Handles node registration, peer discovery, and heartbeats.
"""

import asyncio
import platform
import socket
import time
from typing import List, Optional
import httpx

from .auth import CONTROL_URL, get_access_token, get_network_id, get_node_id


class ControlClient:
    """
    Async HTTP client that talks to the CH8 control server.
    Responsible for registration, peer discovery, and heartbeats.
    """

    def __init__(self, advertise_addr: Optional[str] = None, port: int = 7878):
        self.node_id       = get_node_id()
        self.advertise_addr = advertise_addr or _get_local_ip()
        self.port          = port
        self._client: Optional[httpx.AsyncClient] = None

    def _headers(self) -> dict:
        token = get_access_token()
        if not token:
            raise RuntimeError("Not authenticated. Run `ch8 login` or `ch8 up --token TOKEN`.")
        return {"Authorization": f"Bearer {token}"}

    async def _re_authenticate(self) -> bool:
        """Try to get a new token via /auth/recover, DB, or bootstrap."""
        import logging
        log = logging.getLogger("ch8.coordinator")
        try:
            # Strategy 1: Ask control server to recover session from DB
            client = await self._get()
            resp = await client.post("/auth/recover", json={"node_id": self.node_id})
            if resp.status_code == 200:
                new_token = resp.json().get("access_token")
                if new_token:
                    from .auth import _save_token
                    _save_token(new_token)
                    log.info(f"Re-authenticated via /auth/recover")
                    return True

            # Strategy 2: Try bootstrap from localhost (only works on control node)
            resp = await client.post(
                "/api/admin/bootstrap",
                params={"network_id": get_network_id(), "label": f"auto-{self.node_id}", "ttl_hours": 8760},
            )
            if resp.status_code == 200:
                preauth_token = resp.json().get("token")
                if preauth_token:
                    resp2 = await client.post("/auth/preauth", json={"token": preauth_token, "node_id": self.node_id})
                    if resp2.status_code == 200:
                        new_token = resp2.json().get("access_token")
                        if new_token:
                            from .auth import _save_token
                            _save_token(new_token)
                            log.info("Re-authenticated via bootstrap")
                            return True
        except Exception as e:
            log.warning(f"Re-authentication failed: {e}")
        return False

    async def _get(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=CONTROL_URL, timeout=15)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    # ------------------------------------------------------------------ #

    async def register(self, capabilities: List[str]) -> dict:
        """Register this node with the control server."""
        client = await self._get()
        payload = {
            "node_id":    self.node_id,
            "network_id": get_network_id(),
            "address":    self.advertise_addr,
            "port":       self.port,
            "hostname":   socket.gethostname(),
            "os":         platform.system().lower(),
            "arch":       platform.machine(),
            "capabilities": capabilities,
            "models":     [],  # populated via first heartbeat
            "version":    _get_version(),
        }
        resp = await client.post("/nodes/register", json=payload, headers=self._headers())
        if resp.status_code == 401:
            if await self._re_authenticate():
                resp = await client.post("/nodes/register", json=payload, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    async def heartbeat(self, metrics: Optional[dict] = None) -> bool:
        """Send heartbeat — keeps the node listed as online."""
        client = await self._get()
        payload = {
            "node_id":    self.node_id,
            "network_id": get_network_id(),
            "ts":         int(time.time()),
            "version":    _get_version(),
            **(metrics or {}),
        }
        # ensure services/models are always lists
        payload.setdefault("models", [])
        payload.setdefault("services", [])
        resp = await client.put(
            f"/nodes/{self.node_id}/heartbeat",
            json=payload,
            headers=self._headers(),
        )
        if resp.status_code == 401:
            # Token expired/invalid — try to re-authenticate
            if await self._re_authenticate():
                resp = await client.put(
                    f"/nodes/{self.node_id}/heartbeat",
                    json=payload,
                    headers=self._headers(),
                )
        return resp.status_code == 200

    async def get_peers(self) -> List[dict]:
        """Return all active nodes in this network (excluding self)."""
        client = await self._get()
        resp = await client.get(
            "/nodes",
            params={"network_id": get_network_id()},
            headers=self._headers(),
        )
        resp.raise_for_status()
        nodes = resp.json().get("nodes", [])
        return [n for n in nodes if n["node_id"] != self.node_id]

    async def deregister(self) -> None:
        """Mark this node as offline."""
        try:
            client = await self._get()
            await client.delete(
                f"/nodes/{self.node_id}",
                params={"network_id": get_network_id()},
                headers=self._headers(),
            )
        except Exception:
            pass  # best-effort on shutdown

    async def create_preauth_token(self, label: str = "", ttl_hours: int = 24 * 7) -> dict:
        """Generate a new pre-auth token (for headless node enrollment)."""
        client = await self._get()
        resp = await client.post("/auth/preauth/create", json={
            "network_id": get_network_id(),
            "label":      label,
            "ttl_hours":  ttl_hours,
        }, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    async def relay_message(self, target_node_id: str, payload: dict) -> dict:
        """Relay a message to a target node via the control server."""
        client = await self._get()
        resp = await client.post(
            f"/api/relay/{target_node_id}",
            json=payload,
            headers=self._headers(),
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()


# ------------------------------------------------------------------ #
# Helpers

def _get_local_ip() -> str:
    """Get best address. Prefers Tailscale (100.x) over public/LAN IP."""
    try:
        import subprocess
        out = subprocess.check_output(["tailscale", "ip", "--4"], timeout=5, stderr=subprocess.DEVNULL).decode().strip()
        if out.startswith("100."):
            return out
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _get_version() -> str:
    from pathlib import Path
    import subprocess
    repo = Path(__file__).parent.parent
    # Try VERSION file first
    try:
        v = (repo / "VERSION").read_text().strip()
        if v:
            return v
    except Exception:
        pass
    # Fallback: git short hash
    try:
        h = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                    cwd=str(repo), timeout=3, stderr=subprocess.DEVNULL).decode().strip()
        return f"1.0.0-{h}" if h else "1.0.0"
    except Exception:
        return "1.0.0"
