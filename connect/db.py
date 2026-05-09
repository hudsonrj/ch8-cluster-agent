"""
CH8 Cluster — PostgreSQL persistence layer.

Stores: chat messages, agent states, node metrics, cluster events,
broadcast results, SLA checks.

Connection: postgresql://ch8app:ch8cluster2024@127.0.0.1:5432/ch8_cluster
Replica: configured via PostgreSQL streaming replication to vmi3201672.
"""

import os
import logging
import time
from typing import Optional, Dict, List
from contextlib import contextmanager

log = logging.getLogger("ch8.db")

DB_URL = os.environ.get("CH8_DB_URL", "postgresql://ch8app:ch8cluster2024@127.0.0.1:5432/ch8_cluster")

_pool = None


def _get_conn():
    """Get a database connection (lazy pool init)."""
    global _pool
    if _pool is None:
        try:
            import psycopg2
            from psycopg2 import pool as pg_pool
            _pool = pg_pool.ThreadedConnectionPool(1, 5, DB_URL)
        except Exception as e:
            log.warning(f"DB connection failed: {e}")
            return None
    try:
        return _pool.getconn()
    except Exception:
        _pool = None
        return None


def _put_conn(conn):
    if _pool and conn:
        try:
            _pool.putconn(conn)
        except Exception:
            pass


@contextmanager
def get_db():
    conn = _get_conn()
    if not conn:
        yield None
        return
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        log.error(f"DB error: {e}")
    finally:
        _put_conn(conn)


# ═══════════════════════════════════════════════════════════════
# Chat Messages
# ═══════════════════════════════════════════════════════════════

def save_chat_message(node_id: str, role: str, content: str,
                      session_id: str = "", model: str = "",
                      tokens: int = 0, latency_ms: int = 0):
    with get_db() as conn:
        if not conn:
            return
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO chat_messages (node_id, session_id, role, content, model, tokens_used, latency_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (node_id, session_id or f"s_{int(time.time())}", role, content, model, tokens, latency_ms))


def get_chat_history(node_id: str, limit: int = 50) -> List[Dict]:
    with get_db() as conn:
        if not conn:
            return []
        cur = conn.cursor()
        cur.execute("""
            SELECT role, content, model, created_at FROM chat_messages
            WHERE node_id = %s ORDER BY created_at DESC LIMIT %s
        """, (node_id, limit))
        return [{"role": r[0], "content": r[1], "model": r[2], "ts": str(r[3])} for r in reversed(cur.fetchall())]


# ═══════════════════════════════════════════════════════════════
# Agent States
# ═══════════════════════════════════════════════════════════════

def save_agent_state(node_id: str, agent_name: str, status: str,
                     task: str = "", model: str = "", platform: str = "",
                     details: dict = None):
    with get_db() as conn:
        if not conn:
            return
        cur = conn.cursor()
        import json
        cur.execute("""
            INSERT INTO agent_states (node_id, agent_name, status, task, model, platform, details)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (node_id, agent_name, status, task, model, platform, json.dumps(details or {})))


# ═══════════════════════════════════════════════════════════════
# Node Metrics
# ═══════════════════════════════════════════════════════════════

def save_node_metrics(node_id: str, hostname: str, cpu_pct: float,
                      mem_pct: float, disk_pct: float, load_avg: float = 0,
                      services_count: int = 0, agents_count: int = 0,
                      version: str = ""):
    with get_db() as conn:
        if not conn:
            return
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO node_metrics (node_id, hostname, cpu_pct, mem_pct, disk_pct, load_avg, services_count, agents_count, version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (node_id, hostname, cpu_pct, mem_pct, disk_pct, load_avg, services_count, agents_count, version))


# ═══════════════════════════════════════════════════════════════
# Cluster Events
# ═══════════════════════════════════════════════════════════════

def log_event(event_type: str, message: str, severity: str = "info",
              node_id: str = "", agent_name: str = "", details: dict = None):
    with get_db() as conn:
        if not conn:
            return
        cur = conn.cursor()
        import json
        cur.execute("""
            INSERT INTO cluster_events (event_type, severity, node_id, agent_name, message, details)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (event_type, severity, node_id, agent_name, message, json.dumps(details or {})))


# ═══════════════════════════════════════════════════════════════
# Broadcast Results
# ═══════════════════════════════════════════════════════════════

def save_broadcast(task: str, strategy: str, nodes_used: int,
                   nodes_failed: int, elapsed_s: float, results: list):
    with get_db() as conn:
        if not conn:
            return
        cur = conn.cursor()
        import json
        cur.execute("""
            INSERT INTO broadcast_results (task, strategy, nodes_used, nodes_failed, elapsed_s, results)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (task, strategy, nodes_used, nodes_failed, elapsed_s, json.dumps(results)))


# ═══════════════════════════════════════════════════════════════
# SLA Checks
# ═══════════════════════════════════════════════════════════════

def save_sla_check(node_id: str, hostname: str, is_online: bool, response_ms: int = 0):
    with get_db() as conn:
        if not conn:
            return
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO sla_checks (node_id, hostname, is_online, response_ms)
            VALUES (%s, %s, %s, %s)
        """, (node_id, hostname, is_online, response_ms))


def get_sla_stats(days: int = 7) -> Dict[str, Dict]:
    """Get uptime % per node over the last N days."""
    with get_db() as conn:
        if not conn:
            return {}
        cur = conn.cursor()
        cur.execute("""
            SELECT hostname,
                   COUNT(*) as total,
                   SUM(CASE WHEN is_online THEN 1 ELSE 0 END) as online_count
            FROM sla_checks
            WHERE checked_at > NOW() - INTERVAL '%s days'
            GROUP BY hostname
        """, (days,))
        result = {}
        for row in cur.fetchall():
            total = row[1]
            online = row[2]
            result[row[0]] = {"total_checks": total, "online": online,
                              "uptime_pct": round(online * 100 / total, 2) if total > 0 else 0}
        return result


# ═══════════════════════════════════════════════════════════════
# Cleanup (retention)
# ═══════════════════════════════════════════════════════════════

def cleanup_old_data(metrics_days: int = 30, events_days: int = 90,
                     chat_days: int = 365, sla_days: int = 90):
    """Remove old data to keep DB size manageable."""
    with get_db() as conn:
        if not conn:
            return
        cur = conn.cursor()
        cur.execute("DELETE FROM node_metrics WHERE recorded_at < NOW() - INTERVAL '%s days'", (metrics_days,))
        cur.execute("DELETE FROM cluster_events WHERE created_at < NOW() - INTERVAL '%s days'", (events_days,))
        cur.execute("DELETE FROM chat_messages WHERE created_at < NOW() - INTERVAL '%s days'", (chat_days,))
        cur.execute("DELETE FROM sla_checks WHERE checked_at < NOW() - INTERVAL '%s days'", (sla_days,))
        cur.execute("DELETE FROM agent_states WHERE recorded_at < NOW() - INTERVAL '%s days'", (metrics_days,))
        log.info("DB cleanup complete")
