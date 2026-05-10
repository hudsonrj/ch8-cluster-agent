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

# ── Load env vars from ~/.config/ch8/env ─────────────────────────────────────

def _load_env_file():
    env_file = CONFIG_DIR / "env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip()
                if key and val:
                    os.environ.setdefault(key, val)

_load_env_file()


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
    peers_full = []
    try:
        state = json.loads(STATE_FILE.read_text())
        raw_peers = state.get("peers", [])
        for p in raw_peers:
            hostname = p.get("hostname", "?")
            address  = p.get("address", "?")
            node_id  = p.get("node_id", "")
            alias    = p.get("alias", "")
            models   = p.get("models", [])
            services = p.get("services", [])
            ai_model = p.get("ai_model", "")
            peers.append(f"{hostname} ({address})")
            peers_full.append({
                "hostname": hostname,
                "node_id":  node_id,
                "alias":    alias,
                "address":  address,
                "models":   models,
                "services": services,
                "ai_model": ai_model,
            })
    except Exception:
        pass
    ctx["peers"] = peers
    ctx["peers_full"] = peers_full

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

    # Build detailed peer section
    peers_full = ctx.get("peers_full", [])
    if peers_full:
        peer_lines = []
        for p in peers_full:
            name = p["alias"] or p["hostname"]
            ref  = p["alias"] or p["hostname"]
            parts = [f"  - {name}"]
            if p["address"]:
                parts.append(f"addr={p['address']}")
            if p["ai_model"]:
                parts.append(f"model={p['ai_model']}")
            if p["models"]:
                parts.append(f"ollama={','.join(p['models'][:3])}")
            if p["services"]:
                svc_names = [s.get("name", "?") if isinstance(s, dict) else str(s) for s in p["services"][:5]]
                parts.append(f"services={','.join(svc_names)}")
            peer_lines.append("  ".join(parts) + f"  → use node_chat(node=\"{ref}\", ...)")
        peers_section = "\n".join(peer_lines)
    else:
        peers_section = "  (no peers discovered yet)"

    return f"""You are CH8 agent for node {ctx['hostname']}. You execute tasks on this server and coordinate with other nodes.

IMPORTANT: You are an EXECUTOR, not an advisor. Never explain steps. Always DO it using tool_call.

## Tool format
```tool_call
{{"name": "tool_name", "args": {{"key": "value"}}}}
```

Local tools: shell_exec, file_write, file_read, docker_exec, service_restart, http_request, security_scan, node_info

## Delegation tool: node_chat
Use node_chat to send tasks to other nodes and get their responses.
```tool_call
{{"name": "node_chat", "args": {{"node": "rpi-sala", "message": "run df -h and return disk usage"}}}}
```
- You can call node_chat multiple times IN THE SAME response to parallelize tasks across nodes.
- Each remote node has its own AI agent — it will understand natural language tasks and execute them.
- After collecting all responses, synthesize the results into a final answer.

## Distributed execution strategy
- Delegate AI-heavy tasks to nodes with larger models when speed/quality matters.
- Delegate local commands (disk check, service restart, file ops) to the node where they make sense.
- Run independent subtasks in parallel using multiple node_chat calls in the same response.
- Aggregate results here and return a unified answer.

## Network nodes
{peers_section}

## Example — user says "check disk usage on all nodes"
```tool_call
{{"name": "shell_exec", "args": {{"command": "df -h /"}}}}
```
```tool_call
{{"name": "node_chat", "args": {{"node": "rpi-sala", "message": "run df -h / and return disk usage"}}}}
```
```tool_call
{{"name": "node_chat", "args": {{"node": "manager2", "message": "run df -h / and return disk usage"}}}}
```
(All three tool calls in the same response — executed in parallel. Then summarize.)

## This node info
Host: {ctx['hostname']} | OS: {ctx['os']} | CPU: {ctx['cpu_pct']}% | RAM: {ctx['mem_pct']}% | Disk: {ctx['disk_pct']}%
AI: {ctx.get('ai_provider','?')} / {ctx.get('ai_model','?')} | Local models: {models_txt}
Containers: {len(ctx.get('containers', []))} | Time: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}

Active containers:
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


def _normalize_bedrock_model(model: str) -> str:
    """Map short/invalid model IDs to valid Bedrock model ARN-style IDs."""
    _MAP = {
        "anthropic.claude-sonnet-4-6-v1": "us.anthropic.claude-sonnet-4-20250514-v1:0",
        "claude-sonnet-4-6": "us.anthropic.claude-sonnet-4-20250514-v1:0",
        "claude-sonnet-4": "us.anthropic.claude-sonnet-4-20250514-v1:0",
        "claude-haiku-4-5": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        "anthropic.claude-haiku-4-5-v1": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    }
    return _MAP.get(model, model)


async def _stream_bedrock(model: str, messages: list, region: str):
    """Stream from AWS Bedrock using httpx with bearer token or boto3 fallback."""
    model = _normalize_bedrock_model(model)
    # Separate system message
    system_text = ""
    chat_msgs = []
    for m in messages:
        if m["role"] == "system":
            system_text += m["content"] + "\n"
        else:
            chat_msgs.append(m)

    body = {
        "messages": chat_msgs,
        "max_tokens": 4096,
        "anthropic_version": "bedrock-2023-05-31",
    }
    if system_text:
        body["system"] = system_text.strip()

    # Prefer bearer token auth via httpx (no boto3 needed)
    bearer_token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "")
    if bearer_token:
        async for chunk in _stream_bedrock_httpx(model, body, region, bearer_token):
            yield chunk
    else:
        async for chunk in _stream_bedrock_boto3(model, body, region):
            yield chunk


async def _stream_bedrock_httpx(model: str, body: dict, region: str, bearer_token: str):
    """Stream from Bedrock using httpx + bearer token auth."""
    import struct
    from base64 import b64decode
    from urllib.parse import quote as urlquote

    encoded_model = urlquote(model, safe="")
    url = f"https://bedrock-runtime.{region}.amazonaws.com/model/{encoded_model}/invoke-with-response-stream"
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream("POST", url, json=body, headers=headers) as resp:
                if resp.status_code != 200:
                    err_body = await resp.aread()
                    yield "data: " + json.dumps({"error": f"Bedrock {resp.status_code}: {err_body.decode()[:300]}"}) + "\n\n"
                    return

                # Parse AWS event stream binary frames
                buffer = b""
                async for raw_chunk in resp.aiter_bytes():
                    buffer += raw_chunk
                    while len(buffer) >= 12:
                        total_len = struct.unpack("!I", buffer[:4])[0]
                        if len(buffer) < total_len:
                            break
                        frame = buffer[:total_len]
                        buffer = buffer[total_len:]

                        # Frame: [total_len:4][header_len:4][prelude_crc:4][headers:N][payload:M][msg_crc:4]
                        header_len = struct.unpack("!I", frame[4:8])[0]
                        payload_start = 12 + header_len
                        payload_end = total_len - 4
                        if payload_start >= payload_end:
                            continue

                        payload = frame[payload_start:payload_end]
                        try:
                            event = json.loads(payload)
                            # Bedrock wraps content in {"bytes": "base64..."}
                            if "bytes" in event:
                                inner = json.loads(b64decode(event["bytes"]).decode())
                            else:
                                inner = event

                            if inner.get("type") == "content_block_delta":
                                text = inner.get("delta", {}).get("text", "")
                                if text:
                                    yield "data: " + json.dumps({"message": {"content": text}}) + "\n\n"
                        except (json.JSONDecodeError, Exception):
                            pass
    except Exception as ex:
        yield "data: " + json.dumps({"error": f"Bedrock error: {str(ex)[:200]}"}) + "\n\n"


async def _stream_bedrock_boto3(model: str, body: dict, region: str):
    """Stream from Bedrock using boto3 (standard AWS credentials)."""
    try:
        import boto3
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet",
                               "--break-system-packages", "boto3"])
        import boto3

    try:
        client = boto3.client("bedrock-runtime", region_name=region)
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
        yield "data: " + json.dumps({"error": f"Bedrock boto3 error: {str(ex)[:200]}"}) + "\n\n"


# ── agent state ───────────────────────────────────────────────────────────────

try:
    import fcntl as _fcntl
    def _flock(f):   _fcntl.flock(f, _fcntl.LOCK_EX)
    def _funlock(f): _fcntl.flock(f, _fcntl.LOCK_UN)
except ImportError:
    def _flock(f):   pass   # Windows
    def _funlock(f): pass

def _atomic_update_state(updater_fn) -> None:
    """Atomically read-modify-write state.json with file locking."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        lock_file = CONFIG_DIR / "state.lock"
        with open(lock_file, "w") as lf:
            _flock(lf)
            try:
                state = {}
                if STATE_FILE.exists():
                    state = json.loads(STATE_FILE.read_text())
                updater_fn(state)
                STATE_FILE.write_text(json.dumps(state, indent=2))
            finally:
                _funlock(lf)
    except Exception:
        pass


