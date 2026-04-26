#!/usr/bin/env python3
"""
CH8 Orchestrator Agent — default agent for every node.

Runs as an HTTP server on port 7879.
Answers questions about this node using live system context injected
into the system prompt. Supports multiple AI backends.

Starts automatically via `ch8 up`.
"""

import json
import logging
import os
import platform
import re
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

# Add parent to path for connect.ai_config
sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger("ch8.orchestrator")

AGENT_PORT    = int(os.environ.get("CH8_AGENT_PORT", "7879"))
OLLAMA_URL    = os.environ.get("CH8_OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("CH8_MODEL", "")   # auto-detect if empty
CONFIG_DIR    = Path.home() / ".config" / "ch8"
STATE_FILE    = CONFIG_DIR / "state.json"

app = FastAPI(title="CH8 Orchestrator", docs_url=None)

# ── AI provider ──────────────────────────────────────────────────────────────

def _load_ai_provider() -> dict:
    """Load AI provider config. Falls back to Ollama if not configured."""
    try:
        from connect.ai_config import get_provider_info
        return get_provider_info()
    except Exception:
        return {
            "provider": "ollama",
            "name": "Ollama (local)",
            "api_key": "",
            "api_url": OLLAMA_URL,
            "model": DEFAULT_MODEL,
            "aws_region": "",
        }


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
    try:
        ld = os.getloadavg()
        ctx["load"] = f"{ld[0]:.2f} {ld[1]:.2f} {ld[2]:.2f}"
    except (OSError, AttributeError):
        ctx["load"] = "N/A"
    ctx["cpu_pct"]   = cpu
    ctx["mem_pct"]   = round(mem.percent, 1)
    ctx["mem_free_gb"] = round(mem.available / 1e9, 1)
    ctx["disk_pct"]  = round(dsk.percent, 1)
    ctx["disk_free_gb"] = round(dsk.free / 1e9, 1)

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

    # Ollama models (local)
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

    # AI provider info
    ai = _load_ai_provider()
    ctx["ai_provider"] = ai["name"]
    ctx["ai_model"]    = ai["model"]

    _ctx_cache = ctx
    _ctx_ts    = time.time()
    return ctx


def _build_system_prompt(ctx: dict) -> str:
    containers_txt = "\n".join(
        f"  - {c['name']} [{c['image']}] {c['status']}  {c['ports']}"
        for c in ctx.get("containers", [])
    ) or "  (none detected)"

    peers_txt = ", ".join(ctx.get("peers", [])) or "no other nodes"
    models_txt = ", ".join(ctx.get("models", [])) or "none"

    return f"""You are the CH8 Orchestrator agent for node {ctx['hostname']}.
You manage this server. You MUST use tools to execute actions — never just describe steps.

## Tools — ALWAYS use these to take action
To call a tool, output this exact format:
```tool_call
{{"name": "tool_name", "args": {{"param": "value"}}}}
```

Tools available:
- shell_exec: run shell commands. Args: {{"command": "...", "timeout": 30}}
- file_write: create/write files. Args: {{"path": "...", "content": "...", "append": false}}
- file_read: read files. Args: {{"path": "...", "lines": 100}}
- docker_exec: run in container. Args: {{"container": "...", "command": "..."}}
- service_restart: restart service. Args: {{"name": "...", "type": "docker"}}
- http_request: HTTP call. Args: {{"url": "...", "method": "GET"}}
- security_scan: security check. Args: {{"scan_type": "full"}}

RULES:
1. When asked to DO something, use tool_call to do it. Do NOT just explain.
2. One tool_call per code block. The system runs it and gives you the result.
3. After getting results, use more tool_call blocks if needed, or summarize what you DID.
4. For destructive actions (delete, kill, restart), confirm first.

## Node Status
Host: {ctx['hostname']} | OS: {ctx['os']} | Tailscale: {ctx['tailscale_ip']}
CPU: {ctx['cpu_pct']}% | RAM: {ctx['mem_pct']}% ({ctx['mem_free_gb']}GB free) | Disk: {ctx['disk_pct']}% ({ctx['disk_free_gb']}GB free)
Containers: {len(ctx.get('containers', []))} running | Peers: {peers_txt} | Models: {models_txt}
AI: {ctx.get('ai_provider', '?')} / {ctx.get('ai_model', '?')}
Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}

Containers:
{containers_txt}
"""


# ── model selection ───────────────────────────────────────────────────────────

def _best_model() -> str:
    ai = _load_ai_provider()
    if ai.get("model"):
        return ai["model"]
    if DEFAULT_MODEL:
        return DEFAULT_MODEL
    # Ollama auto-detect
    ctx = _get_context()
    models = ctx.get("models", [])
    if not models:
        return "llama3.2"
    for pref in ["llama3", "qwen2.5:7b", "gemma3:4b", "mistral"]:
        for m in models:
            if pref in m:
                return m
    return models[0]


# ── streaming backends ───────────────────────────────────────────────────────

async def _stream_ollama(model: str, messages: list):
    """Stream from local Ollama."""
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST", f"{OLLAMA_URL}/api/chat",
            json={"model": model, "messages": messages, "stream": True},
        ) as resp:
            if resp.status_code != 200:
                yield "data: " + json.dumps({"error": f"Ollama error {resp.status_code}"}) + "\n\n"
                return
            async for line in resp.aiter_lines():
                if line.strip():
                    yield "data: " + line + "\n\n"


