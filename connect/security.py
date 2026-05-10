"""
CH8 Cluster — Security Middleware

Validates Bearer tokens on all orchestrator endpoints.
Accepted tokens:
  1. Local node token (from ~/.config/ch8/auth.json)
  2. Peer tokens validated via Redis cache + control server

Public endpoints (no auth): /health, /version
All others require: Authorization: Bearer <token>
"""

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import Header, HTTPException, Request

log = logging.getLogger("ch8.security")

CONFIG_DIR = Path(os.environ.get("CH8_CONFIG_DIR", str(Path.home() / ".config" / "ch8")))
AUTH_FILE = CONFIG_DIR / "auth.json"

# Endpoints that don't require authentication
PUBLIC_ENDPOINTS = {"/health", "/version", "/docs", "/openapi.json"}

# Token cache: {token_hash: {"node_id": ..., "validated_at": timestamp}}
_token_cache: dict = {}
_CACHE_TTL = 300  # 5 minutes
_local_token: Optional[str] = None
_local_token_ts: float = 0


def _get_local_token() -> str:
    """Get this node's access token (cached, refreshes every 60s)."""
    global _local_token, _local_token_ts
    now = time.time()
    if _local_token and now - _local_token_ts < 60:
        return _local_token
    try:
        data = json.loads(AUTH_FILE.read_text())
        _local_token = data.get("access_token", "")
        _local_token_ts = now
        return _local_token
    except Exception:
        return ""


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def _validate_via_redis(token: str) -> Optional[dict]:
    """Check if token is in Redis cache of known valid tokens."""
    try:
        from .redis_bus import _get_redis
        r = _get_redis()
        if not r:
            return None
        key = f"ch8:token:{_hash_token(token)}"
        data = r.get(key)
        if data:
            return json.loads(data)
    except Exception:
        pass
    return None


def _cache_valid_token(token: str, info: dict):
    """Cache a validated token in Redis."""
    try:
        from .redis_bus import _get_redis
        r = _get_redis()
        if r:
            key = f"ch8:token:{_hash_token(token)}"
            r.setex(key, _CACHE_TTL, json.dumps(info))
    except Exception:
        pass


def _validate_via_control(token: str) -> Optional[dict]:
    """Validate token against the control server (checks if it's a registered node)."""
    try:
        import httpx
        from .auth import CONTROL_URL
        r = httpx.get(
            f"{CONTROL_URL}/nodes",
            params={"network_id": "net_default"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        if r.status_code == 200:
            return {"node_id": "peer", "validated_at": time.time()}
    except Exception:
        pass
    return None


def require_node_auth(authorization: Optional[str] = Header(None, alias="Authorization")) -> dict:
    """
    FastAPI Dependency — validates that the request carries a valid cluster Bearer token.

    Returns dict with auth info on success, raises 401 on failure.
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Autenticação necessária. Use: Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Formato inválido. Use: Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token vazio")

    # 1. Fast path: is it our own token?
    local = _get_local_token()
    if local and token == local:
        return {"authenticated": True, "node_id": "local", "method": "local_token"}

    # 2. Check Redis cache
    cached = _validate_via_redis(token)
    if cached:
        return {"authenticated": True, **cached, "method": "cache"}

    # 3. Check in-memory cache
    token_hash = _hash_token(token)
    if token_hash in _token_cache:
        entry = _token_cache[token_hash]
        if time.time() - entry.get("validated_at", 0) < _CACHE_TTL:
            return {"authenticated": True, **entry, "method": "memory_cache"}

    # 4. Validate against control server
    result = _validate_via_control(token)
    if result:
        _token_cache[token_hash] = result
        _cache_valid_token(token, result)
        log.info(f"Token validated via control server (hash: {token_hash})")
        return {"authenticated": True, **result, "method": "control_server"}

    # 5. All validation failed
    log.warning(f"Authentication failed for token hash: {token_hash}")
    raise HTTPException(
        status_code=401,
        detail="Token inválido ou expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )


def is_public_endpoint(path: str) -> bool:
    """Check if an endpoint is public (no auth required)."""
    return path in PUBLIC_ENDPOINTS