def _update_agent_state(status: str, task: str) -> None:
    ai = _load_ai_provider()

    def _update(state):
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

    _atomic_update_state(_update)


def _refresh_sub_agents() -> None:
    """Touch updated_at on all sub-agents created by orchestrator so they don't expire."""
    def _update(state):
        now = int(time.time())
        for a in state.get("agents", []):
            if a.get("created_by") == "orchestrator":
                a["updated_at"] = now
    _atomic_update_state(_update)


def _register_sub_agent(name: str, status: str, task: str, script_path: str = "") -> None:
    """Register a sub-agent (created by orchestrator) in state.json."""
    def _update(state):
        agents = state.get("agents", [])
        agents = [a for a in agents if a.get("name") != name]
        agents.append({
            "name":        name,
            "status":      status,
            "task":        task,
            "model":       "script",
            "platform":    "cron" if "cron" in task.lower() else "local",
            "script":      script_path,
            "created_by":  "orchestrator",
            "updated_at":  int(time.time()),
        })
        state["agents"] = agents
    _atomic_update_state(_update)


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

def _fix_json(raw: str) -> str:
    """Try to fix common small-model JSON errors."""
    s = raw.strip()
    # Remove trailing ) that some models add: {...}) → {...}
    if s.endswith('})') and s.count('(') < s.count(')'):
        s = s[:-1]
    if s.endswith('}})') and s.count('(') < s.count(')'):
        s = s[:-1]
    # Fix unescaped single quotes inside strings by attempting parse
    return s


def _try_parse_tool_json(raw: str) -> dict | None:
    """Attempt to parse tool call JSON with progressive fixing."""
    for attempt in [raw, _fix_json(raw)]:
        try:
            obj = json.loads(attempt)
            if isinstance(obj, dict) and "name" in obj:
                return obj
        except json.JSONDecodeError:
            pass

    # Last resort: extract name and args with regex
    name_m = re.search(r'"name"\s*:\s*"(\w+)"', raw)
    if not name_m:
        return None
    name = name_m.group(1)

    # Try to extract args object
    args_m = re.search(r'"args"\s*:\s*(\{.*)', raw, re.DOTALL)
    if args_m:
        args_raw = args_m.group(1)
        # Find the matching closing brace
        depth = 0
        for i, c in enumerate(args_raw):
            if c == '{': depth += 1
            elif c == '}': depth -= 1
            if depth == 0:
                try:
                    args = json.loads(args_raw[:i+1])
                    return {"name": name, "args": args}
                except json.JSONDecodeError:
                    break

    # Minimal fallback: just the name with empty args
    return {"name": name, "args": {}}


def _extract_tool_calls(text: str) -> list[dict]:
    """Extract tool_call blocks from LLM output. Handles multiple formats and broken JSON."""
    calls = []

    # Try explicit tool_call blocks first, then json blocks with name+args
    for pattern in [
        r"```tool_call\s*\n(.*?)\n```",
        r"```json\s*\n(\{[^`]*?\"name\"[^`]*?\})\s*\n```",
        r"```\s*\n(\{[^`]*?\"name\"[^`]*?\})\s*\n```",
    ]:
        for m in re.findall(pattern, text, re.DOTALL):
            obj = _try_parse_tool_json(m.strip())
            if obj and obj not in calls:
                calls.append(obj)
        if calls:
            return calls

    return calls


def _extract_fallback_actions(text: str) -> list[dict]:
    """
    Fallback: if the LLM didn't use tool_call but wrote code blocks with commands
    or file contents, convert them to tool calls automatically.
    This catches the 'tutorial mode' where the LLM explains instead of executing.
    """
    actions = []

    # Detect python code blocks that look like full scripts
    for pattern in [r"```python\s*\n(.*?)\n```", r"```py\s*\n(.*?)\n```"]:
        for code in re.findall(pattern, text, re.DOTALL):
            code = code.strip()
            if len(code) > 30 and ("\ndef " in code or "\nclass " in code or "import " in code or "print(" in code):
                # This looks like a script the LLM wanted to create
                # Try to find a filename hint in the surrounding text
                fname_match = re.search(r'(?:salve|save|arquivo|file|create|crie)[^`]*?[`\s]([/\w._-]+\.py)', text, re.IGNORECASE)
                fname = fname_match.group(1) if fname_match else "/opt/ch8/agent_script.py"
                if not fname.startswith("/"):
                    fname = f"/opt/ch8/{fname}"
                actions.append({"name": "file_write", "args": {"path": fname, "content": code}})

    # Detect bash/shell code blocks
    for pattern in [r"```(?:bash|sh|shell)\s*\n(.*?)\n```"]:
        for code in re.findall(pattern, text, re.DOTALL):
            code = code.strip()
            if code and len(code) > 5:
                actions.append({"name": "shell_exec", "args": {"command": code}})

    # Detect crontab lines
    cron_match = re.findall(r'((?:\d+|\*)[/\d*,\-]* (?:\d+|\*)[/\d*,\-]* (?:\d+|\*)[/\d*,\-]* (?:\d+|\*)[/\d*,\-]* (?:\d+|\*)[/\d*,\-]* .+)', text)
    for cron_line in cron_match:
        if cron_line.strip():
            actions.append({"name": "shell_exec", "args": {"command": f"(crontab -l 2>/dev/null; echo '{cron_line.strip()}') | crontab -"}})

    return actions


# ── Smart task execution (compensates for small models) ─────────────────────