async def _stream_openai_compatible(api_url: str, api_key: str, model: str, messages: list):
    """Stream from any OpenAI-compatible API (OpenAI, Groq, custom)."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    headers["Content-Type"] = "application/json"
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST", f"{api_url}/chat/completions",
            json={"model": model, "messages": messages, "stream": True},
            headers=headers,
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                yield "data: " + json.dumps({"error": f"API error {resp.status_code}: {body.decode()[:200]}"}) + "\n\n"
                return
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    raw = line[6:]
                    try:
                        obj = json.loads(raw)
                        delta = obj.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            # Convert to Ollama-like format for the dashboard
                            yield "data: " + json.dumps({"message": {"content": content}}) + "\n\n"
                    except json.JSONDecodeError:
                        pass


async def _stream_anthropic(api_key: str, model: str, messages: list):
    """Stream from Anthropic Claude API."""
    # Separate system message
    system_text = ""
    chat_msgs = []
    for m in messages:
        if m["role"] == "system":
            system_text += m["content"] + "\n"
        else:
            chat_msgs.append(m)

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": 4096,
        "stream": True,
        "messages": chat_msgs,
    }
    if system_text:
        body["system"] = system_text.strip()

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST", "https://api.anthropic.com/v1/messages",
            json=body, headers=headers,
        ) as resp:
            if resp.status_code != 200:
                err_body = await resp.aread()
                yield "data: " + json.dumps({"error": f"Anthropic error {resp.status_code}: {err_body.decode()[:200]}"}) + "\n\n"
                return
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line.startswith("data: "):
                    continue
                raw = line[6:]
                try:
                    obj = json.loads(raw)
                    if obj.get("type") == "content_block_delta":
                        text = obj.get("delta", {}).get("text", "")
                        if text:
                            yield "data: " + json.dumps({"message": {"content": text}}) + "\n\n"
                except json.JSONDecodeError:
                    pass


async def _stream_bedrock(model: str, messages: list, region: str):
    """Stream from AWS Bedrock (uses boto3)."""
    try:
        import boto3
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet",
                               "--break-system-packages", "boto3"])
        import boto3

    # Separate system message
    system_text = ""
    chat_msgs = []
    for m in messages:
        if m["role"] == "system":
            system_text += m["content"] + "\n"
        else:
            chat_msgs.append(m)

    client = boto3.client("bedrock-runtime", region_name=region)
    body = {
        "messages": chat_msgs,
        "max_tokens": 4096,
        "anthropic_version": "bedrock-2023-05-31",
    }
    if system_text:
        body["system"] = system_text.strip()

    try:
        response = client.invoke_model_with_response_stream(
            modelId=model,
            body=json.dumps(body),
            contentType="application/json",
        )
        for event in response["body"]:
            chunk = json.loads(event["chunk"]["bytes"])
            if chunk.get("type") == "content_block_delta":
                text = chunk.get("delta", {}).get("text", "")
                if text:
                    yield "data: " + json.dumps({"message": {"content": text}}) + "\n\n"
    except Exception as ex:
        yield "data: " + json.dumps({"error": f"Bedrock error: {str(ex)[:200]}"}) + "\n\n"


# ── agent state ───────────────────────────────────────────────────────────────

def _update_agent_state(status: str, task: str) -> None:
    try:
        ai = _load_ai_provider()
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        state = {}
        if STATE_FILE.exists():
            state = json.loads(STATE_FILE.read_text())
        agents = [a for a in state.get("agents", []) if a.get("name") != "orchestrator"]
        agents.insert(0, {
            "name":       "orchestrator",
            "status":     status,
            "task":       task,
            "model":      ai.get("model") or _best_model(),
            "platform":   ai.get("provider", "ollama"),
            "updated_at": int(time.time()),
        })
        state["agents"] = agents
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception:
        pass


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    ai = _load_ai_provider()
    return {
        "status": "ok",
        "agent": "orchestrator",
        "provider": ai["provider"],
        "model": ai.get("model", ""),
        "ts": int(time.time()),
    }


# Max tool-call rounds to prevent infinite loops
MAX_TOOL_ROUNDS = 8

def _extract_tool_calls(text: str) -> list[dict]:
    """Extract tool_call blocks from LLM output. Handles multiple formats small models might use."""
    calls = []
    # Primary: ```tool_call\n{...}\n```
    # Also accept: ```json\n{...}\n``` and ```\n{...}\n``` if they contain "name" + "args"
    for pattern in [
        r"```tool_call\s*\n(.*?)\n```",
        r"```json\s*\n(\{[^`]*\"name\"[^`]*\"args\"[^`]*\})\s*\n```",
        r"```\s*\n(\{[^`]*\"name\"[^`]*\"args\"[^`]*\})\s*\n```",
    ]:
        for m in re.findall(pattern, text, re.DOTALL):
            try:
                obj = json.loads(m.strip())
                if "name" in obj and obj not in calls:
                    calls.append(obj)
            except json.JSONDecodeError:
                pass
        if calls:
            break  # Use the first pattern that matches
    return calls


def _get_stream_generator(ai_info: dict, model: str, messages: list):
    """Get the appropriate stream generator for the AI provider."""
    provider = ai_info["provider"]
    if provider == "ollama":
        return _stream_ollama(model, messages)
    elif provider in ("openai", "groq", "custom"):
        return _stream_openai_compatible(ai_info["api_url"], ai_info["api_key"], model, messages)
    elif provider == "anthropic":
        return _stream_anthropic(ai_info["api_key"], model, messages)
    elif provider == "bedrock":
        return _stream_bedrock(model, messages, ai_info.get("aws_region", "us-east-1"))
    return None


@app.post("/chat")
async def chat(request: Request):
    """
    Stream a conversation with the orchestrator.
    Body: { "messages": [{role, content}, ...], "model": "optional" }
    Returns: SSE stream with automatic tool execution.

    When the LLM outputs a ```tool_call block, the orchestrator:
    1. Executes the tool
    2. Feeds the result back into the conversation
    3. Calls the LLM again to continue
    This repeats until the LLM responds without tool calls (or max rounds).
    """
    body     = await request.json()
    messages = body.get("messages", [])
    model    = body.get("model") or _best_model()

    ctx     = _get_context()
    sys_msg = _build_system_prompt(ctx)

    # Build full message list with live system prompt
    full_messages = [{"role": "system", "content": sys_msg}] + messages

    last_user = next((m["content"] for m in reversed(messages)
                      if m["role"] == "user"), "...")
    _update_agent_state("running", last_user[:80])

    ai = _load_ai_provider()

    async def stream_gen():
        try:
            from connect.tools_config import execute_tool
        except ImportError:
            execute_tool = None

        conversation = list(full_messages)
        rounds = 0

        try:
            while rounds < MAX_TOOL_ROUNDS:
                rounds += 1

                # Stream LLM response in real-time while accumulating full text
                gen = _get_stream_generator(ai, model, conversation)
                if gen is None:
                    yield "data: " + json.dumps({"error": f"Unknown provider: {ai['provider']}"}) + "\n\n"
                    break

                full_text = ""
                async for chunk in gen:
                    yield chunk  # Stream to client in real-time
                    # Accumulate text for tool-call detection
                    if chunk.startswith("data: "):
                        raw = chunk[6:].strip()
                        try:
                            obj = json.loads(raw)
                            content = obj.get("message", {}).get("content", "")
                            if content:
                                full_text += content
                        except (json.JSONDecodeError, AttributeError):
                            pass

                # Check for tool calls in the completed response
                tool_calls = _extract_tool_calls(full_text) if execute_tool else []

                if not tool_calls:
                    break  # No tool calls — LLM is done

                # Add assistant message to conversation history
                conversation.append({"role": "assistant", "content": full_text})

                # Execute each tool call and collect results
                results_text = ""
                for tc in tool_calls:
                    tool_name = tc.get("name", "unknown")
                    tool_args = tc.get("args", {})
                    _update_agent_state("running", f"executing: {tool_name}")

                    # Notify client
                    yield "data: " + json.dumps({"message": {"content": f"\n\n⚙ Executing `{tool_name}`...\n"}}) + "\n\n"

                    try:
                        result = execute_tool(tool_name, tool_args)
                    except Exception as e:
                        result = {"error": str(e)}

                    result_json = json.dumps(result, indent=2, default=str)
                    if len(result_json) > 6000:
                        result_json = result_json[:6000] + "\n... (truncated)"

                    # Show result to client
                    yield "data: " + json.dumps({"message": {"content": f"```\n{result_json}\n```\n"}}) + "\n\n"

                    results_text += f"\nTool `{tool_name}` result:\n```json\n{result_json}\n```\n"

                # Feed results back so the LLM can continue
                conversation.append({
                    "role": "user",
                    "content": f"[Tool execution results — continue based on these. Use tool_call again if more actions needed, otherwise summarize what was done.]\n{results_text}",
                })

                _update_agent_state("running", f"continuing after {len(tool_calls)} tool(s)")

        except httpx.ConnectError:
            yield "data: " + json.dumps({"error": f"{ai['name']} not reachable"}) + "\n\n"
        except Exception as ex:
            log.exception("Chat stream error")
            yield "data: " + json.dumps({"error": str(ex)[:200]}) + "\n\n"
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


@app.get("/ai")
async def get_ai_config():
    """Return current AI provider info (no secrets)."""
    ai = _load_ai_provider()
    return {
        "provider": ai["provider"],
        "name": ai["name"],
        "model": ai["model"],
        "api_url": ai.get("api_url", ""),
    }


@app.post("/execute")
async def execute_tool_endpoint(request: Request):
    """Execute a tool call directly. Used by the dashboard or external clients."""
    body = await request.json()
    tool_name = body.get("name", "")
    tool_args = body.get("args", {})

    try:
        from connect.tools_config import execute_tool
        result = execute_tool(tool_name, tool_args)
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/tools")
async def list_tools():
    """List all available tools."""
    try:
        from connect.tools_config import get_all_tools
        return {"tools": get_all_tools()}
    except Exception:
        return {"tools": []}


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
                task = "alert: " + ", ".join(alerts) if alerts else (
                    f"CPU {ctx.get('cpu_pct',0):.0f}% | "
                    f"MEM {ctx.get('mem_pct',0):.0f}% | "
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
    ai = _load_ai_provider()
    log.info(f"CH8 Orchestrator starting on port {AGENT_PORT}  provider={ai['provider']}  model={ai.get('model','auto')}")
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT, log_level="warning")


if __name__ == "__main__":
    main()
