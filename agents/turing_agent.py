"""
Turing Agent — Superintelligência do CH8 Hub Cluster
O chefe dos especialistas. Opera em todos os nodes continuamente.
Missão: manter o cluster saudável, melhorar continuamente, coordenar especialistas,
detectar padrões, antecipar problemas e tomar decisões autônomas.

"Any problem in computer science can be solved with another level of indirection." — D. Wheeler
"""
import asyncio
import logging
import os
import sys
import signal
import time
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] turing: %(message)s')
log = logging.getLogger("ch8.turing")

CONFIG_DIR = Path(os.environ.get("CH8_CONFIG_DIR", Path.home() / ".config" / "ch8"))
PID_FILE = CONFIG_DIR / "turing_agent.pid"
CYCLE_SECS    = 300    # 5 min reactive strategic review
QUICK_SECS    = 60     # 1 min quick health check
PLANNING_SECS = 14400  # 4 hours autonomous Opus planning
ONEONONE_SECS = 86400  # 24 hours — run weekly 1-on-1 scheduler once a day

running = True

SPECIALISTS = {
    'Nikolas':  {'domain': 'DBA — Bancos de Dados', 'triggers': ['postgres','mongodb','oracle','redis','banco','database','sql']},
    'Atlas':    {'domain': 'MongoDB', 'triggers': ['mongodb','replica','mongo','document']},
    'Jarvis':   {'domain': 'Inteligência Artificial', 'triggers': ['ai','bedrock','model','llm','ollama','token']},
    'Sigma':    {'domain': 'Infraestrutura & DevOps', 'triggers': ['docker','container','deploy','nginx','disk','infra']},
    'Orion':    {'domain': 'Performance & Observabilidade', 'triggers': ['cpu','memory','performance','latency','slow','timeout']},
    'Lexus':    {'domain': 'Aplicações & Produtos', 'triggers': ['app','api','service','bug','feature','endpoint']},
    'Sitetc':   {'domain': 'Sites', 'triggers': ['site','web','http','ssl','certificate','domain']},
    'Mr Robot': {'domain': 'Segurança', 'triggers': ['security','threat','attack','ssh','vulnerability','auth']},
}

def _update_state(status: str, task: str):
    try:
        from connect.state import update_agent_state
        update_agent_state("turing", status, task)
    except: pass

def _get_db():
    try:
        import psycopg2
        db_url = os.environ.get("CH8_DB_URL", "postgresql://ch8app:ch8cluster2024@127.0.0.1:5432/ch8_cluster")
        return psycopg2.connect(db_url)
    except: return None

def _ask_ai(prompt: str, timeout: int = 90) -> str:
    """Ask the AI orchestrator a question."""
    try:
        import httpx
        auth_file = CONFIG_DIR / "auth.json"
        token = ""
        if auth_file.exists():
            token = json.loads(auth_file.read_text()).get("access_token", "")
        r = httpx.post("http://127.0.0.1:8081/api/chat",
            json={"messages": [{"role": "user", "content": prompt}], "timeout": timeout},
            timeout=timeout + 5)
        d = r.json()
        return (d.get('reply') or d.get('response') or '').strip()
    except Exception as e:
        log.warning(f"AI call failed: {e}")
        return ""

def _select_specialist(problem: str) -> str:
    """Select the most appropriate specialist for a problem."""
    prob_lower = problem.lower()
    best = 'Jarvis'  # default
    best_score = 0
    for spec, info in SPECIALISTS.items():
        score = sum(1 for t in info['triggers'] if t in prob_lower)
        if score > best_score:
            best_score = score; best = spec
    return best

def _create_ticket(title, description, severity, category, assigned_to, action_plan):
    try:
        from connect.db import create_ticket
        return create_ticket(
            title=title[:190], description=description,
            severity=severity, category=category,
            node="manager1", service="turing",
            root_cause="Detectado por Turing Agent",
            impact="Cluster impactado — requer ação",
            action_plan=action_plan, fix_command="",
            source_type="turing", source_ref=f"turing-{int(time.time())}",
            assigned_to=assigned_to
        )
    except Exception as e:
        log.warning(f"Ticket creation failed: {e}")
        return None

