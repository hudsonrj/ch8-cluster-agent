"""
CH8 Cluster — Rate Limiter

Redis-based sliding window rate limiting per endpoint + source IP.
Returns 429 Too Many Requests if limit exceeded.
"""

import logging
import time
from typing import Optional, Tuple

log = logging.getLogger("ch8.rate_limit")

# Limits: (max_requests, window_seconds)
RATE_LIMITS = {
    "/execute":       (10, 60),     # 10 per minute
    "/chat":          (30, 60),     # 30 per minute
    "/cluster/task":  (5, 60),      # 5 per minute
    "/cluster/update": (2, 300),    # 2 per 5 minutes
    "/update":        (3, 300),     # 3 per 5 minutes
    "/create-agent":  (5, 300),     # 5 per 5 minutes
    "/relay/forward": (20, 60),     # 20 per minute
}


def check_rate_limit(path: str, source_ip: str = "unknown") -> Tuple[bool, Optional[str]]:
    """
    Check if a request is within rate limits.
    Returns (allowed: bool, error_message: Optional[str])
    """
    # Find matching limit
    limit_config = None
    for prefix, config in RATE_LIMITS.items():
        if path.startswith(prefix):
            limit_config = config
            break

    if not limit_config:
        return True, None  # No limit configured for this path

    max_requests, window_seconds = limit_config

    try:
        from .redis_bus import _get_redis
        r = _get_redis()
        if not r:
            return True, None  # Allow if Redis unavailable

        key = f"ch8:rate:{path}:{source_ip}"
        current = r.incr(key)
        if current == 1:
            r.expire(key, window_seconds)

        if current > max_requests:
            remaining_ttl = r.ttl(key)
            log.warning(f"Rate limit exceeded: {path} from {source_ip} ({current}/{max_requests} in {window_seconds}s)")
            return False, f"Rate limit exceeded: {max_requests} requests per {window_seconds}s. Retry in {remaining_ttl}s."

        return True, None

    except Exception as e:
        log.debug(f"Rate limit check failed: {e}")
        return True, None  # Allow on error


def get_rate_info(path: str, source_ip: str = "unknown") -> dict:
    """Get current rate limit status for a path+IP."""
    limit_config = None
    for prefix, config in RATE_LIMITS.items():
        if path.startswith(prefix):
            limit_config = config
            break

    if not limit_config:
        return {"limited": False, "limit": None}

    max_requests, window = limit_config
    try:
        from .redis_bus import _get_redis
        r = _get_redis()
        if not r:
            return {"limited": False, "limit": f"{max_requests}/{window}s"}
        key = f"ch8:rate:{path}:{source_ip}"
        current = int(r.get(key) or 0)
        return {
            "limited": current >= max_requests,
            "current": current,
            "limit": max_requests,
            "window": window,
            "remaining": max(0, max_requests - current),
        }
    except Exception:
        return {"limited": False}
