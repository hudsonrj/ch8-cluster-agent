"""
CH8 Cluster — Security Policy Engine

Validates shell commands and file paths against configurable deny/allow rules.
Prevents destructive operations even from authenticated users.

Config: ~/.config/ch8/security.json (auto-created with safe defaults)
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

log = logging.getLogger("ch8.security_policy")

CONFIG_DIR = Path(os.environ.get("CH8_CONFIG_DIR", str(Path.home() / ".config" / "ch8")))
POLICY_FILE = CONFIG_DIR / "security.json"

# Default policy (used if security.json doesn't exist)
DEFAULT_POLICY = {
    "shell": {
        "denied_patterns": [
            r"rm\s+-rf\s+/\s*$",
            r"rm\s+-rf\s+/\*",
            r"mkfs\.",
            r"dd\s+if=/dev/(zero|random|urandom)\s+of=/dev/[sh]d",
            r">\s*/etc/passwd",
            r">\s*/etc/shadow",
            r">\s*/etc/sudoers",
            r"chmod\s+777\s+/\s*$",
            r"chmod\s+-R\s+777\s+/",
            r"curl\s+.*\|\s*(ba)?sh",
            r"wget\s+.*\|\s*(ba)?sh",
            r"curl\s+.*\|\s*python",
            r":()\{\s*:\|:&\s*\};:",  # fork bomb
            r"echo\s+.*>\s*/dev/sd[a-z]",
            r"shred\s+/dev/",
            r"wipefs",
        ],
        "denied_commands": [
            "halt", "poweroff", "shutdown", "init 0", "init 6",
            "reboot", "systemctl poweroff", "systemctl halt",
        ],
        "max_timeout": 120,
    },
    "files": {
        "allowed_paths": [
            "/data", "/data2", "/home", "/tmp", "/var/log",
            "/root/.config/ch8", "/opt", "/usr/local",
        ],
        "denied_paths": [
            "/etc/shadow", "/etc/gshadow",
            "/etc/sudoers", "/etc/sudoers.d",
            "/root/.ssh/id_rsa", "/root/.ssh/id_ed25519",
            "/etc/ssl/private",
        ],
        "denied_write_patterns": [
            r"\.pem$", r"\.key$", r"id_rsa", r"id_ed25519",
            r"/etc/passwd$", r"/etc/group$",
            r"/boot/", r"/proc/", r"/sys/",
        ],
        "denied_read_patterns": [
            r"/etc/shadow$", r"/etc/gshadow$",
            r"\.env$",  # environment files with secrets
        ],
    },
    "docker": {
        "denied_container_patterns": [
            r"[;&|`$]",  # shell injection in container name
        ],
        "denied_commands_in_container": [
            "rm -rf /",
        ],
    },
}

_policy_cache: Optional[dict] = None
_policy_mtime: float = 0


def _load_policy() -> dict:
    """Load security policy from file or use defaults."""
    global _policy_cache, _policy_mtime

    # Create default policy file if doesn't exist
    if not POLICY_FILE.exists():
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            POLICY_FILE.write_text(json.dumps(DEFAULT_POLICY, indent=2, ensure_ascii=False))
            log.info(f"Created default security policy at {POLICY_FILE}")
        except Exception:
            pass
        _policy_cache = DEFAULT_POLICY
        return DEFAULT_POLICY

    # Cache with mtime check
    try:
        mtime = POLICY_FILE.stat().st_mtime
        if _policy_cache and mtime == _policy_mtime:
            return _policy_cache
        _policy_cache = json.loads(POLICY_FILE.read_text())
        _policy_mtime = mtime
        return _policy_cache
    except Exception:
        return DEFAULT_POLICY


def check_command_policy(command: str) -> Optional[str]:
    """
    Validate a shell command against security policy.
    Returns None if OK, or a string describing the violation.
    """
    if not command or not command.strip():
        return None

    policy = _load_policy()
    shell_policy = policy.get("shell", {})
    cmd_lower = command.lower().strip()

    # Check denied exact commands
    for denied in shell_policy.get("denied_commands", []):
        if cmd_lower == denied.lower() or cmd_lower.startswith(denied.lower() + " "):
            return f"Comando bloqueado: '{denied}' — operação destrutiva não permitida"

    # Check denied patterns (regex)
    for pattern in shell_policy.get("denied_patterns", []):
        try:
            if re.search(pattern, command, re.IGNORECASE):
                return f"Comando bloqueado por padrão de segurança: {pattern}"
        except re.error:
            pass

    # Check timeout limit
    max_timeout = shell_policy.get("max_timeout", 120)
    # (timeout is enforced by the caller, not here)

    return None


def check_path_policy(path: str, mode: str = "read") -> Optional[str]:
    """
    Validate a file path against security policy.
    mode: "read" or "write"
    Returns None if OK, or a string describing the violation.
    """
    if not path:
        return "Caminho vazio"

    policy = _load_policy()
    file_policy = policy.get("files", {})
    normalized = os.path.normpath(path)

    # Check denied paths (exact match or starts with)
    for denied in file_policy.get("denied_paths", []):
        if normalized == denied or normalized.startswith(denied + "/"):
            return f"Acesso negado: '{path}' — caminho protegido"

    # Check denied patterns based on mode
    patterns_key = f"denied_{mode}_patterns"
    for pattern in file_policy.get(patterns_key, []):
        try:
            if re.search(pattern, normalized, re.IGNORECASE):
                return f"Acesso negado: '{path}' — padrão bloqueado ({mode})"
        except re.error:
            pass

    # For write mode: check if path is in allowed_paths
    if mode == "write":
        allowed = file_policy.get("allowed_paths", [])
        if allowed:
            in_allowed = any(
                normalized.startswith(a) or normalized.startswith(os.path.expanduser(a))
                for a in allowed
            )
            if not in_allowed:
                return f"Escrita negada: '{path}' — fora dos caminhos permitidos: {allowed}"

    return None


def check_docker_policy(container: str, command: str = "") -> Optional[str]:
    """
    Validate docker exec parameters against policy.
    Returns None if OK, or a string describing the violation.
    """
    policy = _load_policy()
    docker_policy = policy.get("docker", {})

    # Check container name for injection
    for pattern in docker_policy.get("denied_container_patterns", []):
        try:
            if re.search(pattern, container):
                return f"Nome de container inválido: '{container}' — caracteres proibidos"
        except re.error:
            pass

    # Check command inside container
    if command:
        for denied in docker_policy.get("denied_commands_in_container", []):
            if denied.lower() in command.lower():
                return f"Comando bloqueado no container: '{denied}'"

    return None
