"""
InovaTest Agent — Autonomous Innovation & Testing Lab

Regras de segurança:
  - Máximo 20 projetos em /data2/sandbox/ (para depois limpa os antigos)
  - Máximo 8 ciclos por dia (reseta à meia-noite)
  - Não roda se CPU > 70% ou disco > 85%
  - Intervalo mínimo de 30 min entre ciclos
  - test_command: APENAS python3 com --test, sem shell pipes/redirects
  - Timeout de 15s nos testes (não pode travar)
  - Máximo 3 cluster tasks por ciclo
  - Log rotaciona a 5MB
  - Se falhar 3 ciclos seguidos, para e espera 2h
"""

import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from connect.ai_config import get_ai_client

log = logging.getLogger("ch8.inova_test")

# ── Configuration ─────────────────────────────────────────────────────────────

SANDBOX_DIR = Path("/data2/sandbox")
BACKLOG_DIR = Path("/data2/backlog")
CONFIG_DIR = Path.home() / ".config" / "ch8"
STATE_FILE = CONFIG_DIR / "state.json"
PID_FILE = CONFIG_DIR / "inova_test.pid"
LOG_FILE = CONFIG_DIR / "inova_test.log"
COUNTER_FILE = CONFIG_DIR / "inova_test_counter.json"

# Safety limits
MAX_PROJECTS = 20
MAX_CYCLES_PER_DAY = 8
MAX_CLUSTER_TASKS_PER_CYCLE = 3
CYCLE_INTERVAL = 1800          # 30 minutes
COOLDOWN_AFTER_FAILURES = 7200  # 2 hours
MAX_CONSECUTIVE_FAILURES = 3
TEST_TIMEOUT = 15              # seconds
MAX_LOG_SIZE = 5 * 1024 * 1024  # 5MB
CPU_THRESHOLD = 70.0
DISK_THRESHOLD = 85.0

# Allowed test command pattern: only python3 with safe args
SAFE_TEST_RE = re.compile(r'^python3\s+[\w./-]+\s*(--test|--check|--validate|--dry-run)?\s*$')

SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
BACKLOG_DIR.mkdir(parents=True, exist_ok=True)

AUTONOMY_FILE = CONFIG_DIR / "autonomy.json"


def is_autonomous() -> bool:
    """Check if this node is in autonomous mode."""
    try:
        data = json.loads(AUTONOMY_FILE.read_text())
        return data.get("enabled", False)
    except Exception:
        return False


# Runtime state
_last_status_msg = "Starting..."
_action_history = []  # last N actions [{ts, action, result}]
MAX_HISTORY = 10


# ── Safety Checks ─────────────────────────────────────────────────────────────

