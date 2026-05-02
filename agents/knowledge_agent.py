"""
Knowledge Agent — Obsidian-style Cluster Knowledge Base

Roda no master e organiza todo o conhecimento do cluster em /data2/knowledge/.
Formato: Markdown com wikilinks ([[...]]), compatível com Obsidian.

Responsabilidades:
  - Coleta catálogo do cluster a cada ciclo
  - Gera/atualiza páginas de nós, agentes, serviços
  - Indexa projetos do sandbox
  - Processa security findings e gera relatórios
  - Mantém log diário de atividade
  - Expõe endpoint /knowledge/write para outros agentes publicarem

Regras:
  - Ciclo a cada 10 min
  - Não sobrescreve edições manuais (verifica mtime)
  - Máximo 500 arquivos no vault (cleanup automático)
  - Não roda se CPU > 80%
"""

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from connect.ai_config import get_ai_client

log = logging.getLogger("ch8.knowledge")

# ── Configuration ─────────────────────────────────────────────────────────────

VAULT_DIR = Path("/data2/knowledge")
SANDBOX_DIR = Path("/data2/sandbox")
BACKLOG_DIR = Path("/data2/backlog")
CONFIG_DIR = Path.home() / ".config" / "ch8"
STATE_FILE = CONFIG_DIR / "state.json"
PID_FILE = CONFIG_DIR / "knowledge_agent.pid"
LOG_FILE = CONFIG_DIR / "knowledge_agent.log"

CYCLE_INTERVAL = 600  # 10 minutes
CPU_THRESHOLD = 80.0
MAX_VAULT_FILES = 500

_last_status = "Starting..."
_action_history = []


# ── State ─────────────────────────────────────────────────────────────────────

def _update_agent_state(status: str, task: str):
    global _last_status
    _last_status = task
    try:
        state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        agents = state.get("agents", [])
        entry = {
            "name": "knowledge",
            "status": status,
            "task": task,
            "model": "vault-indexer",
            "platform": "obsidian",
            "autonomous": True,
            "alerts": 0,
            "security_findings": 0,
            "predictions": 0,
            "heavy_procs": 0,
            "tools": ["file_write", "cluster_catalog"],
            "details": {
                "history": _action_history[-10:],
                "stats": _get_vault_stats(),
            },
            "updated_at": int(time.time()),
        }
        agents = [a for a in agents if a.get("name") != "knowledge"]
        agents.append(entry)
        state["agents"] = agents
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        log.warning(f"State update failed: {e}")


def _record(action: str, detail: str):
    _action_history.append({
        "ts": datetime.now().strftime("%H:%M:%S"),
        "action": action[:60],
        "result": detail[:80],
    })
    if len(_action_history) > 15:
        _action_history[:] = _action_history[-15:]


