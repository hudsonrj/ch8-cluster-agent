"""
Log Shipper Agent — Collects logs from all services on this node and ships them to PostgreSQL.

Sources: syslog, docker containers, nginx, application logs.
Destination: ch8_cluster.node_logs on master (100.120.31.61:5432).
Interval: every 60s, ships new lines since last checkpoint.
"""

import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger("ch8.log_shipper")

CONFIG_DIR = Path.home() / ".config" / "ch8"
PID_FILE = CONFIG_DIR / "log_shipper.pid"
LOG_FILE = CONFIG_DIR / "log_shipper.log"
CHECKPOINT_FILE = CONFIG_DIR / "log_shipper_checkpoint.json"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Database connection (tries master first, then local)
DB_URLS = [
    "postgresql://ch8app:ch8cluster2024@127.0.0.1:5432/ch8_cluster",
    "postgresql://ch8app:ch8cluster2024@100.120.31.61:5432/ch8_cluster",
]

SHIP_INTERVAL = 60  # seconds
MAX_LINES_PER_SOURCE = 200  # prevent flooding
running = True


def signal_handler(sig, frame):
    global running
    running = False


def _get_node_info():
    """Get node_id and hostname."""
    try:
        from connect.auth import get_node_id
        node_id = get_node_id()
    except Exception:
        node_id = f"node_{os.uname().nodename}"
    hostname = os.uname().nodename
    return node_id, hostname


def _get_db_conn():
    """Get PostgreSQL connection (try multiple URLs)."""
    try:
        import psycopg2
    except ImportError:
        return None
    for url in DB_URLS:
        try:
            conn = psycopg2.connect(url, connect_timeout=5)
            return conn
        except Exception:
            continue
    return None


def _load_checkpoint():
    try:
        return json.loads(CHECKPOINT_FILE.read_text())
    except Exception:
        return {}


def _save_checkpoint(cp):
    CHECKPOINT_FILE.write_text(json.dumps(cp))


def _parse_level(line):
    """Extract log level from a line."""
    ll = line.lower()
    if any(k in ll for k in ['error', 'err]', 'fatal', 'crit']):
        return 'error'
    if any(k in ll for k in ['warn', 'warning']):
        return 'warning'
    if any(k in ll for k in ['debug', 'trace']):
        return 'debug'
    return 'info'


def collect_syslog(checkpoint):
    """Collect from /var/log/syslog or /var/log/messages."""
    entries = []
    for path in ['/var/log/syslog', '/var/log/messages', '/var/log/system.log']:
        if not os.path.exists(path):
            continue
        try:
            # Read only new lines since last position
            last_pos = checkpoint.get(f'syslog_{path}', 0)
            with open(path, 'r', errors='ignore') as f:
                f.seek(0, 2)  # end
                size = f.tell()
                if last_pos > size:
                    last_pos = 0  # file was rotated
                f.seek(last_pos)
                lines = f.readlines()[-MAX_LINES_PER_SOURCE:]
                new_pos = f.tell()
            checkpoint[f'syslog_{path}'] = new_pos
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                entries.append({
                    'source': os.path.basename(path),
                    'level': _parse_level(line),
                    'message': line[:2000],
                    'logged_at': datetime.now(timezone.utc).isoformat(),
                })
        except Exception:
            pass
    return entries


def collect_docker_logs(checkpoint):
    """Collect recent logs from Docker containers."""
    entries = []
    try:
        result = subprocess.run(
            ['docker', 'ps', '--format', '{{.Names}}'],
            capture_output=True, text=True, timeout=5)
        containers = [c.strip() for c in result.stdout.strip().split('\n') if c.strip()]
    except Exception:
        return entries

    last_ts = checkpoint.get('docker_ts', '60s')

    for container in containers[:15]:  # limit to 15 containers
        try:
            result = subprocess.run(
                ['docker', 'logs', '--since', last_ts, '--tail', '50', container],
                capture_output=True, text=True, timeout=10)
            output = (result.stdout + result.stderr).strip()
            for line in output.split('\n')[-MAX_LINES_PER_SOURCE:]:
                line = line.strip()
                if not line:
                    continue
                level = _parse_level(line)
                if level in ('error', 'warning'):  # only ship errors/warnings from docker
                    entries.append({
                        'source': f'docker:{container}',
                        'level': level,
                        'message': line[:2000],
                        'logged_at': datetime.now(timezone.utc).isoformat(),
                    })
        except Exception:
            pass

    checkpoint['docker_ts'] = '60s'
    return entries