def _detect_and_execute_task(user_msg: str) -> list[dict] | None:
    """
    Detect common actionable requests and execute them directly.
    Returns list of {action, result} dicts, or None if not a known pattern.
    This compensates for small LLMs that can't reliably produce tool_call JSON.
    """
    from connect.tools_config import execute_tool
    msg = user_msg.lower().strip()
    results = []

    # Pattern: create agent/script that shows daily quote/message
    agent_match = re.search(
        r'(?:cri[ea]r?|make|create|faz(?:er)?)\s+(?:um\s+)?(?:agente?|script|programa?)\s+'
        r'(?:chamado\s+|named?\s+)?["\']?(\w+)["\']?',
        msg, re.IGNORECASE
    )
    daily_match = re.search(r'(?:frase|quote|mensagem|message).*(?:dia|daily|todo dia|every day)', msg, re.IGNORECASE)
    jesus_match = re.search(r'(?:jesus|cristo|bibl|evangel)', msg, re.IGNORECASE)

    if agent_match and daily_match:
        agent_name = agent_match.group(1).lower()
        agent_dir = f"/opt/ch8/agents/{agent_name}"

        # Determine content theme
        if jesus_match:
            quotes_content = '''#!/usr/bin/env python3
"""CH8 Agent: {name} — daily quote"""
import random, datetime

QUOTES = [
    "Eu sou o caminho, a verdade e a vida. (Joao 14:6)",
    "Amaras o teu proximo como a ti mesmo. (Mateus 22:39)",
    "Bem-aventurados os pacificadores, porque serao chamados filhos de Deus. (Mateus 5:9)",
    "Amai-vos uns aos outros, assim como eu vos amei. (Joao 13:34)",
    "Nao andeis ansiosos por coisa alguma. (Filipenses 4:6)",
    "Porque Deus amou o mundo de tal maneira que deu o seu Filho unigenito. (Joao 3:16)",
    "Vinde a mim, todos os que estais cansados e oprimidos, e eu vos aliviarei. (Mateus 11:28)",
    "A verdade vos libertara. (Joao 8:32)",
    "Tudo posso naquele que me fortalece. (Filipenses 4:13)",
    "O Senhor e o meu pastor, nada me faltara. (Salmos 23:1)",
    "Buscai primeiro o Reino de Deus e a sua justica. (Mateus 6:33)",
    "Pedi e dar-se-vos-a; buscai e encontrareis. (Mateus 7:7)",
    "Eu estou convosco todos os dias, ate o fim dos tempos. (Mateus 28:20)",
    "A paz vos deixo, a minha paz vos dou. (Joao 14:27)",
    "Sede misericordiosos, como tambem vosso Pai e misericordioso. (Lucas 6:36)",
    "Se alguem quer vir apos mim, negue-se a si mesmo. (Mateus 16:24)",
    "Onde estiver o vosso tesouro, ai estara tambem o vosso coracao. (Mateus 6:21)",
    "Deixai vir a mim as criancinhas. (Marcos 10:14)",
    "Em tudo dai gracas. (1 Tessalonicenses 5:18)",
    "Quem crer e for batizado sera salvo. (Marcos 16:16)",
    "Nem so de pao vivera o homem. (Mateus 4:4)",
    "Perdoai e sereis perdoados. (Lucas 6:37)",
    "Eu vim para que tenham vida, e a tenham com abundancia. (Joao 10:10)",
    "Nao julgueis, para que nao sejais julgados. (Mateus 7:1)",
    "O maior entre vos sera vosso servo. (Mateus 23:11)",
    "Se Deus e por nos, quem sera contra nos? (Romanos 8:31)",
    "Dai a Cesar o que e de Cesar, e a Deus o que e de Deus. (Mateus 22:21)",
    "Eu sou a luz do mundo. (Joao 8:12)",
    "Ama o teu inimigo e ora pelos que te perseguem. (Mateus 5:44)",
    "Eis que faco novas todas as coisas. (Apocalipse 21:5)",
]

today = datetime.date.today()
idx = today.toordinal() % len(QUOTES)
quote = QUOTES[idx]
print(f"\\n  Paz — Frase do dia ({today.strftime('%d/%m/%Y')}):")
print(f"  {quote}\\n")
'''.format(name=agent_name)
        else:
            quotes_content = '''#!/usr/bin/env python3
"""CH8 Agent: {name} — daily message"""
import random, datetime
MESSAGES = ["Have a great day!", "Stay positive!", "Keep going!"]
today = datetime.date.today()
idx = today.toordinal() % len(MESSAGES)
print(f"  {name} — {{today.strftime('%d/%m/%Y')}}: {{MESSAGES[idx]}}")
'''.format(name=agent_name)

        # Step 1: Create directory
        r1 = execute_tool("shell_exec", {"command": f"mkdir -p {agent_dir}"})
        results.append({"tool": "shell_exec", "action": f"mkdir -p {agent_dir}", "result": r1})

        # Step 2: Write script
        script_path = f"{agent_dir}/{agent_name}.py"
        r2 = execute_tool("file_write", {"path": script_path, "content": quotes_content})
        results.append({"tool": "file_write", "action": f"Created {script_path}", "result": r2})

        # Step 3: Make executable
        r3 = execute_tool("shell_exec", {"command": f"chmod +x {script_path}"})
        results.append({"tool": "shell_exec", "action": f"chmod +x {script_path}", "result": r3})

        # Step 4: Test it
        r4 = execute_tool("shell_exec", {"command": f"python3 {script_path}"})
        results.append({"tool": "shell_exec", "action": f"Test run: python3 {script_path}", "result": r4})

        # Step 5: Set up daily cron at 8:00 AM
        cron_cmd = f"0 8 * * * python3 {script_path} >> /var/log/ch8-{agent_name}.log 2>&1"
        r5 = execute_tool("shell_exec", {
            "command": f"(crontab -l 2>/dev/null | grep -v '{agent_name}.py'; echo '{cron_cmd}') | crontab -"
        })
        results.append({"tool": "shell_exec", "action": f"Cron scheduled: daily at 08:00", "result": r5})

        # Step 6: Register as a sub-agent in the dashboard
        _register_sub_agent(
            name=agent_name,
            status="idle",
            task="daily quote — cron 08:00",
            script_path=script_path,
        )
        results.append({"tool": "register", "action": f"Agent '{agent_name}' registered in dashboard", "result": {"ok": True}})

        return results

    return None


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
    # Also accept simple {"message": "..."} format (used by node_chat)
    if not messages and body.get("message"):
        messages = [{"role": "user", "content": body["message"]}]
    stream   = body.get("stream", True)
    _m = body.get("model", "")
    model = _m if _m and _m != "auto" else _best_model()

    # Intercept: if user asks to create an agent, handle it directly
    user_msg = (messages[-1].get("content", "") if messages else "").lower()
    create_keywords = ["crie um agente", "criar agente", "create agent", "cria um agente", "novo agente", "new agent"]
    if any(kw in user_msg for kw in create_keywords):
        # Extract name and description from the message
        from connect.ai_config import get_ai_client
        ai = get_ai_client()
        extract = ai.chat([{"role": "user", "content": f'Extraia o nome e descrição do agente. Retorne SOMENTE JSON: {{"name":"nome-do-agente","description":"o que ele faz"}}\n\nSolicitação: {messages[-1]["content"]}'}], max_tokens=200, temperature=0.1)
        try:
            import json as _j
            if "```" in extract: extract = extract.split("```")[1].split("```")[0]
            if extract.strip().startswith("json"): extract = extract.strip()[4:]
            info = _j.loads(extract.strip())
            # Call create-agent internally
            # Use internal function directly instead
            import subprocess, time as _t2
            safe_name = info["name"].lower().replace(" ", "_").replace("-", "_")
            safe_name = ''.join(c for c in safe_name if c.isalnum() or c == '_')
            desc = info.get("description", messages[-1]["content"])

            # Generate and create
            prompt = f"""Crie um script Python de agente para o cluster CH8.
Nome do agente: {safe_name}
Descrição: {desc}
Requisitos:
- Loop main() com signal handling (SIGTERM para parar graciosamente)
- PID salvo em ~/.config/ch8/{safe_name}.pid
- Registrar estado via: from connect.state import update_agent_state
  Chamar update_agent_state("{safe_name}", status, task_description) a cada 30s
- Logging em ~/.config/ch8/{safe_name}.log
- sys.path.insert(0, str(Path(__file__).parent.parent))
- Máximo 120 linhas, funcional, sem placeholders
- Todos os textos/logs em português do Brasil
Retorne SOMENTE código Python, sem markdown, sem explicação."""

            code = ai.chat([{"role": "user", "content": prompt}], max_tokens=2000, temperature=0.2)
            if "```python" in code: code = code.split("```python")[1].split("```")[0]
            elif "```" in code: code = code.split("```")[1].split("```")[0]
            code = code.strip()

            if code and len(code) > 50 and "def main" in code:
                agents_dir = Path(__file__).parent
                agent_file = agents_dir / f"{safe_name}.py"
                agent_file.write_text(code + "\n")

                install_dir = str(Path(__file__).parent.parent)
                env = {**os.environ, "PYTHONPATH": install_dir}
                log_f = Path.home() / ".config" / "ch8" / f"{safe_name}.log"
                pid_f = Path.home() / ".config" / "ch8" / f"{safe_name}.pid"
                proc = subprocess.Popen([sys.executable, str(agent_file)], cwd=install_dir, env=env,
                    stdout=open(log_f, "w"), stderr=subprocess.STDOUT, start_new_session=True)
                pid_f.write_text(str(proc.pid))

                # Wait and verify agent is still alive
                _t2.sleep(2)
                if proc.poll() is not None:
                    # Agent died — read log for error
                    err_log = log_f.read_text()[-300:] if log_f.exists() else "no log"
                    async def _stream_error():
                        yield f'data: {{"message": {{"content": "\\n\\n❌ Agent `{safe_name}` crashed on start:\\n```\\n{err_log}\\n```"}}}}\n\n'
                        yield "data: [DONE]\n\n"
                    return StreamingResponse(_stream_error(), media_type="text/event-stream")

                # Register in state
                _t2.sleep(0)
                state_file = Path.home() / ".config" / "ch8" / "state.json"
                try:
                    state = _j.loads(state_file.read_text()) if state_file.exists() else {}
                    al = state.get("agents", [])
                    al = [a for a in al if a.get("name") != safe_name]
                    al.append({"name": safe_name, "status": "running", "task": desc[:60], "model": "custom",
                        "platform": "custom", "autonomous": True, "updated_at": int(_t2.time()),
                        "tools": [], "details": {"description": desc}, "alerts": 0,
                        "security_findings": 0, "predictions": 0, "heavy_procs": 0})
                    state["agents"] = al
                    state_file.write_text(_j.dumps(state, indent=2))
                except Exception:
                    pass

                # Return as SSE response
                async def _stream_created():
                    msg = f"✅ Agente **{safe_name}** criado e iniciado (PID {proc.pid})!\n\n📋 Arquivo: `agents/{safe_name}.py`\n🔧 Descrição: {desc}\n\nO agente já está rodando e aparece no dashboard."
                    yield f"data: {_j.dumps({'message': {'content': msg}})}\n\n"
                    yield "data: [DONE]\n\n"
                return StreamingResponse(_stream_created(), media_type="text/event-stream")
            else:
                pass  # Fall through to normal chat if code generation failed
        except Exception:
            pass  # Fall through to normal chat

    loop = _asyncio.get_event_loop()
    ctx     = await loop.run_in_executor(None, _get_context)
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

        # Smart task detection — execute directly if pattern matches
        last_user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        try:
            task_results = _detect_and_execute_task(last_user_msg) if execute_tool else None
        except Exception as ex:
            log.warning(f"Smart task detection failed: {ex}")
            task_results = None

        if task_results:
            # Show execution results to client
            summary_lines = []
            for tr in task_results:
                tool_name = tr["tool"]
                action = tr["action"]
                result = tr["result"]

                yield "data: " + json.dumps({"message": {"content": f"\n⚙ {action}\n"}}) + "\n\n"

                # Show output if there is any
                stdout = result.get("stdout", "").strip() if isinstance(result, dict) else ""
                if stdout:
                    yield "data: " + json.dumps({"message": {"content": f"```\n{stdout[:2000]}\n```\n"}}) + "\n\n"

                ok = result.get("ok") or result.get("exit_code", 1) == 0
                summary_lines.append(f"{'✓' if ok else '✗'} {action}")

            # Feed results into conversation so LLM can summarize
            results_text = "\n".join(summary_lines)
            conversation.append({
                "role": "assistant",
                "content": f"I executed the following actions:\n{results_text}"
            })
            conversation.append({
                "role": "user",
                "content": "Summarize what was done in 2-3 sentences. Be direct. Say what was created and where."
            })

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

                # Fallback: if LLM wrote code/commands but didn't use tool_call,
                # auto-convert to tool calls (catches "tutorial mode")
                if not tool_calls and execute_tool and rounds == 1:
                    fallback = _extract_fallback_actions(full_text)
                    if fallback:
                        tool_calls = fallback
                        yield "data: " + json.dumps({"message": {"content": "\n\n---\n*Auto-executing detected code...*\n"}}) + "\n\n"

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

                    # Auto-register agent if file_write created an agent script
                    if tool_name == "file_write" and result.get("ok"):
                        fpath = tool_args.get("path", "")
                        if "/ch8/" in fpath and fpath.endswith(".py"):
                            aname = Path(fpath).stem.replace("_agent", "").replace("agent_", "")
                            _register_sub_agent(aname, "idle", f"script: {fpath}", fpath)

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
            # Persist chat to PostgreSQL (best effort)
            try:
                from connect.db import save_chat_message
                from connect.auth import get_node_id
                _nid = get_node_id()
                user_content = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
                if user_content:
                    save_chat_message(_nid, "user", user_content, model=model)
                if full_text:
                    save_chat_message(_nid, "assistant", full_text[:5000], model=model)
            except Exception:
                pass
        yield "data: [DONE]\n\n"

    # Non-streaming mode: collect full text and return JSON
    # Used by node_chat (node-to-node calls) — stream=False in request body
    if stream is False:
        collected = []
        async for chunk in stream_gen():
            if chunk.startswith("data: ") and "[DONE]" not in chunk:
                raw = chunk[6:].strip()
                try:
                    obj = json.loads(raw)
                    content = obj.get("message", {}).get("content", "")
                    if content:
                        collected.append(content)
                except Exception:
                    pass
        return JSONResponse({
            "response": "".join(collected),
            "node": socket.gethostname(),
        })

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


