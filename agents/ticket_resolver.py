"""
Ticket Resolver Agent — Gerencia o ciclo de vida dos tickets ITSM automaticamente.

Fluxo autônomo:
1. Pega tickets 'open' → move para 'investigating' + adiciona diagnóstico
2. Tickets 'investigating' → tenta resolver via fix_command → move para 'in_progress'
3. Tickets 'in_progress' → verifica se problema persistiu → 'resolved' ou 'escalated'
4. Tickets resolvidos há >24h → move para 'closed'
5. Tickets com SLA estourado → escala para humano

Ciclo: a cada 2 minutos
"""

import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger("ch8.ticket_resolver")

CONFIG_DIR = Path.home() / ".config" / "ch8"
PID_FILE = CONFIG_DIR / "ticket_resolver.pid"
LOG_FILE = CONFIG_DIR / "ticket_resolver.log"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

CHECK_INTERVAL = 120  # 2 minutos
running = True


def signal_handler(sig, frame):
    global running
    running = False


def _get_db():
    """Get database connection."""
    try:
        import psycopg2
        db_url = os.environ.get("CH8_DB_URL", "")
        if not db_url:
            env_file = CONFIG_DIR / "env"
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if line.startswith("CH8_DB_URL="):
                        db_url = line.split("=", 1)[1].strip().strip('"')
                        break
        if not db_url:
            return None
        return psycopg2.connect(db_url, connect_timeout=5)
    except Exception as e:
        log.warning(f"DB connection failed: {e}")
        return None


def _add_history(conn, ticket_id, action, note, by="ticket_resolver"):
    """Add entry to ticket history."""
    cur = conn.cursor()
    entry = json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "action": action, "by": by, "note": note})
    cur.execute(
        "UPDATE tickets SET history = history || %s::jsonb, updated_at = NOW() WHERE ticket_id = %s",
        (f'[{entry}]', ticket_id)
    )


def _check_problem_resolved(ticket):
    """Verify if a problem is resolved by checking recent logs."""
    conn = _get_db()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        # Check if similar errors occurred in last 10 minutes
        node = ticket.get("node", "")
        category = ticket.get("category", "")

        # Map category to log patterns
        pattern_map = {
            "service_down": "%connection refused%",
            "disk_full": "%No space%",
            "oom": "%out of memory%",
            "performance": "%timeout%",
            "config": "%permission denied%",
        }
        pattern = pattern_map.get(category, f"%{category}%")

        query = """
            SELECT count(*) FROM node_logs
            WHERE logged_at > NOW() - INTERVAL '10 minutes'
            AND level = 'error'
        """
        params = []
        if node:
            query += " AND hostname = %s"
            params.append(node)
        query += " AND message ILIKE %s"
        params.append(pattern)

        cur.execute(query, params)
        count = cur.fetchone()[0]
        conn.close()

        # If no recent errors matching the pattern, consider resolved
        return count == 0
    except Exception as e:
        log.error(f"Check resolved failed: {e}")
        try:
            conn.close()
        except:
            pass
        return False