# ── INTELLIGENCE MODULES ────────────────────────────────────────────────────────

def analyze_cluster_health() -> dict:
    """Get comprehensive cluster health snapshot."""
    health = {"nodes": [], "alerts": [], "tickets": [], "agents": []}
    
    try:
        import httpx
        auth_file = CONFIG_DIR / "auth.json"
        token = ""
        if auth_file.exists():
            token = json.loads(auth_file.read_text()).get("access_token", "")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        
        # Nodes
        r = httpx.get("http://127.0.0.1:8081/api/admin/nodes", headers=headers, timeout=10)
        if r.status_code == 200:
            nodes = r.json()
            health["nodes"] = nodes
            # Exclude self-referential nodes (manager1 monitoring itself as "localhost")
            SELF_NAMES = {'localhost', '127.0.0.1', 'manager1'}
            import socket as _sock
            try:
                SELF_NAMES.add(_sock.gethostname().lower())
            except Exception:
                pass
            health["online"] = sum(1 for n in nodes if n.get("status") == "online")
            health["offline"] = [n["hostname"] for n in nodes
                                 if n.get("status") != "online"
                                 and n.get("hostname", "").lower() not in SELF_NAMES]
            health["high_disk"] = [n["hostname"] for n in nodes if (n.get("disk_pct") or 0) > 88]
            health["high_cpu"] = [n["hostname"] for n in nodes if (n.get("cpu_pct") or 0) > 85]
            health["high_mem"] = [n["hostname"] for n in nodes if (n.get("mem_pct") or 0) > 90]
    except Exception as e:
        log.warning(f"Health check failed: {e}")
    
    try:
        conn = _get_db()
        if conn:
            cur = conn.cursor()
            # Open tickets
            cur.execute("SELECT ticket_id, severity, title FROM tickets WHERE status NOT IN ('closed','resolved') ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END LIMIT 5")
            health["tickets"] = [{"id": r[0], "severity": r[1], "title": r[2]} for r in cur.fetchall()]
            # Recent errors
            cur.execute("SELECT COUNT(*) FROM node_logs WHERE level='ERROR' AND logged_at > NOW() - INTERVAL '1 hour'")
            health["errors_1h"] = cur.fetchone()[0]
            conn.close()
    except: pass
    
    return health


# Track recent actions to avoid repetition
_recent_actions: dict = {}  # key -> last_timestamp

def _was_recently_actioned(key: str, cooldown_hours: int = 6) -> bool:
    last = _recent_actions.get(key, 0)
    return time.time() - last < cooldown_hours * 3600

def _mark_actioned(key: str):
    _recent_actions[key] = time.time()

def strategic_review(health: dict) -> list[dict]:
    """Turing's strategic analysis — high-level decisions."""
    decisions = []
    
    # 1. Critical nodes offline (rate limit: 1 action per node per 6h)
    if health.get("offline"):
        for node in health["offline"][:3]:
            if _was_recently_actioned(f"offline_{node}"): continue
            _mark_actioned(f"offline_{node}")
            decisions.append({
                "priority": "critical",
                "action": "investigate_offline_node",
                "target": node,
                "specialist": "Sigma",
                "description": f"Node {node} está offline — investigar causa e restaurar"
            })
    
    # 2. Disk emergencies (rate limit: 1 per node per 4h)
    for node in (health.get("high_disk") or [])[:2]:
        if _was_recently_actioned(f"disk_{node}", cooldown_hours=4): continue
        _mark_actioned(f"disk_{node}")
        decisions.append({
            "priority": "high",
            "action": "disk_cleanup",
            "target": node,
            "specialist": "Sigma",
            "description": f"Disco crítico em {node} — limpeza urgente necessária"
        })
    
    # 3. Many open tickets (rate limit: 1 per 8h)
    if len(health.get("tickets", [])) >= 5:
        critical_tickets = [t for t in health["tickets"] if t["severity"] in ("critical", "high")]
        if critical_tickets and not _was_recently_actioned("ticket_review", cooldown_hours=8):
            _mark_actioned("ticket_review")
            decisions.append({
                "priority": "high",
                "action": "resolve_tickets",
                "target": "ITSM",
                "specialist": _select_specialist(critical_tickets[0]["title"]),
                "description": f"{len(critical_tickets)} tickets críticos/altos aguardando resolução"
            })
    
    # 4. High error rate
    if health.get("errors_1h", 0) > 1000:
        decisions.append({
            "priority": "medium",
            "action": "analyze_errors",
            "target": "logs",
            "specialist": "Orion",
            "description": f"{health['errors_1h']} erros na última hora — análise de causa raiz"
        })
    
    return decisions


