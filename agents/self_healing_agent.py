"""
CH8 Self-Healing Agent — Detecção e resolução autônoma de problemas
Protocolo: Detectar → Diagnosticar → Tentar Fix → Verificar → Escalar se necessário
Ciclo: 2 minutos
"""
import asyncio
import logging
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Setup
sys.path.insert(0, str(Path(__file__).parent.parent))
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
log = logging.getLogger("ch8.self_healing")

CONFIG_DIR = Path(os.environ.get("CH8_CONFIG_DIR", Path.home() / ".config" / "ch8"))
PID_FILE = CONFIG_DIR / "self_healing_agent.pid"
CYCLE_SECS = 120  # 2 minutes
MAX_FIX_ATTEMPTS = 3  # per error type per hour

running = True

def _update_state(status: str, task: str):
    try:
        from connect.state import update_agent_state
        update_agent_state("self_healing", status, task)
    except Exception:
        pass

def _get_db():
    try:
        import psycopg2
        db_url = os.environ.get("CH8_DB_URL", "postgresql://ch8app:ch8cluster2024@127.0.0.1:5432/ch8_cluster")
        return psycopg2.connect(db_url)
    except Exception:
        return None

def _create_ticket(title, description, severity, category, action_plan, node="manager1"):
    try:
        from connect.db import create_ticket
        return create_ticket(
            title=title[:190], description=description,
            severity=severity, category=category,
            node=node, service="self-healing",
            root_cause="Auto-detectado pelo self_healing_agent",
            impact="Sistema afetado — requer ação",
            action_plan=action_plan, fix_command="",
            source_type="self_healing",
            source_ref=f"heal-{int(time.time())}"
        )
    except Exception as e:
        log.warning(f"Failed to create ticket: {e}")
        return None

