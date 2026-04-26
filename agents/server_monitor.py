#!/usr/bin/env python3
"""
CH8 Server Monitor Agent
========================
Monitors resources, detects security threats, proposes and executes
remediation actions with user authorization.

Capabilities:
  - Resource monitoring (CPU, MEM, DISK, load, processes)
  - Security scanning (cryptominers, suspicious binaries, exposed ports)
  - Docker audit (public ports, weak passwords, unauthorized containers)
  - Predictive analysis (trend-based alerts)
  - Action proposals (structured, executable with authorization)

Usage:
    python3 agents/server_monitor.py             # observe mode
    python3 agents/server_monitor.py --auto      # autonomous mode
    python3 agents/server_monitor.py --report    # one-shot report
    python3 agents/server_monitor.py --scan      # security scan only
"""

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List

try:
    import psutil
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet",
                           "--break-system-packages", "psutil"])
    import psutil

# ── Config ───────────────────────────────────────────────────────────────────

HISTORY_FILE     = Path(os.environ.get("CH8_MONITOR_HISTORY",
                        Path.home() / ".config/ch8/monitor_history.jsonl"))
STATE_FILE       = Path(os.environ.get("CH8_AGENT_STATE",
                        Path.home() / ".config/ch8/state.json"))
ACTIONS_FILE     = Path(os.environ.get("CH8_ACTIONS_FILE",
                        Path.home() / ".config/ch8/pending_actions.json"))

SAMPLE_INTERVAL  = int(os.environ.get("CH8_MONITOR_INTERVAL", "15"))
SECURITY_INTERVAL = int(os.environ.get("CH8_SECURITY_INTERVAL", "60"))
HISTORY_KEEP     = int(os.environ.get("CH8_MONITOR_HISTORY_KEEP", "1440"))
ALERT_CPU        = float(os.environ.get("CH8_ALERT_CPU",  "85"))
ALERT_MEM        = float(os.environ.get("CH8_ALERT_MEM",  "88"))
ALERT_DISK       = float(os.environ.get("CH8_ALERT_DISK", "90"))
PREDICT_WINDOW   = int(os.environ.get("CH8_PREDICT_WINDOW", "20"))

log = logging.getLogger("ch8.monitor")

# ── Protected processes (never kill) ─────────────────────────────────────────

PROTECTED_NAMES = {
    "init", "systemd", "kernel", "kthreadd", "sshd", "cron",
    "postgres", "mysqld", "mongod", "redis-server",
    "nginx", "caddy", "apache2",
    "dockerd", "containerd", "docker-proxy",
    "tailscaled", "NetworkManager", "systemd-networkd",
    "uvicorn", "ch8", "python3",
    "node_exporter", "prometheus",
}

PROTECTED_CMDLINE = [
    "connect.daemon", "server_monitor", "orchestrator", "uvicorn",
    "gunicorn", "ch8", "docker", "containerd", "tailscale",
]

SUSPICIOUS_PATHS = ["/tmp", "/dev/shm", "/var/tmp", "/dev/mqueue"]
KNOWN_MINER_NAMES = ["xmrig", "minerd", "kdevtmpfsi", "kinsing", "solr",
                      "mysql", "apache2", "httpd", "sshd"]
DEFAULT_PASSWORDS = ["postgres", "password", "admin", "root", "123456",
                     "redis", "default", "changeme", "test"]


def is_protected(proc: psutil.Process) -> bool:
    try:
        name = proc.name().lower()
        if name in PROTECTED_NAMES:
            return True
        cmdline = " ".join(proc.cmdline()).lower()
        if any(p in cmdline for p in PROTECTED_CMDLINE):
            return True
        if proc.pid <= 2:
            return True
        return False
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return True


# ── Resource collection ──────────────────────────────────────────────────────

