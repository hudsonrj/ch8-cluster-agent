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
  - web_search     — Search the web using DuckDuckGo
  - web_extract    — Extract content from web pages

Custom tools can be added via ~/.config/ch8/tools.json
"""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

# Import web tools
try:
    import sys
    sys.path.insert(0, '/data/ch8-agent')
    from tools.web_tools import TOOLS as WEB_TOOLS
    WEB_TOOLS_AVAILABLE = True
except ImportError:
    WEB_TOOLS = []
    WEB_TOOLS_AVAILABLE = False
    logging.warning("Web tools not available")

CONFIG_DIR = Path(os.environ.get("CH8_CONFIG_DIR", Path.home() / ".config" / "ch8"))
TOOLS_FILE = CONFIG_DIR / "tools.json"

# ── Built-in tool definitions (Hermes/OpenClaw format) ────────────────────────

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
            "description": "Make an HTTP request to a URL. Returns response status, headers, and body.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to request"},
                    "method": {"type": "string", "description": "HTTP method (GET, POST, etc.)", "default": "GET"},
                    "headers": {"type": "object", "description": "Optional headers"},
                    "body": {"type": "string", "description": "Request body (for POST/PUT)"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "node_info",
            "description": "Get information about this CH8 node or query the cluster.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional query filter"},
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
                    "service": {"type": "string", "description": "Service/container name"},
                    "type": {"type": "string", "description": "Type: 'docker' or 'systemd'", "default": "docker"},
                },
                "required": ["service"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "security_scan",
            "description": "Run security scanner on specified targets (ports, services, etc.)",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Target to scan (IP, hostname, 'self')"},
                    "scan_type": {"type": "string", "description": "Type of scan: 'port', 'vuln', 'full'", "default": "port"},
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ticket_list",
            "description": "List ITSM tickets from the cluster. Filter by status (open/in_progress/resolved/closed), severity, node, category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status":   {"type": "string", "description": "Filter by status: open, in_progress, resolved, closed"},
                    "severity": {"type": "string", "description": "Filter by severity: critical, high, medium, low"},
                    "limit":    {"type": "integer", "description": "Max tickets to return (default 50)"},
                    "node":     {"type": "string", "description": "Filter by node name"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ticket_update",
            "description": "Update an ITSM ticket: change status, assign to specialist, add resolution notes, close duplicates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id":   {"type": "string", "description": "Ticket ID (e.g. TK-001)"},
                    "status":      {"type": "string", "description": "New status: open, investigating, in_progress, resolved, closed"},
                    "assigned_to": {"type": "string", "description": "Specialist name to assign"},
                    "resolution":  {"type": "string", "description": "Resolution notes"},
                    "note":        {"type": "string", "description": "History note"},
                },
                "required": ["ticket_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wazuh_summary",
            "description": "Get Wazuh SIEM 24h summary: alert counts (critical/high/medium/low), active agents, top attack source IPs.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wazuh_alerts",
            "description": "Query Wazuh SIEM for recent security alerts. Filter by minimum level (1-15), time window (hours), and result limit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {"type": "integer", "description": "Minimum alert level (1-15). 8=medium, 12=high, 15=critical. Default 8."},
                    "hours": {"type": "integer", "description": "Time window in hours (default 24)"},
                    "limit": {"type": "integer", "description": "Max alerts to return (default 50)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wazuh_cves",
            "description": "List CVEs detected by Wazuh vulnerability scanner in the last 7 days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max CVEs to return (default 20)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ticket_create",
            "description": "Create a new ITSM ticket in the cluster.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title":       {"type": "string", "description": "Ticket title"},
                    "description": {"type": "string", "description": "Detailed description"},
                    "severity":    {"type": "string", "description": "critical, high, medium, low"},
                    "category":    {"type": "string", "description": "service_down, performance, config, security, etc."},
                    "node":        {"type": "string", "description": "Affected node"},
                    "assigned_to": {"type": "string", "description": "Specialist to assign"},
                },
                "required": ["title", "severity"],
            },
        },
    },
]

# Add web tools if available
if WEB_TOOLS_AVAILABLE:
    BUILTIN_TOOLS.extend(WEB_TOOLS)

def load_tools() -> list:
    """
    Load all available tools (built-in + custom).
    Custom tools are loaded from ~/.config/ch8/tools.json if present.
    """
    tools = BUILTIN_TOOLS.copy()
    
    # Load custom tools if config file exists
    if TOOLS_FILE.exists():
        try:
            with open(TOOLS_FILE) as f:
                custom_tools = json.load(f)
                if isinstance(custom_tools, list):
                    tools.extend(custom_tools)
                    logging.info(f"Loaded {len(custom_tools)} custom tools from {TOOLS_FILE}")
        except Exception as e:
            logging.error(f"Failed to load custom tools from {TOOLS_FILE}: {e}")
    
    return tools

# Aliases mantidos para compatibilidade com 'ch8 up' e outros importadores
get_all_tools = load_tools


def interactive_setup() -> dict:
    """Interactive tools setup — called by 'ch8 up'. All tools enabled by default."""
    all_names = [t["function"]["name"] for t in BUILTIN_TOOLS]
    config = {"enabled": all_names}
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        (CONFIG_DIR / "tools_enabled.json").write_text(json.dumps(config, indent=2))
    except Exception:
        pass
    return config

def get_tool_names() -> list[str]:
    """Return list of all available tool names."""
    return [t["function"]["name"] for t in load_tools()]

# ── New tools from Hermes/OpenClaw integration ────────────────────────────────
try:
    from tools.session_search import session_search as _session_search
    from tools.skills_tools import skills_list as _skills_list, skill_view as _skill_view, skill_save as _skill_save
    from tools.user_profile_tools import profile_get as _profile_get, profile_set as _profile_set, profile_context as _profile_context
    from tools.kanban_tools import kanban_create as _kanban_create, kanban_show as _kanban_show, kanban_complete as _kanban_complete, kanban_block as _kanban_block, kanban_heartbeat as _kanban_heartbeat, kanban_comment as _kanban_comment

    EXTRA_TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "session_search",
                "description": "Search past conversations using full-text search (FTS). Use when you need context from previous interactions.",
                "parameters": {"type": "object", "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results", "default": 5}
                }, "required": ["query"]}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "skills_list",
                "description": "List available skills in the CH8 skills marketplace.",
                "parameters": {"type": "object", "properties": {
                    "query": {"type": "string", "description": "Filter by query (optional)"}
                }}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "skill_view",
                "description": "View the content of a specific skill.",
                "parameters": {"type": "object", "properties": {
                    "name": {"type": "string", "description": "Skill name"}
                }, "required": ["name"]}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "profile_context",
                "description": "Get the user profile context to personalize responses.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "kanban_create",
                "description": "Create a task on the kanban board for multi-agent coordination.",
                "parameters": {"type": "object", "properties": {
                    "title": {"type": "string"},
                    "assignee": {"type": "string"},
                    "priority": {"type": "string", "enum": ["low","medium","high","critical"]},
                    "description": {"type": "string"}
                }, "required": ["title"]}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "kanban_show",
                "description": "Show current kanban board status.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
    ]

    # Register executor functions
    _EXTRA_EXEC = {
        "session_search": lambda args: _session_search(**args),
        "skills_list": lambda args: _skills_list(**args),
        "skill_view": lambda args: _skill_view(**args),
        "profile_context": lambda args: _profile_context(),
        "kanban_create": lambda args: _kanban_create(**args),
        "kanban_show": lambda args: _kanban_show(),
    }

    BUILTIN_TOOLS.extend(EXTRA_TOOLS)

    # Patch execute_tool to handle new tools
    _orig_execute = execute_tool if 'execute_tool' in dir() else None

except Exception as _e:
    _EXTRA_EXEC = {}
    EXTRA_TOOLS = []


# ── Tool execution ────────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict) -> dict:
    """Execute a tool call and return the result."""
    # Extra tools (Hermes/OpenClaw) take priority
    if name in _EXTRA_EXEC:
        try:
            return _EXTRA_EXEC[name](args)
        except Exception as e:
            return {"error": str(e)}

    handlers = {
        "shell_exec":      _exec_shell,
        "docker_exec":     _exec_docker,
        "file_read":       _exec_file_read,
        "file_write":      _exec_file_write,
        "http_request":    _exec_http,
        "node_info":       _exec_node_info,
        "service_restart": _exec_service_restart,
        "security_scan":   _exec_security_scan,
        "node_chat":       _exec_node_chat,
        "cluster_task":    _exec_cluster_task,
        "cluster_catalog": _exec_cluster_catalog,
        "ha_status":       _exec_ha_status,
        "cluster_update":  _exec_cluster_update,
        "web_search":      _exec_web_search,
        "web_extract":     _exec_web_extract,
        "calendar_create": _exec_calendar_create,
        "openclaw_chat":   _exec_openclaw_chat,
        "ticket_list":     _exec_ticket_list,
        "ticket_update":   _exec_ticket_update,
        "ticket_create":   _exec_ticket_create,
        "wazuh_summary":   _exec_wazuh_summary,
        "wazuh_alerts":    _exec_wazuh_alerts,
        "wazuh_cves":      _exec_wazuh_cves,
    }

    # Custom tools from tools.json
    if TOOLS_FILE.exists():
        try:
            custom = json.loads(TOOLS_FILE.read_text())
            for t in custom:
                if t.get("function", {}).get("name") == name:
                    cmd = t.get("execute", {}).get("command", "")
                    if cmd:
                        return _exec_shell({"command": cmd.format(**args)})
        except Exception:
            pass

    handler = handlers.get(name)
    if not handler:
        return {"error": f"Unknown tool: {name}"}
    try:
        return handler(args)
    except Exception as e:
        return {"error": str(e)}


def _exec_shell(args: dict) -> dict:
    cmd = args.get("command", "")
    timeout = args.get("timeout", 30)
    # Security policy check
    try:
        from connect.security_policy import check_command_policy
        violation = check_command_policy(cmd)
        if violation:
            return {"error": f"Command blocked by security policy: {violation}", "blocked": True}
    except ImportError:
        pass
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"stdout": r.stdout[:4000], "stderr": r.stderr[:2000], "exit_code": r.returncode}
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


def _exec_docker(args: dict) -> dict:
    container = args.get("container", "")
    command = args.get("command", "")
    # Basic injection prevention
    if ";" in container or "`" in container or "$(" in container:
        return {"error": "Invalid container name"}
    return _exec_shell({"command": f"docker exec {container} sh -c {json.dumps(command)}", "timeout": 30})


def _exec_file_read(args: dict) -> dict:
    path = args.get("path", "")
    lines = args.get("lines", 100)
    try:
        from connect.security_policy import check_path_policy
        violation = check_path_policy(path, "read")
        if violation:
            return {"error": f"Path blocked by security policy: {violation}", "blocked": True}
    except ImportError:
        pass
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
    try:
        from connect.security_policy import check_path_policy
        violation = check_path_policy(path, "write")
        if violation:
            return {"error": f"Path blocked by security policy: {violation}", "blocked": True}
    except ImportError:
        pass
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
    try:
        import httpx
        method = args.get("method", "GET")
        url = args["url"]
        body = args.get("body")
        headers = args.get("headers", {})
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
    name = args.get("service", args.get("name", ""))
    svc_type = args.get("type", "docker")
    if svc_type == "docker":
        return _exec_shell({"command": f"docker restart {name}", "timeout": 60})
    elif svc_type == "systemd":
        return _exec_shell({"command": f"systemctl restart {name}", "timeout": 60})
    return {"error": f"Unknown service type: {svc_type}"}


def _exec_security_scan(args: dict) -> dict:
    try:
        import sys as _sys
        agents_dir = Path(__file__).parent.parent / "agents"
        r = subprocess.run(
            [_sys.executable, str(agents_dir / "server_monitor.py"), "--scan"],
            capture_output=True, text=True, timeout=30,
        )
        return {"output": r.stdout[:4000], "exit_code": r.returncode}
    except Exception as e:
        return {"error": str(e)}


def _exec_node_chat(args: dict) -> dict:
    import httpx as _httpx
    node = args.get("node", "").strip()
    message = args.get("message", "").strip()
    if not node:
        return {"error": "Missing 'node' argument"}
    if not message:
        return {"error": "Missing 'message' argument"}

    state_file = CONFIG_DIR / "state.json"
    try:
        state = json.loads(state_file.read_text())
        peers = state.get("peers", [])
    except Exception:
        peers = []

    peer = None
    node_lower = node.lower()
    for p in peers:
        if node_lower in (p.get("hostname", "").lower(), p.get("node_id", "").lower(), p.get("alias", "").lower()):
            peer = p
            break

    if not peer:
        known = [p.get("hostname", p.get("node_id", "?")) for p in peers]
        return {"error": f"Node '{node}' not found. Known: {known}"}

    address = peer.get("address", "")
    target_node_id = peer.get("node_id", "")
    payload = {"message": message, "stream": False}

    if address:
        orch_port = int(os.environ.get("CH8_AGENT_PORT", "7879"))
        url = f"http://{address}:{orch_port}/chat"
        try:
            from connect.auth import get_access_token
            token = get_access_token()
            r = _httpx.post(url, json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=60)
            if r.status_code == 200:
                data = r.json()
                return {"node": peer.get("hostname", node), "response": data.get("response", str(data)), "method": "direct"}
            direct_error = f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            direct_error = str(e)
    else:
        direct_error = "no address"

    # Relay fallback
    try:
        from connect.auth import CONTROL_URL, get_access_token
        token = get_access_token()
        r = _httpx.post(f"{CONTROL_URL}/api/relay/{target_node_id}", json=payload,
                        headers={"Authorization": f"Bearer {token}"}, timeout=60)
        if r.status_code == 200:
            data = r.json()
            return {"node": peer.get("hostname", node), "response": data.get("response", str(data)), "method": "relay"}
        return {"error": f"Relay failed HTTP {r.status_code}. Direct: {direct_error}"}
    except Exception as e:
        return {"error": f"Relay failed: {e}. Direct: {direct_error}"}


def _exec_cluster_task(args: dict) -> dict:
    try:
        from connect.cluster_orchestrator import run_cluster_task
        task = args.get("task", "")
        if not task:
            return {"error": "Missing 'task' argument"}
        steps = []
        out = run_cluster_task(task, strategy=args.get("strategy", "auto"),
                               target_nodes=args.get("nodes") or None,
                               progress_cb=lambda s, m: steps.append(f"[{s}] {m}"))
        return {"result": out["result"], "nodes_used": out["nodes_used"],
                "elapsed": f"{out['elapsed']:.1f}s", "progress": steps}
    except Exception as e:
        return {"error": str(e)}


def _exec_cluster_catalog(args: dict) -> dict:
    try:
        from connect.cluster_orchestrator import get_catalog, rank_nodes, catalog_summary
        nodes = get_catalog()
        ranked = rank_nodes(nodes)
        if args.get("detail") == "full":
            return {"nodes": ranked, "count": len(ranked)}
        return {"summary": catalog_summary(ranked), "count": len(ranked)}
    except Exception as e:
        return {"error": str(e)}


def _exec_ha_status(args: dict) -> dict:
    try:
        from connect.cluster_ha import ha_status, get_current_leader
        return {"local": ha_status(), "control_server": get_current_leader() or {}}
    except Exception as e:
        return {"error": str(e)}


def _exec_cluster_update(args: dict) -> dict:
    try:
        from connect.cluster_orchestrator import update_cluster
        steps = []
        out = update_cluster(ref=args.get("ref", "main"),
                             target_nodes=args.get("nodes") or None,
                             progress_cb=lambda s, m: steps.append(f"[{s}] {m}"))
        return {"updated": out.get("updated", []), "failed": out.get("failed", []),
                "elapsed": str(out.get("elapsed", "")), "progress": steps}
    except Exception as e:
        return {"error": str(e)}


def _exec_web_search(args: dict) -> dict:
    try:
        from tools.web_tools import web_search
        return web_search(query=args.get("query", ""), max_results=args.get("max_results", 5))
    except Exception as e:
        return {"error": str(e)}


def _exec_web_extract(args: dict) -> dict:
    try:
        from tools.web_tools import web_extract
        return web_extract(url=args.get("url", ""))
    except Exception as e:
        return {"error": str(e)}


def _exec_openclaw_chat(args: dict) -> dict:
    """Call an OpenClaw agent via the local gateway CLI."""
    try:
        import subprocess
        agent_id = args.get("agent_id") or args.get("agent", "cluster-master")
        message = args.get("message", "")
        if not message:
            return {"error": "message required"}
        result = subprocess.run(
            ["openclaw", "agent", "--agent", agent_id, "--message", message, "--json"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            import json as _j
            d = _j.loads(result.stdout)
            payloads = d.get("result", {}).get("payloads", [])
            reply = " ".join(p.get("text", "") for p in payloads)
            return {"ok": True, "agent": agent_id, "reply": reply, "run_id": d.get("runId")}
        return {"ok": False, "error": result.stderr[:200] or result.stdout[:200]}
    except Exception as e:
        return {"error": str(e)}


def _exec_calendar_create(args: dict) -> dict:
    """Create an event in the cluster agenda (persistent DB)."""
    try:
        import httpx
        from connect.auth import CONTROL_URL, get_access_token
        token = get_access_token()
        payload = {
            "title":       args.get("title", "Evento"),
            "description": args.get("description", ""),
            "type":        args.get("type", "monitoramento"),
            "date":        args.get("date"),
            "time":        args.get("time", "09:00"),
            "end_time":    args.get("end_time"),
            "recurrence":  args.get("recurrence", "none"),
            "recur_until": args.get("recur_until"),
            "specialist":  args.get("specialist"),
            "source":      args.get("source", "specialist"),
            "source_ref":  args.get("source_ref"),
            "color":       args.get("color"),
            "node":        args.get("node", "manager1"),
        }
        r = httpx.post(
            f"{CONTROL_URL}/api/agenda/events",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        return r.json()
    except Exception as e:
        return {"error": str(e)}


# ── ITSM ticket tools ─────────────────────────────────────────────────────────

def _exec_ticket_list(args: dict) -> dict:
    """List ITSM tickets from the cluster with optional filters."""
    try:
        import httpx
        from connect.auth import CONTROL_URL, get_access_token
        token = get_access_token()
        params = {}
        for k in ("status", "severity", "node", "category", "limit"):
            if args.get(k):
                params[k] = args[k]
        r = httpx.get(
            f"{CONTROL_URL}/api/itsm/tickets",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        data = r.json()
        tickets = data.get("tickets", data) if isinstance(data, dict) else data
        return {"tickets": tickets, "count": len(tickets)}
    except Exception as e:
        return {"error": str(e)}


def _exec_ticket_update(args: dict) -> dict:
    """Update a ticket: change status, assign, add resolution note."""
    try:
        import httpx
        from connect.auth import CONTROL_URL, get_access_token
        ticket_id = args.get("ticket_id") or args.get("id", "")
        if not ticket_id:
            return {"error": "ticket_id required"}
        token = get_access_token()
        payload = {k: v for k, v in args.items() if k not in ("ticket_id", "id")}
        r = httpx.put(
            f"{CONTROL_URL}/api/itsm/tickets/{ticket_id}",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def _exec_ticket_create(args: dict) -> dict:
    """Create a new ITSM ticket."""
    try:
        import httpx
        from connect.auth import CONTROL_URL, get_access_token
        token = get_access_token()
        r = httpx.post(
            f"{CONTROL_URL}/api/itsm/tickets",
            json=args,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        return r.json()
    except Exception as e:
        return {"error": str(e)}


# ── Wazuh SIEM tools ──────────────────────────────────────────────────────────

def _exec_wazuh_alerts(args: dict) -> dict:
    """Query Wazuh SIEM for recent security alerts."""
    try:
        import httpx
        from connect.auth import CONTROL_URL, get_access_token
        token = get_access_token()
        params = {k: args[k] for k in ("level","limit","hours") if args.get(k)}
        r = httpx.get(f"{CONTROL_URL}/api/wazuh/alerts",
                      params=params,
                      headers={"Authorization": f"Bearer {token}"},
                      timeout=15)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def _exec_wazuh_summary(args: dict) -> dict:
    """Get Wazuh 24h summary: alert counts by severity, active agents, top attackers."""
    try:
        import httpx
        from connect.auth import CONTROL_URL, get_access_token
        token = get_access_token()
        r = httpx.get(f"{CONTROL_URL}/api/wazuh/summary",
                      headers={"Authorization": f"Bearer {token}"},
                      timeout=15)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def _exec_wazuh_cves(args: dict) -> dict:
    """List CVEs detected by Wazuh vulnerability scanner (last 7 days)."""
    try:
        import httpx
        from connect.auth import CONTROL_URL, get_access_token
        token = get_access_token()
        params = {"limit": args.get("limit", 20)}
        r = httpx.get(f"{CONTROL_URL}/api/wazuh/cves",
                      params=params,
                      headers={"Authorization": f"Bearer {token}"},
                      timeout=15)
        return r.json()
    except Exception as e:
        return {"error": str(e)}
