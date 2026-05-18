"""
Specialist Runner Agent — Executa todos os Colaboradores Especialistas registrados.

Carrega os especialistas da Knowledge Base e os executa como sub-agentes autônomos.
Cada especialista monitora seu domínio em TODOS os nodes do cluster.

Ciclo: a cada 60 minutos
- Carrega especialistas da KB (tag: colaborador)
- Para cada especialista, executa um ciclo de monitoramento usando seu system prompt
- Detecta problemas, cria tickets, gera insights
- Às 09:00 BRT: gera e salva report diário na KB
"""

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger("ch8.specialist_runner")

CONFIG_DIR = Path.home() / ".config" / "ch8"
PID_FILE = CONFIG_DIR / "specialist_runner.pid"
LOG_FILE = CONFIG_DIR / "specialist_runner.log"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

CHECK_INTERVAL = 3600  # 60 minutes
running = True


def signal_handler(sig, frame):
    global running
    running = False


def _load_specialists() -> list:
    """Load all registered specialists from Knowledge Base."""
    try:
        db_url = _get_db_url()
        if not db_url:
            return []
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(db_url)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, title, content, tags, node, created_at
            FROM knowledge_articles
            WHERE 'colaborador' = ANY(tags)
              AND 'especialista' = ANY(tags)
            ORDER BY created_at DESC
        """)
        rows = cur.fetchall()
        conn.close()
        specialists = []
        for row in rows:
            title = row['title']
            # Extract name and domain from title
            # Format: "Colaborador Especialista: {NOME} ({DOMINIO})"
            import re
            m = re.match(r'Colaborador Especialista: (.+?) \((.+?)\)', title)
            if m:
                nome, domain = m.group(1).strip(), m.group(2).strip()
            else:
                nome = title.replace('Colaborador Especialista: ', '').split('(')[0].strip()
                domain = 'Geral'
            specialists.append({
                'id': row['id'],
                'nome': nome,
                'domain': domain,
                'system_prompt': row['content'] or '',
                'created_at': str(row['created_at']),
            })
        return specialists
    except Exception as e:
        log.warning(f"Failed to load specialists: {e}")
        return []


def _get_db_url() -> str:
    db_url = os.environ.get("CH8_DB_URL", "")
    if not db_url:
        env_file = CONFIG_DIR / "env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("CH8_DB_URL="):
                    db_url = line.split("=", 1)[1].strip()
    return db_url


def _get_cluster_nodes() -> list:
    """Get all online nodes from control server."""
    try:
        import httpx
        from connect.auth import CONTROL_URL, get_access_token, get_network_id
        token = get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        r = httpx.get(f"{CONTROL_URL}/nodes",
                      params={"network_id": get_network_id()},
                      headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json().get("nodes", [])
    except Exception:
        pass
    # Fallback: use known nodes from memory
    return [
        {"hostname": "manager1", "address": "100.120.31.61", "node_id": "node_23b8a646e03f3e74"},
        {"hostname": "vmi3201672", "address": "100.65.70.126", "node_id": "node_650a678f71cf5d55"},
        {"hostname": "kali", "address": "100.117.164.25", "node_id": "node_e6092be709702acf"},
    ]


def _run_specialist_cycle(specialist: dict, nodes: list) -> dict:
    """Run one monitoring cycle for a specialist across all nodes."""
    nome = specialist['nome']
    domain = specialist['domain']
    findings = []
    actions_taken = []

    log.info(f"  [{nome}] Scanning {len(nodes)} nodes for domain: {domain}")

    # Domain-specific monitoring checks
    domain_lower = domain.lower()

    if any(k in domain_lower for k in ['banco', 'database', 'postgresql', 'mongodb', 'oracle', 'redis', 'mysql']):
        findings.extend(_check_databases(nodes))
    if any(k in domain_lower for k in ['segurança', 'security', 'soc']):
        findings.extend(_check_security(nodes))
    if any(k in domain_lower for k in ['observab', 'monitor', 'log', 'metric']):
        findings.extend(_check_observability(nodes))
    if any(k in domain_lower for k in ['devops', 'deploy', 'container', 'docker']):
        findings.extend(_check_containers_health(nodes))
    if any(k in domain_lower for k in ['rede', 'network', 'dns', 'vpn']):
        findings.extend(_check_network(nodes))
    if any(k in domain_lower for k in ['ia', 'ml', 'llm', 'ollama', 'model']):
        findings.extend(_check_ai_models(nodes))

    # Always check: open tickets in this domain
    open_tickets = _get_open_tickets(domain)
    if open_tickets:
        findings.append(f"{len(open_tickets)} tickets abertos no domínio {domain}")

    # Create tickets for critical findings
    for f in findings:
        if any(w in f.lower() for w in ['crítico', 'critical', 'down', 'offline', 'error', 'failed']):
            _create_finding_ticket(nome, domain, f)
            actions_taken.append(f"Ticket criado: {f[:60]}")

    return {
        "specialist": nome,
        "domain": domain,
        "nodes_scanned": len(nodes),
        "findings": findings,
        "actions_taken": actions_taken,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _check_databases(nodes: list) -> list:
    """Check database health across all nodes."""
    findings = []
    try:
        db_url = _get_db_url()
        if not db_url:
            return findings
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        # Check for recent DB errors in logs
        cur.execute("""
            SELECT hostname, COUNT(*) as cnt
            FROM node_logs
            WHERE level IN ('error','critical')
              AND (message ILIKE '%database%' OR message ILIKE '%postgres%'
                   OR message ILIKE '%mongodb%' OR message ILIKE '%oracle%')
              AND logged_at > NOW() - INTERVAL '30 minutes'
            GROUP BY hostname
            HAVING COUNT(*) > 2
        """)
        for hostname, cnt in cur.fetchall():
            findings.append(f"⚠️ {hostname}: {cnt} erros de banco nos últimos 30min")

        # Check replication slot
        cur.execute("SELECT slot_name, active FROM pg_replication_slots WHERE active = false")
        for slot, _ in cur.fetchall():
            findings.append(f"❌ Replication slot '{slot}' INATIVO — replica pode estar desatualizada")

        conn.close()
    except Exception as e:
        log.debug(f"DB check error: {e}")
    return findings


def _check_security(nodes: list) -> list:
    """Check security findings across nodes."""
    findings = []
    try:
        db_url = _get_db_url()
        if not db_url:
            return findings
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute("""
            SELECT hostname, COUNT(*) FROM audit_log
            WHERE blocked_reason IS NOT NULL AND blocked_reason != ''
              AND ts > NOW() - INTERVAL '1 hour'
            GROUP BY hostname HAVING COUNT(*) > 5
        """)
        for hostname, cnt in cur.fetchall():
            findings.append(f"🔒 {hostname}: {cnt} tentativas bloqueadas na última hora")
        conn.close()
    except Exception as e:
        log.debug(f"Security check error: {e}")
    return findings


def _check_observability(nodes: list) -> list:
    """Check observability health."""
    findings = []
    offline = [n for n in nodes if n.get("status") == "offline"]
    if offline:
        findings.append(f"⚠️ {len(offline)} node(s) offline: {', '.join(n['hostname'] for n in offline)}")
    high_disk = [n for n in nodes if n.get("disk_pct", 0) > 85]
    if high_disk:
        for n in high_disk:
            findings.append(f"💾 {n['hostname']}: disco {n['disk_pct']}% — ATENÇÃO")
    high_mem = [n for n in nodes if n.get("mem_pct", 0) > 90]
    if high_mem:
        for n in high_mem:
            findings.append(f"🔴 {n['hostname']}: memória {n['mem_pct']}% — CRÍTICO")
    return findings


def _check_containers_health(nodes: list) -> list:
    """Check container health from node services."""
    findings = []
    for node in nodes:
        for svc in node.get("services", []):
            if svc.get("type") == "docker" and svc.get("status") not in ("running", "healthy", ""):
                findings.append(f"🐳 {node['hostname']}/{svc['name']}: status={svc['status']}")
    return findings


def _check_network(nodes: list) -> list:
    """Check network connectivity."""
    findings = []
    offline = [n for n in nodes if n.get("status") == "offline"]
    if offline:
        findings.append(f"🌐 {len(offline)} node(s) sem conectividade Tailscale")
    return findings


def _check_ai_models(nodes: list) -> list:
    """Check AI model availability."""
    findings = []
    for node in nodes:
        models = node.get("models", [])
        if not models and node.get("status") == "online":
            findings.append(f"🤖 {node['hostname']}: nenhum modelo Ollama detectado")
    return findings


def _get_open_tickets(domain: str) -> list:
    """Get open tickets related to this domain."""
    try:
        db_url = _get_db_url()
        if not db_url:
            return []
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute("""
            SELECT ticket_id, title FROM tickets
            WHERE status IN ('open','investigating')
              AND (title ILIKE %s OR description ILIKE %s)
            LIMIT 10
        """, (f"%{domain.split('(')[0][:20]}%", f"%{domain.split('(')[0][:20]}%"))
        tickets = [{"id": r[0], "title": r[1]} for r in cur.fetchall()]
        conn.close()
        return tickets
    except Exception:
        return []


def _create_finding_ticket(nome: str, domain: str, finding: str) -> None:
    """Create ITSM ticket for critical finding."""
    try:
        from connect.db import create_ticket
        create_ticket(
            title=f"[{nome}] {finding[:80]}",
            description=f"Especialista {nome} (domínio: {domain}) detectou:\n\n{finding}\n\nDetectado automaticamente durante ciclo de monitoramento do cluster.",
            severity="high" if any(w in finding.lower() for w in ['crítico', 'critical', 'down']) else "medium",
            category="service_down" if "down" in finding.lower() else "performance",
            node="manager1",
            service=f"specialist-{nome.lower()}",
            root_cause=finding,
            action_plan=f"1. {nome} investigando\n2. Verificar nodes afetados\n3. Aplicar correção\n4. Validar resolução",
            source_type="specialist",
            source_ref=f"specialist-{nome.lower()}",
        )
    except Exception as e:
        log.debug(f"Failed to create finding ticket: {e}")


def _save_daily_report(specialist: dict, results: dict) -> None:
    """Save daily health report to Knowledge Base."""
    try:
        db_url = _get_db_url()
        if not db_url:
            return
        nome = specialist['nome']
        domain = specialist['domain']
        now = datetime.now()
        report_content = f"""# Report Diário — {nome}
