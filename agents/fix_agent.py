"""
Fix Agent — Autonomous Bug Fixer

Responsabilidades:
  - Monitorar /data2/backlog/ para novos erros
  - Pegar um erro por vez (FIFO)
  - Analisar o código com defeito
  - Propor e aplicar fix
  - Re-testar
  - Se passou → marcar como resolved
  - Se falhou → incrementar attempts, pedir ajuda ao cluster

Ciclo:
  1. Scan /data2/backlog/ por items com status=open
  2. Pegar o mais antigo
  3. Ler o projeto em /data2/sandbox/<name>/
  4. Pedir ao LLM para diagnosticar e corrigir
  5. Aplicar fix
  6. Re-testar
  7. Atualizar backlog item
"""

import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from connect.ai_config import get_ai_client

log = logging.getLogger("ch8.fix_agent")

SANDBOX_DIR = Path("/data2/sandbox")
BACKLOG_DIR = Path("/data2/backlog")
STATE_FILE = Path.home() / ".config" / "ch8" / "state.json"
PID_FILE = Path.home() / ".config" / "ch8" / "fix_agent.pid"
LOG_FILE = Path.home() / ".config" / "ch8" / "fix_agent.log"
CHECK_INTERVAL = 60  # check backlog every 60 seconds
MAX_ATTEMPTS = 3


# ── State Management ──────────────────────────────────────────────────────────

def _update_agent_state(status: str, task: str):
    """Register this agent in state.json."""
    try:
        state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        agents = state.get("agents", [])
        entry = {
            "name": "fix_agent",
            "status": status,
            "task": task,
            "model": "auto-debugger",
            "platform": "sandbox",
            "autonomous": True,
            "alerts": 0,
            "security_findings": 0,
            "predictions": 0,
            "heavy_procs": 0,
            "tools": ["file_read", "file_write", "shell_exec"],
            "details": {},
            "updated_at": int(time.time()),
        }
        agents = [a for a in agents if a.get("name") != "fix_agent"]
        agents.append(entry)
        state["agents"] = agents
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        log.warning(f"State update failed: {e}")


# ── Cluster Communication ─────────────────────────────────────────────────────