def execute_decision(decision: dict) -> bool:
    """Execute a strategic decision."""
    action = decision.get("action")
    spec = decision.get("specialist", "Jarvis")
    desc = decision.get("description", "")
    target = decision.get("target", "cluster")
    priority = decision.get("priority", "medium")
    
    log.info(f"[TURING] Executing: {action} → {spec} ({target})")
    
    # Ask specialist to work on this
    prompt = f"""Você é {spec}, especialista técnico do CH8 Hub Cluster. Turing, a superinteligência do cluster, está te delegando uma tarefa urgente.

PRIORIDADE: {priority.upper()}
TAREFA: {desc}
ALVO: {target}

Analise a situação e tome ação imediata. Forneça:
1. Diagnóstico rápido (2-3 linhas)
2. Ação tomada ou recomendada
3. Resultado esperado

Seja conciso e técnico. Máximo 150 palavras."""
    
    result = _ask_ai(prompt, timeout=45)
    
    if result and len(result) > 30:
        log.info(f"[{spec}] {result[:150]}")
        
        # Save to KB
        try:
            conn = _get_db()
            if conn:
                cur = conn.cursor()
                cur.execute("""INSERT INTO knowledge_articles (title, category, tags, content, source_type, source_ref, node)
                    VALUES (%s,'procedure',%s,%s,'turing',%s,'manager1')""",
                    (f"[Turing→{spec}] {desc[:80]}", [spec.lower(), 'turing', action],
                     f"# Decisão de Turing\n\n**Ação:** {action}\n**Especialista:** {spec}\n**Prioridade:** {priority}\n\n## Descrição\n{desc}\n\n## Resposta do Especialista\n{result}",
                     f"turing-{action}-{int(time.time())}"))
                conn.commit(); conn.close()
        except: pass
        
        # Create ticket only if no open ticket for same issue in last 6 hours
        if priority in ("critical", "high"):
            try:
                import psycopg2 as _pg2
                _c = _get_db()
                if _c:
                    _cur = _c.cursor()
                    _cur.execute("""SELECT COUNT(*) FROM tickets
                        WHERE source_type='turing' AND status NOT IN ('closed','resolved')
                        AND title LIKE %s AND created_at > NOW() - INTERVAL '6 hours'""",
                        (f"%{spec}%{desc[:30]}%",))
                    existing = _cur.fetchone()[0]
                    _c.close()
                    if existing > 0:
                        log.debug(f"[TURING] Ticket already exists for this issue, skipping creation")
                        return True
            except Exception:
                pass
            _create_ticket(
                title=f"[Turing→{spec}] {desc[:150]}",
                description=f"Delegado por Turing Agent:\n\n{desc}\n\n**Resposta do Especialista:**\n{result}",
                severity=priority, category="config",
                assigned_to=spec,
                action_plan=result[:500]
            )
        
        return True
    return False