def collect_nginx_errors(checkpoint):
    """Collect from nginx error logs."""
    entries = []
    log_paths = ['/var/log/nginx/error.log']
    # Also check per-site error logs
    try:
        for f in os.listdir('/var/log/nginx/'):
            if 'error' in f and f.endswith('.log'):
                log_paths.append(f'/var/log/nginx/{f}')
    except Exception:
        pass

    for path in log_paths:
        if not os.path.exists(path):
            continue
        try:
            last_pos = checkpoint.get(f'nginx_{path}', 0)
            with open(path, 'r', errors='ignore') as f:
                f.seek(0, 2)
                size = f.tell()
                if last_pos > size:
                    last_pos = 0
                f.seek(last_pos)
                lines = f.readlines()[-MAX_LINES_PER_SOURCE:]
                new_pos = f.tell()
            checkpoint[f'nginx_{path}'] = new_pos
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                entries.append({
                    'source': f'nginx:{os.path.basename(path)}',
                    'level': _parse_level(line),
                    'message': line[:2000],
                    'logged_at': datetime.now(timezone.utc).isoformat(),
                })
        except Exception:
            pass
    return entries


def collect_agent_logs(checkpoint):
    """Collect error lines from ch8 agent logs."""
    entries = []
    log_dir = CONFIG_DIR
    for lf in log_dir.glob('*.log'):
        if lf.name == 'log_shipper.log':
            continue
        try:
            last_pos = checkpoint.get(f'agent_{lf.name}', 0)
            with open(lf, 'r', errors='ignore') as f:
                f.seek(0, 2)
                size = f.tell()
                if last_pos > size:
                    last_pos = 0
                f.seek(last_pos)
                lines = f.readlines()[-50:]
                new_pos = f.tell()
            checkpoint[f'agent_{lf.name}'] = new_pos
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                level = _parse_level(line)
                if level in ('error', 'warning'):
                    entries.append({
                        'source': f'agent:{lf.stem}',
                        'level': level,
                        'message': line[:2000],
                        'logged_at': datetime.now(timezone.utc).isoformat(),
                    })
        except Exception:
            pass
    return entries


def ship_logs(entries, node_id, hostname):
    """Send log entries to PostgreSQL."""
    if not entries:
        return 0
    conn = _get_db_conn()
    if not conn:
        log.warning("Cannot connect to DB — logs will retry next cycle")
        return 0
    try:
        cur = conn.cursor()
        # Batch insert
        values = []
        for e in entries:
            # Sanitize: remove NUL bytes
            msg = e['message'].replace('\x00', '').strip()
            if not msg:
                continue
            values.append(cur.mogrify(
                "(%s, %s, %s, %s, %s, %s, %s)",
                (node_id, hostname, e['source'], e['level'], msg,
                 json.dumps(e.get('metadata', {})), e['logged_at'])
            ).decode())
        if values:
            cur.execute(
                "INSERT INTO node_logs (node_id, hostname, source, level, message, metadata, logged_at) VALUES " +
                ",".join(values)
            )
            conn.commit()
        conn.close()
        return len(entries)
    except Exception as ex:
        log.error(f"Ship failed: {ex}")
        try:
            conn.close()
        except Exception:
            pass
        return 0


def _update_state(status, task):
    try:
        from connect.state import update_agent_state
        update_agent_state("log_shipper", status, task,
                           model="log-collector", platform="psutil",
                           tools=["collect_syslog", "collect_docker", "collect_nginx"])
    except Exception:
        pass


def main():
    global running
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])

    PID_FILE.write_text(str(os.getpid()))
    log.info("Log Shipper starting")

    node_id, hostname = _get_node_info()
    _update_state("running", f"Shipping logs from {hostname}")

    while running:
        try:
            checkpoint = _load_checkpoint()

            # Collect from all sources
            entries = []
            entries.extend(collect_syslog(checkpoint))
            entries.extend(collect_docker_logs(checkpoint))
            entries.extend(collect_nginx_errors(checkpoint))
            entries.extend(collect_agent_logs(checkpoint))

            # Ship to PostgreSQL
            shipped = ship_logs(entries, node_id, hostname)

            # Save checkpoint
            _save_checkpoint(checkpoint)

            # Update state
            errors = sum(1 for e in entries if e['level'] == 'error')
            warnings = sum(1 for e in entries if e['level'] == 'warning')
            _update_state("running",
                          f"Shipped {shipped} logs ({errors} err, {warnings} warn) from {hostname}")

            if shipped > 0:
                log.info(f"Shipped {shipped} log entries ({errors} errors, {warnings} warnings)")

        except Exception as ex:
            log.error(f"Cycle error: {ex}")
            _update_state("error", str(ex)[:80])

        # Wait for next cycle
        for _ in range(SHIP_INTERVAL):
            if not running:
                break
            time.sleep(1)

    _update_state("idle", "Stopped")
    PID_FILE.unlink(missing_ok=True)
    log.info("Log Shipper stopped")


if __name__ == "__main__":
    main()
