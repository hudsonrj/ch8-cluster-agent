"""
CH8 Cluster — Audit Logger

Logs all tool executions to PostgreSQL for forensic analysis.
Records: who, what, when, from where, result, and if blocked.
"""

import json
import logging
import time
from typing import Optional

log = logging.getLogger("ch8.audit")


def log_audit(
    node_id: str = "",
    source_ip: str = "",
    endpoint: str = "",
    tool_name: str = "",
    tool_args: dict = None,
    result_status: str = "ok",
    blocked_reason: str = "",
    duration_ms: int = 0,
):
    """Record a tool execution in the audit_log table (best effort, non-blocking)."""
    try:
        from .db import get_db
        with get_db() as conn:
            if not conn:
                return
            cur = conn.cursor()
            # Sanitize args (remove sensitive content)
            safe_args = _sanitize_args(tool_args or {})
            cur.execute(
                """INSERT INTO audit_log (node_id, source_ip, endpoint, tool_name, tool_args, result_status, blocked_reason, duration_ms)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (node_id, source_ip, endpoint, tool_name,
                 json.dumps(safe_args), result_status, blocked_reason, duration_ms)
            )
    except Exception as e:
        log.debug(f"Audit log failed: {e}")


def _sanitize_args(args: dict) -> dict:
    """Remove sensitive content from args before logging."""
    safe = {}
    for k, v in args.items():
        if k in ("password", "token", "secret", "key"):
            safe[k] = "***REDACTED***"
        elif isinstance(v, str) and len(v) > 500:
            safe[k] = v[:500] + "...(truncated)"
        else:
            safe[k] = v
    return safe