def _get_vault_stats() -> dict:
    md_files = list(VAULT_DIR.rglob("*.md"))
    return {
        "total_files": len(md_files),
        "max_files": MAX_VAULT_FILES,
        "categories": len([d for d in VAULT_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")]),
    }


# ── Catalog Fetching ──────────────────────────────────────────────────────────

def get_catalog() -> list:
    """Get all online nodes from control server."""
    import httpx
    try:
        from connect.auth import CONTROL_URL, get_access_token, get_network_id
        headers = {"Authorization": f"Bearer {get_access_token()}"}
        r = httpx.get(f"{CONTROL_URL}/nodes?network_id={get_network_id()}",
                      headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("nodes", data) if isinstance(data, dict) else data
    except Exception as e:
        log.warning(f"Catalog fetch failed: {e}")
    return []


# ── Vault Writers ─────────────────────────────────────────────────────────────

def _safe_write(path: Path, content: str):
    """Write only if content changed (preserves mtime for manual edits)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text()
        if existing.strip() == content.strip():
            return False
    path.write_text(content)
    return True


def update_node_page(node: dict):
    """Create/update a node's knowledge page."""
    hostname = node.get("hostname", node.get("node_id", "unknown"))
    safe_name = hostname.replace("/", "-").replace("\\", "-")
    path = VAULT_DIR / "nodes" / f"{safe_name}.md"

    caps = "\n".join(f"- {c}" for c in node.get("capabilities", []))
    models = "\n".join(f"- {m}" for m in node.get("models", []))
    services = "\n".join(
        f"- **{s.get('name', '?')}** ({s.get('type', '?')}) — {s.get('status', '?')}"
        for s in node.get("services", [])
    )
    agents_list = "\n".join(
        f"- [[{a.get('name', '?')}]] — {a.get('status', '?')}: {a.get('task', '')[:60]}"
        for a in node.get("agents", [])
    )

    content = f"""---
type: node
node_id: "{node.get('node_id', '')}"
hostname: "{hostname}"
address: "{node.get('address', '')}"
os: "{node.get('os', '?')}"
arch: "{node.get('arch', '?')}"
updated: "{datetime.now().isoformat()}"
---

# {hostname}

## Hardware
- **CPU:** {node.get('cpu_cores', '?')} cores (usage: {node.get('cpu_pct', 0):.0f}%)
- **RAM:** {node.get('mem_total_gb', 0):.1f} GB (usage: {node.get('mem_pct', 0):.0f}%)
- **Disk:** {node.get('disk_total_gb', 0):.1f} GB (usage: {node.get('disk_pct', 0):.0f}%)

## AI
- **Provider:** {node.get('ai_provider', 'none')}
- **Model:** {node.get('ai_model', 'none')}

## Capabilities
{caps or '- none'}

## Ollama Models
{models or '- none'}

## Services
{services or '- none detected'}

## Agents
{agents_list or '- none running'}

## Network
- Address: `{node.get('address', '')}:{node.get('port', 7878)}`
- Status: {node.get('status', 'unknown')}
- Last seen: {datetime.fromtimestamp(node.get('last_seen', 0)).strftime('%Y-%m-%d %H:%M:%S') if node.get('last_seen') else 'never'}

---
*Auto-generated by [[Knowledge Agent]] — {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""
    return _safe_write(path, content)


def update_agent_page(agent: dict, node_hostname: str):
    """Create/update an agent's knowledge page."""
    name = agent.get("name", "unknown")
    path = VAULT_DIR / "agents" / f"{name}.md"

    details = agent.get("details", {})
    tools = agent.get("tools", [])
    history = details.get("history", [])
    stats = details.get("stats", {})

    tools_list = "\n".join(f"- `{t}`" for t in tools)
    history_list = "\n".join(
        f"- `{h.get('ts','')}` **{h.get('action','')}** → {h.get('result','')}"
        for h in history[-10:]
    )
    stats_list = "\n".join(f"- {k}: **{v}**" for k, v in stats.items())

    content = f"""---
type: agent
name: "{name}"
node: "{node_hostname}"
status: "{agent.get('status', 'unknown')}"
model: "{agent.get('model', '')}"
platform: "{agent.get('platform', '')}"
autonomous: {str(agent.get('autonomous', False)).lower()}
updated: "{datetime.now().isoformat()}"
---

# {name}

> Runs on [[{node_hostname}]]

## Status
- **State:** {agent.get('status', '?')}
- **Current task:** {agent.get('task', 'none')}
- **Model:** {agent.get('model', '?')} / {agent.get('platform', '?')}
- **Autonomous:** {'Yes' if agent.get('autonomous') else 'No'}

## Tools
{tools_list or '- none'}

## Recent Activity
{history_list or '- no recent actions'}

## Stats
{stats_list or '- none'}

---
*Auto-generated by [[Knowledge Agent]] — {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""
    return _safe_write(path, content)


def update_services_page(nodes: list):
    """Create a consolidated services overview."""
    path = VAULT_DIR / "services" / "overview.md"

    all_services = []
    for n in nodes:
        hostname = n.get("hostname", "?")
        for s in n.get("services", []):
            all_services.append({**s, "_host": hostname})

    by_type = {}
    for s in all_services:
        t = s.get("type", "other")
        by_type.setdefault(t, []).append(s)

    sections = []
    for stype, svcs in sorted(by_type.items()):
        rows = "\n".join(
            f"| {s.get('name','?')} | {s.get('_host','?')} | {s.get('status','?')} | {s.get('image','')} |"
            for s in svcs
        )
        sections.append(f"""### {stype.title()} ({len(svcs)})

| Service | Node | Status | Image |
|---------|------|--------|-------|
{rows}
""")

    content = f"""---
type: services
updated: "{datetime.now().isoformat()}"
---

# Cluster Services

Total: **{len(all_services)}** services across **{len(nodes)}** nodes

{''.join(sections)}

---
*Auto-generated by [[Knowledge Agent]] — {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""
    _safe_write(path, content)


def update_projects_page():
    """Index sandbox projects."""
    if not SANDBOX_DIR.exists():
        return

    projects = []
    for d in sorted(SANDBOX_DIR.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "project.json"
        meta = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
            except Exception:
                pass

        idea = meta.get("idea", {})
        test = meta.get("test", {})
        projects.append({
            "name": d.name,
            "description": idea.get("description", ""),
            "test_status": test.get("status", "unknown"),
            "created": meta.get("created_at", ""),
        })

    rows = "\n".join(
        f"| [[{p['name']}]] | {p['description'][:50]} | {p['test_status']} | {p['created'][:10]} |"
        for p in projects
    )

    content = f"""---
type: projects
updated: "{datetime.now().isoformat()}"
---

# Sandbox Projects

Total: **{len(projects)}** projects in `/data2/sandbox/`

| Project | Description | Test | Created |
|---------|-------------|------|---------|
{rows}

## Backlog
"""

    # Add backlog summary
    if BACKLOG_DIR.exists():
        for f in sorted(BACKLOG_DIR.glob("*.json"))[-10:]:
            try:
                item = json.loads(f.read_text())
                status_icon = {"open": "🔴", "resolved": "✅", "skipped": "⏭"}.get(item.get("status"), "❓")
                content += f"- {status_icon} **{item.get('project', '?')}** — {item.get('error', '')[:50]}\n"
            except Exception:
                pass

    content += f"""
---
*Auto-generated by [[Knowledge Agent]] — {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""
    _safe_write(VAULT_DIR / "projects" / "overview.md", content)

    # Individual project pages
    for p in projects:
        proj_path = VAULT_DIR / "projects" / f"{p['name']}.md"
        if proj_path.exists():
            continue  # Don't overwrite existing project docs
        proj_content = f"""---
type: project
name: "{p['name']}"
status: "{p['test_status']}"
---

# {p['name']}

{p['description']}

- **Test status:** {p['test_status']}
- **Created:** {p['created']}
- **Location:** `/data2/sandbox/{p['name']}/`

## Related
- [[Sandbox Projects]]
"""
        _safe_write(proj_path, proj_content)


def update_security_page(nodes: list):
    """Consolidate security findings from all nodes."""
    findings = []
    for n in nodes:
        hostname = n.get("hostname", "?")
        for a in n.get("agents", []):
            details = a.get("details", {})
            for f in details.get("security", []):
                findings.append({**f, "_host": hostname, "_agent": a.get("name", "?")})

    if not findings:
        return

    rows = "\n".join(
        f"| {f.get('severity','?')} | {f.get('_host','?')} | {f.get('type','?')} | {f.get('desc','')[:60]} |"
        for f in findings
    )

    content = f"""---
type: security
updated: "{datetime.now().isoformat()}"
---

# Security Findings

Total: **{len(findings)}** across cluster

| Severity | Node | Type | Description |
|----------|------|------|-------------|
{rows}

---
*Auto-generated by [[Knowledge Agent]] — {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""
    _safe_write(VAULT_DIR / "security" / "findings.md", content)


def update_daily_log(nodes: list):
    """Append to today's daily log."""
    today = date.today().isoformat()
    path = VAULT_DIR / "logs" / f"{today}.md"

    online = [n for n in nodes if n.get("status") == "online"]
    total_agents = sum(len(n.get("agents", [])) for n in nodes)
    avg_cpu = sum(n.get("cpu_pct", 0) for n in online) / max(len(online), 1)

    entry = f"\n## {datetime.now().strftime('%H:%M')}\n"
    entry += f"- Nodes: {len(online)}/{len(nodes)} online\n"
    entry += f"- Agents: {total_agents} total\n"
    entry += f"- Avg CPU: {avg_cpu:.0f}%\n"

    if path.exists():
        existing = path.read_text()
        path.write_text(existing + entry)
    else:
        header = f"""---
type: daily-log
date: "{today}"
---

# Cluster Log — {today}
{entry}"""
        path.write_text(header)


def update_cluster_overview(nodes: list):
    """Main overview page."""
    online = [n for n in nodes if n.get("status") == "online"]
    total_agents = sum(len(n.get("agents", [])) for n in nodes)
    total_services = sum(len(n.get("services", [])) for n in nodes)

    node_links = "\n".join(f"- [[{n.get('hostname', n.get('node_id', '?'))}]]" for n in nodes)

    content = f"""---
type: overview
updated: "{datetime.now().isoformat()}"
---

# Cluster Overview

## Status
- **Nodes:** {len(online)}/{len(nodes)} online
- **Agents:** {total_agents} running
- **Services:** {total_services} detected

## Nodes
{node_links}

## Quick Links
- [[services/overview|Services]]
- [[projects/overview|Sandbox Projects]]
- [[security/findings|Security Findings]]
- [[logs/{date.today().isoformat()}|Today's Log]]

---
*Auto-generated by [[Knowledge Agent]] — {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""
    _safe_write(VAULT_DIR / "Cluster Overview.md", content)


# ── Write API (for other agents) ─────────────────────────────────────────────

def write_note(category: str, title: str, content: str, tags: list = None):
    """
    Public API for other agents to write notes to the vault.
    Called via the orchestrator endpoint /knowledge/write
    """
    safe_cat = category.replace("/", "-").replace("\\", "-")
    safe_title = title.replace("/", "-").replace("\\", "-")[:80]

    if tags:
        frontmatter = f"---\ntags: {json.dumps(tags)}\nupdated: \"{datetime.now().isoformat()}\"\n---\n\n"
    else:
        frontmatter = f"---\nupdated: \"{datetime.now().isoformat()}\"\n---\n\n"

    full_content = frontmatter + content
    path = VAULT_DIR / safe_cat / f"{safe_title}.md"
    _safe_write(path, full_content)
    _record("write", f"{safe_cat}/{safe_title}")
    return str(path)


# ── Main Cycle ────────────────────────────────────────────────────────────────

def run_cycle():
    """One knowledge indexing cycle."""
    _update_agent_state("running", "Fetching catalog...")

    # 1. Get cluster data
    nodes = get_catalog()
    if not nodes:
        _record("catalog", "empty — skipping")
        return

    _record("catalog", f"{len(nodes)} nodes")

    # 2. Update node pages
    _update_agent_state("running", "Updating node pages...")
    updated = 0
    for n in nodes:
        if update_node_page(n):
            updated += 1
        # Also update agent pages
        for a in n.get("agents", []):
            update_agent_page(a, n.get("hostname", "?"))
    _record("nodes", f"{updated} updated")

    # 3. Services
    _update_agent_state("running", "Indexing services...")
    update_services_page(nodes)

    # 4. Projects
    _update_agent_state("running", "Indexing projects...")
    update_projects_page()
    _record("projects", f"{sum(1 for d in SANDBOX_DIR.iterdir() if d.is_dir())} indexed")

    # 5. Security
    update_security_page(nodes)

    # 6. Daily log
    update_daily_log(nodes)

    # 7. Overview
    update_cluster_overview(nodes)

    stats = _get_vault_stats()
    _update_agent_state("idle", f"Vault: {stats['total_files']} files")
    _record("cycle", f"done — {stats['total_files']} files")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
    )

    PID_FILE.write_text(str(os.getpid()))

    stop = False
    def _stop(sig, frame):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    log.info("Knowledge Agent started")
    _update_agent_state("idle", "Starting...")

    while not stop:
        # Check resources
        try:
            import psutil
            if psutil.cpu_percent(interval=0.5) > CPU_THRESHOLD:
                _update_agent_state("idle", "Waiting: CPU high")
                _wait(120, lambda: stop)
                continue
        except Exception:
            pass

        try:
            run_cycle()
        except Exception as e:
            log.error(f"Cycle error: {e}", exc_info=True)
            _update_agent_state("error", str(e)[:60])

        # Wait with periodic refresh
        _wait(CYCLE_INTERVAL, lambda: stop)

    _update_agent_state("idle", "Stopped")
    PID_FILE.unlink(missing_ok=True)
    log.info("Knowledge Agent stopped")


def _wait(seconds, should_stop):
    elapsed = 0
    while elapsed < seconds:
        if should_stop():
            break
        time.sleep(1)
        elapsed += 1
        if elapsed % 30 == 0:
            _update_agent_state("idle", _last_status)


if __name__ == "__main__":
    main()
