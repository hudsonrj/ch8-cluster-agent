"""
CH8 MCP Server — Model Context Protocol server para o cluster CH8
Expõe ferramentas de: PostgreSQL, Redis, ITSM, Knowledge Base, Shell, Web, Nodes

Transport: HTTP/SSE (porta configurável via CH8_MCP_PORT, default 8765)
Auth: Bearer token (mesmo token do cluster, via CH8_MCP_TOKEN ou auth.json)

Deploy: python3 /data/ch8-agent/mcp/ch8_mcp_server.py
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import fastmcp

log = logging.getLogger("ch8.mcp")

# ── Config ────────────────────────────────────────────────────────────────────

DB_URL   = os.environ.get("CH8_DB_URL",
           "postgresql://ch8app:ch8cluster2024@127.0.0.1:5432/ch8_cluster")
PORT     = int(os.environ.get("CH8_MCP_PORT", "8765"))
NODE_NAME = os.environ.get("CH8_HOSTNAME", subprocess.getoutput("hostname"))

# Auth token (for relay calls to orchestrator)
def _token() -> str:
    try:
        auth = Path.home() / ".config" / "ch8" / "auth.json"
        return json.loads(auth.read_text()).get("access_token", "")
    except Exception:
        return ""

# ── DB helper ─────────────────────────────────────────────────────────────────

def _db():
    import psycopg2, psycopg2.extras
    return psycopg2.connect(DB_URL), psycopg2.extras.RealDictCursor

# ── MCP Server ────────────────────────────────────────────────────────────────

mcp = fastmcp.FastMCP(
    name=f"CH8 Cluster MCP — {NODE_NAME}",
    instructions=(
        "Você tem acesso ao cluster CH8 via este servidor MCP. "
        "Use as ferramentas para consultar bancos de dados, gerenciar tickets ITSM, "
        "buscar na Knowledge Base, executar comandos nos nodes e pesquisar na web. "
        "Todas as ações destrutivas requerem confirmação explícita."
    ),
)

# ── NODES ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def node_list() -> dict:
    """Lista todos os nodes do cluster com status, CPU, MEM, DISK."""
    try:
        import httpx
        token = _token()
        r = httpx.get("http://127.0.0.1:8081/nodes",
                      params={"network_id": "net_default"},
                      headers={"Authorization": f"Bearer {token}"}, timeout=10)
        nodes = r.json().get("nodes", [])
        return {
            "total": len(nodes),
            "online": sum(1 for n in nodes if n.get("status") == "online"),
            "nodes": [
                {
                    "hostname": n.get("hostname"),
                    "status": n.get("status"),
                    "cpu_pct": n.get("cpu_pct"),
                    "mem_pct": n.get("mem_pct"),
                    "disk_pct": n.get("disk_pct"),
                    "agents": len(n.get("agents", [])),
                    "node_id": n.get("node_id"),
                }
                for n in nodes
            ],
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def node_execute(command: str, node: str = "manager1") -> dict:
    """
    Executa um comando shell em um node do cluster.
    node: hostname do node (ex: manager1, kali, vmi3201672) ou 'manager1' para local.
    Comandos destrutivos (rm -rf, DROP, etc.) são bloqueados por política de segurança.
    """
    sys.path.insert(0, "/data/ch8-agent")
    try:
        from connect.tools_config import execute_tool
        if node in ("manager1", "localhost", NODE_NAME):
            return execute_tool("shell_exec", {"command": command, "timeout": 30})
        else:
            return execute_tool("node_chat", {
                "node": node,
                "message": f"Execute this shell command and return only the output: `{command}`"
            })
    except Exception as e:
        return {"error": str(e)}


# ── POSTGRESQL ────────────────────────────────────────────────────────────────

@mcp.tool()
def postgres_query(sql: str, db: str = "ch8_cluster") -> dict:
    """
    Executa uma query SELECT no PostgreSQL do cluster.
    Apenas SELECT é permitido — use para consultas, análises e relatórios.
    db: ch8_cluster (padrão) | carros | postgres
    """
    if not sql.strip().upper().startswith("SELECT"):
        return {"error": "Apenas SELECT é permitido via MCP. Use ticket_create para solicitar mudanças."}
    try:
        url = DB_URL.rsplit("/", 1)[0] + f"/{db}"
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(url)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql)
        rows = cur.fetchall()
        conn.close()
        return {
            "rows": [dict(r) for r in rows],
            "count": len(rows),
            "db": db,
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def postgres_tables(db: str = "ch8_cluster") -> dict:
    """Lista tabelas e tamanhos do banco PostgreSQL."""
    return postgres_query(
        "SELECT table_name, pg_size_pretty(pg_total_relation_size(quote_ident(table_name))) as size "
        "FROM information_schema.tables WHERE table_schema='public' ORDER BY "
        "pg_total_relation_size(quote_ident(table_name)) DESC",
        db=db
    )


# ── REDIS ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def redis_get(key: str) -> dict:
    """Lê um valor do Redis (cache do cluster)."""
    try:
        import redis as _redis
        r = _redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
        val = r.get(key)
        ttl = r.ttl(key)
        return {"key": key, "value": val, "ttl_seconds": ttl, "exists": val is not None}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def redis_keys(pattern: str = "ch8:*") -> dict:
    """Lista chaves Redis por padrão glob (ex: 'ch8:*', 'web_cache:*')."""
    try:
        import redis as _redis
        r = _redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
        keys = list(r.scan_iter(pattern, count=100))[:50]
        return {"pattern": pattern, "keys": keys, "count": len(keys)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def redis_info() -> dict:
    """Retorna métricas do Redis: memória, clientes, hits/misses."""
    try:
        import redis as _redis
        r = _redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
        info = r.info()
        return {
            "used_memory_human": info.get("used_memory_human"),
            "connected_clients": info.get("connected_clients"),
            "keyspace_hits": info.get("keyspace_hits"),
            "keyspace_misses": info.get("keyspace_misses"),
            "total_commands_processed": info.get("total_commands_processed"),
            "uptime_in_days": info.get("uptime_in_days"),
        }
    except Exception as e:
        return {"error": str(e)}


# ── ITSM TICKETS ──────────────────────────────────────────────────────────────

@mcp.tool()
def tickets_list(
    status: str = "open",
    severity: str = "",
    limit: int = 20,
) -> dict:
    """
    Lista tickets ITSM do cluster.
    status: open | investigating | in_progress | resolved | closed | all
    severity: critical | high | medium | low | '' (todos)
    """
    try:
        conn, DictCursor = _db()
        cur = conn.cursor(cursor_factory=DictCursor)
        wheres, params = [], []
        if status != "all":
            wheres.append("status = %s"); params.append(status)
        if severity:
            wheres.append("severity = %s"); params.append(severity)
        sql = "SELECT ticket_id, title, status, severity, node, created_at, resolved_at FROM tickets"
        if wheres:
            sql += " WHERE " + " AND ".join(wheres)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        rows = cur.fetchall()
        conn.close()
        tickets = []
        for r in rows:
            d = dict(r)
            for k, v in d.items():
                if hasattr(v, "isoformat"):
                    d[k] = v.isoformat()
            tickets.append(d)
        return {"tickets": tickets, "count": len(tickets)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def ticket_create(
    title: str,
    description: str,
    severity: str = "medium",
    category: str = "config",
    node: str = "manager1",
) -> dict:
    """
    Cria um novo ticket ITSM no cluster.
    severity: critical | high | medium | low
    category: service_down | performance | disk_full | config | security
    """
    try:
        conn, _ = _db()
        cur = conn.cursor()
        now = datetime.now(timezone.utc)
        sla_map = {"critical": 1, "high": 4, "medium": 24, "low": 72}
        from datetime import timedelta
        sla_deadline = now + timedelta(hours=sla_map.get(severity, 24))
        ticket_id = f"TKT-{now.strftime('%Y%m%d')}-MCP{now.strftime('%H%M%S')}"
        cur.execute("""
            INSERT INTO tickets
              (ticket_id, title, description, severity, category, status, node,
               source_type, source_ref, sla_deadline, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,'open',%s,'mcp','ch8-mcp-server',%s,NOW(),NOW())
        """, (ticket_id, title, description, severity, category, node, sla_deadline))
        conn.commit()
        conn.close()
        return {"ok": True, "ticket_id": ticket_id, "severity": severity}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def ticket_update(
    ticket_id: str,
    status: str,
    resolution: str = "",
) -> dict:
    """
    Atualiza status de um ticket ITSM.
    status: investigating | in_progress | resolved | closed
    """
    valid = {"investigating", "in_progress", "resolved", "closed", "escalated"}
    if status not in valid:
        return {"error": f"Status inválido. Use: {valid}"}
    try:
        conn, _ = _db()
        cur = conn.cursor()
        if status in ("resolved", "closed"):
            cur.execute(
                "UPDATE tickets SET status=%s, resolution=%s, resolved_at=NOW(), updated_at=NOW() WHERE ticket_id=%s",
                (status, resolution, ticket_id),
            )
        else:
            cur.execute(
                "UPDATE tickets SET status=%s, updated_at=NOW() WHERE ticket_id=%s",
                (status, ticket_id),
            )
        conn.commit()
        conn.close()
        return {"ok": True, "ticket_id": ticket_id, "new_status": status}
    except Exception as e:
        return {"error": str(e)}


# ── KNOWLEDGE BASE ────────────────────────────────────────────────────────────

@mcp.tool()
def knowledge_search(query: str, limit: int = 10) -> dict:
    """Busca artigos na Knowledge Base do cluster por texto livre."""
    try:
        conn, DictCursor = _db()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute(
            """SELECT id, title, category, tags,
                      LEFT(content, 300) AS preview, created_at
               FROM knowledge_articles
               WHERE to_tsvector('portuguese', title || ' ' || COALESCE(content,''))
                     @@ plainto_tsquery('portuguese', %s)
               ORDER BY created_at DESC LIMIT %s""",
            (query, limit),
        )
        rows = cur.fetchall()
        conn.close()
        articles = []
        for r in rows:
            d = dict(r)
            if hasattr(d.get("created_at"), "isoformat"):
                d["created_at"] = d["created_at"].isoformat()
            articles.append(d)
        return {"articles": articles, "count": len(articles), "query": query}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def knowledge_get(article_id: int) -> dict:
    """Retorna o conteúdo completo de um artigo da Knowledge Base pelo ID."""
    try:
        conn, DictCursor = _db()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("SELECT * FROM knowledge_articles WHERE id = %s", (article_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return {"error": f"Artigo {article_id} não encontrado"}
        d = dict(row)
        for k, v in d.items():
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        return d
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def knowledge_write(
    title: str,
    content: str,
    category: str = "troubleshooting",
    tags: list[str] = None,
) -> dict:
    """
    Salva um artigo na Knowledge Base do cluster.
    category: troubleshooting | procedure | lab_project | security
    """
    try:
        conn, _ = _db()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO knowledge_articles
                 (title, category, tags, content, source_type, source_ref, node)
               VALUES (%s, %s, %s, %s, 'mcp', 'ch8-mcp', %s)
               ON CONFLICT DO NOTHING RETURNING id""",
            (title, category, tags or [], content, NODE_NAME),
        )
        row = cur.fetchone()
        conn.commit()
        conn.close()
        return {"ok": True, "id": row[0] if row else None, "title": title}
    except Exception as e:
        return {"error": str(e)}


