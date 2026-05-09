"""
CH8 Agent State — Thread-safe state.json management with file locking.

All agents MUST use update_agent_state() instead of writing state.json directly.
This prevents race conditions that cause agents to disappear.
"""

import json
import fcntl
import time
from pathlib import Path

STATE_FILE = Path.home() / ".config" / "ch8" / "state.json"
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def update_agent_state(name: str, status: str, task: str = "",
                       model: str = "", platform: str = "custom",
                       autonomous: bool = True, tools: list = None,
                       details: dict = None, **extra):
    """
    Thread-safe update of a single agent's entry in state.json.
    Uses file locking to prevent race conditions between multiple processes.
    """
    entry = {
        "name": name,
        "status": status,
        "task": task,
        "model": model,
        "platform": platform,
        "autonomous": autonomous,
        "updated_at": int(time.time()),
        "tools": tools or [],
        "details": details or {},
        "alerts": 0,
        "security_findings": 0,
        "predictions": 0,
        "heavy_procs": 0,
        **extra,
    }

    lock_file = STATE_FILE.parent / "state.lock"

    try:
        with open(lock_file, "w") as lf:
            # Acquire exclusive lock (blocks until available, max 5s)
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                # Read current state
                if STATE_FILE.exists():
                    try:
                        state = json.loads(STATE_FILE.read_text())
                    except (json.JSONDecodeError, ValueError):
                        state = {}
                else:
                    state = {}

                # Update agent entry
                agents = state.get("agents", [])
                agents = [a for a in agents if a.get("name") != name]
                agents.append(entry)
                state["agents"] = agents

                # Write atomically (write to temp, then rename)
                tmp = STATE_FILE.parent / "state.json.tmp"
                tmp.write_text(json.dumps(state, indent=2))
                tmp.rename(STATE_FILE)
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    except Exception:
        # Fallback: try direct write if locking fails (Windows, etc.)
        try:
            state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
            agents = state.get("agents", [])
            agents = [a for a in agents if a.get("name") != name]
            agents.append(entry)
            state["agents"] = agents
            STATE_FILE.write_text(json.dumps(state, indent=2))
        except Exception:
            pass


def remove_agent_state(name: str):
    """Remove an agent from state.json (when stopped)."""
    lock_file = STATE_FILE.parent / "state.lock"
    try:
        with open(lock_file, "w") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
                state["agents"] = [a for a in state.get("agents", []) if a.get("name") != name]
                tmp = STATE_FILE.parent / "state.json.tmp"
                tmp.write_text(json.dumps(state, indent=2))
                tmp.rename(STATE_FILE)
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
