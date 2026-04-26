#!/usr/bin/env python3
"""
CH8 Orchestrator Agent — default agent for every node.

Runs as an HTTP server on port 7879.
Answers questions about this node using live system context injected
into the system prompt. Uses the local Ollama model as its brain.

Starts automatically via `ch8 up`.
"""

import json
import logging
import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# ── deps ─────────────────────────────────────────────────────────────────────
try:
    import psutil, httpx
    from fastapi import FastAPI
    from fastapi.requests import Request
    from fastapi.responses import StreamingResponse, JSONResponse
    import uvicorn
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet",
                           "--break-system-packages",
                           "psutil", "httpx", "fastapi", "uvicorn"])
    import psutil, httpx
    from fastapi import FastAPI
    from fastapi.requests import Request
    from fastapi.responses import StreamingResponse, JSONResponse
    import uvicorn

log = logging.getLogger("ch8.orchestrator")

AGENT_PORT    = int(os.environ.get("CH8_AGENT_PORT", "7879"))
OLLAMA_URL    = os.environ.get("CH8_OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("CH8_MODEL", "")   # auto-detect if empty
CONFIG_DIR    = Path.home() / ".config" / "ch8"
STATE_FILE    = CONFIG_DIR / "state.json"

app = FastAPI(title="CH8 Orchestrator", docs_url=None)

# ── context collection ────────────────────────────────────────────────────────

_ctx_cache: dict = {}
_ctx_ts: float   = 0.0
CTX_TTL = 10  # seconds


def _get_context() -> dict:
    global _ctx_cache, _ctx_ts
    if time.time() - _ctx_ts < CTX_TTL:
        return _ctx_cache

    ctx: dict = {}

    # Basic
    ctx["hostname"]  = socket.gethostname()
    ctx["os"]        = platform.system() + " " + platform.release()
    ctx["arch"]      = platform.machine()
    ctx["python"]    = platform.python_version()

    # Resources
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    dsk = psutil.disk_usage("/")
    ld  = os.getloadavg()
    ctx["cpu_pct"]   = cpu
    ctx["mem_pct"]   = round(mem.percent, 1)
    ctx["mem_free_gb"] = round(mem.available / 1e9, 1)
    ctx["disk_pct"]  = round(dsk.percent, 1)
    ctx["disk_free_gb"] = round(dsk.free / 1e9, 1)
    ctx["load"]      = f"{ld[0]:.2f} {ld[1]:.2f} {ld[2]:.2f}"

    # Top processes
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        try:
            if p.info["cpu_percent"] > 1 or p.info["memory_percent"] > 1:
                procs.append({
                    "pid":  p.info["pid"],
                    "name": p.info["name"],
                    "cpu":  round(p.info["cpu_percent"], 1),
                    "mem":  round(p.info["memory_percent"], 1),
                })
        except Exception:
            pass
    procs.sort(key=lambda x: x["cpu"] + x["mem"], reverse=True)
    ctx["top_procs"] = procs[:12]

    # Docker containers
    containers = []
    try:
        out = subprocess.check_output(
            ["docker", "ps", "--format",
             "{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}"],
            timeout=5, stderr=subprocess.DEVNULL
        ).decode().strip()
        for line in out.splitlines():
            if not line.strip():
                continue
            parts = (line + "|||").split("|")
            containers.append({
                "name":   parts[0].strip(),
                "image":  parts[1].strip(),
                "status": parts[2].strip(),
                "ports":  parts[3].strip(),
            })
    except Exception:
        pass
    ctx["containers"] = containers

    # Ollama models
    models = []
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    ctx["models"] = models

    # CH8 peers from state
    peers = []
    try:
        state = json.loads(STATE_FILE.read_text())
        peers = [
            f"{p.get('hostname','?')} ({p.get('address','?')})"
            for p in state.get("peers", [])
        ]
    except Exception:
        pass
    ctx["peers"] = peers

    # Tailscale IP
    try:
        ts_ip = subprocess.check_output(
            ["tailscale", "ip", "--4"], timeout=3, stderr=subprocess.DEVNULL
        ).decode().strip()
        ctx["tailscale_ip"] = ts_ip
    except Exception:
        ctx["tailscale_ip"] = "unavailable"

    _ctx_cache = ctx
    _ctx_ts    = time.time()
    return ctx


def _build_system_prompt(ctx: dict) -> str:
    containers_txt = "\n".join(
        f"  • {c['name']} [{c['image']}] {c['status']}  {c['ports']}"
        for c in ctx.get("containers", [])
    ) or "  (none detected)"

    procs_txt = "\n".join(
        f"  • PID {p['pid']} {p['name']}  CPU:{p['cpu']}%  MEM:{p['mem']}%"
        for p in ctx.get("top_procs", [])[:8]
    ) or "  (none)"

    peers_txt = ", ".join(ctx.get("peers", [])) or "no other nodes"
    models_txt = ", ".join(ctx.get("models", [])) or "none"

    return f"""You are the CH8 Orchestrator for node **{ctx['hostname']}**.
You are the primary AI agent responsible for administering and operating this server and its AI cluster.

## Your Node — Live Status
- Hostname:      {ctx['hostname']}
- OS:            {ctx['os']} ({ctx['arch']})
- Tailscale IP:  {ctx['tailscale_ip']}
- CPU:           {ctx['cpu_pct']}%  (load: {ctx['load']})
- Memory:        {ctx['mem_pct']}% used  ({ctx['mem_free_gb']} GB free)
- Disk:          {ctx['disk_pct']}% used  ({ctx['disk_free_gb']} GB free)

## Running Containers
{containers_txt}

## Top Processes
{procs_txt}

## CH8 Cluster
- Peers online:  {peers_txt}
- Local models:  {models_txt}

## Your Capabilities
- Analyze resource usage and identify bottlenecks
- Explain what each service/container does
- Suggest and guide actions (restart containers, scale services)
- Orchestrate tasks across the cluster nodes
- Monitor trends and predict issues
- Answer questions about this server, its configuration, and workloads

## Guidelines
- Be direct and technical. The user is an operator or developer.
- When reporting metrics, use the live data above.
- If asked to take an action you cannot execute directly, describe the exact commands needed.
- Always prioritize service stability — never recommend actions that would bring down active services.
- You are aware of the full cluster topology.
- Current time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}
"""


# ── model selection ───────────────────────────────────────────────────────────

def _best_model() -> str:
    if DEFAULT_MODEL:
        return DEFAULT_MODEL
    ctx = _get_context()
    models = ctx.get("models", [])
    if not models:
        return "llama3.2"
    # Prefer larger models
    for pref in ["llama3", "qwen2.5:7b", "gemma3:4b", "mistral"]:
        for m in models:
            if pref in m:
                return m
    return models[0]


# ── agent state ───────────────────────────────────────────────────────────────

def _update_agent_state(status: str, task: str) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        state = {}
        if STATE_FILE.exists():
            state = json.loads(STATE_FILE.read_text())
        agents = [a for a in state.get("agents", []) if a.get("name") != "orchestrator"]
        agents.insert(0, {   # orchestrator is always first
            "name":       "orchestrator",
            "status":     status,
            "task":       task,
            "model":      _best_model(),
            "platform":   "ollama",
            "updated_at": int(time.time()),
        })
        state["agents"] = agents
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception:
        pass


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "agent": "orchestrator", "ts": int(time.time())}


