"""
Tools configuration for CH8 agents.

Defines the available tools that the orchestrator can use.
Follows the Hermes/OpenClaw tool-calling convention:
  - Tools are defined as JSON schemas
  - The LLM can call them via structured output
  - Results are fed back into the conversation

Built-in tools:
  - shell_exec     — Execute shell commands (with authorization)
  - docker_exec    — Run commands inside Docker containers
  - file_read      — Read file contents
  - file_write     — Write/edit files
  - http_request   — Make HTTP requests
  - node_info      — Get info about CH8 nodes
  - service_restart — Restart a Docker container or systemd service
  - security_scan  — Run the security scanner

Custom tools can be added via ~/.config/ch8/tools.json
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path(os.environ.get("CH8_CONFIG_DIR", Path.home() / ".config" / "ch8"))
TOOLS_FILE = CONFIG_DIR / "tools.json"

# ── Built-in tool definitions (Hermes/OpenClaw format) ──────────────────────

BUILTIN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "shell_exec",
            "description": "Execute a shell command on this node. Returns stdout, stderr, and exit code. Use for system administration tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30)", "default": 30},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "docker_exec",
            "description": "Execute a command inside a running Docker container.",
            "parameters": {
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Container name or ID"},
                    "command": {"type": "string", "description": "Command to run inside the container"},
                },
                "required": ["container", "command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Read the contents of a file on this node.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute file path"},
                    "lines": {"type": "integer", "description": "Max lines to read (default: 100)", "default": 100},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "Write content to a file on this node. Creates parent directories if needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute file path"},
                    "content": {"type": "string", "description": "Content to write"},
                    "append": {"type": "boolean", "description": "Append instead of overwrite", "default": False},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "http_request",
            "description": "Make an HTTP request to a URL. Useful for checking APIs, health endpoints, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"], "default": "GET"},
                    "url": {"type": "string", "description": "The URL to request"},
                    "body": {"type": "string", "description": "Request body (for POST/PUT)"},
                    "headers": {"type": "object", "description": "Additional headers"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "node_info",
            "description": "Get information about CH8 cluster nodes — status, metrics, peers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "Specific node ID (empty = all nodes)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "service_restart",
            "description": "Restart a Docker container or systemd service.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Container name or systemd service name"},
                    "type": {"type": "string", "enum": ["docker", "systemd"], "default": "docker"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "security_scan",
            "description": "Run a security scan on this node. Checks for suspicious processes, exposed ports, weak passwords.",
            "parameters": {
                "type": "object",
                "properties": {
                    "scan_type": {"type": "string", "enum": ["full", "processes", "ports", "passwords"], "default": "full"},
                },
            },
        },
    },
]

# ── Tool execution ──────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict) -> dict:
    """Execute a tool call and return the result."""
    handlers = {
        "shell_exec":      _exec_shell,
        "docker_exec":     _exec_docker,
        "file_read":       _exec_file_read,
        "file_write":      _exec_file_write,
        "http_request":    _exec_http,
        "node_info":       _exec_node_info,
        "service_restart": _exec_service_restart,
        "security_scan":   _exec_security_scan,
    }

    # Check custom tools
    custom = _load_custom_tools()
    for t in custom:
        if t.get("function", {}).get("name") == name:
            cmd = t.get("execute", {}).get("command", "")
            if cmd:
                return _exec_shell({"command": cmd.format(**args)})

    handler = handlers.get(name)
    if not handler:
        return {"error": f"Unknown tool: {name}"}
    try:
        return handler(args)
    except Exception as e:
        return {"error": str(e)}


def _exec_shell(args: dict) -> dict:
    cmd = args["command"]
    timeout = args.get("timeout", 30)
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"stdout": r.stdout[:4000], "stderr": r.stderr[:2000], "exit_code": r.returncode}
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s"}


def _exec_docker(args: dict) -> dict:
    container = args["container"]
    command = args["command"]
    return _exec_shell({"command": f"docker exec {container} {command}", "timeout": 30})


def _exec_file_read(args: dict) -> dict:
    path = args["path"]
    lines = args.get("lines", 100)
    try:
        content = Path(path).read_text()
        content_lines = content.splitlines()
        if len(content_lines) > lines:
            content = "\n".join(content_lines[:lines]) + f"\n... ({len(content_lines) - lines} more lines)"
        return {"content": content, "lines": len(content_lines), "path": path}
    except Exception as e:
        return {"error": str(e)}


def _exec_file_write(args: dict) -> dict:
    path = args.get("path", "")
    content = args.get("content", "")
    if not path:
        return {"error": "Missing 'path' argument"}
    if not content:
        return {"error": "Missing 'content' argument"}
    append = args.get("append", False)
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if append:
            with p.open("a") as f:
                f.write(content)
        else:
            p.write_text(content)
        return {"ok": True, "path": path, "bytes": len(content)}
    except Exception as e:
        return {"error": str(e)}


def _exec_http(args: dict) -> dict:
    import httpx
    method = args.get("method", "GET")
    url = args["url"]
    body = args.get("body")
    headers = args.get("headers", {})
    try:
        r = httpx.request(method, url, content=body, headers=headers, timeout=15)
        return {"status": r.status_code, "body": r.text[:4000], "headers": dict(r.headers)}
    except Exception as e:
        return {"error": str(e)}


def _exec_node_info(args: dict) -> dict:
    state_file = CONFIG_DIR / "state.json"
    try:
        state = json.loads(state_file.read_text())
        return {"status": state.get("status"), "peers": state.get("peers", []), "agents": state.get("agents", [])}
    except Exception as e:
        return {"error": str(e)}


def _exec_service_restart(args: dict) -> dict:
    name = args["name"]
    svc_type = args.get("type", "docker")
    if svc_type == "docker":
        return _exec_shell({"command": f"docker restart {name}", "timeout": 60})
    elif svc_type == "systemd":
        return _exec_shell({"command": f"systemctl restart {name}", "timeout": 60})
    return {"error": f"Unknown service type: {svc_type}"}


def _exec_security_scan(args: dict) -> dict:
    scan_type = args.get("scan_type", "full")
    try:
        import sys
        agents_dir = Path(__file__).parent.parent / "agents"
        r = subprocess.run(
            [sys.executable, str(agents_dir / "server_monitor.py"), "--scan"],
            capture_output=True, text=True, timeout=30,
        )
        return {"output": r.stdout[:4000], "exit_code": r.returncode}
    except Exception as e:
        return {"error": str(e)}


# ── Tool loading ────────────────────────────────────────────────────────────

def _load_custom_tools() -> list:
    """Load user-defined custom tools from ~/.config/ch8/tools.json"""
    if TOOLS_FILE.exists():
        try:
            return json.loads(TOOLS_FILE.read_text())
        except Exception:
            pass
    return []


def get_all_tools(include_builtin: bool = True) -> list:
    """Return all available tools (built-in + custom)."""
    tools = []
    config = _load_tools_config()
    enabled = config.get("enabled", [t["function"]["name"] for t in BUILTIN_TOOLS])

    if include_builtin:
        for t in BUILTIN_TOOLS:
            if t["function"]["name"] in enabled:
                tools.append(t)

    tools.extend(_load_custom_tools())
    return tools


def _load_tools_config() -> dict:
    """Load tools enablement config."""
    cfg_file = CONFIG_DIR / "tools_enabled.json"
    if cfg_file.exists():
        try:
            return json.loads(cfg_file.read_text())
        except Exception:
            pass
    return {"enabled": [t["function"]["name"] for t in BUILTIN_TOOLS]}


def save_tools_config(config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "tools_enabled.json").write_text(json.dumps(config, indent=2))


def interactive_setup() -> dict:
    """Interactive tools setup."""
    print("\n  Agent Tools Configuration\n")
    print("  Tools allow the orchestrator to execute actions on this node.")
    print("  Select which tools to enable:\n")

    all_names = [t["function"]["name"] for t in BUILTIN_TOOLS]
    enabled = list(all_names)  # all enabled by default

    for i, t in enumerate(BUILTIN_TOOLS, 1):
        fn = t["function"]
        print(f"    {i}) {fn['name']}")
        print(f"       {fn['description'][:70]}")
        print()

    print(f"  All {len(BUILTIN_TOOLS)} tools are enabled by default.")
    customize = input("  Customize? [y/N] ").strip().lower()

    if customize == "y":
        enabled = []
        for t in BUILTIN_TOOLS:
            name = t["function"]["name"]
            yn = input(f"  Enable {name}? [Y/n] ").strip().lower()
            if yn != "n":
                enabled.append(name)

    config = {"enabled": enabled}
    save_tools_config(config)
    print(f"\n  {len(enabled)}/{len(all_names)} tools enabled.")
    return config