def ask_cluster(question: str) -> str:
    """Ask the cluster for help with a debugging problem."""
    import httpx
    try:
        resp = httpx.post(
            "http://127.0.0.1:7879/cluster/task",
            json={"task": question, "strategy": "auto"},
            timeout=180,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("result", "No result")
    except Exception as e:
        log.error(f"Cluster ask failed: {e}")
    return ""


# ── Backlog Scanner ───────────────────────────────────────────────────────────

def get_next_issue() -> tuple:
    """Get the oldest open backlog issue. Returns (path, data) or (None, None)."""
    issues = []
    for f in sorted(BACKLOG_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            if data.get("status") == "open" and data.get("attempts", 0) < MAX_ATTEMPTS:
                issues.append((f, data))
        except Exception:
            continue

    if not issues:
        return None, None

    # Return oldest
    return issues[0]


# ── Fix Logic ─────────────────────────────────────────────────────────────────

FIX_PROMPT = """\
Você é um debugger especialista. Analise o erro abaixo e corrija o código.

PROJETO: {project}
ERRO: {error}
CONTEXTO: {context}

CÓDIGO ATUAL:
```
{code}
```

Responda APENAS com o código corrigido completo (sem markdown, sem explicação).
Se o erro é de dependência ausente ou permissão, diga "SKIP: <motivo>" no início.
"""


def attempt_fix(issue_path: Path, issue_data: dict) -> bool:
    """Try to fix a backlog issue. Returns True if fixed."""
    project_name = issue_data["project"]
    project_dir = SANDBOX_DIR / project_name
    error = issue_data["error"]
    context = issue_data.get("context", "")

    if not project_dir.exists():
        log.warning(f"Project dir not found: {project_dir}")
        issue_data["status"] = "abandoned"
        issue_data["resolved_at"] = datetime.now().isoformat()
        issue_path.write_text(json.dumps(issue_data, indent=2))
        return False

    # Read project files
    code_files = {}
    for f in project_dir.glob("*.py"):
        try:
            code_files[f.name] = f.read_text()
        except Exception:
            pass

    if not code_files:
        issue_data["status"] = "abandoned"
        issue_data["note"] = "no python files found"
        issue_path.write_text(json.dumps(issue_data, indent=2))
        return False

    # Build code context
    code_str = "\n\n".join(f"# --- {name} ---\n{content}" for name, content in code_files.items())

    ai = get_ai_client()

    # Attempt 1: local AI
    prompt = FIX_PROMPT.format(
        project=project_name, error=error, context=context,
        code=code_str[:6000]
    )

    response = ai.chat([{"role": "user", "content": prompt}], max_tokens=4000, temperature=0.1)

    if response.strip().startswith("SKIP:"):
        log.info(f"Skipping: {response.strip()}")
        issue_data["status"] = "skipped"
        issue_data["skip_reason"] = response.strip()
        issue_path.write_text(json.dumps(issue_data, indent=2))
        return False

    # If local AI couldn't help after 2 attempts, ask cluster
    if issue_data.get("attempts", 0) >= 1:
        cluster_response = ask_cluster(
            f"Debug this Python project '{project_name}'. "
            f"Error: {error}\n\nCode:\n{code_str[:3000]}\n\n"
            f"Return ONLY the fixed code."
        )
        if cluster_response and not cluster_response.startswith("SKIP"):
            response = cluster_response

    # Parse fixed code
    fixed_code = response.strip()
    if "```python" in fixed_code:
        fixed_code = fixed_code.split("```python")[1].split("```")[0]
    elif "```" in fixed_code:
        fixed_code = fixed_code.split("```")[1].split("```")[0]

    # Apply fix to the first file (most common case)
    main_file = list(code_files.keys())[0]
    (project_dir / main_file).write_text(fixed_code.strip() + "\n")
    log.info(f"Applied fix to {project_dir / main_file}")

    # Re-test
    meta_path = project_dir / "project.json"
    test_cmd = ""
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            test_cmd = meta.get("idea", {}).get("test_command", "")
        except Exception:
            pass

    if test_cmd:
        try:
            r = subprocess.run(
                test_cmd, shell=True, cwd=str(project_dir),
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode == 0:
                issue_data["status"] = "resolved"
                issue_data["resolved_at"] = datetime.now().isoformat()
                issue_data["fix_applied"] = main_file
                issue_path.write_text(json.dumps(issue_data, indent=2))
                log.info(f"FIXED: {project_name}")
                return True
            else:
                issue_data["attempts"] = issue_data.get("attempts", 0) + 1
                issue_data["last_error"] = (r.stderr or r.stdout)[:300]
                issue_path.write_text(json.dumps(issue_data, indent=2))
                log.warning(f"Fix didn't work for {project_name} (attempt {issue_data['attempts']})")
                return False
        except Exception as e:
            issue_data["attempts"] = issue_data.get("attempts", 0) + 1
            issue_data["last_error"] = str(e)
            issue_path.write_text(json.dumps(issue_data, indent=2))
            return False
    else:
        # No test command — assume fixed
        issue_data["status"] = "resolved"
        issue_data["resolved_at"] = datetime.now().isoformat()
        issue_data["note"] = "no test_command to verify"
        issue_path.write_text(json.dumps(issue_data, indent=2))
        return True


# ── Main Loop ─────────────────────────────────────────────────────────────────

def run_check():
    """Check backlog and fix one issue."""
    issue_path, issue_data = get_next_issue()

    if issue_path is None:
        _update_agent_state("idle", "Backlog empty — waiting")
        return

    project = issue_data["project"]
    _update_agent_state("running", f"Fixing: {project}")
    log.info(f"Working on: {project} — {issue_data['error'][:60]}")

    attempt_fix(issue_path, issue_data)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(),
        ],
    )

    PID_FILE.write_text(str(os.getpid()))

    stop = False

    def _stop(sig, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    log.info("Fix Agent started")
    _update_agent_state("idle", "Starting up...")

    while not stop:
        try:
            run_check()
        except Exception as e:
            log.error(f"Check error: {e}", exc_info=True)
            _update_agent_state("error", str(e)[:80])

        for _ in range(CHECK_INTERVAL):
            if stop:
                break
            time.sleep(1)

    _update_agent_state("idle", "Stopped")
    PID_FILE.unlink(missing_ok=True)
    log.info("Fix Agent stopped")


if __name__ == "__main__":
    main()
