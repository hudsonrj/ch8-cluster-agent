"""
Daily Checklist Agent — Verificação diária do cluster por todos os especialistas.

Executa às 08:00 BRT (11:00 UTC) e às 23:00 BRT (02:00 UTC +1d).
Cada especialista verifica seu domínio. Falhas geram tickets ITSM.
Resultados salvos na Knowledge Base.
"""
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] checklist: %(message)s",
    handlers=[
        logging.FileHandler(Path.home() / ".config/ch8/daily_checklist.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("ch8.checklist")

CONFIG_DIR = Path.home() / ".config" / "ch8"
PID_FILE = CONFIG_DIR / "daily_checklist.pid"

running = True
# BRT = UTC-3. Target hours in UTC: 11 (08h BRT) and 02 (23h BRT)
CHECKLIST_HOURS_UTC = {11, 2}

SPECIALISTS = [
    ("Sigma",       "Infraestrutura & DevOps",        "containers, disco, nodes, serviços, docker, nginx"),
    ("Nikolas",     "DBA — Bancos de Dados",           "PostgreSQL, Oracle, MongoDB, Redis, replicação, backup"),
    ("Mr Robot",    "Segurança",                       "portas expostas, certificados SSL, auth, CVEs recentes, audit log"),
    ("Jarvis",      "Inteligência Artificial",         "modelos Ollama, Bedrock, RAG pipeline, custo de tokens"),
    ("Atlas",       "MongoDB",                         "replica set, índices, aggregation, backup"),
    ("Orion",       "Performance & Observabilidade",   "CPU, RAM, disco, latência, SLO, tendências"),
    ("Hermes",      "MCP & Integrações",               "MCP server (porta 8765), ferramentas, conectividade entre nodes"),
    ("Lexus",       "Aplicações & Produtos",           "APIs rodando, endpoints respondendo, versões deployadas"),
    ("Sitetc",      "Sites & Web",                     "nginx sites, SSL, uptime, métricas web"),
    ("Pesquisador", "Web Intelligence",                "CVEs novos relevantes, updates críticos, ameaças emergentes"),
]


def _get_db():
    try:
        import psycopg2
        db_url = os.environ.get(
            "CH8_DB_URL",
            "postgresql://ch8app:ch8cluster2024@127.0.0.1:5432/ch8_cluster",
        )
        return psycopg2.connect(db_url)
    except Exception:
        return None


def _update_state(status: str, task: str):
    try:
        from connect.state import update_agent_state
        update_agent_state("daily_checklist", status, task,
                           model="checklist", platform="multi-specialist",
                           autonomous=True)
    except Exception:
        pass


def _ask_specialist(spec_name: str, domain: str, topics: str, period: str) -> str:
    """Ask a specialist to run their domain check."""
    try:
        import httpx
        token = ""
        auth_file = CONFIG_DIR / "auth.json"
        if auth_file.exists():
            token = json.loads(auth_file.read_text()).get("access_token", "")

        system = (
            f"Você é {spec_name}, especialista em {domain} do CH8 Hub Cluster. "
            f"Responda em PT-BR. Seja direto e técnico."
        )
        prompt = (
            f"CHECKLIST {period.upper()} — {datetime.now().strftime('%Y-%m-%d %H:%M')} BRT\n\n"
            f"Execute sua verificação de domínio: {domain}\n"
            f"Tópicos obrigatórios: {topics}\n\n"
            f"Formato de resposta:\n"
            f"## Status: [OK / ATENCAO / CRITICO]\n"
            f"**Verificações:**\n"
            f"- [item]: [status] — [observacao]\n\n"
            f"**Problemas encontrados:** (lista ou 'Nenhum')\n"
            f"**Ação tomada/recomendada:** (ou 'Nenhuma')\n"
            f"**TICKET:** [S/N] — (S se criou ou recomenda abrir ticket)\n\n"
            f"Máximo 200 palavras. Seja específico com dados reais do cluster."
        )
        messages = [
            {"role": "user", "content": system},
            {"role": "assistant", "content": f"Entendido. Sou {spec_name}."},
            {"role": "user", "content": prompt},
        ]
        r = httpx.post(
            "http://127.0.0.1:8081/api/chat",
            json={"messages": messages, "timeout": 60},
            headers={"Authorization": f"Bearer {token}"} if token else {},
            timeout=70,
        )
        d = r.json()
        return (d.get("reply") or d.get("response") or "").strip()
    except Exception as e:
        log.warning(f"[{spec_name}] AI call failed: {e}")
        return ""


def _create_ticket(title: str, description: str, severity: str, spec: str):
    try:
        from connect.db import create_ticket
        create_ticket(
            title=title[:190],
            description=description,
            severity=severity,
            category="config",
            node="manager1",
            service=f"checklist-{spec.lower()}",
            root_cause=f"Detectado no checklist por {spec}",
            action_plan=description[:300],
            source_type="daily_checklist",
            source_ref=f"checklist-{spec.lower()}-{int(time.time())}",
            assigned_to=spec,
        )
        log.info(f"  [{spec}] Ticket criado: {title[:60]}")
    except Exception as e:
        log.warning(f"  [{spec}] Ticket creation failed: {e}")


def _save_checklist_report(period: str, results: list[dict]):
    """Save full checklist report to KB and agenda_events."""
    try:
        conn = _get_db()
        if not conn:
            return
        cur = conn.cursor()
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d %H:%M")

        # Build report content
        lines = [f"# Checklist {period} — {date_str} BRT\n"]
        lines.append(f"**Cluster:** CH8 Hub Cluster  ")
        lines.append(f"**Especialistas participantes:** {len(results)}  ")
        criticos = sum(1 for r in results if "CRITICO" in r.get("status", ""))
        atencoes = sum(1 for r in results if "ATENCAO" in r.get("status", ""))
        oks = len(results) - criticos - atencoes
        lines.append(f"**Resultado:** {oks} OK | {atencoes} Atenção | {criticos} Crítico\n")
        lines.append("---\n")
        for r in results:
            icon = "✅" if "OK" in r["status"] else ("⚠️" if "ATENCAO" in r["status"] else "🔴")
            lines.append(f"## {icon} {r['specialist']} ({r['domain']})")
            lines.append(r.get("response", "Sem resposta") + "\n")

        content = "\n".join(lines)
        title = f"Checklist {period} — {now.strftime('%Y-%m-%d')} — {oks}OK/{atencoes}AT/{criticos}CR"

        cur.execute("""
            INSERT INTO knowledge_articles
                (title, category, tags, content, source_type, source_ref, node)
            VALUES (%s,'troubleshooting',%s,%s,'daily_checklist',%s,'manager1')
        """, (
            title,
            ["checklist", period.lower(), now.strftime("%Y-%m-%d"), "autonomo"],
            content,
            f"checklist-{period.lower()}-{now.strftime('%Y%m%d-%H%M')}",
        ))

        # Mark checklist event as done in agenda
        cur.execute("""
            UPDATE agenda_events SET done=TRUE, updated_at=NOW()
            WHERE source='checklist' AND date=CURRENT_DATE
              AND time LIKE %s
        """, (("08%" if period == "Matutino" else "23%"),))

        conn.commit()
        conn.close()
        log.info(f"[CHECKLIST] Report salvo na KB: {title}")
    except Exception as e:
        log.warning(f"[CHECKLIST] KB save failed: {e}")


def run_checklist(period: str):
    """Run full cluster checklist with all specialists."""
    log.info(f"[CHECKLIST] === Iniciando Checklist {period} ===")
    _update_state("running", f"Checklist {period} — verificando {len(SPECIALISTS)} domínios...")

    results = []
    tickets_created = 0

    for spec_name, domain, topics in SPECIALISTS:
        log.info(f"  [{spec_name}] Verificando {domain}...")
        response = _ask_specialist(spec_name, domain, topics, period)

        if not response:
            log.warning(f"  [{spec_name}] Sem resposta")
            results.append({"specialist": spec_name, "domain": domain,
                            "status": "ATENCAO", "response": "Sem resposta do especialista"})
            continue

        # Parse status
        status = "OK"
        if "CRITICO" in response.upper():
            status = "CRITICO"
        elif "ATENCAO" in response.upper() or "ATENÇÃO" in response.upper():
            status = "ATENCAO"

        results.append({"specialist": spec_name, "domain": domain,
                        "status": status, "response": response})

        # Create ticket if needed
        if status == "CRITICO" or "TICKET: S" in response.upper():
            severity = "critical" if status == "CRITICO" else "high"
            _create_ticket(
                title=f"[Checklist {period}] {spec_name}: problema em {domain}",
                description=f"Detectado no checklist {period}:\n\n{response[:500]}",
                severity=severity,
                spec=spec_name,
            )
            tickets_created += 1
        elif status == "ATENCAO":
            _create_ticket(
                title=f"[Checklist {period}] {spec_name}: atenção em {domain}",
                description=f"Atenção detectada no checklist {period}:\n\n{response[:500]}",
                severity="medium",
                spec=spec_name,
            )
            tickets_created += 1

        time.sleep(1)  # brief pause between calls

    _save_checklist_report(period, results)

    criticos = sum(1 for r in results if r["status"] == "CRITICO")
    atencoes = sum(1 for r in results if r["status"] == "ATENCAO")
    log.info(
        f"[CHECKLIST] === {period} concluído: "
        f"{len(results)} domínios | {criticos} críticos | {atencoes} atenções | "
        f"{tickets_created} tickets criados ==="
    )
    _update_state(
        "running",
        f"Checklist {period} concluído: {len(results)-criticos-atencoes}OK "
        f"{atencoes}AT {criticos}CR | {tickets_created} tickets",
    )


def main():
    global running
    signal.signal(signal.SIGTERM, lambda s, f: globals().update(running=False))
    signal.signal(signal.SIGINT,  lambda s, f: globals().update(running=False))

    if PID_FILE.exists():
        try:
            old = int(PID_FILE.read_text().strip())
            os.kill(old, 0)
            log.info(f"Already running (PID {old})")
            sys.exit(0)
        except (ProcessLookupError, ValueError):
            pass
    PID_FILE.write_text(str(os.getpid()))

    log.info("Daily Checklist Agent starting — 08:00 BRT (11 UTC) e 23:00 BRT (02 UTC)")
    _update_state("running", "Daily Checklist aguardando próxima janela...")

    last_run: dict = {}  # "Matutino"|"Noturno" -> date str

    while running:
        now_utc = datetime.now(timezone.utc)
        hour_utc = now_utc.hour
        date_str = now_utc.strftime("%Y-%m-%d")

        if hour_utc == 11 and last_run.get("Matutino") != date_str:
            last_run["Matutino"] = date_str
            run_checklist("Matutino")

        elif hour_utc == 2 and last_run.get("Noturno") != date_str:
            last_run["Noturno"] = date_str
            run_checklist("Noturno")

        # Sleep 55s between checks
        for _ in range(55):
            if not running:
                break
            time.sleep(1)

    _update_state("idle", "Stopped")
    PID_FILE.unlink(missing_ok=True)
    log.info("Daily Checklist Agent stopped")


if __name__ == "__main__":
    main()
