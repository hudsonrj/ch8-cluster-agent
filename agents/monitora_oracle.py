#!/usr/bin/env python3
import json
import logging
import signal
import sys
import time
import subprocess
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from connect.state import update_agent_state

CONFIG_DIR = Path.home() / ".config" / "ch8"
PID_FILE = CONFIG_DIR / "monitora_oracle.pid"
LOG_FILE = CONFIG_DIR / "monitora_oracle.log"
STATE_FILE = CONFIG_DIR / "state.json"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger("monitora_oracle")

running = True

def signal_handler(signum, frame):
    global running
    logger.info(f"Received signal {signum}, shutting down...")
    running = False

def write_pid():
    PID_FILE.write_text(str(subprocess.os.getpid()))

def remove_pid():
    PID_FILE.unlink(missing_ok=True)

def check_container_health():
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format={{.State.Health.Status}}", "oracle-free"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return "unknown"
    except Exception as e:
        logger.error(f"Error checking container health: {e}")
        return "error"

def _oracle_sql(query):
    """Execute SQL on Oracle via docker exec + sqlplus as sysdba."""
    sql = f"SET PAGESIZE 0 FEEDBACK OFF VERIFY OFF HEADING OFF ECHO OFF\n{query}\nEXIT;"
    cmd = f"echo \"{sql}\" | sqlplus -s / as sysdba"
    result = subprocess.run(
        ["docker", "exec", "oracle-free", "bash", "-c", cmd],
        capture_output=True, text=True, timeout=15
    )
    return result.stdout.strip() if result.returncode == 0 else ""

def check_active_connections():
    try:
        out = _oracle_sql("SELECT COUNT(*) FROM v\\$session WHERE status='ACTIVE';")
        for line in out.split('\n'):
            line = line.strip()
            if line.isdigit():
                return int(line)
        return 0
    except Exception as e:
        logger.error(f"Error checking connections: {e}")
        return -1

def check_tablespace_usage():
    try:
        out = _oracle_sql(
            "SELECT tablespace_name || ': ' || ROUND(used_percent,1) || '%' "
            "FROM dba_tablespace_usage_metrics WHERE used_percent > 0 ORDER BY used_percent DESC FETCH FIRST 5 ROWS ONLY;"
        )
        return out if out else "N/A"
    except Exception as e:
        logger.error(f"Error checking tablespace: {e}")
        return "error"

def main():
    global running
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    write_pid()
    logger.info("monitora_oracle agent started")
    
    last_state_update = 0
    
    try:
        while running:
            health = check_container_health()
            connections = check_active_connections()
            tablespace = check_tablespace_usage()
            
            status = "healthy"
            alerts = []
            
            if health != "healthy":
                status = "unhealthy"
                alerts.append(f"Container unhealthy: {health}")
            
            if connections > 100:
                status = "warning"
                alerts.append(f"High connections: {connections}")
            
            metrics = {
                "health": health,
                "active_connections": connections,
                "tablespace_usage": tablespace,
                "status": status,
                "alerts": alerts,
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"Metrics: {json.dumps(metrics)}")
            
            if time.time() - last_state_update >= 30:
                task_str = f"{status} | {metrics.get('active_connections',0)} sessions | SYSTEM {metrics.get('tablespace_usage','').split(chr(10))[0] if metrics.get('tablespace_usage') else 'N/A'}"
                update_agent_state("monitora_oracle", status, task_str,
                                   model="oracle-monitor", platform="custom",
                                   autonomous=True, details=metrics)
                last_state_update = time.time()
            
            time.sleep(60)
    
    finally:
        remove_pid()
        logger.info("monitora_oracle agent stopped")

if __name__ == "__main__":
    main()
