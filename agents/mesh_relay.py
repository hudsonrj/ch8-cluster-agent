"""
Mesh Relay Agent — Local network bridge for unreachable nodes

Each node runs this agent. It:
1. Discovers peers on the same local network (LAN scan)
2. Registers as a relay for peers that can't be reached directly
3. Forwards requests to LAN-only nodes via local network
4. Reports reachability map to control server

This creates a mesh where ANY node can relay to ANY other node
on its local network, providing redundancy when Tailscale is down
or when a node has no VPN (like MacBook-Air).

Cycle every 60s:
- Ping known peers on LAN
- Update relay table
- Report to control server
"""

import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger("ch8.mesh_relay")

CONFIG_DIR = Path.home() / ".config" / "ch8"
STATE_FILE = CONFIG_DIR / "state.json"
PID_FILE = CONFIG_DIR / "mesh_relay.pid"
LOG_FILE = CONFIG_DIR / "mesh_relay.log"
RELAY_FILE = CONFIG_DIR / "mesh_relay_table.json"

CHECK_INTERVAL = 60
ORCH_PORT = 7879

_last_status = "Starting..."
_reachable = {}  # {node_id: {address, hostname, latency_ms}}


def _update_agent_state(status: str, task: str):
    global _last_status
    _last_status = task
    try:
        state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        agents = state.get("agents", [])
        entry = {
            "name": "mesh_relay",
            "status": status,
            "task": task,
            "model": "network-bridge",
            "platform": "mesh",
            "autonomous": True,
            "alerts": 0, "security_findings": 0, "predictions": 0, "heavy_procs": 0,
            "tools": ["relay", "ping"],
            "details": {
                "reachable_nodes": len(_reachable),
                "relay_table": {k: v.get("hostname", "?") for k, v in list(_reachable.items())[:10]},
            },
            "updated_at": int(time.time()),
        }
        agents = [a for a in agents if a.get("name") != "mesh_relay"]
        agents.append(entry)
        state["agents"] = agents
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        log.warning(f"State update: {e}")


def get_peers() -> list:
    """Get peer list from local state."""
    try:
        state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        return state.get("peers", [])
    except Exception:
        return []


def get_all_nodes() -> list:
    """Get all nodes from control server."""
    import httpx
    try:
        from connect.auth import CONTROL_URL, get_access_token, get_network_id
        headers = {"Authorization": f"Bearer {get_access_token()}"}
        r = httpx.get(f"{CONTROL_URL}/nodes?network_id={get_network_id()}",
                      headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("nodes", data) if isinstance(data, dict) else data
    except Exception:
        pass
    return []


def scan_reachability(nodes: list) -> dict:
    """Probe each node on its address:7879 to check if reachable from here."""
    import httpx
    reachable = {}
    for n in nodes:
        node_id = n.get("node_id", "")
        address = n.get("address", "")
        hostname = n.get("hostname", "?")

        if not address:
            continue

        # Skip self
        from connect.auth import get_node_id
        if node_id == get_node_id():
            continue

        # Try to reach orchestrator
        t0 = time.time()
        try:
            r = httpx.get(f"http://{address}:{ORCH_PORT}/health", timeout=3)
            if r.status_code == 200:
                latency = round((time.time() - t0) * 1000, 1)
                reachable[node_id] = {
                    "address": address,
                    "hostname": hostname,
                    "latency_ms": latency,
                    "last_seen": int(time.time()),
                }
        except Exception:
            pass

        # Also try LAN addresses (local_ip from heartbeat)
        local_ip = n.get("local_ip", "")
        if local_ip and local_ip != address:
            try:
                r = httpx.get(f"http://{local_ip}:{ORCH_PORT}/health", timeout=3)
                if r.status_code == 200:
                    latency = round((time.time() - t0) * 1000, 1)
                    reachable[node_id] = {
                        "address": local_ip,
                        "hostname": hostname,
                        "latency_ms": latency,
                        "last_seen": int(time.time()),
                        "via": "lan",
                    }
            except Exception:
                pass

    return reachable


def save_relay_table(reachable: dict):
    """Save relay table locally and report to control server."""
    RELAY_FILE.write_text(json.dumps(reachable, indent=2))

    # Report to control server via heartbeat (included in next metrics cycle)
    # The relay info is read by the orchestrator when it needs to forward


def register_as_relay():
    """Tell the control server this node can relay to certain peers."""
    import httpx
    try:
        from connect.auth import CONTROL_URL, get_access_token, get_node_id
        headers = {"Authorization": f"Bearer {get_access_token()}"}
        payload = {
            "node_id": get_node_id(),
            "can_reach": list(_reachable.keys()),
            "relay_table": {k: v["address"] for k, v in _reachable.items()},
        }
        httpx.post(f"{CONTROL_URL}/api/mesh/relay-report",
                   json=payload, headers=headers, timeout=5)
    except Exception:
        pass  # Endpoint might not exist yet, that's OK


def run_cycle():
    """One relay discovery cycle."""
    global _reachable
    _update_agent_state("running", "Scanning peers...")

    # Get all known nodes
    nodes = get_all_nodes()
    if not nodes:
        # Fallback to local peer list
        peers = get_peers()
        nodes = peers

    # Scan reachability
    _reachable = scan_reachability(nodes)
    save_relay_table(_reachable)
    register_as_relay()

    count = len(_reachable)
    names = [v["hostname"] for v in list(_reachable.values())[:5]]
    _update_agent_state("idle", f"Relay: {count} node(s) reachable — {', '.join(names)}")
    log.info(f"Mesh scan: {count} reachable nodes")
    for nid, info in _reachable.items():
        log.debug(f"  {info['hostname']} @ {info['address']} ({info['latency_ms']}ms)")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
    )

    PID_FILE.write_text(str(os.getpid()))
    stop = False

    def _stop(sig, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    log.info("Mesh Relay Agent started")
    _update_agent_state("idle", "Starting...")

    while not stop:
        try:
            run_cycle()
        except Exception as e:
            log.error(f"Cycle error: {e}")
            _update_agent_state("error", str(e)[:60])

        # Wait
        elapsed = 0
        while elapsed < CHECK_INTERVAL:
            if stop:
                break
            time.sleep(1)
            elapsed += 1
            if elapsed % 30 == 0:
                _update_agent_state("idle", _last_status)

    _update_agent_state("idle", "Stopped")
    PID_FILE.unlink(missing_ok=True)
    log.info("Mesh Relay Agent stopped")


if __name__ == "__main__":
    main()
