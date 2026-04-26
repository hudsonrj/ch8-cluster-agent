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
                os.environ.setdefault(key.strip(), val.strip())

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

    return f"""You are CH8 agent for node {ctx['hostname']}. You execute tasks on this server.

IMPORTANT: You are an EXECUTOR, not an advisor. Never explain steps. Always DO it using tool_call.

## Tool format
```tool_call
{{"name": "tool_name", "args": {{"key": "value"}}}}
```

Tools: shell_exec, file_write, file_read, docker_exec, service_restart, http_request, security_scan

## Example — user says "create a script that prints hello"
CORRECT (what you must do):
```tool_call
{{"name": "file_write", "args": {{"path": "/opt/ch8/hello.py", "content": "#!/usr/bin/env python3\\nprint('Hello!')"}}}}
```
Then after seeing the result:
```tool_call
{{"name": "shell_exec", "args": {{"command": "chmod +x /opt/ch8/hello.py && python3 /opt/ch8/hello.py"}}}}
```
Then say: "Done. Created /opt/ch8/hello.py and tested it. Output: Hello!"

WRONG (never do this): "Here's how you can create a script: step 1... step 2..."

## Node info
Host: {ctx['hostname']} | OS: {ctx['os']} | CPU: {ctx['cpu_pct']}% | RAM: {ctx['mem_pct']}% | Disk: {ctx['disk_pct']}%
Containers: {len(ctx.get('containers', []))} | Peers: {peers_txt} | Time: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}

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


async def _stream_bedrock(model: str, messages: list, region: str):
    """Stream from AWS Bedrock using httpx with bearer token or boto3 fallback."""
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
