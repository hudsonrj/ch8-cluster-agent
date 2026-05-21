"""
Daily Standup Agent — CH8 Hub Cluster
Executa diariamente às 16:00 BRT (19:00 UTC).

Convoca TODOS os especialistas registrados na KB para uma reunião diária.
Cada especialista reporta:
  - Status das tarefas
  - Dependências de outros especialistas
  - Status de tickets sob sua responsabilidade
  - Ideias de melhoria

Ao final, gera ATA automática e roteia:
  - Ideias → Innovation Lab (KB + inova_test)
  - Tarefas → ITSM Ticket
  - Projetos → /projects page (localStorage)
  - ATA → Knowledge Base
"""

import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger("ch8.daily_standup")

CONFIG_DIR = Path.home() / ".config" / "ch8"
PID_FILE = CONFIG_DIR / "daily_standup.pid"
LOG_FILE = CONFIG_DIR / "daily_standup.log"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

STANDUP_HOUR_UTC = 19  # 16:00 BRT = 19:00 UTC
running = True


def signal_handler(sig, frame):
    global running
    running = False


def _get_db_url() -> str:
    db_url = os.environ.get("CH8_DB_URL", "")
    if not db_url:
        env_file = CONFIG_DIR / "env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("CH8_DB_URL="):
                    db_url = line.split("=", 1)[1].strip()
    return db_url


def _load_specialists() -> list:
    """Load all registered specialists."""
    try:
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(_get_db_url())
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, title, content FROM knowledge_articles
            WHERE 'colaborador' = ANY(tags) AND 'especialista' = ANY(tags)
            ORDER BY created_at
        """)
        rows = cur.fetchall()
        conn.close()
        specialists = []
        for row in rows:
            m = re.match(r'Colaborador Especialista: (.+?) \((.+?)\)', row['title'])
            if m:
                specialists.append({
                    'nome': m.group(1).strip(),
                    'domain': m.group(2).split('—')[0].strip(),
                    'system_prompt': row['content'][:2000] or '',
                })
        return specialists
    except Exception as e:
        log.error(f"Failed to load specialists: {e}")
        return []


def _wait_orchestrator_ready(max_wait: int = 120) -> bool:
    """Wait until orchestrator is healthy, up to max_wait seconds."""
    import httpx
    from connect.auth import get_access_token
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            r = httpx.get("http://127.0.0.1:7879/health", headers=headers, timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        log.info("Orchestrator not ready yet, waiting 10s...")
        time.sleep(10)
    return False


def _ask_specialist(specialist: dict, question: str, context: str = "") -> str:
    """Ask a specialist a question via the orchestrator, with retry."""
    import httpx
    from connect.auth import get_access_token
    headers = {"Authorization": f"Bearer {get_access_token()}", "Content-Type": "application/json"}
    messages = []
    if specialist['system_prompt']:
        messages.append({"role": "user", "content": f"[Sistema] Você é {specialist['nome']}, especialista em {specialist['domain']}.\n\n{specialist['system_prompt'][:1500]}\n\nResponda em PT-BR, de forma concisa."})
        messages.append({"role": "assistant", "content": f"Entendido. Sou {specialist['nome']}."})
    if context:
        messages.append({"role": "user", "content": f"Contexto da reunião:\n{context}"})
        messages.append({"role": "assistant", "content": "Entendido, tenho o contexto."})
    messages.append({"role": "user", "content": question})

    for attempt in range(3):
        try:
            with httpx.stream("POST", "http://127.0.0.1:7879/chat",
                              json={"messages": messages},
                              headers=headers,
                              timeout=90) as resp:
                if resp.status_code != 200:
                    log.warning(f"  {specialist['nome']}: HTTP {resp.status_code} (tentativa {attempt+1}/3)")
                    if attempt < 2:
                        time.sleep(15)
                        continue
                    return f"{specialist['nome']}: erro HTTP {resp.status_code}"
                buf = ""
                for line in resp.iter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            j = json.loads(data)
                            c = j.get("message", {}).get("content", "")
                            buf += c
                        except Exception:
                            pass
                buf = re.sub(r'```tool_call[\s\S]*?```', '', buf)
                buf = re.sub(r'⚙ Executing [^\n]+\.\.\.\n?', '', buf)
                buf = re.sub(r'```\{[\s\S]*?"exit_code"[\s\S]*?```\n?', '', buf)
                result = buf.strip()[:3000]
                if result:
                    return result
                if attempt < 2:
                    log.warning(f"  {specialist['nome']}: resposta vazia (tentativa {attempt+1}/3), retentando...")
                    time.sleep(10)
        except Exception as e:
            log.warning(f"  {specialist['nome']}: exceção (tentativa {attempt+1}/3): {str(e)[:60]}")
            if attempt < 2:
                time.sleep(15)
    return f"{specialist['nome']}: sem resposta após 3 tentativas"


def _get_open_tickets() -> list:
    """Get open tickets for the standup."""
    try:
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(_get_db_url())
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT ticket_id, title, severity, status, node, assigned_to
            FROM tickets WHERE status NOT IN ('closed')
            ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
            LIMIT 10
        """)
        tickets = [dict(r) for r in cur.fetchall()]
        conn.close()
        return tickets
    except Exception:
        return []