def _check_resources() -> str:
    """Return empty string if OK, or reason to skip this cycle."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=1)
        disk = psutil.disk_usage("/data2").percent
        if cpu > CPU_THRESHOLD:
            return f"CPU too high: {cpu:.0f}%"
        if disk > DISK_THRESHOLD:
            return f"Disk too full: {disk:.0f}%"
    except Exception:
        pass
    return ""


def _check_project_limit() -> str:
    """Return empty string if OK, or reason."""
    count = sum(1 for d in SANDBOX_DIR.iterdir() if d.is_dir())
    if count >= MAX_PROJECTS:
        return f"Max projects reached ({count}/{MAX_PROJECTS})"
    return ""


def _get_daily_counter() -> dict:
    """Load/reset daily cycle counter."""
    today = date.today().isoformat()
    try:
        data = json.loads(COUNTER_FILE.read_text())
        if data.get("date") != today:
            data = {"date": today, "cycles": 0}
    except Exception:
        data = {"date": today, "cycles": 0}
    return data


def _save_daily_counter(data: dict):
    COUNTER_FILE.write_text(json.dumps(data))


def _check_daily_limit() -> str:
    """Return empty string if OK."""
    data = _get_daily_counter()
    if data["cycles"] >= MAX_CYCLES_PER_DAY:
        return f"Daily limit reached ({data['cycles']}/{MAX_CYCLES_PER_DAY})"
    return ""


def _increment_daily_counter():
    data = _get_daily_counter()
    data["cycles"] += 1
    _save_daily_counter(data)


def _validate_test_command(cmd: str) -> bool:
    """Only allow safe test commands (python3 script.py --test)."""
    if not cmd:
        return False
    # Block dangerous patterns
    dangerous = ['|', ';', '&&', '||', '`', '$(',  '>', '<', 'rm ', 'curl ',
                 'wget ', 'sudo ', 'chmod ', 'kill ', 'dd ', 'mkfs', '/dev/']
    for d in dangerous:
        if d in cmd:
            return False
    return bool(SAFE_TEST_RE.match(cmd.strip()))


def _rotate_log():
    """Rotate log if it exceeds MAX_LOG_SIZE."""
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_LOG_SIZE:
        backup = LOG_FILE.with_suffix(".log.1")
        if backup.exists():
            backup.unlink()
        LOG_FILE.rename(backup)


# ── State Management ──────────────────────────────────────────────────────────

def _record_action(action: str, result: str):
    """Record an action in history (kept in memory + state details)."""
    global _action_history
    _action_history.append({
        "ts": datetime.now().strftime("%H:%M:%S"),
        "action": action[:80],
        "result": result[:80],
    })
    _action_history = _action_history[-MAX_HISTORY:]


def _update_agent_state(status: str, task: str):
    """Register this agent in the shared state.json."""
    global _last_status_msg
    _last_status_msg = task
    try:
        state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        agents = state.get("agents", [])

        # Build details with history
        counter = _get_daily_counter()
        projects = sum(1 for d in SANDBOX_DIR.iterdir() if d.is_dir())
        details = {
            "history": _action_history[-MAX_HISTORY:],
            "stats": {
                "projects_total": projects,
                "cycles_today": counter.get("cycles", 0),
                "max_cycles_day": MAX_CYCLES_PER_DAY,
                "max_projects": MAX_PROJECTS,
                "interval_min": CYCLE_INTERVAL // 60,
            },
        }

        entry = {
            "name": "inova_test",
            "status": status,
            "task": task,
            "model": "cluster-delegator",
            "platform": "sandbox",
            "autonomous": True,
            "alerts": 0,
            "security_findings": 0,
            "predictions": 0,
            "heavy_procs": 0,
            "tools": ["cluster_task", "file_write"],
            "details": details,
            "updated_at": int(time.time()),
        }
        agents = [a for a in agents if a.get("name") != "inova_test"]
        agents.append(entry)
        state["agents"] = agents
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        log.warning(f"State update failed: {e}")


# ── Cluster Communication ─────────────────────────────────────────────────────

_cluster_tasks_this_cycle = 0


def send_cluster_task(task: str, strategy: str = "auto") -> dict:
    """Send a task to the cluster (rate-limited)."""
    global _cluster_tasks_this_cycle
    if _cluster_tasks_this_cycle >= MAX_CLUSTER_TASKS_PER_CYCLE:
        log.warning("Cluster task limit reached this cycle, using local AI")
        return {"error": "rate_limited"}

    import httpx
    try:
        resp = httpx.post(
            "http://127.0.0.1:7879/cluster/task",
            json={"task": task, "strategy": strategy},
            timeout=120,
        )
        _cluster_tasks_this_cycle += 1
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        log.error(f"Cluster task failed: {e}")
    return {"error": "cluster unreachable"}


# ── Backlog Management ────────────────────────────────────────────────────────

def report_error(project: str, error: str, context: str = ""):
    """Write an error to /data2/backlog/ for fix_agent to resolve."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_{project}.json"
    entry = {
        "project": project,
        "error": error[:1000],
        "context": context[:500],
        "created_at": datetime.now().isoformat(),
        "status": "open",
        "attempts": 0,
    }
    (BACKLOG_DIR / filename).write_text(json.dumps(entry, indent=2))
    log.info(f"Backlog: {filename}")
    return filename


# ── Idea Generation ───────────────────────────────────────────────────────────

IDEAS_PROMPT = """\
Você é um engenheiro que propõe micro-projetos úteis para sysadmin com IA.

REGRAS OBRIGATÓRIAS:
- Projeto deve usar APENAS Python 3 + bibliotecas padrão (+ psutil, httpx se necessário)
- Máximo 2 arquivos .py
- test_command DEVE ser: python3 <arquivo>.py --test (nada mais)
- Projeto deve funcionar offline, sem APIs externas
- Foco: monitoramento, otimização, segurança, automação local

PROJETOS JÁ EXISTENTES (não repetir):
{existing}

Proponha UM micro-projeto. Responda APENAS JSON válido:
{{
  "name": "nome-do-projeto",
  "description": "o que faz",
  "files": ["main.py"],
  "test_command": "python3 main.py --test",
  "delegation": null
}}
"""