@app.post("/cluster/task")
async def cluster_task_endpoint(request: Request):
    """Receive a cluster task from the dashboard and distribute it."""
    try:
        body = await request.json()

        # Handle HA sync (from master)
        if "ha_sync" in body:
            try:
                from connect.cluster_ha import _sync_state, load_ha_state, save_ha_state
                _sync_state.from_dict(body["ha_sync"])
                state = load_ha_state()
                state["last_master_seen"] = int(__import__("time").time())
                save_ha_state(state)
            except Exception:
                pass
            return {"ok": True}

        task     = body.get("task", "")
        strategy = body.get("strategy", "auto")
        nodes    = body.get("nodes", [])

        if not task:
            return {"error": "Missing 'task'"}

        from connect.cluster_orchestrator import run_cluster_task_async
        steps = []
        def _cb(step, msg):
            steps.append(f"[{step}] {msg}")

        result = await run_cluster_task_async(
            task, strategy=strategy,
            target_nodes=nodes if nodes else None,
            progress_cb=_cb
        )

        return {
            "result":       result["result"],
            "plan":         result["plan"],
            "results":      result["results"],
            "nodes_used":   result["nodes_used"],
            "nodes_failed": result["nodes_failed"],
            "elapsed":      f"{result['elapsed']:.1f}s",
            "subtasks":     len(result["plan"].get("subtasks", [])),
            "reasoning":    result["plan"].get("reasoning", ""),
            "progress":     steps,
        }
    except Exception as e:
        import logging
        logging.getLogger("ch8.orchestrator").error(f"cluster_task error: {e}", exc_info=True)
        return {"error": str(e)}