# ── LOGS ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def logs_recent(
    node: str = "",
    level: str = "ERROR",
    limit: int = 50,
) -> dict:
    """
    Retorna logs recentes do cluster.
    node: hostname do node (vazio = todos)
    level: ERROR | WARN | INFO | DEBUG
    """
    try:
        conn, DictCursor = _db()
        cur = conn.cursor(cursor_factory=DictCursor)
        wheres, params = ["logged_at > NOW() - INTERVAL '2 hours'"], []
        if node:
            wheres.append("hostname = %s"); params.append(node)
        if level:
            wheres.append("level = %s"); params.append(level.upper())
        sql = (f"SELECT hostname, level, message, service, logged_at "
               f"FROM node_logs WHERE {' AND '.join(wheres)} "
               f"ORDER BY logged_at DESC LIMIT %s")
        params.append(limit)
        cur.execute(sql, params)
        rows = cur.fetchall()
        conn.close()
        entries = []
        for r in rows:
            d = dict(r)
            if hasattr(d.get("logged_at"), "isoformat"):
                d["logged_at"] = d["logged_at"].isoformat()
            entries.append(d)
        return {"logs": entries, "count": len(entries)}
    except Exception as e:
        return {"error": str(e)}


# ── METRICS ───────────────────────────────────────────────────────────────────

