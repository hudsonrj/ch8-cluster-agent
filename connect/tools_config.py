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
    EXTRA_TOOLS = []
    logging.warning(f"Extra tools not loaded: {_e}")