@app.post("/ha/sync")
async def ha_sync_endpoint(request: Request):
    """Receive HA state sync from master."""
    try:
        body = await request.json()
        from connect.cluster_ha import _sync_state, load_ha_state, save_ha_state
        state_dict = body.get("ha_sync", body)
        _sync_state.from_dict(state_dict)
        s = load_ha_state()
        s["last_master_seen"] = int(__import__("time").time())
        s["master_seq"] = _sync_state.seq
        save_ha_state(s)
        return {"ok": True, "seq": _sync_state.seq}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/ha/new_master")
async def ha_new_master_endpoint(request: Request):
    """Receive notification that a new master was elected."""
    try:
        body  = await request.json()
        info  = body.get("ha_new_master", body)
        from connect.cluster_ha import load_ha_state, save_ha_state
        state = load_ha_state()
        state["master_id"]       = info.get("master_id")
        state["master_hostname"] = info.get("master_hostname")
        state["standbys"]        = info.get("standbys", [])
        state["elected_at"]      = info.get("elected_at", 0)
        from connect.auth import get_node_id
        my_id = get_node_id()
        standby_ids = [s.get("node_id") for s in state["standbys"]]
        if state["master_id"] == my_id:
            state["role"] = "master"
        elif my_id in standby_ids:
            state["role"] = "standby"
        else:
            state["role"] = "worker"
        save_ha_state(state)
        return {"ok": True, "role": state["role"]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/cluster/update")
async def cluster_update_endpoint(request: Request):
    """Push update to all nodes in the cluster. Body: {"ref":"main","nodes":[]} (optional)"""
    try:
        body = await request.json()
    except Exception:
        body = {}
    ref = body.get("ref", "main")
    target = body.get("nodes", None)

    from connect.cluster_orchestrator import get_catalog, _push_update_to_node_async
    import asyncio as _aio2
    catalog = get_catalog()
    if target:
        catalog = [n for n in catalog if n.get("node_id") in target or n.get("hostname") in target]
    nodes = [n for n in catalog if n.get("status") == "online"]
    repo = "https://github.com/hudsonrj/ch8-cluster-agent.git"
    tasks = [_push_update_to_node_async(n, ref, repo) for n in nodes]
    results = await _aio2.gather(*tasks, return_exceptions=True)
    out = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            out.append({"hostname": nodes[i].get("hostname", "?"), "ok": False, "error": str(r)})
        else:
            out.append(r)
    ok = [r for r in out if r.get("ok")]
    return {"results": out, "updated": len(ok), "failed": len(out) - len(ok), "total": len(out)}


@app.post("/update")
async def node_update_endpoint(request: Request):
    """
    Receive a self-update command from the master node.
    Pulls the latest code from git and restarts the daemon.
    Body: {"ref": "main", "repo": "https://..."} (both optional)
    """
    import subprocess, os, sys, threading
    try:
        body = await request.json()
    except Exception:
        body = {}

    ref  = body.get("ref", "main")
    repo = body.get("repo", "")

    # Find the repo root (two levels up from this file)
    repo_dir = str(Path(__file__).parent.parent.resolve())

    def _do_update():
        import time as _time
        _log = logging.getLogger("ch8.update")
        ch8_bin = str(Path(repo_dir) / "ch8")
        try:
            # 1. Set remote if provided
            if repo:
                subprocess.run(["git", "-C", repo_dir, "remote", "set-url", "origin", repo],
                               capture_output=True)
            # 2. Pull latest (try requested ref, fall back to master)
            r = subprocess.run(["git", "-C", repo_dir, "pull", "origin", ref],
                               capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                r = subprocess.run(["git", "-C", repo_dir, "pull", "--rebase", "origin", "master"],
                                   capture_output=True, text=True, timeout=60)
            _log.info(f"git pull {ref}: {(r.stdout or r.stderr or '').strip()[:120]}")
            # 3. Install updated deps
            pip_r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q", "--break-system-packages",
                 "-r", f"{repo_dir}/requirements.txt"],
                capture_output=True, text=True, timeout=120
            )
            if pip_r.returncode != 0:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-q",
                     "-r", f"{repo_dir}/requirements.txt"],
                    capture_output=True, timeout=120
                )
            # 4. Zero-downtime restart:
            #    - Keep current orchestrator alive
            #    - Start new daemon from updated code
            #    - Wait for new one to be healthy
            #    - Then kill the old one
            restart_script = f'''
import time, subprocess, sys, os, signal

python = r"{sys.executable}"
ch8 = r"{ch8_bin}"
cwd = r"{repo_dir}"
log = open(os.path.join(cwd, "update.log"), "a")

log.write(f"[UPDATE] Starting zero-downtime restart at {{time.strftime('%H:%M:%S')}}\\n")
log.flush()

# Get current orchestrator PID (we'll kill it after new one starts)
old_orch_pid = None
pid_file = os.path.expanduser("~/.config/ch8/orchestrator.pid")
if os.path.exists(pid_file):
    try:
        old_orch_pid = int(open(pid_file).read().strip())
    except:
        pass

# Stop non-orchestrator agents (they'll restart with ch8 up)
for pf in os.listdir(os.path.expanduser("~/.config/ch8/")):
    if pf.endswith(".pid") and pf != "orchestrator.pid" and pf != "daemon.pid":
        try:
            pid = int(open(os.path.join(os.path.expanduser("~/.config/ch8"), pf)).read().strip())
            os.kill(pid, signal.SIGTERM)
        except:
            pass

time.sleep(1)

# Kill old orchestrator
if old_orch_pid:
    try:
        os.kill(old_orch_pid, signal.SIGTERM)
        time.sleep(2)
        os.kill(old_orch_pid, signal.SIGKILL)
    except:
        pass

time.sleep(1)

# Full restart: ch8 down (kills daemon + all agents) then ch8 up (fresh start)
log.write(f"[UPDATE] Running ch8 down + ch8 up\\n")
log.flush()
subprocess.run([python, ch8, "down"], cwd=cwd, stdout=log, stderr=log)
time.sleep(2)
subprocess.run([python, ch8, "up"], cwd=cwd, stdout=log, stderr=log)

# Verify health
time.sleep(5)
try:
    import urllib.request
    r = urllib.request.urlopen("http://127.0.0.1:7879/health", timeout=5)
    log.write(f"[UPDATE] New orchestrator healthy: {{r.read().decode()[:80]}}\\n")
except Exception as e:
    log.write(f"[UPDATE] Health check failed: {{e}}\\n")

log.write(f"[UPDATE] Done at {{time.strftime('%H:%M:%S')}}\\n")
log.close()
'''
            # Write restart script to temp file and execute detached
            restart_file = Path(repo_dir) / "_restart.py"
            restart_file.write_text(restart_script)

            if sys.platform == "win32":
                # Windows: use CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS
                CREATE_NEW_PROCESS_GROUP = 0x00000200
                DETACHED_PROCESS = 0x00000008
                subprocess.Popen(
                    [sys.executable, str(restart_file)],
                    cwd=repo_dir,
                    creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
                    close_fds=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                # Unix: start_new_session + double fork via nohup
                subprocess.Popen(
                    [sys.executable, str(restart_file)],
                    cwd=repo_dir,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )

            _log.info("Update complete — restart script launched")
        except Exception as e:
            _log.error(f"Update failed: {e}")

    # Run in background so we can return 200 immediately
    threading.Thread(target=_do_update, daemon=True).start()

    git_hash = ""
    try:
        git_hash = subprocess.check_output(
            ["git", "-C", repo_dir, "rev-parse", "--short", "HEAD"],
            timeout=5
        ).decode().strip()
    except Exception:
        pass

    return {"ok": True, "ref": ref, "current_commit": git_hash, "message": "Update started"}


@app.post("/relay/forward")
async def relay_forward(request: Request):
    """Forward a request to another node (peer relay). Tries all known addresses for target."""
    import httpx as _hx
    body = await request.json()
    target_node_id = body.get("target_node_id")
    payload = body.get("payload", {})
    if not target_node_id:
        return {"error": "target_node_id required"}

    orch_port = int(os.environ.get("CH8_AGENT_PORT", "7879"))

    # Get all known nodes from control server
    try:
        from connect.auth import get_access_token, CONTROL_URL
        token = get_access_token()
        hdrs = {"Authorization": f"Bearer {token}"} if token else {}
        async with _hx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{CONTROL_URL}/nodes?network_id=net_default", headers=hdrs)
            nodes = r.json() if r.status_code == 200 else []
    except Exception:
        nodes = []
        hdrs = {}

    target = next((n for n in nodes if n.get("node_id") == target_node_id), None)
    if not target:
        return {"error": f"Target {target_node_id} not found"}

    # Build list of ALL possible addresses for the target
    addresses_to_try = set()
    target_addr = target.get("address", "")
    if target_addr:
        addresses_to_try.add(target_addr)

    # Check if target has Tailscale IP (100.x) we might know
    # Also try local subnet variations
    import subprocess as _sp2
    try:
        # Get our local IPs to understand what subnets we're on
        local_ips = _sp2.check_output(["hostname", "-I"], timeout=3, text=True).strip().split()
        for lip in local_ips:
            # If target is on same /24 as one of our IPs, we can probably reach it
            if lip.rsplit(".", 1)[0] == target_addr.rsplit(".", 1)[0]:
                addresses_to_try.add(target_addr)
    except Exception:
        pass

    # Also try pinging via tailscale to discover DERP relay path
    try:
        ts_ip = _sp2.check_output(["tailscale", "ip", "-4", target.get("hostname", "")],
                                   timeout=5, text=True, stderr=_sp2.DEVNULL).strip()
        if ts_ip:
            addresses_to_try.add(ts_ip)
    except Exception:
        pass

    # Try each address
    errors = []
    for addr in addresses_to_try:
        url = f"http://{addr}:{orch_port}/chat"
        try:
            async with _hx.AsyncClient(timeout=30) as c:
                r = await c.post(url, json=payload, headers=hdrs)
                if r.status_code == 200:
                    data = r.json()
                    result = data.get("response", data.get("result", ""))
                    if result:
                        return {"result": result, "via": os.uname().nodename, "addr_used": addr}
        except Exception as e:
            errors.append(f"{addr}: {type(e).__name__}")

    return {"error": f"Cannot reach {target.get('hostname',target_node_id)} from {os.uname().nodename}: tried {list(addresses_to_try)}"}


@app.get("/version")
async def node_version():
    """Return current version and git commit of this node."""
    import subprocess
    repo_dir = str(Path(__file__).parent.parent.resolve())
    git_hash = ""
    try:
        git_hash = subprocess.check_output(
            ["git", "-C", repo_dir, "rev-parse", "--short", "HEAD"],
            timeout=5
        ).decode().strip()
    except Exception:
        pass
    version = ""
    try:
        version = (Path(repo_dir) / "VERSION").read_text().strip()
    except Exception:
        pass
    from connect.auth import get_node_id as _get_nid
    return {"version": version, "commit": git_hash, "node_id": _get_nid()}


@app.post("/create-agent")
async def create_agent_endpoint(request: Request):
    """
    Create a real agent on this node from a description.
    1. LLM generates the agent code
    2. Saves to agents/ directory
    3. Starts the process
    4. Registers in state.json (appears in dashboard immediately)

    Body: {"name": "my-agent", "description": "what it does", "model": "optional model override"}
    """
    import subprocess, time as _t
    try:
        body = await request.json()
        name = body.get("name", "").strip()
        description = body.get("description", "").strip()

        if not name or not description:
            return {"ok": False, "error": "name and description required"}

        # Sanitize name
        safe_name = name.lower().replace(" ", "_").replace("-", "_")
        safe_name = ''.join(c for c in safe_name if c.isalnum() or c == '_')

        agents_dir = Path(__file__).parent
        agent_file = agents_dir / f"{safe_name}.py"

        if agent_file.exists():
            return {"ok": False, "error": f"Agent '{safe_name}' already exists"}

        # Generate agent code via AI
        from connect.ai_config import get_ai_client
        ai = get_ai_client()

        prompt = f"""Crie um script Python de agente para o cluster CH8.

Nome: {safe_name}
Descrição: {description}

Requisitos obrigatórios:
- Função main() com loop e signal handling (SIGTERM para parar)
- Salvar PID em ~/.config/ch8/{safe_name}.pid ao iniciar
- Registrar estado a cada 30s usando:
  from connect.state import update_agent_state
  update_agent_state("{safe_name}", "running", "descrição da tarefa atual",
                     model="custom", platform="custom", autonomous=True)
- Logging em ~/.config/ch8/{safe_name}.log
- Import: sys.path.insert(0, str(Path(__file__).parent.parent))
- Máximo 150 linhas, funcional, sem placeholders
- Tratamento de erros adequado
- Textos e logs em português do Brasil

Retorne SOMENTE código Python, sem markdown, sem explicação."""

        code = ai.chat([{"role": "user", "content": prompt}], max_tokens=2000, temperature=0.2)

        # Clean response
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0]
        elif "```" in code:
            code = code.split("```")[1].split("```")[0]
        code = code.strip()

        if not code or len(code) < 50 or "def main" not in code:
            return {"ok": False, "error": "AI generated invalid code"}

        # Save the agent file
        agent_file.write_text(code + "\n")

        # Start the agent
        install_dir = str(Path(__file__).parent.parent)
        env = {**os.environ, "PYTHONPATH": install_dir}
        log_file = Path.home() / ".config" / "ch8" / f"{safe_name}.log"
        pid_file = Path.home() / ".config" / "ch8" / f"{safe_name}.pid"

        proc = subprocess.Popen(
            [sys.executable, str(agent_file)],
            cwd=install_dir, env=env,
            stdout=open(log_file, "w"), stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        # Write PID
        pid_file.write_text(str(proc.pid))

        # Register immediately in state.json so it appears in dashboard
        _t.sleep(1)
        state_file = Path.home() / ".config" / "ch8" / "state.json"
        try:
            import json as _json2
            state = _json2.loads(state_file.read_text()) if state_file.exists() else {}
            agents_list = state.get("agents", [])
            agents_list = [a for a in agents_list if a.get("name") != safe_name]
            agents_list.append({
                "name": safe_name,
                "status": "running",
                "task": f"Started: {description[:50]}",
                "model": "custom",
                "platform": "custom",
                "autonomous": True,
                "alerts": 0, "security_findings": 0, "predictions": 0, "heavy_procs": 0,
                "tools": [],
                "details": {"description": description},
                "updated_at": int(_t.time()),
            })
            state["agents"] = agents_list
            state_file.write_text(_json2.dumps(state, indent=2))
        except Exception:
            pass

        return {
            "ok": True,
            "agent": safe_name,
            "pid": proc.pid,
            "file": str(agent_file),
            "description": description,
            "message": f"Agent '{safe_name}' created and started (PID {proc.pid})",
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/autonomy")
async def set_autonomy(request: Request):
    """Enable/disable autonomous mode on this node."""
    try:
        body = await request.json()
        enabled = body.get("enabled", False)
        # Save to config
        config_dir = Path.home() / ".config" / "ch8"
        autonomy_file = config_dir / "autonomy.json"
        import json as _json
        autonomy_file.write_text(_json.dumps({"enabled": enabled, "ts": int(time.time())}))
        log.info(f"Autonomy {'ENABLED' if enabled else 'DISABLED'}")
        return {"ok": True, "autonomous": enabled}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/knowledge/write")
async def knowledge_write(request: Request):
    """
    API for any agent to write a note to the knowledge vault.
    Body: {"category": "docs", "title": "My Note", "content": "...", "tags": ["tag1"]}
    """
    try:
        body = await request.json()
        category = body.get("category", "inbox")
        title = body.get("title", f"note-{int(time.time())}")
        content = body.get("content", "")
        tags = body.get("tags", [])

        if not content:
            return {"ok": False, "error": "empty content"}

        sys.path.insert(0, str(Path(__file__).parent))
        from knowledge_agent import write_note
        path = write_note(category, title, content, tags)
        return {"ok": True, "path": path}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/knowledge/index")
async def knowledge_index():
    """Return vault index with categories and file lists."""
    vault = Path("/data2/knowledge")
    if not vault.exists():
        return {"error": "vault not found", "total_files": 0, "categories": []}

    categories = []
    total = 0
    for d in sorted(vault.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            files = sorted([f.name for f in d.glob("*.md")])
            categories.append({"name": d.name, "files": files})
            total += len(files)

    # Root-level files
    root_files = sorted([f.name for f in vault.glob("*.md")])
    if root_files:
        categories.insert(0, {"name": "(root)", "files": root_files})
        total += len(root_files)

    return {"total_files": total, "categories": categories}


@app.get("/knowledge/file")
async def knowledge_file(path: str = ""):
    """Return content of a specific vault file."""
    vault = Path("/data2/knowledge")
    if not path:
        return {"error": "path required"}

    target = (vault / path).resolve()
    # Security: ensure path stays within vault
    if not str(target).startswith(str(vault.resolve())):
        return {"error": "invalid path"}
    if not target.exists():
        return {"error": "file not found"}

    return {"path": path, "content": target.read_text()[:50000]}


@app.get("/knowledge/graph")
async def knowledge_graph():
    """Return nodes and edges for the knowledge graph visualization."""
    import re
    vault = Path("/data2/knowledge")
    if not vault.exists():
        return {"nodes": [], "edges": []}

    # Build node list and extract wikilinks
    file_nodes = {}
    edges = []
    wikilink_re = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')

    for md in vault.rglob("*.md"):
        rel = str(md.relative_to(vault))
        name = md.stem
        category = md.parent.name if md.parent != vault else "root"
        file_nodes[name.lower()] = {
            "id": name,
            "path": rel,
            "category": category,
        }

    # Extract edges from wikilinks
    for md in vault.rglob("*.md"):
        source = md.stem
        try:
            text = md.read_text()
            links = wikilink_re.findall(text)
            for link in links:
                # Handle paths like "services/overview"
                target = link.split("/")[-1] if "/" in link else link
                if target.lower() in file_nodes and target.lower() != source.lower():
                    edges.append({"source": source, "target": target})
        except Exception:
            pass

    nodes = list(file_nodes.values())
    return {"nodes": nodes, "edges": edges}


@app.get("/knowledge/search")
async def knowledge_search(q: str = ""):
    """Search the knowledge vault by text."""
    if not q:
        return {"results": []}
    vault = Path("/data2/knowledge")
    results = []
    for md in vault.rglob("*.md"):
        try:
            text = md.read_text()
            if q.lower() in text.lower():
                # Extract context around match
                idx = text.lower().index(q.lower())
                snippet = text[max(0, idx-50):idx+len(q)+100].replace("\n", " ")
                results.append({
                    "path": str(md.relative_to(vault)),
                    "snippet": snippet[:200],
                })
                if len(results) >= 20:
                    break
        except Exception:
            continue
    return {"results": results, "query": q, "count": len(results)}


@app.get("/ops/nginx-sites")
async def nginx_sites():
    """List active nginx sites with stats from access logs."""
    import subprocess, re, glob as _glob
    from pathlib import Path
    sites = []
    total_requests = 0
    total_errors = 0
    total_ips = set()
    try:
        enabled_dir = Path("/etc/nginx/sites-enabled")
        if not enabled_dir.exists():
            return {"sites": [], "error": "sites-enabled not found"}
        for conf_path in sorted(enabled_dir.iterdir()):
            fname = conf_path.name
            if fname == "default":
                continue
            try:
                conf = conf_path.read_text()
                server_names = re.findall(r"server_name\s+([^;]+);", conf)
                domain = server_names[0].split()[0] if server_names else fname
                proxy_pass = re.findall(r"proxy_pass\s+([^;]+);", conf)
                backend = proxy_pass[0].strip() if proxy_pass else ""
                ssl = "ssl" in conf or "443" in conf

                # Read access_log path directly from config
                access_logs = re.findall(r"access_log\s+(/[^;]+);", conf)
                req_current = 0
                req_all = 0
                errors = 0
                unique_ips = 0
                avg_bytes = 0
                log_found = ""

                for lp in access_logs:
                    lp = lp.strip()
                    if lp == "off" or not os.path.exists(lp):
                        continue
                    log_found = lp
                    # Current log stats
                    try:
                        result = subprocess.run(
                            ["awk", '{reqs++; if($9>=400)errs++; ips[$1]; bytes+=$10} END {printf "%d %d %d %.0f", reqs, errs, length(ips), (reqs>0?bytes/reqs:0)}', lp],
                            capture_output=True, text=True, timeout=5)
                        parts = result.stdout.strip().split()
                        if len(parts) >= 4:
                            req_current = int(parts[0])
                            errors = int(parts[1])
                            unique_ips = int(parts[2])
                            avg_bytes = int(parts[3])
                    except Exception:
                        pass
                    # Count all rotated logs for total
                    base = lp.rsplit('.log', 1)[0]
                    for rotated in _glob.glob(f"{base}*"):
                        if rotated.endswith('.gz'):
                            continue  # skip compressed for speed
                        try:
                            r2 = subprocess.run(["wc", "-l", rotated], capture_output=True, text=True, timeout=3)
                            req_all += int(r2.stdout.strip().split()[0])
                        except Exception:
                            pass

                error_pct = round(errors * 100 / req_current, 1) if req_current > 0 else 0
                total_requests += req_all
                total_errors += errors
                sites.append({
                    "domain": domain,
                    "backend": backend,
                    "ssl": ssl,
                    "requests": req_current,
                    "requests_all": req_all,
                    "unique_ips": unique_ips,
                    "error_pct": error_pct,
                    "avg_bytes": avg_bytes,
                    "status": "active",
                })
            except Exception:
                sites.append({"domain": fname, "backend": "", "ssl": False, "requests": 0, "requests_all": 0, "unique_ips": 0, "error_pct": 0, "avg_bytes": 0, "status": "error"})
    except Exception as e:
        return {"sites": [], "error": str(e)}
    sites.sort(key=lambda s: s["requests_all"], reverse=True)
    return {
        "sites": sites,
        "total": len(sites),
        "stats": {
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": round(total_errors * 100 / total_requests, 1) if total_requests > 0 else 0,
        }
    }


@app.get("/agents/all")
async def list_all_agents():
    """List ALL agent files on this node (installed + running status + MCPs)."""
    import json as _j3
    agents_dir = Path(__file__).parent
    pid_dir = Path.home() / ".config" / "ch8"
    state_file = pid_dir / "state.json"

    # Read state for active agents
    active_agents = {}
    try:
        state = _j3.loads(state_file.read_text()) if state_file.exists() else {}
        for a in state.get("agents", []):
            active_agents[a.get("name", "")] = a
    except Exception:
        pass

    # Get all running python agent processes for cross-reference
    import subprocess as _sp3
    try:
        ps_out = _sp3.check_output(["ps", "aux"], text=True, timeout=5)
        running_procs = {line.split()[-1]: line.split()[1] for line in ps_out.split('\n')
                         if 'agents/' in line and 'python' in line and 'grep' not in line}
    except Exception:
        running_procs = {}

    # Scan all agent files
    all_agents = []
    for f in sorted(agents_dir.glob("*.py")):
        if f.name.startswith("_") or f.name == "orchestrator.py":
            continue
        name = f.stem
        pid_file = pid_dir / f"{name}.pid"
        is_running = False
        pid = None
        # Check PID file first
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, 0)
                is_running = True
            except (OSError, ValueError):
                is_running = False
        # Fallback: check ps output for this agent file
        if not is_running:
            for proc_cmd, proc_pid in running_procs.items():
                if f.name in proc_cmd:
                    is_running = True
                    pid = int(proc_pid)
                    break

        # Get info from state if available
        state_info = active_agents.get(name, {})

        # Read first docstring/comment from file for description
        desc = ""
        try:
            content = f.read_text()
            if content.startswith('"""'):
                desc = content.split('"""')[1].strip().split('\n')[0][:100]
            elif content.startswith('#'):
                desc = content.split('\n')[0][1:].strip()[:100]
        except Exception:
            pass

        all_agents.append({
            "name": name,
            "file": str(f),
            "status": state_info.get("status", "running" if is_running else "stopped"),
            "running": is_running,
            "pid": pid if is_running else None,
            "model": state_info.get("model", ""),
            "platform": state_info.get("platform", ""),
            "task": state_info.get("task", ""),
            "tools": state_info.get("tools", []),
            "description": desc or state_info.get("details", {}).get("description", ""),
            "updated_at": state_info.get("updated_at", 0),
            "autonomous": state_info.get("autonomous", False),
        })

    # Also include orchestrator
    all_agents.insert(0, {
        "name": "orchestrator",
        "file": str(agents_dir / "orchestrator.py"),
        "status": "running",
        "running": True,
        "pid": os.getpid(),
        "model": active_agents.get("orchestrator", {}).get("model", ""),
        "platform": active_agents.get("orchestrator", {}).get("platform", ""),
        "task": active_agents.get("orchestrator", {}).get("task", ""),
        "tools": active_agents.get("orchestrator", {}).get("tools", []),
        "description": "Main orchestrator — chat, tools, cluster tasks",
        "updated_at": active_agents.get("orchestrator", {}).get("updated_at", 0),
        "autonomous": False,
    })

    # MCPs / configured tools
    mcps = []
    try:
        from connect.tools_config import get_all_tools
        mcps = [{"name": t, "type": "tool"} for t in get_all_tools()]
    except Exception:
        pass

    return {
        "agents": all_agents,
        "total": len(all_agents),
        "running": sum(1 for a in all_agents if a["running"]),
        "stopped": sum(1 for a in all_agents if not a["running"]),
        "mcps": mcps,
    }


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
                # Run blocking _get_context() in thread to avoid freezing event loop
                loop = _asyncio.get_event_loop()
                ctx = await loop.run_in_executor(None, _get_context)
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
                _refresh_sub_agents()

                # Persist metrics + SLA to PostgreSQL (best effort)
                try:
                    from connect.db import save_node_metrics, save_sla_check
                    from connect.auth import get_node_id, CONTROL_URL as _CU
                    import httpx as _hx2
                    my_id = get_node_id()
                    from pathlib import Path as _P2
                    _ver = (_P2(__file__).parent.parent / "VERSION").read_text().strip() if (_P2(__file__).parent.parent / "VERSION").exists() else "1.0.0"
                    save_node_metrics(my_id, __import__('socket').gethostname(),
                                      ctx.get('cpu_pct', 0), ctx.get('mem_pct', 0),
                                      ctx.get('disk_pct', 0), 0,
                                      len(ctx.get('containers', [])),
                                      len(ctx.get('agents', [])), _ver)
                    # SLA checks for all known peers (use local control server)
                    try:
                        r = await loop.run_in_executor(None, lambda: _hx2.get(
                            "http://127.0.0.1:8081/api/admin/nodes", timeout=5).json())
                        peers = r if isinstance(r, list) else []
                        for peer in peers:
                            if peer.get('node_id') == my_id:
                                continue
                            save_sla_check(peer['node_id'], peer.get('hostname', ''),
                                          peer.get('status') == 'online')
                    except Exception:
                        pass
                except Exception:
                    pass
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
    bind_host = os.environ.get("CH8_BIND_HOST", "0.0.0.0")
    uds = os.environ.get("CH8_UDS")  # Unix domain socket path (for WSL2)
    if uds:
        log.info(f"Listening on Unix socket: {uds}")
        # Also start a TCP forwarder so external access still works
        import threading
        def _tcp_forwarder():
            """Forward TCP connections to Unix socket."""
            import socket as _socket
            srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            srv.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
            srv.bind((bind_host, AGENT_PORT))
            srv.listen(16)
            while True:
                try:
                    client, _ = srv.accept()
                    uds_sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
                    uds_sock.connect(uds)
                    t1 = threading.Thread(target=_pipe, args=(client, uds_sock), daemon=True)
                    t2 = threading.Thread(target=_pipe, args=(uds_sock, client), daemon=True)
                    t1.start(); t2.start()
                except Exception:
                    pass
        def _pipe(src, dst):
            try:
                while True:
                    data = src.recv(65536)
                    if not data:
                        break
                    dst.sendall(data)
            except Exception:
                pass
            finally:
                src.close(); dst.close()
        threading.Thread(target=_tcp_forwarder, daemon=True).start()
        # Remove stale socket file
        Path(uds).unlink(missing_ok=True)
        uvicorn.run(app, uds=uds, log_level="warning", loop="asyncio")
    else:
        uvicorn.run(app, host=bind_host, port=AGENT_PORT, log_level="warning", loop="asyncio")


if __name__ == "__main__":
    main()