def _try_auto_fix(ticket):
    """Attempt to execute the fix_command for a ticket."""
    fix_cmd = ticket.get("fix_command", "")
    if not fix_cmd or fix_cmd.startswith("#"):
        return None, "Sem comando de fix executável"

    # Safety: don't execute dangerous commands
    try:
        from connect.security_policy import check_command_policy
        violation = check_command_policy(fix_cmd)
        if violation:
            return None, f"Fix bloqueado por política de segurança: {violation}"
    except Exception:
        pass

    try:
        result = subprocess.run(
            fix_cmd, shell=True, capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return result.stdout[:500], None
        else:
            return None, f"Fix falhou (exit {result.returncode}): {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return None, "Fix timeout (>30s)"
    except Exception as e:
        return None, f"Erro ao executar fix: {e}"


# Patterns that identify known false positives — auto-resolve immediately
_FALSE_POSITIVE_PATTERNS = [
    ("snap-",         "Snap mount unit — não é serviço CH8. Falso positivo filtrado."),
    ("hassio",        "Home Assistant supervisor — não faz parte da infra CH8. Falso positivo."),
    ("localhost está offline", "localhost é o próprio nó master — não é um node remoto. Falso positivo."),
    ("manager1 está offline",  "manager1 é o nó master e está online. Monitoramento circular detectado. Falso positivo."),
    ("Nodes offline detectados: manager1",  "manager1 é o nó master, está online. Falso positivo de auto-monitoramento."),
    ("Nodes offline detectados: localhost", "localhost é o próprio host. Não é node remoto offline. Falso positivo."),
]


def _is_false_positive(title: str) -> str | None:
    """Return resolution message if ticket is a known false positive, else None."""
    title_lower = title.lower()
    for pattern, resolution in _FALSE_POSITIVE_PATTERNS:
        if pattern.lower() in title_lower:
            return resolution
    return None


def process_open_tickets(conn):
    """Move open tickets to investigating + add initial diagnosis. Auto-close false positives."""
    cur = conn.cursor()
    cur.execute("""
        SELECT ticket_id, title, category, node, root_cause, severity
        FROM tickets WHERE status = 'open'
        ORDER BY
            CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
            created_at ASC
        LIMIT 10
    """)
    tickets = cur.fetchall()

    for row in tickets:
        ticket_id, title, category, node, root_cause, severity = row

        # Auto-resolve false positives immediately
        fp_reason = _is_false_positive(title)
        if fp_reason:
            log.info(f"Falso positivo: {ticket_id} — {title[:60]}")
            cur.execute(
                "UPDATE tickets SET status = 'resolved', resolved_at = NOW(), "
                "resolution = %s, assigned_to = 'ticket_resolver', updated_at = NOW() "
                "WHERE ticket_id = %s",
                (fp_reason, ticket_id)
            )
            _add_history(conn, ticket_id, "resolved", f"[Auto] Falso positivo identificado e resolvido: {fp_reason}")
            conn.commit()
            continue

        log.info(f"Investigando: {ticket_id} — {title}")
        cur.execute(
            "UPDATE tickets SET status = 'investigating', assigned_to = 'ticket_resolver', updated_at = NOW() WHERE ticket_id = %s",
            (ticket_id,)
        )
        diagnosis = root_cause or f"Analisando problema de {category} no nó {node}"
        _add_history(conn, ticket_id, "investigating",
                     f"Ticket assumido para investigação automática. Diagnóstico: {diagnosis}")
        conn.commit()


def process_investigating_tickets(conn):
    """Try to fix investigating tickets. Uses fresh connection after each fix attempt."""
    cur = conn.cursor()
    cur.execute("""
        SELECT ticket_id, title, category, node, fix_command, severity
        FROM tickets WHERE status = 'investigating'
        AND updated_at < NOW() - INTERVAL '1 minute'
        ORDER BY
            CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END
        LIMIT 3
    """)
    tickets = cur.fetchall()
    conn.close()  # Close before potentially long fix operations

    for row in tickets:
        ticket_id, title, category, node, fix_command, severity = row
        log.info(f"Tentando resolver: {ticket_id} — {title}")

        # Try auto-fix (can take up to 30s)
        ticket_data = {"fix_command": fix_command, "category": category, "node": node}
        output, error = _try_auto_fix(ticket_data)

        # Fresh connection for DB update after fix
        conn2 = _get_db()
        if not conn2:
            continue
        try:
            cur2 = conn2.cursor()
            if output:
                cur2.execute(
                    "UPDATE tickets SET status = 'in_progress', updated_at = NOW() WHERE ticket_id = %s",
                    (ticket_id,)
                )
                _add_history(conn2, ticket_id, "fix_applied",
                             f"Fix executado com sucesso. Output: {output[:200]}")
            elif error:
                _add_history(conn2, ticket_id, "fix_attempt",
                             f"Tentativa de fix: {error}")
                if severity == 'critical':
                    cur2.execute(
                        "UPDATE tickets SET status = 'escalated', escalated = true, updated_at = NOW() WHERE ticket_id = %s",
                        (ticket_id,)
                    )
                    _add_history(conn2, ticket_id, "escalated",
                                 "Escalado para humano — ticket critico sem resolucao automatica")
                else:
                    cur2.execute(
                        "UPDATE tickets SET status = 'in_progress', updated_at = NOW() WHERE ticket_id = %s",
                        (ticket_id,)
                    )
            conn2.commit()
            conn2.close()
        except Exception as e:
            log.warning(f"DB update after fix failed: {e}")
            try:
                conn2.close()
            except:
                pass


def process_in_progress_tickets(conn):
    """Check if in_progress tickets are actually resolved."""
    cur = conn.cursor()
    cur.execute("""
        SELECT ticket_id, title, category, node, severity
        FROM tickets WHERE status = 'in_progress'
        AND updated_at < NOW() - INTERVAL '5 minutes'
        LIMIT 5
    """)
    tickets = cur.fetchall()

    for row in tickets:
        ticket_id, title, category, node, severity = row
        ticket_data = {"category": category, "node": node}

        if _check_problem_resolved(ticket_data):
            log.info(f"Resolvido: {ticket_id} — {title}")
            cur.execute(
                "UPDATE tickets SET status = 'resolved', resolved_at = NOW(), "
                "resolution = 'Problema não reincidiu nos últimos 10 minutos — considerado resolvido.', "
                "updated_at = NOW() WHERE ticket_id = %s",
                (ticket_id,)
            )
            _add_history(conn, ticket_id, "resolved",
                         "Verificação automática: erro não reincidiu. Ticket resolvido.")
        else:
            # Problem persists — escalate if too long
            _add_history(conn, ticket_id, "check",
                         "Problema ainda persiste. Monitorando...")
            # Escalate high/critical after 30 min without resolution
            cur.execute(
                "UPDATE tickets SET status = 'escalated', escalated = true, updated_at = NOW() "
                "WHERE ticket_id = %s AND severity IN ('critical','high') "
                "AND created_at < NOW() - INTERVAL '30 minutes' AND status = 'in_progress'",
                (ticket_id,)
            )
        conn.commit()


def process_sla_breaches(conn):
    """Escalate tickets that breached SLA."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE tickets SET status = 'escalated', escalated = true, updated_at = NOW()
        WHERE status IN ('open', 'investigating', 'in_progress')
        AND sla_deadline < NOW()
        AND escalated = false
        RETURNING ticket_id, title
    """)
    breached = cur.fetchall()
    for ticket_id, title in breached:
        _add_history(conn, ticket_id, "sla_breach",
                     "SLA estourado — ticket escalado automaticamente para humano")
        log.warning(f"SLA breach: {ticket_id} — {title}")
    conn.commit()