@app.post("/chat")
async def chat(request: Request):
    """
    Stream a conversation with the orchestrator.
    Body: { "messages": [{role, content}, ...], "model": "optional" }
    Returns: SSE stream (Ollama format).
    """
    body     = await request.json()
    messages = body.get("messages", [])
    model    = body.get("model") or _best_model()

    ctx     = _get_context()
    sys_msg = _build_system_prompt(ctx)

    # Build full message list with live system prompt
    full_messages = [{"role": "system", "content": sys_msg}] + messages

    last_user = next((m["content"] for m in reversed(messages)
                      if m["role"] == "user"), "…")
    _update_agent_state("running", last_user[:80])

    async def stream_gen():
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST", f"{OLLAMA_URL}/api/chat",
                    json={"model": model, "messages": full_messages, "stream": True},
                ) as resp:
                    if resp.status_code != 200:
                        err = "Ollama error " + str(resp.status_code)
                        yield "data: " + json.dumps({"error": err}) + "\n\n"
                        return
                    async for line in resp.aiter_lines():
                        if line.strip():
                            yield "data: " + line + "\n\n"
        except httpx.ConnectError:
            yield "data: " + json.dumps({"error": "Ollama not reachable"}) + "\n\n"
        except Exception as ex:
            yield "data: " + json.dumps({"error": str(ex)}) + "\n\n"
        finally:
            _update_agent_state("idle", "waiting for tasks")
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/context")
async def get_context():
    """Return the current node context (for debugging)."""
    return _get_context()


# ── startup ───────────────────────────────────────────────────────────────────

import asyncio as _asyncio

@app.on_event("startup")
async def _keepalive():
    """Refresh agent state every 30s so it never expires from the dashboard."""
    async def _loop():
        while True:
            try:
                ctx     = _get_context()
                alerts  = []
                if ctx.get("cpu_pct", 0) > 85:
                    alerts.append(f"CPU {ctx['cpu_pct']}%")
                if ctx.get("mem_pct", 0) > 88:
                    alerts.append(f"MEM {ctx['mem_pct']}%")
                if ctx.get("disk_pct", 0) > 90:
                    alerts.append(f"DISK {ctx['disk_pct']}%")
                task = "⚠ " + ", ".join(alerts) if alerts else (
                    f"CPU {ctx.get('cpu_pct',0):.0f}% · "
                    f"MEM {ctx.get('mem_pct',0):.0f}% · "
                    f"{len(ctx.get('containers',[]))} containers"
                )
                _update_agent_state("running" if alerts else "idle", task)
            except Exception:
                pass
            await _asyncio.sleep(30)
    _asyncio.create_task(_loop())


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    _update_agent_state("idle", "waiting for tasks")
    log.info(f"CH8 Orchestrator starting on port {AGENT_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT, log_level="warning")


if __name__ == "__main__":
    main()