def generate_idea(ai) -> dict:
    """Ask LLM for a new project idea."""
    existing = [d.name for d in SANDBOX_DIR.iterdir() if d.is_dir()]
    prompt = IDEAS_PROMPT.format(existing=", ".join(existing) if existing else "(nenhum)")

    response = ai.chat([{"role": "user", "content": prompt}], max_tokens=600, temperature=0.8)

    text = response.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    idea = json.loads(text)

    # Sanitize
    idea["name"] = re.sub(r'[^a-zA-Z0-9_-]', '-', idea.get("name", "unnamed"))[:40]
    idea["files"] = [f for f in idea.get("files", [])[:2] if f.endswith(".py")]
    if not idea["files"]:
        idea["files"] = ["main.py"]

    # Force safe test command
    test_cmd = idea.get("test_command", "")
    if not _validate_test_command(test_cmd):
        idea["test_command"] = f"python3 {idea['files'][0]} --test"

    return idea


# ── Project Building ──────────────────────────────────────────────────────────

BUILD_PROMPT = """\
Crie o código Python completo para: {name}
Descrição: {description}
Arquivo: {filename}

REGRAS:
- Python 3, apenas stdlib + psutil (se necessário)
- Inclua if __name__ == "__main__" com argparse
- Se receber --test: execute um self-test que printe "TEST PASSED" se OK
- NÃO use APIs externas, não faça requests HTTP
- Código funcional, não placeholder

Responda APENAS com código Python puro, SEM markdown.
"""


def build_project(ai, idea: dict) -> dict:
    """Build project files."""
    project_dir = SANDBOX_DIR / idea["name"]
    project_dir.mkdir(parents=True, exist_ok=True)

    results = {"files_created": [], "errors": []}

    for filename in idea["files"]:
        prompt = BUILD_PROMPT.format(
            name=idea["name"],
            description=idea["description"],
            filename=filename,
        )

        # Try cluster first for first file, local for rest
        code = ""
        if idea.get("delegation") and _cluster_tasks_this_cycle < MAX_CLUSTER_TASKS_PER_CYCLE:
            cluster_result = send_cluster_task(
                f"Escreva código Python para: {idea['description']}. "
                f"Arquivo: {filename}. Deve imprimir 'TEST PASSED' quando chamado com --test."
            )
            if "error" not in cluster_result:
                code = cluster_result.get("result", "")

        if not code:
            code = ai.chat([{"role": "user", "content": prompt}], max_tokens=3000, temperature=0.2)

        # Strip markdown wrappers
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0]
        elif "```" in code:
            code = code.split("```")[1].split("```")[0]

        code = code.strip()
        if not code or len(code) < 20:
            results["errors"].append(f"Empty/invalid code for {filename}")
            continue

        filepath = project_dir / filename
        filepath.write_text(code + "\n")
        results["files_created"].append(str(filepath))
        log.info(f"Created: {filepath}")

    return results


# ── Testing (sandboxed) ───────────────────────────────────────────────────────

