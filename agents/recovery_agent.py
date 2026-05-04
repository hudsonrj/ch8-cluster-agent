"""
Recovery Agent — Auto-heals offline nodes

Runs on the master node and:
  1. Monitors all peers every 60s
  2. If a node goes offline for >90s, tries to recover it via SSH
  3. Logs all recovery attempts to /data2/ch8-metrics/recovery.json
  4. Only acts if autonomous mode is enabled

Recovery methods (in order):
  1. SSH → run `ch8 up`
  2. If SSH fails, record alert for manual intervention
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

log = logging.getLogger("ch8.recovery")

CONFIG_DIR = Path.home() / ".config" / "ch8"
STATE_FILE = CONFIG_DIR / "state.json"
PID_FILE = CONFIG_DIR / "recovery_agent.pid"
LOG_FILE = CONFIG_DIR / "recovery_agent.log"
ACCESS_FILE = CONFIG_DIR / "node_access.json"
METRICS_DIR = Path("/data2/ch8-metrics")
AUTONOMY_FILE = CONFIG_DIR / "autonomy.json"

CHECK_INTERVAL = 60
OFFLINE_THRESHOLD = 90  # seconds before attempting recovery
MAX_RECOVERY_ATTEMPTS = 3  # per hour per node

_recovery_log = []  # last actions
_attempts = {}  # {node_id: [timestamps]}


def is_autonomous() -> bool:
    try:
        return json.loads(AUTONOMY_FILE.read_text()).get("enabled", False)
    except Exception:
        return False


def load_access() -> dict:
    try:
        return json.loads(ACCESS_FILE.read_text())
    except Exception:
        return {}


def get_offline_nodes() -> list:
    """Get nodes that are offline from the control server."""
    import httpx
    try:
        from connect.auth import CONTROL_URL, get_access_token, get_network_id
        headers = {"Authorization": f"Bearer {get_access_token()}"}
        r = httpx.get(f"{CONTROL_URL}/nodes?network_id={get_network_id()}",
                      headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            nodes = data.get("nodes", data) if isinstance(data, dict) else data
            now = int(time.time())
            return [n for n in nodes
                    if n.get("status") == "offline"
                    and (now - n.get("last_seen", 0)) > OFFLINE_THRESHOLD]
    except Exception as e:
        log.warning(f"Failed to get nodes: {e}")
    return []


def can_attempt(node_id: str) -> bool:
    """Rate limit: max 3 attempts per hour per node."""
    now = time.time()
    if node_id not in _attempts:
        _attempts[node_id] = []
    # Clean old attempts
    _attempts[node_id] = [t for t in _attempts[node_id] if now - t < 3600]
    return len(_attempts[node_id]) < MAX_RECOVERY_ATTEMPTS


def attempt_recovery(node: dict, access: dict) -> bool:
    """Try to recover a node via SSH."""
    node_id = node.get("node_id", "")
    hostname = node.get("hostname", "?")
    address = node.get("address", "")

    node_access = access.get(node_id, {})
    ssh_user = node_access.get("ssh_user", "")
    ssh_pass = node_access.get("ssh_pass", "")
    recovery_cmd = node_access.get("recovery_cmd", "cd ~/ch8-agent && python3 ch8 up")
    target_ip = node_access.get("tailscale_ip", address)

    if not ssh_user or not target_ip:
        log.info(f"[{hostname}] No SSH access configured — cannot recover")
        return False

    if not can_attempt(node_id):
        log.info(f"[{hostname}] Rate limited — too many attempts this hour")
        return False

    _attempts.setdefault(node_id, []).append(time.time())
    log.info(f"[{hostname}] Attempting SSH recovery → {ssh_user}@{target_ip}")

    try:
        cmd = ["sshpass", "-p", ssh_pass, "ssh",
               "-o", "ConnectTimeout=10",
               "-o", "StrictHostKeyChecking=no",
               "-o", "BatchMode=no" if ssh_pass else "yes",
               f"{ssh_user}@{target_ip}",
               recovery_cmd]

        if not ssh_pass:
            cmd = ["ssh", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=no",
                   "-o", "BatchMode=yes", f"{ssh_user}@{target_ip}", recovery_cmd]

        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if r.returncode == 0 or "CH8 Connect is up" in r.stdout:
            log.info(f"[{hostname}] Recovery SUCCESSFUL")
            record_recovery(hostname, "ssh", True)
            return True
        else:
            log.warning(f"[{hostname}] Recovery failed: {r.stderr[:100]}")
            record_recovery(hostname, "ssh", False, r.stderr[:100])
            return False
    except subprocess.TimeoutExpired:
        log.warning(f"[{hostname}] SSH timeout")
        record_recovery(hostname, "ssh", False, "timeout")
        return False
    except Exception as e:
        log.warning(f"[{hostname}] Recovery error: {e}")
        record_recovery(hostname, "ssh", False, str(e))
        return False


def record_recovery(hostname: str, method: str, success: bool, error: str = ""):
    """Log recovery attempt to metrics."""
    entry = {
        "ts": int(time.time()),
        "node": hostname,
        "method": method,
        "success": success,
        "error": error[:100],
    }
    _recovery_log.append(entry)
    if len(_recovery_log) > 50:
        _recovery_log.pop(0)

    # Persist
    try:
        METRICS_DIR.mkdir(parents=True, exist_ok=True)
        f = METRICS_DIR / "recovery.json"
        data = {"events": []}
        if f.exists():
            data = json.loads(f.read_text())
        data["events"].append(entry)
        data["events"] = data["events"][-200:]
        f.write_text(json.dumps(data))
    except Exception:
        pass


def _update_state(status: str, task: str):
    try:
        state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        agents = state.get("agents", [])
        entry = {
            "name": "recovery",
            "status": status,
            "task": task,
            "model": "auto-healer",
            "platform": "ssh",
            "autonomous": True,
            "alerts": 0, "security_findings": 0, "predictions": 0, "heavy_procs": 0,
            "tools": ["ssh", "ch8_up"],
            "details": {
                "history": [{"ts": datetime.now().strftime("%H:%M"), "action": e.get("node",""), "result": "OK" if e.get("success") else "FAIL"} for e in _recovery_log[-10:]],
                "stats": {
                    "total_recoveries": len([e for e in _recovery_log if e.get("success")]),
                    "total_failures": len([e for e in _recovery_log if not e.get("success")]),
                },
            },
            "updated_at": int(time.time()),
        }
        agents = [a for a in agents if a.get("name") != "recovery"]
        agents.append(entry)
        state["agents"] = agents
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception:
        pass


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

    log.info("Recovery Agent started")
    _update_state("idle", "Starting...")

    while not stop:
        if not is_autonomous():
            _update_state("idle", "Autonomous OFF")
            time.sleep(30)
            continue

        try:
            offline = get_offline_nodes()
            if offline:
                access = load_access()
                _update_state("running", f"Recovering {len(offline)} node(s)")
                for node in offline:
                    hostname = node.get("hostname", "?")
                    log.info(f"Node offline: {hostname} (last seen {int(time.time()) - node.get('last_seen',0)}s ago)")
                    attempt_recovery(node, access)
                _update_state("idle", f"Last check: {len(offline)} offline, recovered some")
            else:
                _update_state("idle", "All nodes online")
        except Exception as e:
            log.error(f"Check error: {e}")
            _update_state("error", str(e)[:60])

        # Wait with periodic state refresh
        for i in range(CHECK_INTERVAL):
            if stop:
                break
            time.sleep(1)
            if i % 30 == 0 and i > 0:
                _update_state("idle", _recovery_log[-1]["node"] + " recovered" if _recovery_log and _recovery_log[-1].get("success") else "Monitoring...")

    _update_state("idle", "Stopped")
    PID_FILE.unlink(missing_ok=True)
    log.info("Recovery Agent stopped")


if __name__ == "__main__":
    main()
