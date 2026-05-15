"""
Oracle Honda Sync Agent — Real-time integration Oracle → PostgreSQL.

Monitors Oracle AUTOMOVEIS table for Honda brand vehicles and replicates
them to PostgreSQL 'carros' database in near-real-time (every 10 seconds).

Architecture:
  - Source: Oracle (oracle-free container, system/oracle, FREEPDB1)
  - Target: PostgreSQL (carros database, automoveis table)
  - Filter: Only MARCA = 'HONDA' (case-insensitive)
  - Conflict: ON CONFLICT (oracle_id) DO UPDATE (upsert)
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

log = logging.getLogger("ch8.oracle_honda_sync")

CONFIG_DIR = Path.home() / ".config" / "ch8"
PID_FILE = CONFIG_DIR / "oracle_honda_sync.pid"
LOG_FILE = CONFIG_DIR / "oracle_honda_sync.log"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

SYNC_INTERVAL = 10  # seconds
running = True


def signal_handler(sig, frame):
    global running
    running = False


def _get_oracle_connection():
    """Get Oracle connection string from vault or default."""
    try:
        from connect.vault import get
        conn_str = get("oracle/connection")
        if conn_str:
            return conn_str
    except Exception:
        pass
    return "system/oracle@//localhost:1521/FREEPDB1"


def _get_pg_connection():
    """Get PostgreSQL connection string for carros DB."""
    try:
        from connect.vault import get
        url = get("carros/db_url")
        if url:
            return url
    except Exception:
        pass
    return "postgresql://ch8app:ch8cluster2024@127.0.0.1:5432/carros"


def _query_oracle_honda(last_id: int = 0) -> list:
    """Query Oracle for new Honda vehicles since last_id."""
    sql = (
        f"SET PAGESIZE 0 LINESIZE 500 FEEDBACK OFF\n"
        f"SELECT id || '|' || marca || '|' || modelo || '|' || NVL(TO_CHAR(ano),'') || '|' || "
        f"NVL(cor,'') || '|' || NVL(placa,'') || '|' || NVL(chassi,'') || '|' || NVL(TO_CHAR(preco),'0') || '|' || "
        f"NVL(TO_CHAR(created_at,'YYYY-MM-DD HH24:MI:SS'),'') "
        f"FROM automoveis WHERE UPPER(marca) = 'HONDA' AND id > {last_id} ORDER BY id;"
    )
    cmd = f"echo \"{sql}\" | sqlplus -s system/oracle@//localhost:1521/FREEPDB1"
    try:
        result = subprocess.run(
            ["docker", "exec", "oracle-free", "bash", "-c", cmd],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            log.warning(f"Oracle query failed: {result.stderr[:200]}")
            return []

        rows = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line or "no rows" in line.lower():
                continue
            parts = line.split("|")
            if len(parts) >= 3:
                try:
                    oracle_id = int(parts[0].strip())
                    rows.append({
                        "oracle_id": oracle_id,
                        "marca": parts[1].strip() if len(parts) > 1 else "HONDA",
                        "modelo": parts[2].strip() if len(parts) > 2 else "",
                        "ano": int(parts[3].strip()) if len(parts) > 3 and parts[3].strip().isdigit() else None,
                        "cor": parts[4].strip() or None if len(parts) > 4 else None,
                        "placa": parts[5].strip() or None if len(parts) > 5 else None,
                        "chassi": parts[6].strip() or None if len(parts) > 6 else None,
                        "preco": float(parts[7].strip()) if len(parts) > 7 and parts[7].strip() else None,
                        "created_at": parts[8].strip() or None if len(parts) > 8 else None,
                    })
                except (ValueError, IndexError) as e:
                    log.debug(f"Parse error on line: {line[:80]} — {e}")
                    continue
        return rows
    except subprocess.TimeoutExpired:
        log.warning("Oracle query timeout")
        return []
    except Exception as e:
        log.error(f"Oracle error: {e}")
        return []


def _insert_pg(rows: list) -> int:
    """Insert rows into PostgreSQL carros.automoveis."""
    if not rows:
        return 0
    try:
        import psycopg2
        conn = psycopg2.connect(_get_pg_connection())
        cur = conn.cursor()
        inserted = 0
        for r in rows:
            cur.execute("""
                INSERT INTO automoveis (oracle_id, marca, modelo, ano, cor, placa, chassi, preco, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (oracle_id) DO UPDATE SET
                    marca=EXCLUDED.marca, modelo=EXCLUDED.modelo, ano=EXCLUDED.ano,
                    cor=EXCLUDED.cor, placa=EXCLUDED.placa, chassi=EXCLUDED.chassi,
                    preco=EXCLUDED.preco, synced_at=NOW()
            """, (r["oracle_id"], r["marca"], r["modelo"], r["ano"],
                  r["cor"], r["placa"], r["chassi"], r["preco"], r.get("created_at")))
            inserted += 1
        conn.commit()
        conn.close()
        return inserted
    except Exception as e:
        log.error(f"PG insert error: {e}")
        return 0


def _get_last_synced_id() -> int:
    """Get the highest oracle_id already synced."""
    try:
        import psycopg2
        conn = psycopg2.connect(_get_pg_connection())
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(oracle_id), 0) FROM automoveis;")
        result = cur.fetchone()[0]
        conn.close()
        return result
    except Exception:
        return 0


def _update_state(status, task, details=None):
    try:
        from connect.state import update_agent_state
        update_agent_state("oracle_honda_sync", status, task,
                           model="oracle-sync", platform="oracle+postgresql",
                           autonomous=True,
                           tools=["oracle_query", "pg_insert"],
                           details=details or {})
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
    log.info("Oracle Honda Sync Agent starting")
    log.info(f"Source: Oracle FREEPDB1 → Filter: HONDA → Target: PG carros.automoveis")
    _update_state("running", "Monitoring Oracle for Honda vehicles")

    total_synced = 0
    errors = 0

    while running:
        try:
            last_id = _get_last_synced_id()
            rows = _query_oracle_honda(last_id)

            if rows:
                inserted = _insert_pg(rows)
                total_synced += inserted
                log.info(f"Synced {inserted} Honda vehicle(s) (total: {total_synced})")
                _update_state("running", f"Synced {inserted} Honda(s) | Total: {total_synced}",
                              {"last_sync": datetime.now(timezone.utc).isoformat(),
                               "total_synced": total_synced, "last_batch": inserted})
                errors = 0
            else:
                _update_state("running", f"Monitoring | {total_synced} synced | Last check: {datetime.now().strftime('%H:%M:%S')}",
                              {"total_synced": total_synced})

        except Exception as e:
            errors += 1
            log.error(f"Sync cycle error: {e}")
            _update_state("warning" if errors < 3 else "error", f"Error: {str(e)[:60]}")
            if errors >= 5:
                # Create ITSM ticket for persistent failure
                try:
                    from connect.db import create_ticket
                    create_ticket(
                        title=f"[manager1] Oracle Honda Sync failing ({errors} errors)",
                        description=f"Agent oracle_honda_sync has {errors} consecutive errors.\nLast error: {e}",
                        severity="high", category="service_down",
                        node="manager1", service="oracle_honda_sync",
                        root_cause=str(e)[:200],
                        action_plan="1. Check Oracle container status\n2. Verify PG carros database\n3. Restart agent"
                    )
                except Exception:
                    pass
                errors = 0  # Reset after ticket

        for _ in range(SYNC_INTERVAL):
            if not running:
                break
            time.sleep(1)

    _update_state("idle", "Stopped")
    PID_FILE.unlink(missing_ok=True)
    log.info("Oracle Honda Sync Agent stopped")


if __name__ == "__main__":
    main()