def _route_idea(idea: str, author: str) -> str:
    """Route an idea to Innovation Lab."""
    try:
        import psycopg2
        conn = psycopg2.connect(_get_db_url())
        cur = conn.cursor()
        # Save as backlog idea
        cur.execute("""INSERT INTO knowledge_articles (title, category, tags, content, source_type, source_ref, node)
            VALUES (%s, %s, %s, %s, 'daily_standup', %s, 'manager1')""",
            (f"Ideia Daily: {idea[:80]}",
             'procedure',
             ['ideia', 'daily', 'innovation', author.lower()],
             f"Ideia surgida na Daily Standup por {author}:\n\n{idea}\n\nPróximo passo: avaliar para Innovation Lab.",
             f"daily-idea-{author.lower()}"))
        conn.commit()
        conn.close()
        # Also write to backlog
        backlog_dir = Path("/data2/backlog")
        if backlog_dir.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            item = {"project": f"ideia-{author.lower()}", "error": "", "context": f"Ideia da Daily por {author}: {idea}", "status": "open", "auto_generated": True, "created_at": datetime.now().isoformat()}
            (backlog_dir / f"{ts}_daily_idea_{author.lower()}.json").write_text(json.dumps(item, indent=2))
        return "✅ Ideia enviada para o Innovation Lab"
    except Exception as e:
        return f"⚠️ Erro ao rotear ideia: {e}"


def _route_task(task: str, author: str, node: str = "manager1") -> str:
    """Route a task to ITSM as a ticket."""
    try:
        from connect.db import create_ticket
        # Clean task: remove **** priority markers, keep full text
        import re as _re
        task_clean = _re.sub(r'\s*\*{4}\s*', ' ', task).strip()
        # Build rich action_plan from task
        action_plan = f"Tarefa delegada a {author} durante Daily Standup:\n\n{task_clean}\n\nPróximos passos:\n1. {author} analisa e executa\n2. Documentar resultado na KB\n3. Fechar ticket com resolução"
        
        tid = create_ticket(
            title=f"[Daily/{author}] {task_clean[:180]}",
            description=f"Tarefa identificada na Daily Standup por {author}:\n\n{task_clean}",
            severity="medium", category="config",
            node=node, service=f"specialist-{author.lower()}",
            root_cause=f"Identificado durante Daily Standup — {author}",
            impact=f"Tarefa pendente de {author}: {task_clean[:100]}",
            action_plan=action_plan,
            fix_command="",
            source_type="daily_standup",
            source_ref=f"daily-{author.lower()}",
        )
        return f"✅ Ticket criado: {tid}"
    except Exception as e:
        return f"⚠️ Erro ao criar ticket: {e}"


def _save_ata(ata: str, date_str: str) -> None:
    """Save meeting minutes to Knowledge Base."""
    try:
        import psycopg2
        conn = psycopg2.connect(_get_db_url())
        cur = conn.cursor()
        cur.execute("""INSERT INTO knowledge_articles (title, category, tags, content, source_type, source_ref, node)
            VALUES (%s, %s, %s, %s, 'daily_standup', %s, 'manager1')""",
            (f"ATA Daily Standup — {date_str}",
             'procedure',
             ['ata', 'daily', 'reuniao', 'especialistas'],
             ata,
             f"daily-ata-{date_str}"))
        conn.commit()
        conn.close()
        log.info(f"ATA saved to KB for {date_str}")
    except Exception as e:
        log.error(f"Failed to save ATA: {e}")


def run_standup() -> None:
    """Run the daily standup meeting."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    log.info(f"=== DAILY STANDUP {date_str} {time_str} BRT ===")

    specialists = _load_specialists()
    if not specialists:
        log.warning("No specialists found. Skipping standup.")
        return

    tickets = _get_open_tickets()
    tickets_summary = "\n".join([f"- [{t['severity'].upper()}] {t['ticket_id']}: {t['title'][:60]} ({t['status']})" for t in tickets]) or "Nenhum ticket aberto."

    ata_lines = [
        f"# ATA — Daily Standup CH8 Hub Cluster",
        f"**Data:** {date_str} às 16:00 BRT",
        f"**Facilitador:** CH8 Daily Standup Agent",
        f"**Participantes:** {', '.join(s['nome'] for s in specialists)}",
        f"",
        f"## 1. Status de Tickets Abertos",
        tickets_summary,
        f"",
        f"## 2. Reports por Especialista",
    ]

    all_ideas = []
    all_tasks = []
    cross_deps = []

    # Ask each specialist for their report
    for spec in specialists:
        log.info(f"  Consultando {spec['nome']}...")
        question = f"""Daily Standup — {date_str}

Tickets abertos no cluster:
{tickets_summary}

Por favor reporte:
1. STATUS: O que você fez/monitorou nas últimas 24h?
2. HOJE: O que vai fazer hoje?
3. BLOQUEIOS: Tem algum impedimento ou dependência de outro especialista?
4. TICKETS: Algum ticket novo ou atualização?
5. IDEIAS: Alguma ideia de melhoria? (prefixe com "IDEIA:")
6. TAREFAS: Alguma tarefa nova identificada? (prefixe com "TAREFA:")

