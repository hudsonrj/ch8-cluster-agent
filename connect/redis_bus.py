"""
CH8 Cluster — Redis Bus (cache, filas, pub/sub)

Usa Redis para:
- Cache de catálogo de nós (evita consultar control server a cada request)
- Fila de tarefas pendentes (broadcast queue)
- Pub/Sub de eventos do cluster (node_up, node_down, alert)
- Rate limiting de requests por nó
- Session cache para respostas de LLM recentes

Redis: 127.0.0.1:6379 (ch8-redis container)
"""

import json
import logging
import time
from typing import Optional, List, Dict

log = logging.getLogger("ch8.redis")

REDIS_URL = "redis://127.0.0.1:6379/0"
CACHE_TTL = 30  # seconds
CATALOG_KEY = "ch8:catalog"
TASK_QUEUE = "ch8:tasks"
EVENTS_CHANNEL = "ch8:events"
RESPONSE_CACHE = "ch8:responses"

_redis = None


def _get_redis():
    """Get Redis connection (lazy init)."""
    global _redis
    if _redis is None:
        try:
            import redis
            _redis = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)
            _redis.ping()
        except Exception as e:
            log.debug(f"Redis not available: {e}")
            _redis = None
    return _redis


def is_available() -> bool:
    """Check if Redis is reachable."""
    r = _get_redis()
    if not r:
        return False
    try:
        return r.ping()
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
# Cache — Catálogo de nós
# ═══════════════════════════════════════════════════════════════

def cache_catalog(nodes: List[Dict], ttl: int = CACHE_TTL):
    """Cache the cluster node catalog."""
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(CATALOG_KEY, ttl, json.dumps(nodes))
    except Exception:
        pass


def get_cached_catalog() -> Optional[List[Dict]]:
    """Get cached catalog (None if expired/missing)."""
    r = _get_redis()
    if not r:
        return None
    try:
        data = r.get(CATALOG_KEY)
        return json.loads(data) if data else None
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# Fila de tarefas
# ═══════════════════════════════════════════════════════════════

def enqueue_task(task: dict):
    """Add a task to the processing queue."""
    r = _get_redis()
    if not r:
        return
    try:
        r.rpush(TASK_QUEUE, json.dumps(task))
    except Exception:
        pass


def dequeue_task() -> Optional[dict]:
    """Get next task from queue (FIFO)."""
    r = _get_redis()
    if not r:
        return None
    try:
        data = r.lpop(TASK_QUEUE)
        return json.loads(data) if data else None
    except Exception:
        return None


def queue_length() -> int:
    """Get number of pending tasks."""
    r = _get_redis()
    if not r:
        return 0
    try:
        return r.llen(TASK_QUEUE)
    except Exception:
        return 0


# ═══════════════════════════════════════════════════════════════
# Pub/Sub — Eventos do cluster
# ═══════════════════════════════════════════════════════════════

def publish_event(event_type: str, data: dict):
    """Publish a cluster event (node_up, node_down, alert, broadcast_done)."""
    r = _get_redis()
    if not r:
        return
    try:
        payload = json.dumps({"type": event_type, "data": data, "ts": time.time()})
        r.publish(EVENTS_CHANNEL, payload)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# Response Cache — LLM responses
# ═══════════════════════════════════════════════════════════════

def cache_response(prompt_hash: str, response: str, ttl: int = 300):
    """Cache an LLM response (5 min default)."""
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(f"{RESPONSE_CACHE}:{prompt_hash}", ttl, response)
    except Exception:
        pass


def get_cached_response(prompt_hash: str) -> Optional[str]:
    """Get cached LLM response."""
    r = _get_redis()
    if not r:
        return None
    try:
        return r.get(f"{RESPONSE_CACHE}:{prompt_hash}")
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# Rate Limiting
# ═══════════════════════════════════════════════════════════════

def check_rate_limit(node_id: str, max_per_minute: int = 10) -> bool:
    """Check if a node has exceeded its rate limit. Returns True if OK."""
    r = _get_redis()
    if not r:
        return True  # allow if Redis down
    try:
        key = f"ch8:rate:{node_id}"
        current = r.incr(key)
        if current == 1:
            r.expire(key, 60)
        return current <= max_per_minute
    except Exception:
        return True


# ═══════════════════════════════════════════════════════════════
# Métricas rápidas
# ═══════════════════════════════════════════════════════════════

def set_metric(name: str, value, ttl: int = 60):
    """Store a quick metric in Redis."""
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(f"ch8:metric:{name}", ttl, json.dumps(value))
    except Exception:
        pass


def get_metric(name: str):
    """Get a stored metric."""
    r = _get_redis()
    if not r:
        return None
    try:
        data = r.get(f"ch8:metric:{name}")
        return json.loads(data) if data else None
    except Exception:
        return None
