"""
DB Failover Agent — Monitors PostgreSQL master/replica health and auto-promotes replica if master dies.

Architecture:
- Checks master (127.0.0.1:5432) health every 30s
- Checks replica (vmi3201672 via Tailscale) health every 30s
- If master down for 3 consecutive checks (90s):
  1. Promotes replica to standalone (pg_promote)
  2. Notifies all nodes to switch DB_URL
  3. Logs critical event
- If replica down: alerts but no action (master still alive)
- If both down: critical alert, attempts local recovery

Also monitors replication lag — alerts if > 30s behind.
"""

import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger("ch8.db_failover")

CONFIG_DIR = Path.home() / ".config" / "ch8"
PID_FILE = CONFIG_DIR / "db_failover.pid"
LOG_FILE = CONFIG_DIR / "db_failover.log"
STATE_FILE = CONFIG_DIR / "db_failover_state.json"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Database endpoints (credentials from env)
MASTER_HOST = "127.0.0.1"
MASTER_PORT = 5432
_db_pass = os.environ.get("CH8_DB_PASSWORD", "")
if not _db_pass:
    _ef = Path.home() / ".config" / "ch8" / "env"
    if _ef.exists():
        for _l in _ef.read_text().splitlines():
            if _l.startswith("CH8_DB_PASSWORD="):
                _db_pass = _l.split("=", 1)[1].strip()
                break
    if not _db_pass:
        _db_pass = "ch8cluster2024"  # last resort fallback
MASTER_CONN = f"postgresql://ch8app:{_db_pass}@{MASTER_HOST}:{MASTER_PORT}/ch8_cluster"

REPLICA_HOST = os.environ.get("CH8_REPLICA_HOST", "100.65.70.126")
REPLICA_PORT = 5432
REPLICA_CONN = f"postgresql://allied:allied_secure_2026@{REPLICA_HOST}:{REPLICA_PORT}/ch8_cluster"

# Thresholds
CHECK_INTERVAL = 30  # seconds
FAIL_THRESHOLD = 3   # consecutive failures before action
LAG_ALERT_SECONDS = 30
MAX_LAG_CRITICAL = 120

running = True


def signal_handler(sig, frame):
    global running
    running = False


