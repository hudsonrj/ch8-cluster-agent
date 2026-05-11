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


# ═══════════════════════════════════════════════════════════════
# SQL Injection Protection
# ═══════════════════════════════════════════════════════════════

_SQL_INJECTION_PATTERNS = [
    r"'\s*OR\s+['\d]",              # ' OR '1'='1
    r"'\s*OR\s+\d\s*=\s*\d",       # ' OR 1=1
    r";\s*DROP\s+",                 # ; DROP TABLE
    r";\s*DELETE\s+FROM\s+",        # ; DELETE FROM
    r";\s*INSERT\s+INTO\s+",       # ; INSERT INTO (unauthorized)
    r";\s*UPDATE\s+.*SET\s+",      # ; UPDATE x SET
    r";\s*ALTER\s+",               # ; ALTER TABLE/ROLE
    r";\s*CREATE\s+",             # ; CREATE (unauthorized)
    r"UNION\s+SELECT",            # UNION SELECT
    r"UNION\s+ALL\s+SELECT",      # UNION ALL SELECT
    r"INTO\s+OUTFILE",            # INTO OUTFILE
    r"INTO\s+DUMPFILE",           # INTO DUMPFILE
    r"LOAD_FILE\s*\(",            # LOAD_FILE()
    r"BENCHMARK\s*\(",            # BENCHMARK() DoS
    r"SLEEP\s*\(\s*\d+\s*\)",    # SLEEP() DoS
    r"pg_sleep\s*\(",             # pg_sleep() DoS
    r"--\s*$",                    # SQL comment at end
    r"/\*.*\*/",                  # Block comments
    r"\\x27",                     # Hex-encoded quote
    r"%27",                       # URL-encoded quote
    r"EXEC\s*\(",                 # EXEC() SQL Server
    r"xp_cmdshell",              # SQL Server RCE
    r"COPY\s+.*TO\s+",          # COPY TO (data exfiltration)
    r"COPY\s+.*FROM\s+",        # COPY FROM (data injection)
]


def check_sql_injection(input_str: str) -> Optional[str]:
    """
    Detect SQL injection attempts in user input.
    Returns None if safe, or description of the violation.
    """
    if not input_str:
        return None

    for pattern in _SQL_INJECTION_PATTERNS:
        try:
            if re.search(pattern, input_str, re.IGNORECASE):
                log.warning(f"SQL injection detected: pattern={pattern} input={input_str[:80]}")
                return f"SQL injection bloqueado: padrão suspeito detectado"
        except re.error:
            pass

    return None


def sanitize_sql_param(value: str) -> str:
    """
    Sanitize a value for use in SQL queries.
    Escapes single quotes and removes dangerous characters.
    """
    if not value:
        return ""
    # Remove null bytes
    value = value.replace("\x00", "")
    # Escape single quotes (double them for SQL)
    value = value.replace("'", "''")
    # Remove semicolons (prevents statement chaining)
    value = value.replace(";", "")
    # Remove comment sequences
    value = re.sub(r"--", "", value)
    value = re.sub(r"/\*.*?\*/", "", value)
    return value


# ═══════════════════════════════════════════════════════════════
# Prompt Injection Protection
# ═══════════════════════════════════════════════════════════════

_PROMPT_INJECTION_PATTERNS = [
    # Direct instruction override attempts
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"ignore\s+(all\s+)?above\s+instructions",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?previous",
    r"ignore\s+your\s+system\s+prompt",
    r"ignore\s+your\s+rules",
    r"new\s+instructions?\s*:",
    r"system\s*:\s*you\s+are",
    r"<\s*system\s*>",
    r"\[system\]",
    r"ADMIN\s+MODE",
    r"SUDO\s+MODE",
    r"DEVELOPER\s+MODE",
    r"DAN\s+MODE",
    r"jailbreak",

    # Role manipulation
    r"you\s+are\s+now\s+(a\s+)?different",
    r"pretend\s+you\s+are\s+(a\s+)?different",
    r"act\s+as\s+if\s+you\s+have\s+no\s+restrictions",
    r"from\s+now\s+on\s+you\s+(will|must|should)\s+ignore",

    # Data exfiltration via prompt
    r"reveal\s+your\s+system\s+prompt",
    r"show\s+me\s+your\s+instructions",
    r"what\s+are\s+your\s+system\s+instructions",
    r"print\s+your\s+initial\s+prompt",
    r"output\s+your\s+system\s+message",
    r"display\s+your\s+rules",

    # Encoding tricks
    r"base64\s+decode",
    r"rot13",
    r"\\u0069\\u0067\\u006e",  # unicode "ign" (ignore)

    # Tool abuse via prompt
    r"execute\s+shell_exec.*rm\s+-rf",
    r"run\s+command.*delete",
    r"call\s+tool.*drop\s+table",
]

# Severity levels for prompt injection
_PROMPT_INJECTION_SEVERITY = {
    "ignore": "high",       # Trying to override instructions
    "system": "high",       # Trying to inject system prompts
    "jailbreak": "critical", # Known jailbreak attempts
    "reveal": "medium",     # Trying to extract system prompt
    "role": "medium",       # Role manipulation
    "encoding": "low",      # Encoding tricks
}


def check_prompt_injection(message: str) -> Optional[dict]:
    """
    Detect prompt injection attempts in user messages.
    Returns None if safe, or dict with {violation, severity, pattern}.
    """
    if not message:
        return None

    msg_lower = message.lower()

    for pattern in _PROMPT_INJECTION_PATTERNS:
        try:
            if re.search(pattern, msg_lower, re.IGNORECASE):
                # Determine severity
                severity = "medium"
                for key, sev in _PROMPT_INJECTION_SEVERITY.items():
                    if key in pattern.lower():
                        severity = sev
                        break

                log.warning(f"Prompt injection detected [{severity}]: pattern={pattern} msg={message[:80]}")
                return {
                    "violation": "Prompt injection detectado: tentativa de manipulação bloqueada",
                    "severity": severity,
                    "pattern": pattern,
                }
        except re.error:
            pass

    return None


def sanitize_prompt(message: str) -> str:
    """
    Sanitize a user message to reduce prompt injection risk.
    Removes control characters and known injection markers.
    """
    if not message:
        return ""
    # Remove null bytes and control characters (except newline/tab)
    sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', message)
    # Remove HTML/XML-like tags that could be interpreted as system markers
    sanitized = re.sub(r'<\s*/?system\s*>', '[filtered]', sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r'\[system\]', '[filtered]', sanitized, flags=re.IGNORECASE)
    # Limit length (extremely long prompts are suspicious)
    if len(sanitized) > 10000:
        sanitized = sanitized[:10000] + "\n[...mensagem truncada por segurança]"
    return sanitized