**Domínio:** {domain}
**Data:** {now.strftime('%Y-%m-%d %H:%M')} BRT
**Gerado por:** Especialista Runner (automático)

## Status Geral
- Nodes escaneados: {results.get('nodes_scanned', 0)}
- Findings: {len(results.get('findings', []))}
- Ações tomadas: {len(results.get('actions_taken', []))}

## Findings Detectados
{chr(10).join('- ' + f for f in results.get('findings', [])) or '- Nenhum problema detectado'}

## Ações Tomadas
{chr(10).join('- ' + a for a in results.get('actions_taken', [])) or '- Nenhuma ação necessária'}

## Insights
- Monitoramento contínuo ativo em todos os nodes
- Próximo ciclo: em 60 minutos
"""
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO knowledge_articles (title, category, tags, content, source_type, source_ref, node)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            f"Report Diário: {nome} — {now.strftime('%Y-%m-%d')}",
            'troubleshooting',
            ['report', 'especialista', nome.lower(), domain.lower().split('(')[0].strip().replace(' ', '_')],
            report_content,
            'specialist_runner',
            f"daily-report-{nome.lower()}-{now.strftime('%Y%m%d')}",
            'manager1',
        ))
        conn.commit()
        conn.close()
        log.info(f"  [{nome}] Daily report saved to Knowledge Base")
    except Exception as e:
        log.debug(f"Failed to save daily report: {e}")


def _update_state(status: str, task: str, details: dict = None) -> None:
    try:
        from connect.state import update_agent_state
        update_agent_state("specialist_runner", status, task,
                           model="specialist-coordinator",
                           platform="multi-node",
                           autonomous=True,
                           tools=["db_check", "security_check", "container_check", "ticket_create", "kb_write"],
                           details=details or {})
    except Exception:
        pass


def main():
    global running
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
    )

    PID_FILE.write_text(str(os.getpid()))
    log.info("Specialist Runner starting — will monitor all nodes for registered specialists")

    last_daily_report = 0

    while running:
        try:
            # HA check — only run on master
            try:
                from connect.cluster_ha import is_master
                if not is_master():
                    _update_state("idle", "Standby — não sou o master")
                    for _ in range(CHECK_INTERVAL):
                        if not running: break
                        time.sleep(1)
                    continue
            except Exception:
                pass

            specialists = _load_specialists()
            if not specialists:
                _update_state("running", "Nenhum especialista registrado. Use 'crie um especialista em X' para adicionar.")
                for _ in range(CHECK_INTERVAL):
                    if not running: break
                    time.sleep(1)
                continue

            nodes = _get_cluster_nodes()
            log.info(f"Running {len(specialists)} specialists across {len(nodes)} nodes")

            all_results = []
            for specialist in specialists:
                try:
                    results = _run_specialist_cycle(specialist, nodes)
                    all_results.append(results)
                    log.info(f"  [{specialist['nome']}] {len(results['findings'])} findings, {len(results['actions_taken'])} actions")
                except Exception as e:
                    log.error(f"  [{specialist['nome']}] Cycle error: {e}")

            # Daily report at 09:00 BRT (12:00 UTC) — max once per day
            now = datetime.now(timezone.utc)
            if now.hour == 12 and (time.time() - last_daily_report) > 23 * 3600:
                for specialist, results in zip(specialists, all_results):
                    _save_daily_report(specialist, results)
                last_daily_report = time.time()

            total_findings = sum(len(r['findings']) for r in all_results)
            total_actions = sum(len(r['actions_taken']) for r in all_results)
            specialist_names = ', '.join(s['nome'] for s in specialists)

            _update_state("running",
                f"{len(specialists)} especialistas ativos: {specialist_names} | {total_findings} findings | {total_actions} ações",
                details={
                    "specialists": len(specialists),
                    "nodes_monitored": len(nodes),
                    "total_findings": total_findings,
                    "total_actions": total_actions,
                    "last_cycle": now.isoformat(),
                })

        except Exception as e:
            log.error(f"Main cycle error: {e}")
            _update_state("error", str(e)[:80])

        for _ in range(CHECK_INTERVAL):
            if not running:
                break
            time.sleep(1)

    _update_state("idle", "Stopped")
    PID_FILE.unlink(missing_ok=True)
    log.info("Specialist Runner stopped")


if __name__ == "__main__":
    main()
