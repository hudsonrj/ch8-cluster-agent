"""
Log Analyzer Agent — Analyzes collected logs, identifies recurring issues,
generates backlog items for fix_agent to resolve automatically.

Flow:
1. Every 5 minutes, queries node_logs in PostgreSQL
2. Groups errors by pattern (source + message similarity)
3. For actionable errors, generates a backlog item with:
   - Problem description
   - Affected node
   - Suggested fix command
4. Writes to /data2/backlog/ for fix_agent to pick up
5. Skips already-known issues (dedup via pattern hash)

Actionable patterns:
- Connection refused → restart service
- Disk full → cleanup old logs/docker images
- OOM / killed → increase limits or move workload
- Permission denied → fix ownership
- Certificate expired → renew cert
"""

import json
import hashlib
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger("ch8.log_analyzer")

CONFIG_DIR = Path.home() / ".config" / "ch8"
PID_FILE = CONFIG_DIR / "log_analyzer.pid"
LOG_FILE = CONFIG_DIR / "log_analyzer.log"
BACKLOG_DIR = Path("/data2/backlog")
KNOWN_FILE = CONFIG_DIR / "log_analyzer_known.json"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
BACKLOG_DIR.mkdir(parents=True, exist_ok=True)

CHECK_INTERVAL = 300  # 5 minutes
DB_URL = "postgresql://ch8app:ch8cluster2024@127.0.0.1:5432/ch8_cluster"

running = True

# Patterns that are actionable (regex-like matching + fix templates)
ACTIONABLE_PATTERNS = [
    {
        "match": "connect() failed (111: Connection refused)",
        "category": "service_down",
        "severity": "high",
        "fix_template": "docker restart {service} || systemctl restart {service}",
        "description": "Service unreachable — needs restart",
    },
    {
        "match": "No space left on device",
        "category": "disk_full",
        "severity": "critical",
        "fix_template": "docker system prune -f && journalctl --vacuum-size=100M && find /var/log -name '*.gz' -mtime +7 -delete",
        "description": "Disk full — cleanup needed",
    },
    {
        "match": "Out of memory",
        "category": "oom",
        "severity": "critical",
        "fix_template": "echo 1 > /proc/sys/vm/drop_caches && docker stats --no-stream | sort -k4 -rn | head -5",
        "description": "OOM — memory pressure, needs investigation",
    },
    {
        "match": "Permission denied",
        "category": "permissions",
        "severity": "medium",
        "fix_template": "# Check ownership: ls -la {path}",
        "description": "Permission denied — ownership/mode issue",
    },
    {
        "match": "certificate has expired",
        "category": "cert_expired",
        "severity": "high",
        "fix_template": "certbot renew --force-renewal",
        "description": "SSL certificate expired — needs renewal",
    },
    {
        "match": "too many open files",
        "category": "ulimit",
        "severity": "medium",
        "fix_template": "ulimit -n 65535 && sysctl -w fs.file-max=100000",
        "description": "File descriptor limit reached",
    },
    {
        "match": "upstream timed out",
        "category": "upstream_slow",
        "severity": "medium",
        "fix_template": "# Check upstream health and increase proxy_read_timeout",
        "description": "Upstream service too slow",
    },
]


def signal_handler(sig, frame):
    global running
    running = False


def _get_db_conn():
    try:
        import psycopg2
        return psycopg2.connect(DB_URL, connect_timeout=5)
    except Exception:
        return None


def _load_known():
    try:
        return json.loads(KNOWN_FILE.read_text())
    except Exception:
        return {}


def _save_known(known):
    KNOWN_FILE.write_text(json.dumps(known))


def _pattern_hash(source, message_pattern):
    """Generate a unique hash for a log pattern."""
    key = f"{source}:{message_pattern[:100]}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def _extract_service(message, source):
    """Try to extract the affected service name from the log message."""
    if "upstream" in message and "connecting to" in message:
        # nginx upstream error — extract backend
        parts = message.split("upstream")
        if len(parts) > 1:
            return source.split(":")[0] if ":" in source else "nginx"
    if "docker" in source.lower():
        return source.split(":")[-1] if ":" in source else "docker"
    return source.split(":")[0] if ":" in source else "unknown"