def auto_close_resolved(conn):
    """Close tickets resolved for >24h."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE tickets SET status = 'closed', updated_at = NOW()
        WHERE status = 'resolved' AND resolved_at < NOW() - INTERVAL '24 hours'
        RETURNING ticket_id
    """)
    closed = cur.fetchall()
    for (ticket_id,) in closed:
        _add_history(conn, ticket_id, "closed",
                     "Fechado automaticamente após 24h sem reincidência")
    conn.commit()
    if closed:
        log.info(f"Auto-closed {len(closed)} ticket(s)")


def _update_state(status, task):
    try:
        from connect.state import update_agent_state
        update_agent_state("ticket_resolver", status, task,
                           model="itsm-auto", platform="postgresql",
                           autonomous=True,
                           tools=["investigate", "fix", "resolve", "escalate", "close"])
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
    log.info("Ticket Resolver Agent starting")
    _update_state("running", "Gerenciando tickets ITSM automaticamente")

    while running:
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
            pass  # If HA check fails, proceed (single-node mode)

        try:
            # Process tickets in lifecycle order (fresh connection per operation)
            for task_fn in [process_open_tickets, process_investigating_tickets,
                            process_in_progress_tickets, process_sla_breaches, auto_close_resolved]:
                conn = _get_db()
                if not conn:
                    _update_state("warning", "Sem conexão com banco de dados")
                    break
                try:
                    task_fn(conn)
                    conn.close()
                except Exception as e:
                    log.warning(f"{task_fn.__name__} error: {e}")
                    try:
                        conn.close()
                    except:
                        pass

            # Count status for reporting (separate connection)
            conn = _get_db()
            if conn:
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT status, count(*) FROM tickets GROUP BY status")
                    counts = dict(cur.fetchall())
                    conn.close()

                    total = sum(counts.values())
                    open_c = counts.get("open", 0)
                    inv = counts.get("investigating", 0)
                    prog = counts.get("in_progress", 0)
                    resolved = counts.get("resolved", 0)
                    escalated = counts.get("escalated", 0)

                    _update_state("running",
                                  f"Tickets: {total} total | {open_c} open | {inv} inv | {prog} prog | {resolved} resolvidos | {escalated} escalados")
                except Exception:
                    try:
                        conn.close()
                    except:
                        pass

        except Exception as e:
            log.error(f"Cycle error: {e}")
            _update_state("error", str(e)[:80])

        for _ in range(CHECK_INTERVAL):
            if not running:
                break
            time.sleep(1)

    _update_state("idle", "Parado")
    PID_FILE.unlink(missing_ok=True)
    log.info("Ticket Resolver Agent stopped")


if __name__ == "__main__":
    main()
