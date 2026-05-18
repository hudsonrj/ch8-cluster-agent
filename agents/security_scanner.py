"""
Security Scanner Agent — Executa scans de segurança periódicos usando projetos do Innovation Lab.

Integra os top-scoring projects:
1. Port Security Scanner — detecta portas suspeitas
2. File Integrity Monitor — detecta alterações não autorizadas
3. TCP Connection Analyzer — detecta conexões anômalas
4. User Session Analyzer — detecta logins suspeitos

Ciclo: a cada 10 minutos
Resultados: log + ITSM tickets para anomalias críticas
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

log = logging.getLogger("ch8.security_scanner")

CONFIG_DIR = Path.home() / ".config" / "ch8"
PID_FILE = CONFIG_DIR / "security_scanner.pid"
LOG_FILE = CONFIG_DIR / "security_scanner.log"
STATE_FILE = CONFIG_DIR / "security_scanner_state.json"
SANDBOX = Path("/data2/sandbox")
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

CHECK_INTERVAL = 600  # 10 minutes
running = True


def signal_handler(sig, frame):
    global running
    running = False


def _run_scanner(project_name, main_file, args="--test"):
    """Run a sandbox project scanner and capture results."""
    project_dir = SANDBOX / project_name
    script = project_dir / main_file
    if not script.exists():
        return {"ok": False, "error": f"Script not found: {script}"}
    try:
        result = subprocess.run(
            ["python3", str(script), args] if args else ["python3", str(script)],
            capture_output=True, text=True, timeout=30,
            cwd=str(project_dir)
        )
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:500],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _check_open_ports():
    """Run port security scanner."""
    result = _run_scanner("smart-port-security-scanner", "port_scanner.py", "--scan")
    if not result["ok"]:
        # Fallback: use ss directly
        try:
            out = subprocess.run(
                ["ss", "-tlnp"], capture_output=True, text=True, timeout=10
            ).stdout
            lines = out.strip().split("\n")[1:]  # skip header
            ports = []
            for line in lines:
                parts = line.split()
                if len(parts) >= 4:
                    addr = parts[3]
                    port = addr.rsplit(":", 1)[-1] if ":" in addr else "?"
                    ports.append(port)
            return {"ok": True, "open_ports": len(ports), "ports": ports[:20]}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return result


def _check_connections():
    """Analyze TCP connections for anomalies."""
    try:
        out = subprocess.run(
            ["ss", "-tn", "state", "established"],
            capture_output=True, text=True, timeout=10
        ).stdout
        lines = out.strip().split("\n")[1:]
        external = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 5:
                peer = parts[4]
                if not any(peer.startswith(p) for p in ["127.", "100.", "10.", "192.168."]):
                    external.append(peer)
        return {
            "ok": True,
            "total_connections": len(lines),
            "external_connections": len(external),
            "top_external": external[:10],
            "suspicious": len(external) > 50,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _check_sessions():
    """Check active user sessions for anomalies."""
    try:
        out = subprocess.run(
            ["who"], capture_output=True, text=True, timeout=5
        ).stdout
        sessions = out.strip().split("\n") if out.strip() else []
        # Check for unusual hours (outside 6-22)
        hour = datetime.now().hour
        unusual_time = hour < 6 or hour > 22
        # Check failed logins
        try:
            fail_out = subprocess.run(
                ["lastb", "-n", "10"],
                capture_output=True, text=True, timeout=5
            ).stdout
            failed_logins = len(fail_out.strip().split("\n")) if fail_out.strip() else 0
        except Exception:
            failed_logins = 0
        return {
            "ok": True,
            "active_sessions": len(sessions),
            "unusual_time": unusual_time,
            "recent_failed_logins": failed_logins,
            "suspicious": failed_logins > 5,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _check_file_integrity():
    """Quick file integrity check on critical paths."""
    critical_files = [
        "/etc/passwd", "/etc/shadow", "/etc/sudoers",
        "/etc/ssh/sshd_config", "/etc/nginx/nginx.conf",
    ]
    changes = []
    state_file = CONFIG_DIR / "file_hashes.json"
    try:
        old_hashes = json.loads(state_file.read_text()) if state_file.exists() else {}
    except Exception:
        old_hashes = {}

    import hashlib
    new_hashes = {}
    for fp in critical_files:
        try:
            h = hashlib.sha256(Path(fp).read_bytes()).hexdigest()[:16]
            new_hashes[fp] = h
            if fp in old_hashes and old_hashes[fp] != h:
                changes.append(fp)
        except Exception:
            pass

    state_file.write_text(json.dumps(new_hashes))
    return {
        "ok": True,
        "files_checked": len(new_hashes),
        "changes_detected": changes,
        "suspicious": len(changes) > 0,
    }


def _check_containers():
    """Check all Docker containers for unhealthy/crashed/restarting status."""
    try:
        out = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}|{{.Status}}|{{.Image}}"],
            capture_output=True, text=True, timeout=15
        ).stdout
        problems = []
        for line in out.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|")
            if len(parts) >= 2:
                name, status = parts[0], parts[1]
                image = parts[2] if len(parts) > 2 else ""
                # Detect problems
                is_bad = False
                if "Restarting" in status or "restarting" in status:
                    is_bad = True
                    reason = "crash loop (restarting)"
                elif "Exited" in status and "Exited (0)" not in status:
                    is_bad = True
                    reason = f"crashed ({status})"
                elif "unhealthy" in status.lower():
                    is_bad = True
                    reason = "unhealthy"
                if is_bad:
                    problems.append({"name": name, "status": status, "image": image, "reason": reason})
        return {
            "ok": True,
            "total": len(out.strip().split("\n")),
            "problems": problems,
            "suspicious": len(problems) > 0,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _create_security_ticket(title, description, severity="high"):
    """Create ITSM ticket for security finding."""
    try:
        from connect.db import create_ticket
        return create_ticket(
            title=title,
            description=description,
            severity=severity,
            category="security",
            node=os.uname().nodename,
            service="security_scanner",
            root_cause="Security anomaly detected by automated scanner",
            impact="Potential security breach requires investigation",
            action_plan="1. Investigate finding\n2. Validate if legitimate\n3. Apply remediation",
            source_type="security_scan",
            fix_command="",
            source_ref=f"scan_{int(time.time())}",
        )
    except Exception as e:
        log.warning(f"Failed to create security ticket: {e}")
        return None


def _update_state(status, task, details=None):
    try:
        from connect.state import update_agent_state
        update_agent_state("security_scanner", status, task,
                           model="security-monitor", platform="linux",
                           autonomous=True,
                           tools=["port_scan", "file_integrity", "tcp_analyze", "session_check"],
                           details=details or {})
    except Exception:
        pass


def _save_scan_state(scan_results):
    try:
        STATE_FILE.write_text(json.dumps({
            "last_scan": int(time.time()),
            "results": scan_results,
        }, indent=2))
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
    log.info("Security Scanner Agent starting")
    _update_state("running", "Iniciando scans de segurança")

    while running:
        try:
            # HA check
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

            # Run all checks
            log.info("Running security scan cycle...")
            results = {}

            # 1. Port scan
            results["ports"] = _check_open_ports()
            # 2. TCP connections
            results["connections"] = _check_connections()
            # 3. User sessions
            results["sessions"] = _check_sessions()
            # 4. File integrity
            results["integrity"] = _check_file_integrity()
            # 5. Docker containers health
            results["containers"] = _check_containers()

            # Evaluate findings
            alerts = []
            if results["connections"].get("suspicious"):
                alerts.append("Excessive external connections detected")
            if results["sessions"].get("suspicious"):
                alerts.append(f"Multiple failed logins: {results['sessions'].get('recent_failed_logins')}")
            if results["integrity"].get("changes_detected"):
                alerts.append(f"Critical files modified: {results['integrity']['changes_detected']}")
            # Container alerts
            for prob in results.get("containers", {}).get("problems", []):
                alerts.append(f"Container {prob['name']} is {prob['reason']}")
                # Create specific ticket for container issues
                _create_security_ticket(
                    title=f"[{os.uname().nodename}] Container {prob['name']} — {prob['reason']}",
                    description=f"Container: {prob['name']}\nStatus: {prob['status']}\nImage: {prob.get('image','?')}\nAction: docker restart {prob['name']}",
                    severity="high" if "crash" in prob['reason'] else "medium",
                )

            # Create tickets for serious findings
            for alert in alerts:
                log.warning(f"SECURITY ALERT: {alert}")
                _create_security_ticket(
                    title=f"[{os.uname().nodename}] {alert}",
                    description=f"Security scanner detected: {alert}\n\nFull scan results: {json.dumps(results, indent=2, default=str)[:1000]}",
                    severity="high" if "Critical files" in alert else "medium",
                )

            _save_scan_state(results)

            # Report status
            total_checks = 4
            suspicious = sum(1 for r in results.values() if r.get("suspicious"))
            ports_count = results.get("ports", {}).get("open_ports", "?")
            conns = results.get("connections", {}).get("total_connections", "?")

            status_msg = f"Scan OK — {ports_count} ports, {conns} conns, {suspicious} alertas"
            if alerts:
                status_msg = f"ALERTA: {len(alerts)} finding(s) — {'; '.join(alerts[:2])}"

            _update_state(
                "warning" if alerts else "running",
                status_msg,
                details={
                    "open_ports": ports_count,
                    "connections": conns,
                    "alerts": len(alerts),
                    "last_scan": datetime.now(timezone.utc).isoformat(),
                }
            )

            if alerts:
                log.warning(f"Scan complete: {len(alerts)} alert(s)")
            else:
                log.info("Scan complete: all clear")

        except Exception as ex:
            log.error(f"Scan cycle error: {ex}")
            _update_state("error", str(ex)[:80])

        for _ in range(CHECK_INTERVAL):
            if not running:
                break
            time.sleep(1)

    _update_state("idle", "Stopped")
    PID_FILE.unlink(missing_ok=True)
    log.info("Security Scanner Agent stopped")


if __name__ == "__main__":
    main()