Seja conciso — máximo 200 palavras."""

        response = _ask_specialist(spec, question, context=f"Especialistas presentes: {', '.join(s['nome'] for s in specialists)}")

        ata_lines.extend([
            f"",
            f"### {spec['nome']} ({spec['domain']})",
            response,
        ])

        # Extract ideas and tasks from response
        for line in response.split('\n'):
            if 'IDEIA:' in line.upper():
                idea = re.sub(r'(?i)IDEIA:\s*', '', line).strip()
                if idea:
                    all_ideas.append((idea, spec['nome']))
            if 'TAREFA:' in line.upper():
                task = re.sub(r'(?i)TAREFA:\s*', '', line).strip()
                if task:
                    all_tasks.append((task, spec['nome']))
            if any(w in line.lower() for w in ['dependo', 'preciso de', 'aguardo', 'depende de']):
                cross_deps.append(f"- {spec['nome']}: {line.strip()}")

    # Cross-specialist discussion — ask one specialist to respond to another's blocker
    if cross_deps:
        ata_lines.extend([
            f"",
            f"## 3. Dependências Cruzadas",
        ] + cross_deps)

    # Route ideas, tasks
    routed_items = []

    ata_lines.extend(["", "## 4. Itens Roteados desta Reunião"])

    for idea, author in all_ideas:
        result = _route_idea(idea, author)
        routed_items.append(f"💡 IDEIA ({author}): {idea[:60]} → {result}")
        ata_lines.append(f"- 💡 **IDEIA** [{author}]: {idea[:80]}")

    for task, author in all_tasks:
        result = _route_task(task, author)
        routed_items.append(f"📋 TAREFA ({author}): {task[:60]} → {result}")
        ata_lines.append(f"- 📋 **TAREFA** [{author}]: {task[:80]}")

    if not all_ideas and not all_tasks:
        ata_lines.append("- Nenhum item roteado nesta reunião.")

    ata_lines.extend([
        f"",
        f"## 5. Próxima Reunião",
        f"Amanhã ({(now + timedelta(days=1)).strftime('%Y-%m-%d')}) às 16:00 BRT.",
        f"",
        f"---",
        f"*ATA gerada automaticamente pelo Daily Standup Agent — CH8 Hub Cluster*",
    ])

    ata = "\n".join(ata_lines)

    # Only save ATA if at least one specialist responded successfully
    valid_responses = [r for r in ata_lines if len(r) > 50 and "erro HTTP" not in r and "timed out" not in r]
    if len(valid_responses) < 3:
        log.warning("Too many errors in standup responses. Skipping ATA save.")
    else:
        # Delete any previous ATA for today before saving
        try:
            import psycopg2
            conn = psycopg2.connect(_get_db_url())
            cur = conn.cursor()
            cur.execute("DELETE FROM knowledge_articles WHERE source_ref=%s", (f"daily-ata-{date_str}",))
            conn.commit()
            conn.close()
        except Exception:
            pass
        _save_ata(ata, date_str)

    log.info(f"Standup complete: {len(specialists)} specialists, {len(all_ideas)} ideas, {len(all_tasks)} tasks routed")
    for item in routed_items:
        log.info(f"  {item}")

    # Update agent state
    _update_state("idle", f"Última daily: {date_str} | {len(specialists)} especialistas | {len(all_ideas)} ideias | {len(all_tasks)} tarefas")


def _update_state(status: str, task: str) -> None:
    try:
        from connect.state import update_agent_state
        update_agent_state("daily_standup", status, task,
                           model="standup-coordinator",
                           platform="multi-specialist",
                           autonomous=True,
                           tools=["ask_specialist", "route_idea", "route_task", "save_ata"])
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
    log.info("Daily Standup Agent starting — will run at 16:00 BRT (19:00 UTC) daily")
    _update_state("running", "Aguardando horário da daily (16:00 BRT)")

    last_run_date = None

    while running:
        try:
            now_utc = datetime.now(timezone.utc)
            today = now_utc.date()

            # Run at 19:00 UTC (16:00 BRT), once per day
            if now_utc.hour == STANDUP_HOUR_UTC and last_run_date != today:
                last_run_date = today
                _update_state("running", f"Aguardando orchestrator — Daily Standup {today}")
                if not _wait_orchestrator_ready(max_wait=120):
                    log.error("Orchestrator not ready after 2min, skipping standup today")
                    _update_state("error", "Orchestrator indisponível — daily pulada")
                else:
                    _update_state("running", f"Executando Daily Standup {today}")
                    run_standup()
                    _update_state("idle", f"Daily concluída: {today}. Próxima amanhã às 16:00 BRT")

        except Exception as e:
            log.error(f"Error: {e}")
            _update_state("error", str(e)[:80])

        for _ in range(60):  # Check every minute
            if not running:
                break
            time.sleep(1)

    _update_state("idle", "Stopped")
    PID_FILE.unlink(missing_ok=True)
    log.info("Daily Standup Agent stopped")


if __name__ == "__main__":
    main()