@mcp.tool()
def metrics_summary(node: str = "", hours: int = 1) -> dict:
    """Retorna médias de CPU/MEM/DISK dos nodes nas últimas N horas."""
    try:
        conn, DictCursor = _db()
        cur = conn.cursor(cursor_factory=DictCursor)
        wheres = [f"recorded_at > NOW() - INTERVAL '{int(hours)} hours'"]
        params = []
        if node:
            wheres.append("hostname = %s"); params.append(node)
        cur.execute(
            f"""SELECT hostname,
                       ROUND(AVG(cpu_pct)::numeric, 1) avg_cpu,
                       ROUND(AVG(mem_pct)::numeric, 1) avg_mem,
                       ROUND(AVG(disk_pct)::numeric, 1) avg_disk,
                       COUNT(*) samples
                FROM node_metrics WHERE {' AND '.join(wheres)}
                GROUP BY hostname ORDER BY avg_cpu DESC""",
            params,
        )
        rows = cur.fetchall()
        conn.close()
        return {"metrics": [dict(r) for r in rows], "hours": hours}
    except Exception as e:
        return {"error": str(e)}


# ── WEB SEARCH ────────────────────────────────────────────────────────────────

@mcp.tool()
def web_search(query: str, max_results: int = 5) -> dict:
    """
    Busca na web via Brave Search API (primário) ou DuckDuckGo (fallback).
    Retorna lista de resultados com título, URL e snippet.
    """
    sys.path.insert(0, "/data/ch8-agent")
    try:
        from tools.web_tools import web_search as _ws
        return _ws(query=query, max_results=max_results)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def web_extract(url: str) -> dict:
    """Extrai texto limpo de uma página web. Útil para ler artigos e documentação."""
    sys.path.insert(0, "/data/ch8-agent")
    try:
        from tools.web_tools import web_extract as _we
        return _we(url=url)
    except Exception as e:
        return {"error": str(e)}