def _check_postgres(host, port, user="ch8app", password="ch8cluster2024", dbname="ch8_cluster"):
    """Check if PostgreSQL is reachable and responding."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=host, port=port, user=user, password=password,
            dbname=dbname, connect_timeout=5
        )
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        conn.close()
        return {"ok": True, "latency_ms": 0}
    except ImportError:
        # Fallback: use pg_isready (checks TCP connectivity, not auth)
        try:
            result = subprocess.run(
                ["pg_isready", "-h", host, "-p", str(port), "-t", "5"],
                capture_output=True, text=True, timeout=8
            )
            return {"ok": result.returncode == 0, "latency_ms": 0}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    except Exception as e:
        error_msg = str(e).lower()
        # Auth error = server is UP but credentials wrong (not really "down")
        if "password authentication failed" in error_msg or "role" in error_msg:
            return {"ok": True, "latency_ms": 0, "auth_error": True,
                    "warning": "Server reachable but auth failed — check credentials"}
        # Connection refused = server truly down
        if "connection refused" in error_msg or "could not connect" in error_msg:
            return {"ok": False, "error": f"Connection refused: {host}:{port}"}
        # Timeout = network issue
        if "timeout" in error_msg:
            return {"ok": False, "error": f"Timeout connecting to {host}:{port}"}
        return {"ok": False, "error": str(e)}


def _check_replication_lag():
    """Check replication lag on master."""
    try:
        import psycopg2
        conn = psycopg2.connect(MASTER_CONN, connect_timeout=5)
        cur = conn.cursor()
        cur.execute("""
            SELECT client_addr, state,
                   EXTRACT(EPOCH FROM replay_lag)::int as lag_seconds,
                   sent_lsn::text, replay_lsn::text
            FROM pg_stat_replication LIMIT 1
        """)
        row = cur.fetchone()
        conn.close()
        if row:
            return {
                "replica_addr": str(row[0]),
                "state": row[1],
                "lag_seconds": row[2] or 0,
                "sent_lsn": row[3],
                "replay_lsn": row[4],
            }
        return {"state": "no_replica", "lag_seconds": -1}
    except Exception as e:
        return {"state": "error", "error": str(e), "lag_seconds": -1}


def _promote_replica():
    """Promote the replica to standalone primary."""
    log.critical("PROMOTING REPLICA TO PRIMARY!")
    try:
        # Send promote command to replica via orchestrator on vmi
        import httpx
        r = httpx.post(f"http://{REPLICA_HOST}:7879/execute", json={
            "name": "shell_exec",
            "args": {"command": "docker exec allied-postgres pg_ctl promote -D /var/lib/postgresql/data 2>&1 || docker exec allied-postgres psql -U allied -d ch8_cluster -c 'SELECT pg_promote();'"}
        }, timeout=15)
        result = r.json().get("result", {}).get("stdout", "")
        log.critical(f"Promote result: {result}")
        return True
    except Exception as e:
        log.critical(f"Promote failed: {e}")
        return False


def _notify_failover(new_primary_host):
    """Notify all nodes that the primary DB has changed."""
    log.critical(f"Notifying cluster: new primary is {new_primary_host}")
    try:
        from connect.db import log_event
        log_event("db_failover", f"Primary DB failed over to {new_primary_host}",
                  severity="critical",
                  details={"new_primary": new_primary_host, "timestamp": time.time()})
    except Exception:
        pass

    # Write failover state so other components know
    failover_info = {
        "primary_host": new_primary_host,
        "primary_port": REPLICA_PORT,
        "failover_at": int(time.time()),
        "reason": "master_unreachable",
    }
    (CONFIG_DIR / "db_primary.json").write_text(json.dumps(failover_info, indent=2))

    # Try to notify via cluster broadcast
    try:
        import httpx
        httpx.post("http://127.0.0.1:7879/cluster/task", json={
            "task": f"ALERT: Database primary has been failed over to {new_primary_host}. Update your DB connections.",
            "strategy": "broadcast"
        }, timeout=5)
    except Exception:
        pass


def _restart_master():
    """Attempt to restart local PostgreSQL."""
    log.warning("Attempting to restart local PostgreSQL...")
    try:
        result = subprocess.run(
            ["sudo", "systemctl", "restart", "postgresql"],
            capture_output=True, text=True, timeout=30
        )
        time.sleep(5)
        check = _check_postgres(MASTER_HOST, MASTER_PORT)
        if check["ok"]:
            log.info("Master PostgreSQL restarted successfully!")
            return True
        log.error(f"Master restart failed: still unreachable")
        return False
    except Exception as e:
        log.error(f"Restart failed: {e}")
        return False


def _update_state(status, task, details=None):
    try:
        from connect.state import update_agent_state
        update_agent_state("db_failover", status, task,
                           model="ha-monitor", platform="postgresql",
                           autonomous=True,
                           tools=["check_master", "check_replica", "promote", "restart"],
                           details=details or {})
    except Exception:
        pass


def _load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"master_failures": 0, "replica_failures": 0, "failover_count": 0, "last_failover": 0}


def _save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def main():
    global running
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])

    PID_FILE.write_text(str(os.getpid()))
    log.info("DB Failover Agent starting")
    log.info(f"  Master: {MASTER_HOST}:{MASTER_PORT}")
    log.info(f"  Replica: {REPLICA_HOST}:{REPLICA_PORT}")

    state = _load_state()

    while running:
        try:
            # Check master
            master_check = _check_postgres(MASTER_HOST, MASTER_PORT)
            # Check replica
            replica_check = _check_postgres(REPLICA_HOST, REPLICA_PORT,
                                            user="allied", password="allied_secure_2026")
            # Check replication lag (only if master is up)
            repl_info = {}
            if master_check["ok"]:
                repl_info = _check_replication_lag()

            # Update counters
            if master_check["ok"]:
                state["master_failures"] = 0
            else:
                state["master_failures"] = state.get("master_failures", 0) + 1
                log.warning(f"Master UNREACHABLE ({state['master_failures']}/{FAIL_THRESHOLD})")

            if replica_check["ok"]:
                state["replica_failures"] = 0
            else:
                state["replica_failures"] = state.get("replica_failures", 0) + 1
                log.warning(f"Replica UNREACHABLE ({state['replica_failures']})")

            # Decision logic
            details = {
                "master": "up" if master_check["ok"] else "DOWN",
                "replica": "up" if replica_check["ok"] else "DOWN",
                "replication": repl_info.get("state", "unknown"),
                "lag_seconds": repl_info.get("lag_seconds", -1),
                "master_failures": state["master_failures"],
                "failover_count": state.get("failover_count", 0),
            }

            # SCENARIO 1: Master down, replica up → FAILOVER
            if state["master_failures"] >= FAIL_THRESHOLD and replica_check["ok"]:
                # First try restart
                if state["master_failures"] == FAIL_THRESHOLD:
                    log.critical("Master down! Attempting restart before failover...")
                    if _restart_master():
                        state["master_failures"] = 0
                        _update_state("running", "Master recovered after restart", details)
                        _save_state(state)
                        time.sleep(CHECK_INTERVAL)
                        continue

                # Restart failed → promote replica
                log.critical(f"FAILOVER TRIGGERED — promoting {REPLICA_HOST}")
                promoted = _promote_replica()
                if promoted:
                    _notify_failover(REPLICA_HOST)
                    state["failover_count"] = state.get("failover_count", 0) + 1
                    state["last_failover"] = int(time.time())
                    state["master_failures"] = 0
                    _update_state("warning", f"FAILOVER to {REPLICA_HOST}!", details)
                else:
                    _update_state("error", "Failover FAILED — manual intervention needed", details)

            # SCENARIO 2: Both down → critical alert
            elif state["master_failures"] >= FAIL_THRESHOLD and not replica_check["ok"]:
                _update_state("error", "CRITICAL: Both master AND replica are DOWN!", details)
                log.critical("BOTH DATABASES DOWN! Manual intervention required!")

            # SCENARIO 3: Replication lag alert
            elif repl_info.get("lag_seconds", 0) > LAG_ALERT_SECONDS:
                lag = repl_info["lag_seconds"]
                severity = "error" if lag > MAX_LAG_CRITICAL else "warning"
                _update_state(severity, f"Replication lag: {lag}s behind!", details)
                log.warning(f"Replication lag: {lag}s (threshold: {LAG_ALERT_SECONDS}s)")

            # SCENARIO 4: All healthy
            elif master_check["ok"] and replica_check["ok"]:
                lag = repl_info.get("lag_seconds", 0)
                _update_state("running",
                              f"Healthy — master OK, replica streaming (lag: {lag}s)", details)

            # SCENARIO 5: Master up, replica down
            elif master_check["ok"] and not replica_check["ok"]:
                _update_state("warning", "Replica unreachable — no redundancy!", details)

            _save_state(state)

        except Exception as ex:
            log.error(f"Check cycle error: {ex}")
            _update_state("error", str(ex)[:80])

        for _ in range(CHECK_INTERVAL):
            if not running:
                break
            time.sleep(1)

    _update_state("idle", "Stopped")
    PID_FILE.unlink(missing_ok=True)
    log.info("DB Failover Agent stopped")


if __name__ == "__main__":
    main()