def analyze_logs():
    """Query recent error logs and find actionable patterns."""
    conn = _get_db_conn()
    if not conn:
        log.warning("Cannot connect to database")
        return []

    try:
        cur = conn.cursor()
        # Get error logs from last 10 minutes, grouped by pattern
        cur.execute("""
            SELECT hostname, source, level,
                   LEFT(message, 200) as msg_pattern,
                   count(*) as cnt,
                   max(logged_at) as last_seen
            FROM node_logs
            WHERE level IN ('error', 'warning')
              AND logged_at > NOW() - INTERVAL '10 minutes'
            GROUP BY hostname, source, level, LEFT(message, 200)
            HAVING count(*) >= 3
            ORDER BY cnt DESC
            LIMIT 20
        """)

        issues = []
        for row in cur.fetchall():
            hostname, source, level, message, count, last_seen = row
            issues.append({
                "hostname": hostname,
                "source": source,
                "level": level,
                "message": message,
                "count": count,
                "last_seen": str(last_seen),
            })
        conn.close()
        return issues
    except Exception as e:
        log.error(f"Query failed: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return []


def match_pattern(message):
    """Match a log message against actionable patterns."""
    for pattern in ACTIONABLE_PATTERNS:
        if pattern["match"].lower() in message.lower():
            return pattern
    return None


def _create_itsm_ticket(issue, pattern, fix_cmd, phash):
    """Create an ITSM ticket in PostgreSQL for the detected issue."""
    try:
        from connect.db import create_ticket

        severity = pattern["severity"]
        title = f"[{issue['hostname']}] {pattern['description']}"
        description = (
            f"Padrao detectado: {pattern['match']}\n"
            f"Mensagem original: {issue['message'][:300]}\n"
            f"Fonte: {issue['source']}\n"
            f"Ocorrencias: {issue['count']} nos ultimos 10 min"
        )
        impact = f"Servico afetado no node {issue['hostname']} — {issue['count']} ocorrencias recentes"
        action_plan = f"1. Verificar status do servico\n2. Executar fix: {fix_cmd}\n3. Validar resolucao"

        ticket_id = create_ticket(
            title=title,
            description=description,
            severity=severity,
            category=pattern["category"],
            node=issue["hostname"],
            service=_extract_service(issue["message"], issue["source"]),
            root_cause=pattern["description"],
            impact=impact,
            action_plan=action_plan,
            fix_command=fix_cmd,
            source_type="log_pattern",
            source_ref=phash,
        )
        if ticket_id:
            log.info(f"Created ITSM ticket: {ticket_id} ({pattern['category']} on {issue['hostname']})")
        return ticket_id
    except Exception as e:
        log.warning(f"Failed to create ITSM ticket: {e}")
        return None


def create_backlog_item(issue, pattern, known):
    """Create a backlog item for the fix_agent AND an ITSM ticket."""
    phash = _pattern_hash(issue["source"], issue["message"])

    # Skip if already known and recent (< 1 hour)
    if phash in known:
        last_created = known[phash].get("created_at", 0)
        if time.time() - last_created < 3600:
            return None

    service = _extract_service(issue["message"], issue["source"])
    fix_cmd = pattern["fix_template"].format(
        service=service,
        path=issue.get("path", "/unknown"),
    )

    # Create ITSM ticket in database
    _create_itsm_ticket(issue, pattern, fix_cmd, phash)

    # Create backlog item (legacy)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    item_name = f"{ts}_auto-fix-{pattern['category']}-{issue['hostname']}"
    item = {
        "project": f"auto-fix-{pattern['category']}",
        "error": f"[{issue['hostname']}] {issue['message'][:300]}",
        "context": (
            f"Source: {issue['source']}\n"
            f"Node: {issue['hostname']}\n"
            f"Occurrences: {issue['count']} in last 10 min\n"
            f"Last seen: {issue['last_seen']}\n"
            f"Category: {pattern['category']}\n"
            f"Severity: {pattern['severity']}\n"
            f"Suggested fix: {fix_cmd}"
        ),
        "created_at": datetime.now().isoformat(),
        "status": "open",
        "attempts": 0,
        "auto_generated": True,
        "node": issue["hostname"],
        "category": pattern["category"],
        "severity": pattern["severity"],
        "fix_command": fix_cmd,
    }

    # Write to backlog
    item_path = BACKLOG_DIR / f"{item_name}.json"
    item_path.write_text(json.dumps(item, indent=2))

    # Mark as known
    known[phash] = {"created_at": time.time(), "item": item_name, "category": pattern["category"]}
    _save_known(known)

    log.info(f"Created backlog: {item_name} ({pattern['category']} on {issue['hostname']})")
    return item_name


def _update_state(status, task):
    try:
        from connect.state import update_agent_state
        update_agent_state("log_analyzer", status, task,
                           model="pattern-matcher", platform="postgresql",
                           autonomous=True,
                           tools=["analyze_logs", "create_backlog"])
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
    log.info("Log Analyzer starting")
    _update_state("running", "Analyzing logs for actionable patterns")

    while running:
        try:
            # Only execute if this node is the elected master
            try:
                from connect.cluster_ha import is_master
                if not is_master():
                    _update_state("idle", "Standby — não sou o master")
                    for _ in range(CHECK_INTERVAL):
                        if not running: break
                        time.sleep(1)
                    continue
            except Exception:
                pass  # If HA check fails, proceed anyway (single-node mode)

            known = _load_known()
            issues = analyze_logs()
            created = 0

            for issue in issues:
                pattern = match_pattern(issue["message"])
                if pattern:
                    result = create_backlog_item(issue, pattern, known)
                    if result:
                        created += 1

            if created:
                _update_state("running", f"Created {created} backlog item(s) from log analysis")
                log.info(f"Cycle done: {len(issues)} issues found, {created} new backlog items")
            else:
                _update_state("running", f"Monitoring — {len(issues)} patterns, no new issues")

        except Exception as e:
            log.error(f"Cycle error: {e}")
            _update_state("error", str(e)[:80])

        for _ in range(CHECK_INTERVAL):
            if not running:
                break
            time.sleep(1)

    _update_state("idle", "Stopped")
    PID_FILE.unlink(missing_ok=True)
    log.info("Log Analyzer stopped")


if __name__ == "__main__":
    main()
