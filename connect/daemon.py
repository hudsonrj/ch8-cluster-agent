"""
CH8 Connect Daemon (ch8d)

Runs in the background after `ch8 up`.
Responsibilities:
  - Register this node with the control server
  - Poll for peers every POLL_INTERVAL seconds
  - Maintain gRPC connections to active peers
  - Send heartbeats
  - Reconnect automatically on failure
"""

import asyncio
import json
import logging
import os
import platform
import signal
import socket
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from .auth import CONFIG_DIR, get_access_token, get_network_id, get_node_id, is_authenticated
from .coordinator import ControlClient

log = logging.getLogger("ch8.daemon")

PID_FILE        = CONFIG_DIR / "daemon.pid"
STATE_FILE      = CONFIG_DIR / "state.json"
POLL_INTERVAL   = int(os.environ.get("CH8_POLL_INTERVAL", "30"))  # seconds
HEARTBEAT_SECS  = int(os.environ.get("CH8_HEARTBEAT", "15"))
NODE_PORT       = int(os.environ.get("CH8_PORT", "7878"))


class ConnectDaemon:
    """
    The background daemon that keeps the cluster connected.
    """

    def __init__(self, advertise_addr: Optional[str] = None,
                 port: int = NODE_PORT,
                 capabilities: Optional[List[str]] = None):
        self.advertise_addr = advertise_addr
        self.port           = port
        self.capabilities   = capabilities or _detect_capabilities()
        self.control        = ControlClient(advertise_addr=advertise_addr, port=port)
        self.peers: Dict[str, dict] = {}   # node_id -> peer info
        self._stop_event    = asyncio.Event()
        self._registered    = False

    # ------------------------------------------------------------------ #
    # Public interface

    async def start(self) -> None:
        """Start the daemon — blocks until stopped."""
        if not is_authenticated():
            log.error("Not authenticated. Run `ch8 login` or `ch8 up --token TOKEN`")
            sys.exit(1)

        _write_pid()
        log.info(f"CH8 daemon starting  node={get_node_id()}  port={self.port}")

        try:
            # Initial registration
            await self._register()

            # Run all background tasks concurrently
            await asyncio.gather(
                self._heartbeat_loop(),
                self._peer_discovery_loop(),
                self._wait_for_stop(),
            )
        finally:
            log.info("Daemon shutting down...")
            await self.control.deregister()
            await self.control.close()
            _clear_pid()
            _write_state({"status": "offline", "peers": []})

    def stop(self) -> None:
        self._stop_event.set()

    # ------------------------------------------------------------------ #
    # Internals

    async def _register(self) -> None:
        while True:
            try:
                result = await self.control.register(self.capabilities)
                self._registered = True
                log.info(f"Registered with control server  network={get_network_id()}")
                _write_state({"status": "online", "peers": []})
                return
            except Exception as e:
                log.warning(f"Registration failed ({e}), retrying in 10s...")
                await asyncio.sleep(10)

    async def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                metrics = _collect_metrics()
                ok = await self.control.heartbeat(metrics)
                if not ok:
                    log.warning("Heartbeat rejected — re-registering...")
                    await self._register()
            except Exception as e:
                log.warning(f"Heartbeat error: {e}")
            await asyncio.sleep(HEARTBEAT_SECS)

    async def _peer_discovery_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                peers = await self.control.get_peers()
                current_ids: Set[str] = {p["node_id"] for p in peers}
                previous_ids: Set[str] = set(self.peers.keys())

                # New nodes
                for peer in peers:
                    nid = peer["node_id"]
                    if nid not in self.peers:
                        log.info(f"New peer discovered: {nid}  ({peer.get('hostname', '?')})")
                    self.peers[nid] = peer

                # Lost nodes
                for lost_id in previous_ids - current_ids:
                    log.info(f"Peer gone: {lost_id}")
                    del self.peers[lost_id]

                _write_state({"status": "online", "peers": list(self.peers.values())})

            except Exception as e:
                log.warning(f"Peer discovery error: {e}")

            await asyncio.sleep(POLL_INTERVAL)

    async def _wait_for_stop(self) -> None:
        await self._stop_event.wait()


# ------------------------------------------------------------------ #
# State helpers

def _write_pid() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))


def _clear_pid() -> None:
    if PID_FILE.exists():
        PID_FILE.unlink()


def _write_state(state: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = int(time.time())
    STATE_FILE.write_text(json.dumps(state, indent=2))


def read_state() -> dict:
    if not STATE_FILE.exists():
        return {"status": "offline", "peers": []}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"status": "offline", "peers": []}


def get_daemon_pid() -> Optional[int]:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return None


def is_daemon_running() -> bool:
    pid = get_daemon_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        _clear_pid()
        return False


# ------------------------------------------------------------------ #
# Capability detection

def _detect_capabilities() -> List[str]:
    caps = ["worker"]
    # Ollama
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=2)
        if r.status_code == 200:
            caps.append("ollama")
    except Exception:
        pass
    # GPU
    try:
        import subprocess
        out = subprocess.check_output(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                                      timeout=3, stderr=subprocess.DEVNULL)
        if out.strip():
            caps.append("gpu")
    except Exception:
        pass
    # Memory tier
    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / 1e9
        if ram_gb >= 16:
            caps.append("high-memory")
        elif ram_gb >= 8:
            caps.append("medium-memory")
        else:
            caps.append("low-memory")
    except Exception:
        pass
    return caps


def _collect_metrics() -> dict:
    metrics = {}
    try:
        import psutil
        metrics["cpu_pct"]    = psutil.cpu_percent(interval=0.2)
        metrics["mem_pct"]    = psutil.virtual_memory().percent
        metrics["disk_pct"]   = psutil.disk_usage("/").percent
    except Exception:
        pass
    return metrics


# ------------------------------------------------------------------ #
# Entry point (used when running as a subprocess)

async def _main(advertise_addr=None, port=NODE_PORT, capabilities=None):
    daemon = ConnectDaemon(
        advertise_addr=advertise_addr,
        port=port,
        capabilities=capabilities,
    )

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, daemon.stop)

    await daemon.start()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(_main())