def collect_sample() -> dict:
    cpu  = psutil.cpu_percent(interval=0.5)
    mem  = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    load = os.getloadavg()
    net  = psutil.net_io_counters()

    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent",
                                   "status", "create_time", "cmdline", "username", "exe"]):
        try:
            info = p.info
            if info["cpu_percent"] > 0.5 or info["memory_percent"] > 0.5:
                cmd = " ".join(info["cmdline"] or [])[:100] if info["cmdline"] else info["name"]
                procs.append({
                    "pid":     info["pid"],
                    "name":    info["name"],
                    "cpu":     round(info["cpu_percent"], 1),
                    "mem":     round(info["memory_percent"], 1),
                    "mem_mb":  round(info["memory_percent"] * mem.total / 100 / 1e6, 0),
                    "status":  info["status"],
                    "user":    info["username"] or "?",
                    "exe":     info.get("exe") or "",
                    "cmd":     cmd,
                    "age_s":   int(time.time() - (info["create_time"] or time.time())),
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(key=lambda x: x["cpu"] + x["mem"], reverse=True)

    return {
        "ts":           int(time.time()),
        "cpu":          round(cpu, 1),
        "mem":          round(mem.percent, 1),
        "mem_avail_mb": mem.available // (1024 * 1024),
        "mem_total_mb": mem.total // (1024 * 1024),
        "disk":         round(disk.percent, 1),
        "disk_free_gb": disk.free // (1024 ** 3),
        "load1":        round(load[0], 2),
        "load5":        round(load[1], 2),
        "load15":       round(load[2], 2),
        "net_sent_mb":  round(net.bytes_sent / 1e6, 1),
        "net_recv_mb":  round(net.bytes_recv / 1e6, 1),
        "top_procs":    procs[:20],
    }


# ── Security scanning ────────────────────────────────────────────────────────

def scan_suspicious_processes(sample: dict) -> list:
    """Detect processes running from suspicious paths or behaving like miners."""
    findings = []
    docker_pids = _get_docker_pids()

    for p in sample.get("top_procs", []):
        exe = p.get("exe", "")
        name = p.get("name", "").lower()
        pid = p["pid"]

        # Process running from /tmp, /dev/shm, /var/tmp
        for path in SUSPICIOUS_PATHS:
            if exe.startswith(path):
                severity = "critical"
                # Extra severity if high CPU (likely miner)
                if p["cpu"] > 50:
                    severity = "critical"
                    desc = f"CRYPTOMINER: {name} running from {path} with {p['cpu']}% CPU, {p.get('mem_mb',0):.0f} MB RAM"
                else:
                    severity = "high"
                    desc = f"Suspicious binary in {path}: {name} (PID {pid})"

                findings.append({
                    "type":     "suspicious_process",
                    "severity": severity,
                    "pid":      pid,
                    "name":     name,
                    "exe":      exe,
                    "cpu":      p["cpu"],
                    "mem":      p["mem"],
                    "desc":     desc,
                    "in_docker": pid in docker_pids,
                    "action":   {
                        "type":    "kill_process",
                        "desc":    f"Kill PID {pid} ({name}) and remove {exe}",
                        "command": f"kill -9 {pid} && rm -f {exe}",
                        "safe":    pid not in docker_pids,
                    },
                })
                break

        # Known miner names with high CPU
        if p["cpu"] > 80 and name in KNOWN_MINER_NAMES and exe:
            already = any(f["pid"] == pid for f in findings)
            if not already:
                findings.append({
                    "type":     "potential_miner",
                    "severity": "critical",
                    "pid":      pid,
                    "name":     name,
                    "exe":      exe,
                    "cpu":      p["cpu"],
                    "desc":     f"Potential miner: {name} using {p['cpu']}% CPU",
                    "action":   {
                        "type":    "kill_process",
                        "desc":    f"Kill {name} (PID {pid})",
                        "command": f"kill -9 {pid}",
                        "safe":    True,
                    },
                })

    return findings


def scan_docker_ports() -> list:
    """Audit Docker containers for publicly exposed ports."""
    findings = []
    try:
        out = subprocess.check_output(
            ["docker", "ps", "--format",
             "{{.Names}}|{{.Image}}|{{.Ports}}|{{.ID}}"],
            timeout=10, stderr=subprocess.DEVNULL
        ).decode().strip()

        for line in out.splitlines():
            if not line.strip():
                continue
            parts = (line + "|||").split("|")
            name, image, ports, cid = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()

            # Parse ports for 0.0.0.0:XXXXX->YYYYY
            if "0.0.0.0:" in ports:
                # Extract public port mappings
                for segment in ports.split(","):
                    segment = segment.strip()
                    if "0.0.0.0:" in segment:
                        # e.g. "0.0.0.0:54320->5432/tcp"
                        public_port = segment.split("0.0.0.0:")[1].split("->")[0]
                        internal_port = segment.split("->")[1].split("/")[0] if "->" in segment else "?"

                        severity = "medium"
                        desc = f"Container '{name}' exposes port {public_port} publicly"

                        # Higher severity for database ports
                        db_ports = {"5432", "3306", "27017", "6379", "9200", "5984"}
                        if internal_port in db_ports:
                            severity = "high"
                            desc = f"DATABASE EXPOSED: '{name}' ({image}) port {public_port}→{internal_port} open to internet"

                        findings.append({
                            "type":      "exposed_port",
                            "severity":  severity,
                            "container": name,
                            "image":     image,
                            "public_port": public_port,
                            "internal_port": internal_port,
                            "desc":      desc,
                            "action":    {
                                "type":    "fix_port",
                                "desc":    f"Remove public mapping for {name}:{public_port}",
                                "command": f"# Edit docker-compose.yml: change ports to expose, then docker compose up -d",
                                "safe":    False,
                            },
                        })
    except Exception as e:
        log.warning(f"Docker port scan failed: {e}")

    return findings


def scan_weak_passwords() -> list:
    """Check known services for default/weak passwords."""
    findings = []

    # PostgreSQL containers
    try:
        out = subprocess.check_output(
            ["docker", "ps", "--format", "{{.Names}}|{{.ID}}"],
            timeout=5, stderr=subprocess.DEVNULL
        ).decode().strip()

        for line in out.splitlines():
            name, cid = (line + "|").split("|")[:2]
            name, cid = name.strip(), cid.strip()
            if not name:
                continue

            # Check Postgres password via env
            try:
                env = subprocess.check_output(
                    ["docker", "exec", name, "sh", "-c", "echo $POSTGRES_PASSWORD"],
                    timeout=5, stderr=subprocess.DEVNULL
                ).decode().strip()
                if env and env.lower() in DEFAULT_PASSWORDS:
                    findings.append({
                        "type":      "weak_password",
                        "severity":  "critical",
                        "container": name,
                        "service":   "PostgreSQL",
                        "desc":      f"Weak password '{env}' on PostgreSQL container '{name}'",
                        "action":    {
                            "type":    "change_password",
                            "desc":    f"Change PostgreSQL password for '{name}'",
                            "command": f"docker exec {name} psql -U postgres -c \"ALTER USER postgres WITH PASSWORD 'NEW_STRONG_PASSWORD';\"",
                            "safe":    True,
                        },
                    })
            except Exception:
                pass
    except Exception:
        pass

    return findings


def _get_docker_pids() -> set:
    pids = set()
    try:
        cids = subprocess.check_output(
            ["docker", "ps", "-q"], timeout=5, stderr=subprocess.DEVNULL
        ).decode().split()
        for cid in cids:
            try:
                top = subprocess.check_output(
                    ["docker", "top", cid.strip(), "-eo", "pid"],
                    timeout=5, stderr=subprocess.DEVNULL
                ).decode()
                for line in top.splitlines()[1:]:
                    line = line.strip()
                    if line.isdigit():
                        pids.add(int(line))
            except Exception:
                pass
    except Exception:
        pass
    return pids


def full_security_scan(sample: dict) -> list:
    """Run all security checks. Returns list of findings."""
    findings = []
    findings.extend(scan_suspicious_processes(sample))
    findings.extend(scan_docker_ports())
    findings.extend(scan_weak_passwords())
    # Sort by severity
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings.sort(key=lambda f: sev_order.get(f.get("severity", "low"), 9))
    return findings


# ── Trend analysis & predictions ─────────────────────────────────────────────

def trend_slope(values: list) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    num   = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denom = sum((i - x_mean) ** 2 for i in range(n))
    return num / denom if denom else 0.0


def minutes_to_threshold(current: float, slope: float, threshold: float) -> Optional[float]:
    if slope <= 0 or current >= threshold:
        return None
    samples = (threshold - current) / slope
    return round(samples * SAMPLE_INTERVAL / 60, 1)


def analyze(history: list, current: dict, security_findings: list) -> dict:
    alerts      = []
    predictions = []

    # Resource alerts
    if current["cpu"] >= ALERT_CPU:
        alerts.append({"level": "critical", "metric": "cpu",
                        "value": current["cpu"], "msg": f"CPU at {current['cpu']}%"})
    if current["mem"] >= ALERT_MEM:
        alerts.append({"level": "critical", "metric": "mem",
                        "value": current["mem"], "msg": f"Memory at {current['mem']}%"})
    if current["disk"] >= ALERT_DISK:
        alerts.append({"level": "critical", "metric": "disk",
                        "value": current["disk"], "msg": f"Disk at {current['disk']}%"})
    if current["load1"] > psutil.cpu_count() * 0.9:
        alerts.append({"level": "warning", "metric": "load",
                        "value": current["load1"],
                        "msg": f"Load {current['load1']} (cores: {psutil.cpu_count()})"})

    # Security alerts
    for f in security_findings:
        alerts.append({
            "level":  f["severity"],
            "metric": "security",
            "value":  f.get("type", ""),
            "msg":    f["desc"],
            "action": f.get("action"),
        })

    # Trend predictions
    if len(history) >= PREDICT_WINDOW:
        window = history[-PREDICT_WINDOW:]
        for metric, threshold in [("cpu", ALERT_CPU), ("mem", ALERT_MEM), ("disk", ALERT_DISK)]:
            values = [s[metric] for s in window]
            slope  = trend_slope(values)
            if slope > 0.1:
                eta = minutes_to_threshold(values[-1], slope, threshold)
                if eta and eta < 120:
                    predictions.append({
                        "metric":   metric,
                        "current":  current[metric],
                        "threshold": threshold,
                        "slope":    round(slope * 60 / SAMPLE_INTERVAL, 2),
                        "eta_min":  eta,
                        "msg":      f"{metric.upper()} will reach {threshold}% in ~{eta}min (+{round(slope*60/SAMPLE_INTERVAL,1)}%/min)",
                    })

    # Heavy processes
    heavy = []
    for p in current.get("top_procs", []):
        reason = []
        if p["cpu"] > 40: reason.append(f"CPU {p['cpu']}%")
        if p["mem"] > 20: reason.append(f"MEM {p['mem']}%")
        if reason:
            heavy.append({**p, "reason": ", ".join(reason)})

    return {
        "alerts":       alerts,
        "predictions":  predictions,
        "heavy_procs":  heavy[:10],
        "security":     security_findings,
    }


# ── History ──────────────────────────────────────────────────────────────────

def append_history(sample: dict) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Strip top_procs to save space
    slim = {k: v for k, v in sample.items() if k != "top_procs"}
    with HISTORY_FILE.open("a") as f:
        f.write(json.dumps(slim) + "\n")
    lines = HISTORY_FILE.read_text().splitlines()
    if len(lines) > HISTORY_KEEP:
        HISTORY_FILE.write_text("\n".join(lines[-HISTORY_KEEP:]) + "\n")


def load_history(n: Optional[int] = None) -> list:
    if not HISTORY_FILE.exists():
        return []
    lines = HISTORY_FILE.read_text().splitlines()
    if n: lines = lines[-n:]
    result = []
    for line in lines:
        try: result.append(json.loads(line))
        except: pass
    return result


# ── Actions ──────────────────────────────────────────────────────────────────

def save_pending_actions(actions: list) -> None:
    """Save proposed actions for user review via dashboard."""
    ACTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if ACTIONS_FILE.exists():
        try: existing = json.loads(ACTIONS_FILE.read_text())
        except: pass

    # Deduplicate by desc
    known = {a["desc"] for a in existing}
    for a in actions:
        if a["desc"] not in known:
            a["proposed_at"] = int(time.time())
            a["status"] = "pending"
            existing.append(a)
            known.add(a["desc"])

    # Keep last 50
    ACTIONS_FILE.write_text(json.dumps(existing[-50:], indent=2))


def execute_action(action: dict, dry_run: bool = False) -> dict:
    """Execute a proposed action."""
    cmd = action.get("command", "")
    if not cmd:
        return {"ok": False, "error": "no command"}

    if dry_run:
        return {"ok": True, "dry_run": True, "command": cmd}

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=30
        )
        return {
            "ok":       result.returncode == 0,
            "command":  cmd,
            "stdout":   result.stdout[:500],
            "stderr":   result.stderr[:500],
            "code":     result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "command": cmd}
    except Exception as e:
        return {"ok": False, "error": str(e), "command": cmd}


# ── State update ─────────────────────────────────────────────────────────────

def update_agent_state(sample: dict, analysis: dict, autonomous: bool) -> None:
    alerts     = analysis.get("alerts", [])
    predictions = analysis.get("predictions", [])
    security   = analysis.get("security", [])

    critical = [a for a in alerts if a.get("level") == "critical"]
    sec_critical = [s for s in security if s.get("severity") == "critical"]

    if sec_critical:
        status = "error"
        task = sec_critical[0]["desc"][:80]
    elif critical:
        status = "error"
        task = critical[0]["msg"][:80]
    elif predictions:
        status = "running"
        task = predictions[0]["msg"][:80]
    else:
        status = "idle"
        task = f"CPU {sample['cpu']}% · MEM {sample['mem']}% · DISK {sample['disk']}%"

    agent_entry = {
        "name":        "server-monitor",
        "status":      status,
        "task":        task,
        "model":       "threat detection + trend analysis",
        "platform":    "psutil",
        "autonomous":  autonomous,
        "alerts":      len(alerts),
        "security_findings": len(security),
        "predictions": len(predictions),
        "heavy_procs": len(analysis.get("heavy_procs", [])),
        "details": {
            "alerts":      alerts[:10],
            "predictions": predictions[:5],
            "security":    security[:10],
            "heavy_procs": analysis.get("heavy_procs", [])[:5],
        },
        "updated_at":  int(time.time()),
    }

    try:
        state = {}
        if STATE_FILE.exists():
            state = json.loads(STATE_FILE.read_text())
        agents = [a for a in (state.get("agents") or []) if a.get("name") != "server-monitor"]
        agents.append(agent_entry)
        state["agents"] = agents
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception:
        pass

    # Save proposed actions from security findings
    actions = [f["action"] for f in security if f.get("action")]
    if actions:
        save_pending_actions(actions)


# ── Display ──────────────────────────────────────────────────────────────────

R = "\033[0m"; B = "\033[1m"; RED = "\033[0;31m"; YEL = "\033[1;33m"
GRN = "\033[0;32m"; CYN = "\033[0;36m"; DIM = "\033[2m"

def bar(pct, w=20):
    f = int(pct / 100 * w)
    c = RED if pct > 85 else (YEL if pct > 65 else GRN)
    return c + "█" * f + DIM + "░" * (w - f) + R

def print_report(sample, analysis, autonomous):
    ts = datetime.fromtimestamp(sample["ts"]).strftime("%H:%M:%S")
    print(f"\n{B}{'─'*64}{R}")
    print(f"  {B}CH8 Server Monitor{R}  {DIM}{ts}{R}  {'🤖 AUTO' if autonomous else '👁 OBSERVE'}")
    print(f"{'─'*64}")
    print(f"  {B}CPU {R} {bar(sample['cpu'])} {sample['cpu']:5.1f}%  load {sample['load1']}/{sample['load5']}/{sample['load15']}")
    print(f"  {B}MEM {R} {bar(sample['mem'])} {sample['mem']:5.1f}%  {sample['mem_avail_mb']:,} MB free")
    print(f"  {B}DISK{R} {bar(sample['disk'])} {sample['disk']:5.1f}%  {sample['disk_free_gb']} GB free")
    print()

    for a in analysis.get("alerts", []):
        icon = "🔴" if a["level"] == "critical" else ("🟡" if a["level"] in ("high","warning") else "🔵")
        print(f"  {icon}  {a['msg']}")
    if analysis["alerts"]: print()

    if analysis.get("security"):
        print(f"  {B}Security findings:{R}")
        for f in analysis["security"][:5]:
            sev = {"critical": RED+"CRIT", "high": YEL+"HIGH", "medium": CYN+"MED"}.get(f["severity"], "LOW")
            print(f"  {sev}{R}  {f['desc']}")
            if f.get("action"):
                print(f"        {DIM}→ {f['action']['desc']}{R}")
        print()

    if analysis.get("predictions"):
        for p in analysis["predictions"]:
            print(f"  {YEL}⚠{R}  {p['msg']}")
        print()

    if analysis.get("heavy_procs"):
        print(f"  {B}Top processes:{R}")
        print(f"  {'PID':>7}  {'NAME':<18} {'CPU':>6} {'MEM':>6}  CMD")
        for p in analysis["heavy_procs"][:6]:
            cc = RED if p["cpu"] > 50 else R
            mc = RED if p["mem"] > 20 else R
            print(f"  {p['pid']:>7}  {p['name']:<18} {cc}{p['cpu']:>5.1f}%{R} {mc}{p['mem']:>5.1f}%{R}  {DIM}{p['cmd'][:30]}{R}")
        print()

    if not analysis["alerts"] and not analysis.get("security") and not analysis.get("predictions"):
        print(f"  {GRN}✓ All systems nominal{R}\n")


# ── Main loop ────────────────────────────────────────────────────────────────

def run(autonomous=False, report_once=False, scan_only=False):
    mode = "AUTONOMOUS" if autonomous else "OBSERVE"
    if not report_once and not scan_only:
        print(f"{B}CH8 Server Monitor — {mode} mode{R}")
        print(f"  Resources every {SAMPLE_INTERVAL}s · Security every {SECURITY_INTERVAL}s")
        print(f"  Thresholds: CPU>{ALERT_CPU}% MEM>{ALERT_MEM}% DISK>{ALERT_DISK}%")
        if autonomous:
            print(f"  {RED}Autonomous actions enabled{R}")
        print(f"  Press Ctrl+C to stop\n")

    last_security_scan = 0
    security_findings = []

    while True:
        sample  = collect_sample()
        history = load_history(PREDICT_WINDOW * 2)
        append_history(sample)

        # Security scan at lower frequency
        now = time.time()
        if now - last_security_scan >= SECURITY_INTERVAL or scan_only or report_once:
            security_findings = full_security_scan(sample)
            last_security_scan = now

        analysis = analyze(history, sample, security_findings)
        update_agent_state(sample, analysis, autonomous)
        print_report(sample, analysis, autonomous)

        if scan_only or report_once:
            if security_findings:
                print(f"\n{B}Proposed actions:{R}")
                for i, f in enumerate(security_findings):
                    if f.get("action"):
                        a = f["action"]
                        print(f"  [{i+1}] {a['desc']}")
                        print(f"      {DIM}{a['command']}{R}")
            return

        try:
            time.sleep(SAMPLE_INTERVAL)
        except KeyboardInterrupt:
            print(f"\n{DIM}Monitor stopped.{R}")
            sys.exit(0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(description="CH8 Server Monitor Agent")
    parser.add_argument("--auto",   action="store_true", help="Autonomous mode")
    parser.add_argument("--report", action="store_true", help="One-shot report")
    parser.add_argument("--scan",   action="store_true", help="Security scan only")
    args = parser.parse_args()
    run(autonomous=args.auto, report_once=args.report, scan_only=args.scan)