def _run(cmd: str, timeout: int = 30) -> tuple[str, str, int]:
    """Run shell command, return (stdout, stderr, returncode)."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", f"Command timed out after {timeout}s", 1
    except Exception as e:
        return "", str(e), 1

# ── CHECKS ────────────────────────────────────────────────────────────────────

class Check:
    name: str
    last_attempt: dict = {}  # error_key → last attempt timestamp
    
    @classmethod
    def can_attempt(cls, key: str, cooldown: int = 3600) -> bool:
        """Rate limit: max 1 attempt per error per cooldown period."""
        last = cls.last_attempt.get(key, 0)
        return time.time() - last > cooldown
    
    @classmethod
    def mark_attempt(cls, key: str):
        cls.last_attempt[key] = time.time()


def check_disk_space() -> list[dict]:
    """Check for critical disk usage and clean if needed."""
    issues = []
    stdout, _, rc = _run("df -h --output=pcent,target 2>/dev/null | tail -n +2")
    if rc != 0:
        return issues
    
    for line in stdout.splitlines():
        parts = line.strip().split()
        if len(parts) < 2: continue
        try:
            pct = int(parts[0].replace('%', ''))
            mount = parts[1]
            if pct >= 95:
                issues.append({"type": "disk_critical", "mount": mount, "pct": pct})
            elif pct >= 88 and mount == '/':
                issues.append({"type": "disk_warning", "mount": mount, "pct": pct})
        except: pass
    return issues


def check_failed_services() -> list[dict]:
    """Check for failed systemd services."""
    issues = []
    stdout, _, rc = _run("systemctl list-units --state=failed --no-legend --plain 2>/dev/null")
    if rc == 0 and stdout:
        for line in stdout.splitlines()[:5]:
            line = line.strip()
            if not line or line.startswith('●') or line.startswith('UNIT'): continue
            parts = line.split()
            name = parts[0] if parts else ''
            # Only flag .service/.socket/.timer — ignore snap/mount/hassio/tmp units
            SKIP_PREFIXES = ('snap-', 'tmp-', 'sys-', 'dev-', 'run-', 'home-', 'boot-', 'hassio')
            if (name and '.' in name
                    and any(name.endswith(s) for s in ('.service', '.socket', '.timer'))
                    and not any(name.startswith(p) for p in SKIP_PREFIXES)
                    and 'hassio' not in name):
                issues.append({"type": "service_failed", "service": name})
    return issues


def check_docker_containers() -> list[dict]:
    """Check for unhealthy or restarting containers."""
    issues = []
    stdout, _, rc = _run('docker ps --format "{{.Names}}\t{{.Status}}" 2>/dev/null')
    if rc != 0: return issues
    
    for line in stdout.splitlines():
        parts = line.strip().split('\t')
        if len(parts) < 2: continue
        name, status = parts[0], parts[1].lower()
        if 'unhealthy' in status:
            issues.append({"type": "container_unhealthy", "name": name, "status": status})
        elif 'restarting' in status:
            issues.append({"type": "container_restarting", "name": name, "status": status})
    return issues


def check_high_memory() -> list[dict]:
    """Check for memory pressure."""
    issues = []
    stdout, _, rc = _run("free -m 2>/dev/null | awk 'NR==2{printf \"%d %d\", $2, $3}'")
    if rc == 0 and stdout:
        try:
            parts = stdout.split()
            total, used = int(parts[0]), int(parts[1])
            pct = used / total * 100
            if pct > 92:
                issues.append({"type": "memory_critical", "pct": round(pct, 1), "used_mb": used, "total_mb": total})
        except: pass
    return issues


def check_orchestrator() -> list[dict]:
    """Check if orchestrator is responsive."""
    issues = []
    try:
        import httpx
        auth_file = CONFIG_DIR / "auth.json"
        headers = {}
        if auth_file.exists():
            import json
            token = json.loads(auth_file.read_text()).get("access_token", "")
            if token: headers["Authorization"] = f"Bearer {token}"
        
        r = httpx.get("http://127.0.0.1:7879/health", headers=headers, timeout=5)
        if r.status_code != 200:
            issues.append({"type": "orchestrator_unhealthy", "status": r.status_code})
    except Exception as e:
        issues.append({"type": "orchestrator_unreachable", "error": str(e)[:100]})
    return issues


def check_postgres() -> list[dict]:
    """Check PostgreSQL health."""
    issues = []
    stdout, stderr, rc = _run("psql postgresql://ch8app:ch8cluster2024@127.0.0.1:5432/ch8_cluster -c 'SELECT 1' -t 2>&1")
    if rc != 0 or '1' not in stdout:
        issues.append({"type": "postgres_unreachable", "error": stderr[:100]})
    return issues


# ── FIXES ─────────────────────────────────────────────────────────────────────

def fix_disk_space(issue: dict) -> bool:
    """Try to free disk space."""
    log.info(f"Attempting disk cleanup (mount={issue.get('mount')}, {issue.get('pct')}%)")
    fixes = [
        "docker system prune -f 2>/dev/null",
        "find /tmp -type f -mtime +7 -delete 2>/dev/null",
        "journalctl --vacuum-time=3d 2>/dev/null",
        "find /var/log -name '*.log' -mtime +30 -exec truncate -s 0 {} \; 2>/dev/null",
    ]
    freed = False
    for cmd in fixes:
        stdout, _, rc = _run(cmd, timeout=60)
        if rc == 0:
            freed = True
            log.info(f"  Ran: {cmd[:50]}")
    return freed


def fix_service(issue: dict) -> bool:
    """Try to restart a failed service."""
    svc = issue.get('service', '')
    if not svc: return False
    log.info(f"Attempting to restart failed service: {svc}")
    # Safety check: don't restart critical services without permission
    skip = ['postgresql', 'mysql', 'mongod', 'redis']
    if any(s in svc.lower() for s in skip):
        log.warning(f"  Skipping {svc} — critical service, manual action required")
        return False
    _, _, rc = _run(f"systemctl restart {svc} 2>/dev/null", timeout=30)
    time.sleep(5)
    stdout, _, _ = _run(f"systemctl is-active {svc} 2>/dev/null")
    return stdout.strip() == 'active'


def fix_container(issue: dict) -> bool:
    """Try to restart an unhealthy container."""
    name = issue.get('name', '')
    if not name: return False
    log.info(f"Attempting to restart container: {name}")
    _, _, rc = _run(f"docker restart {name} 2>/dev/null", timeout=60)
    time.sleep(10)
    stdout, _, _ = _run(f'docker inspect {name} --format "{{{{.State.Health.Status}}}}" 2>/dev/null')
    return rc == 0


def fix_memory(issue: dict) -> bool:
    """Free memory by restarting low-priority agents."""
    log.info("Attempting memory cleanup")
    # Drop page cache (safe)
    _run("sync && echo 3 > /proc/sys/vm/drop_caches 2>/dev/null", timeout=10)
    # Kill zombie processes
    _run("kill $(ps aux | awk '$8 ~ /Z/ {print $2}') 2>/dev/null", timeout=5)
    return True


def restart_orchestrator() -> bool:
    """Restart the orchestrator agent."""
    log.info("Attempting to restart orchestrator")
    import psutil
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            if 'orchestrator.py' in ' '.join(proc.info.get('cmdline', [])):
                proc.kill()
                time.sleep(3)
                break
        except: pass
    
    pid_file = CONFIG_DIR / "orchestrator.pid"
    if pid_file.exists(): pid_file.unlink()
    
    stdout, _, rc = _run(
        f"nohup python3 /data/ch8-agent/agents/orchestrator.py >> {CONFIG_DIR}/orchestrator.log 2>&1 &",
        timeout=5
    )
    time.sleep(8)
    return check_orchestrator() == []


# ── MAIN CYCLE ────────────────────────────────────────────────────────────────

def run_cycle():
    """Run one healing cycle."""
    issues_found = 0
    issues_fixed = 0
    tickets_created = 0
    
    checks_and_fixes = [
        (check_disk_space, {
            'disk_critical': (fix_disk_space, 'critical', 'disk_full', 'docker system prune -f && journalctl --vacuum-time=3d'),
            'disk_warning': (fix_disk_space, 'high', 'disk_full', 'docker system prune -f'),
        }),
        (check_docker_containers, {
            'container_unhealthy': (fix_container, 'high', 'service_down', 'docker restart {name}'),
            'container_restarting': (fix_container, 'medium', 'service_down', 'docker restart {name}'),
        }),
        (check_failed_services, {
            'service_failed': (fix_service, 'high', 'service_down', 'systemctl restart {service}'),
        }),
        (check_high_memory, {
            'memory_critical': (fix_memory, 'high', 'performance', 'Free page cache + restart idle processes'),
        }),
        (check_orchestrator, {
            'orchestrator_unhealthy': (restart_orchestrator, 'critical', 'service_down', 'Restart orchestrator agent'),
            'orchestrator_unreachable': (restart_orchestrator, 'critical', 'service_down', 'Restart orchestrator agent'),
        }),
    ]
    
    for check_fn, fix_map in checks_and_fixes:
        try:
            issues = check_fn()
            for issue in issues:
                issues_found += 1
                issue_type = issue.get('type', 'unknown')
                error_key = f"{issue_type}_{issue.get('mount', issue.get('name', issue.get('service', '')))}"
                
                if issue_type not in fix_map:
                    continue
                
                fix_fn, severity, category, action = fix_map[issue_type]
                log.warning(f"Issue detected: {issue_type} — {issue}")
                
                # Try fix if not rate-limited
                if Check.can_attempt(error_key):
                    Check.mark_attempt(error_key)
                    action_filled = action.format(**issue)
                    
                    try:
                        fixed = fix_fn(issue)
                        if fixed:
                            issues_fixed += 1
                            log.info(f"  ✅ Fixed: {issue_type}")
                            _update_state("running", f"Fixed {issue_type} — {str(issue)[:50]}")
                        else:
                            log.warning(f"  ❌ Fix failed for {issue_type}")
                            # Create ticket for manual resolution
                            detail = ", ".join(f"{k}={v}" for k, v in issue.items() if k != 'type')
                            tid = _create_ticket(
                                title=f"[AutoFix Falhou] {issue_type.replace('_', ' ').title()} — {detail}"[:190],
                                description=f"Self-healing agent detectou e tentou resolver automaticamente:\n\nTipo: {issue_type}\nDetalhes: {issue}\n\nFix tentado: {action_filled}\nResultado: FALHOU — intervenção manual necessária.",
                                severity=severity, category=category,
                                action_plan=f"1. Investigar causa: {issue_type}\n2. Executar: {action_filled}\n3. Verificar se resolveu\n4. Documentar na KB",
                                node=os.uname().nodename
                            )
                            if tid: tickets_created += 1; log.info(f"  🎫 Ticket: {tid}")
                    except Exception as e:
                        log.error(f"  Fix exception for {issue_type}: {e}")
                else:
                    log.info(f"  Rate-limited for {error_key}, skipping")
        except Exception as e:
            log.error(f"Check {check_fn.__name__} failed: {e}")
    
    return issues_found, issues_fixed, tickets_created


# ── ENTRY ─────────────────────────────────────────────────────────────────────

def main():
    global running
    
    # PID file
    if PID_FILE.exists():
        old_pid = int(PID_FILE.read_text().strip())
        try:
            os.kill(old_pid, 0)
            log.info(f"Already running (PID {old_pid}), exiting")
            sys.exit(0)
        except ProcessLookupError:
            pass
    PID_FILE.write_text(str(os.getpid()))
    
    def _stop(sig, frame):
        global running
        running = False
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    
    log.info(f"Self-Healing Agent starting — cycle={CYCLE_SECS}s")
    _update_state("running", "Self-healing agent ativo — monitorando erros")
    
    while running:
        try:
            _update_state("running", f"Executando ciclo de verificação — {datetime.now().strftime('%H:%M:%S')}")
            t0 = time.time()
            found, fixed, tickets = run_cycle()
            elapsed = time.time() - t0
            
            task = f"Último ciclo: {found} problemas, {fixed} corrigidos, {tickets} tickets — {elapsed:.1f}s"
            if found == 0:
                task = f"✅ Sistema saudável — último check {datetime.now().strftime('%H:%M:%S')}"
            _update_state("running", task)
            log.info(f"Cycle done: {found} issues, {fixed} fixed, {tickets} tickets in {elapsed:.1f}s")
            
        except Exception as e:
            log.error(f"Cycle error: {e}")
            _update_state("warning", f"Erro no ciclo: {str(e)[:80]}")
        
        # Sleep in small increments for responsive shutdown
        for _ in range(CYCLE_SECS):
            if not running: break
            time.sleep(1)
    
    _update_state("idle", "Stopped")
    PID_FILE.unlink(missing_ok=True)
    log.info("Self-Healing Agent stopped")


if __name__ == "__main__":
    main()