# ── SPECIALISTS ───────────────────────────────────────────────────────────────

@mcp.tool()
def specialists_list() -> dict:
    """Lista todos os Colaboradores Especialistas registrados no cluster."""
    try:
        conn, DictCursor = _db()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute(
            """SELECT id, title, LEFT(content,200) preview, created_at
               FROM knowledge_articles
               WHERE 'colaborador' = ANY(tags) AND 'especialista' = ANY(tags)
               ORDER BY created_at DESC"""
        )
        rows = cur.fetchall()
        conn.close()
        specs = []
        for r in rows:
            d = dict(r)
            if hasattr(d.get("created_at"), "isoformat"):
                d["created_at"] = d["created_at"].isoformat()
            specs.append(d)
        return {"specialists": specs, "count": len(specs)}
    except Exception as e:
        return {"error": str(e)}


# ── CLUSTER HEALTH SNAPSHOT ───────────────────────────────────────────────────

@mcp.tool()
def cluster_health() -> dict:
    """Snapshot completo da saúde do cluster: nodes, tickets, logs de erro recentes."""
    import httpx
    token = _token()
    result = {}

    try:
        nodes = httpx.get("http://127.0.0.1:8081/nodes",
                          params={"network_id": "net_default"},
                          headers={"Authorization": f"Bearer {token}"}, timeout=8).json().get("nodes", [])
        result["nodes"] = {
            "total": len(nodes),
            "online": sum(1 for n in nodes if n.get("status") == "online"),
            "disk_critical": [n["hostname"] for n in nodes if (n.get("disk_pct") or 0) > 88],
            "cpu_high": [n["hostname"] for n in nodes if (n.get("cpu_pct") or 0) > 85],
        }
    except Exception as e:
        result["nodes"] = {"error": str(e)}

    try:
        conn, DictCursor = _db()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("SELECT status, COUNT(*) n FROM tickets GROUP BY status")
        result["tickets"] = {r["status"]: r["n"] for r in cur.fetchall()}
        cur.execute("SELECT COUNT(*) n FROM node_logs WHERE level='ERROR' AND logged_at > NOW() - INTERVAL '1 hour'")
        result["errors_1h"] = cur.fetchone()["n"]
        conn.close()
    except Exception as e:
        result["db"] = {"error": str(e)}

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log.info(f"CH8 MCP Server starting on port {PORT} (node: {NODE_NAME})")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=PORT, path="/mcp")