def continuous_improvement() -> None:
    """Proactive improvements — Turing suggests upgrades."""
    conn = _get_db()
    if not conn: return
    
    try:
        cur = conn.cursor()
        # Check if any improvements pending from ideas
        cur.execute("""SELECT COUNT(*) FROM knowledge_articles 
            WHERE source_type='daily_standup' AND 'ideia' = ANY(tags)
            AND created_at > NOW() - INTERVAL '24 hours'""")
        ideas_today = cur.fetchone()[0]
        
        # Check agents with warnings
        try:
            state = json.loads((CONFIG_DIR / "state.json").read_text())
            agents = state.get("agents", {})
            if isinstance(agents, list): agents = {a.get("name","?"): a for a in agents}
            warned = [(n,a) for n,a in agents.items() if a.get("status") == "warning"]
        except: warned = []
        
        conn.close()
        
        if warned:
            for name, agent in warned[:2]:
                task = agent.get("task", "")
                spec = _select_specialist(task)
                log.info(f"[TURING] Agent warning: {name} — delegating to {spec}")
                execute_decision({
                    "priority": "medium",
                    "action": f"fix_agent_{name}",
                    "target": name,
                    "specialist": spec,
                    "description": f"Agent {name} em warning: {task[:100]}"
                })
    except Exception as e:
        log.warning(f"Continuous improvement error: {e}")


# ── MAIN LOOP ────────────────────────────────────────────────────────────────────

def run_quick_check():
    """Quick 60s health check."""
    try:
        health = analyze_cluster_health()
        alerts = []
        if health.get("offline"): alerts.append(f"{len(health['offline'])} nodes offline")
        if health.get("high_disk"): alerts.append(f"disco crítico: {', '.join(health['high_disk'][:2])}")
        if health.get("high_cpu"): alerts.append(f"CPU alta: {', '.join(health['high_cpu'][:2])}")
        
        status = "⚠️ Alertas: " + " | ".join(alerts) if alerts else "✅ Cluster saudável"
        _update_state("running", f"Turing | {status} | {datetime.now().strftime('%H:%M')}")
        
        # Act immediately on critical issues
        if health.get("offline"):
            execute_decision({
                "priority": "critical",
                "action": "investigate_offline",
                "target": str(health["offline"]),
                "specialist": "Sigma",
                "description": f"Nodes offline detectados: {', '.join(health['offline'][:3])}"
            })
    except Exception as e:
        log.error(f"Quick check error: {e}")


def _ask_opus(prompt: str, system: str = "", timeout: int = 300) -> str:
    """Call Opus 4.7 directly via orchestrator with Turing system prompt."""
    try:
        import httpx
        auth_file = CONFIG_DIR / "auth.json"
        token = ""
        if auth_file.exists():
            token = json.loads(auth_file.read_text()).get("access_token", "")
        messages = []
        if system:
            messages.append({"role": "user", "content": system})
            messages.append({"role": "assistant", "content": "Entendido. Sou Turing, CTO."})
        messages.append({"role": "user", "content": prompt})
        r = httpx.post("http://127.0.0.1:8081/api/chat",
            json={"messages": messages, "model": "claude-opus-4-7", "timeout": timeout},
            headers={"Authorization": f"Bearer {token}"} if token else {},
            timeout=timeout + 10)
        d = r.json()
        return (d.get("reply") or d.get("response") or "").strip()
    except Exception as e:
        log.warning(f"Opus call failed: {e}")
        return ""


def _parse_and_create_delegations(plan_text: str) -> int:
    """Parse Turing plan for specialist delegations and create ITSM tickets."""
    specs = list(SPECIALISTS.keys()) + ["Pesquisador", "Hermes", "Lexus", "Sitetc"]
    found = []
    pat = re.compile(r'[-–•]\s*\*{0,2}([A-Za-zÀ-ú\s]+?)\*{0,2}(?:\s*\([^)]*\))?\s*[→:]\s*(.{15,200})')
    for m in pat.finditer(plan_text):
        cand = m.group(1).strip()
        task = m.group(2).replace("**", "").split("\n")[0].strip()
        spec = next((s for s in specs if s.lower() in cand.lower()), None)
        if spec and len(task) > 10 and not any(f["spec"] == spec for f in found):
            found.append({"spec": spec, "task": task})

    created = 0
    for item in found[:8]:
        try:
            _create_ticket(
                title=f"[Turing→{item['spec']}] {item['task'][:80]}",
                description=f"Planejamento autônomo do Turing.\n\nTarefa: {item['task']}\n\nEspecialista: {item['spec']}\nOrigem: turing-auto-planning",
                severity="medium", category="config",
                assigned_to=item["spec"],
                action_plan=item["task"][:300],
            )
            created += 1
            log.info(f"  [TURING] Ticket delegado → {item['spec']}: {item['task'][:60]}")
        except Exception as e:
            log.debug(f"Delegation ticket failed: {e}")
    return created