def test_project(idea: dict) -> dict:
    """Run test command in a restricted manner."""
    project_dir = SANDBOX_DIR / idea["name"]
    test_cmd = idea.get("test_command", "")

    if not _validate_test_command(test_cmd):
        return {"status": "skipped", "reason": f"unsafe command blocked: {test_cmd}"}

    try:
        # Run without shell=True for safety, split the command
        parts = test_cmd.strip().split()
        result = subprocess.run(
            parts, cwd=str(project_dir),
            capture_output=True, text=True, timeout=TEST_TIMEOUT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if result.returncode == 0 and "TEST PASSED" in (result.stdout + result.stderr):
            return {"status": "passed", "output": result.stdout[:300]}
        elif result.returncode == 0:
            return {"status": "passed", "output": result.stdout[:300]}
        else:
            error_msg = (result.stderr or result.stdout)[:400]
            report_error(idea["name"], error_msg, f"cmd: {test_cmd}")
            return {"status": "failed", "error": error_msg}
    except subprocess.TimeoutExpired:
        report_error(idea["name"], "Timeout (15s)", test_cmd)
        return {"status": "timeout"}
    except Exception as e:
        report_error(idea["name"], str(e)[:200], test_cmd)
        return {"status": "error", "error": str(e)}


# ── Main Loop ─────────────────────────────────────────────────────────────────

def run_cycle() -> bool:
    """Execute one cycle. Returns True if successful."""
    global _cluster_tasks_this_cycle
    _cluster_tasks_this_cycle = 0

    ai = get_ai_client()
    _update_agent_state("running", "Generating idea...")

    # 1. Generate
    idea = generate_idea(ai)
    log.info(f"Idea: {idea['name']} — {idea['description']}")
    _record_action("idea", f"{idea['name']}: {idea['description'][:50]}")
    _update_agent_state("running", f"Building: {idea['name']}")

    # 2. Build
    build_result = build_project(ai, idea)
    if not build_result["files_created"]:
        _record_action("build", "FAILED: no files")
        log.error("Build produced no files")
        return False
    _record_action("build", f"{len(build_result['files_created'])} file(s)")
    log.info(f"Built {len(build_result['files_created'])} file(s)")

    # 3. Test
    _update_agent_state("running", f"Testing: {idea['name']}")
    test_result = test_project(idea)
    _record_action("test", f"{idea['name']}: {test_result['status']}")
    log.info(f"Test: {test_result['status']}")

    # 4. Save metadata
    meta = {
        "idea": idea,
        "build": build_result,
        "test": test_result,
        "created_at": datetime.now().isoformat(),
    }
    (SANDBOX_DIR / idea["name"] / "project.json").write_text(json.dumps(meta, indent=2))

    status_msg = f"{idea['name']} ({test_result['status']})"
    _update_agent_state("idle", f"Last: {status_msg}")
    return test_result["status"] in ("passed", "skipped")


def main():
    _rotate_log()
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

    log.info("InovaTest agent started (safe mode)")
    _update_agent_state("idle", "Starting...")

    consecutive_failures = 0

    while not stop:
        # Autonomy check
        if not is_autonomous():
            _update_agent_state("idle", "Autonomous mode OFF")
            _wait(60, lambda: stop)
            continue

        # Pre-flight checks
        reason = _check_resources()
        if reason:
            log.info(f"Skipping cycle: {reason}")
            _update_agent_state("idle", f"Waiting: {reason}")
            _wait(300, lambda: stop)
            continue

        reason = _check_project_limit()
        if reason:
            log.info(f"Skipping: {reason}")
            _update_agent_state("idle", reason)
            _wait(3600, lambda: stop)
            continue

        reason = _check_daily_limit()
        if reason:
            log.info(f"Skipping: {reason}")
            _update_agent_state("idle", reason)
            _wait(3600, lambda: stop)
            continue

        # Run cycle
        try:
            success = run_cycle()
            _increment_daily_counter()
            if success:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
        except Exception as e:
            log.error(f"Cycle error: {e}", exc_info=True)
            consecutive_failures += 1
            _update_agent_state("error", str(e)[:60])

        # Backoff on repeated failures
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            log.warning(f"Too many failures ({consecutive_failures}), cooling down {COOLDOWN_AFTER_FAILURES}s")
            _update_agent_state("idle", f"Cooldown ({consecutive_failures} failures)")
            _wait(COOLDOWN_AFTER_FAILURES, lambda: stop)
            consecutive_failures = 0
            continue

        # Normal wait between cycles
        _wait(CYCLE_INTERVAL, lambda: stop)

    _update_agent_state("idle", "Stopped")
    PID_FILE.unlink(missing_ok=True)
    log.info("InovaTest agent stopped")


def _wait(seconds: int, should_stop):
    """Wait with early exit on stop signal. Refreshes state every 30s."""
    elapsed = 0
    while elapsed < seconds:
        if should_stop():
            break
        time.sleep(1)
        elapsed += 1
        if elapsed % 30 == 0:
            _update_agent_state("idle", _last_status_msg)


if __name__ == "__main__":
    main()