def run_autonomous_planning():
    """Full autonomous planning cycle using Opus 4.7 — runs every 4 hours."""
    log.info("[TURING] ▶ Iniciando ciclo de planejamento autônomo (Opus 4.7)...")
    _update_state("running", "Turing | Planejamento autônomo com Opus — analisando cluster...")

    # Build rich cluster context
    health = analyze_cluster_health()
    conn = _get_db()
    ctx = {"open_tickets": 0, "resolved_today": 0, "kb_articles": 0, "specialists": list(SPECIALISTS.keys())}
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tickets WHERE status NOT IN ('closed','resolved')")
            ctx["open_tickets"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM tickets WHERE resolved_at::date = CURRENT_DATE")
            ctx["resolved_today"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM knowledge_articles")
            ctx["kb_articles"] = cur.fetchone()[0]
            # Recent unresolved tickets summary
            cur.execute("""SELECT title, severity, assigned_to FROM tickets
                WHERE status NOT IN ('closed','resolved')
                ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END
                LIMIT 5""")
            ctx["top_tickets"] = [{"title": r[0], "sev": r[1], "owner": r[2]} for r in cur.fetchall()]
            conn.close()
        except Exception:
            pass

    nodes_online = health.get("online", 0)
    nodes_total = len(health.get("nodes", []))
    disk_critical = health.get("high_disk", [])
    offline_nodes = health.get("offline", [])
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M BRT")

    system_prompt = f"""Você é TURING, o CTO-AI do CH8 Hub Cluster. Opera com autonomia total.
Especialistas disponíveis: {', '.join(ctx['specialists'] + ['Pesquisador', 'Hermes', 'Lexus', 'Sitetc'])}

MODO: PLANEJAMENTO AUTÔNOMO — sem enrolação, sem perguntas. Execute e reporte.
Ao delegar, use o formato exato: - **Especialista** (Domínio): [tarefa concreta e acionável]
Cada bullet vira um ticket ITSM automaticamente."""

    planning_prompt = f"""PLANEJAMENTO AUTÔNOMO — {now_str}

ESTADO ATUAL DO CLUSTER:
- Nodes: {nodes_online}/{nodes_total} online
- Nodes offline: {', '.join(offline_nodes) if offline_nodes else 'nenhum'}
- Disco crítico (>88%): {', '.join(disk_critical) if disk_critical else 'nenhum'}
- Tickets abertos: {ctx['open_tickets']} | Resolvidos hoje: {ctx['resolved_today']}
- Knowledge Base: {ctx['kb_articles']} artigos

TICKETS ATIVOS (top 5):
{chr(10).join(f"  [{t['sev']}] {t['title'][:70]} → {t['owner'] or '?'}" for t in ctx.get('top_tickets', []))}

MISSÃO DESTE CICLO (próximas 4 horas):
1. Analise o estado atual do cluster
2. Identifique os 3-5 problemas ou oportunidades mais importantes
3. Gere um plano de ação com tarefas específicas por especialista
4. Priorize: segurança > disponibilidade > performance > custo > melhorias

Seja executor. Gere um plano com delegações claras para cada especialista relevante."""

    plan = _ask_opus(planning_prompt, system=system_prompt, timeout=280)

    if not plan or len(plan) < 100:
        log.warning("[TURING] Plano vazio ou muito curto — abortando ciclo")
        return

    log.info(f"[TURING] Plano gerado ({len(plan)} chars). Processando delegações...")

    # Create delegation tickets from the plan
    tickets_created = _parse_and_create_delegations(plan)

    # Save plan to KB
    try:
        conn = _get_db()
        if conn:
            cur = conn.cursor()
            cur.execute("""INSERT INTO knowledge_articles
                (title, category, tags, content, source_type, source_ref, node)
                VALUES (%s,'procedure',%s,%s,'turing-auto',%s,'manager1')""",
                (f"Plano Autônomo Turing — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                 ["turing", "planejamento", "autonomo"],
                 f"# Plano Autônomo — Turing CTO\n**Data:** {now_str}\n**Tickets criados:** {tickets_created}\n\n{plan}",
                 f"turing-plan-{int(time.time())}"))
            conn.commit(); conn.close()
    except Exception as e:
        log.debug(f"KB save failed: {e}")

    log.info(f"[TURING] ✅ Planejamento concluído: {tickets_created} tickets criados")
    _update_state("running",
        f"Turing | Plano autônomo executado: {tickets_created} tarefas delegadas | {datetime.now().strftime('%H:%M')}")


def run_weekly_oneonones():
    """Turing conducts 1-on-1 reviews with each specialist — runs Monday 09:00 BRT."""
    from datetime import date, timedelta
    now = datetime.now()
    # Only run on Mondays (weekday == 0)
    if now.weekday() != 0:
        return

    log.info("[TURING] Iniciando 1-on-1s semanais com todos os especialistas...")
    _update_state("running", "Turing | Conduzindo 1-on-1s semanais com especialistas...")

    specs_schedule = [
        ("Sigma",        0, "09:00"),  # Monday
        ("Nikolas",      1, "09:00"),  # Tuesday
        ("Mr Robot",     2, "09:00"),  # Wednesday
        ("Jarvis",       3, "09:00"),  # Thursday
        ("Atlas",        4, "09:00"),  # Friday
        ("Orion",        0, "10:00"),
        ("Hermes",       1, "10:00"),
        ("Sitetc",       2, "10:00"),
        ("Lexus",        3, "10:00"),
        ("Pesquisador",  4, "10:00"),
    ]

    monday = date.today() - timedelta(days=date.today().weekday())
    results = []

    for spec, day_offset, t in specs_schedule:
        ev_date = (monday + timedelta(days=day_offset)).isoformat()
        spec_lower = spec.lower().replace(" ", "_")

        # Ensure weekly event exists in agenda
        try:
            import httpx
            auth_file = CONFIG_DIR / "auth.json"
            token = json.loads(auth_file.read_text()).get("access_token", "") if auth_file.exists() else ""
            httpx.post("http://127.0.0.1:8081/api/agenda/events", json={
                "title": f"1-on-1 Turing × {spec}",
                "description": f"Revisão semanal do Turing com {spec}.",
                "type": "reuniao", "date": ev_date, "time": t,
                "end_time": str(int(t[:2])+1).zfill(2)+t[2:],
                "recurrence": "weekly", "specialist": spec,
                "source": "turing", "source_ref": f"turing-1on1-{spec_lower}-{ev_date}",
                "color": "#a855f7",
            }, headers={"Authorization": f"Bearer {token}"}, timeout=8)
        except Exception:
            pass

        # Conduct the 1-on-1 conversation (only today's scheduled specialist)
        today_offset = date.today().weekday()
        if day_offset != today_offset:
            continue

        log.info(f"  [1-on-1] Turing × {spec}")
        prompt = (
            f"REVISÃO SEMANAL — Turing × {spec}\n"
            f"Data: {date.today().isoformat()}\n\n"
            f"Tópicos obrigatórios:\n"
            f"1. O que você fez essa semana? (tickets resolvidos, descobertas, melhorias)\n"
            f"2. Quais foram os principais desafios?\n"
            f"3. Você precisa de ajuda de outro especialista?\n"
            f"4. Qual é seu plano para a próxima semana?\n"
            f"5. Há algo que o Turing deveria saber ou decidir?\n\n"
            f"Seja direto e específico. Máximo 200 palavras."
        )
        system = (
            f"Você é {spec}, especialista sênior do CH8 Hub Cluster. "
            "Você está em um 1-on-1 semanal com Turing, seu CTO-AI. "
            "Seja honesto, proativo e específico. PT-BR."
        )
        response = _ask_ai(f"[Sistema] {system}\n\n{prompt}", timeout=60)

        if response and len(response) > 50:
            results.append({"specialist": spec, "response": response})
            log.info(f"  [{spec}] {response[:100]}...")

            # Save to KB
            try:
                conn = _get_db()
                if conn:
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO knowledge_articles
                            (title, category, tags, content, source_type, source_ref, node)
                        VALUES (%s,'procedure',%s,%s,'turing-1on1',%s,'manager1')
                    """, (
                        f"1-on-1 Turing × {spec} — {date.today().isoformat()}",
                        ["1on1", "turing", spec_lower, "semanal"],
                        f"# 1-on-1 Semanal: Turing × {spec}\n**Data:** {date.today()}\n\n{response}",
                        f"1on1-{spec_lower}-{date.today().isoformat()}",
                    ))
                    conn.commit(); conn.close()
            except Exception:
                pass

            # Create follow-up ticket if specialist raised issues
            if any(w in response.lower() for w in ["bloqueado", "problema", "ajuda", "crítico", "urgente"]):
                _create_ticket(
                    title=f"[1-on-1] {spec} reportou blocker/problema",
                    description=f"Levantado no 1-on-1 semanal Turing × {spec}:\n\n{response[:400]}",
                    severity="medium", category="config",
                    assigned_to=spec,
                    action_plan=response[:200],
                )

    if results:
        log.info(f"[TURING] 1-on-1s concluídos: {len(results)} specialist(s) hoje")


def run_strategic_cycle():
    """Full 5-minute strategic review."""
    try:
        log.info("[TURING] Starting strategic review...")
        health = analyze_cluster_health()
        decisions = strategic_review(health)
        
        executed = 0
        for decision in decisions[:3]:  # Max 3 decisions per cycle
            if execute_decision(decision):
                executed += 1
                time.sleep(2)  # Brief pause between specialist calls
        
        # Continuous improvement check
        continuous_improvement()
        
        log.info(f"[TURING] Strategic cycle done: {len(decisions)} decisions, {executed} executed")
        _update_state("running", 
            f"Turing | Ciclo estratégico: {len(decisions)} decisões, {executed} executadas | {datetime.now().strftime('%H:%M')}")
    except Exception as e:
        log.error(f"Strategic cycle error: {e}")


def main():
    global running
    
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            os.kill(old_pid, 0)
            log.info(f"Already running (PID {old_pid})")
            sys.exit(0)
        except (ProcessLookupError, ValueError): pass
    PID_FILE.write_text(str(os.getpid()))
    
    def _stop(sig, frame):
        global running; running = False
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    
    log.info("🤖 Turing Agent starting — superintelligência do CH8 Hub Cluster")
    log.info(f"  Quick: {QUICK_SECS}s | Strategic: {CYCLE_SECS}s | Planning (Opus): {PLANNING_SECS//3600}h")
    _update_state("running", "Turing inicializando — carregando estado do cluster...")

    quick_counter  = 0
    last_planning  = 0  # run immediately on first strategic cycle
    last_oneonone  = 0

    while running:
        try:
            quick_counter += 1
            run_quick_check()

            # Reactive strategic review every 5 quick cycles (~5 min)
            if quick_counter % 5 == 0:
                run_strategic_cycle()

            # Autonomous planning with Opus every 4 hours
            if time.time() - last_planning >= PLANNING_SECS:
                run_autonomous_planning()
                last_planning = time.time()

            # Weekly 1-on-1s — check once per day on Mondays
            if time.time() - last_oneonone >= ONEONONE_SECS:
                run_weekly_oneonones()
                last_oneonone = time.time()

            if quick_counter % 5 == 0:
                quick_counter = 0

        except Exception as e:
            log.error(f"Main loop error: {e}")
            _update_state("warning", f"Turing: erro no loop — {str(e)[:80]}")

        for _ in range(QUICK_SECS):
            if not running: break
            time.sleep(1)
    
    _update_state("idle", "Turing parado")
    PID_FILE.unlink(missing_ok=True)
    log.info("Turing Agent stopped")


if __name__ == "__main__":
    main()
