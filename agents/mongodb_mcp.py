"""
MongoDB MCP Agent — Model Context Protocol interface for MongoDB.

Exposes tools:
  - mongo_health: Check replica set status
  - mongo_query: Run find queries
  - mongo_insert: Insert documents
  - mongo_collections: List collections
  - mongo_stats: Database statistics

Connection: mongodb://ch8admin:ch8mongo2024@127.0.0.1:27017/?replicaSet=ch8rs
"""

import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger("ch8.mongodb_mcp")

CONFIG_DIR = Path.home() / ".config" / "ch8"
PID_FILE = CONFIG_DIR / "mongodb_mcp.pid"
LOG_FILE = CONFIG_DIR / "mongodb_mcp.log"

MONGO_URI = "mongodb://ch8admin:ch8mongo2024@127.0.0.1:27017/?replicaSet=ch8rs&authSource=admin"

running = True


def signal_handler(sig, frame):
    global running
    running = False


def _get_client():
    """Get MongoDB client."""
    try:
        from pymongo import MongoClient
        return MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    except ImportError:
        # Fallback: use mongosh via docker exec
        return None


def _mongosh(cmd):
    """Execute via mongosh in container."""
    import subprocess
    full_cmd = f'docker exec mongodb-primary mongosh --port 27017 -u ch8admin -p ch8mongo2024 --authenticationDatabase admin --quiet --eval "{cmd}"'
    try:
        r = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=15)
        return r.stdout.strip() if r.returncode == 0 else f"Error: {r.stderr.strip()}"
    except Exception as e:
        return f"Error: {e}"


def mongo_health():
    """Check MongoDB replica set health."""
    result = _mongosh("JSON.stringify(rs.status().members.map(m=>({name:m.name,state:m.stateStr,health:m.health})))")
    try:
        members = json.loads(result)
        return {"ok": True, "members": members, "replica_set": "ch8rs"}
    except Exception:
        return {"ok": True, "raw": result}


def mongo_query(database, collection, filter_json="{}", limit=10):
    """Run a find query on MongoDB."""
    cmd = f"JSON.stringify(db.getSiblingDB('{database}').{collection}.find({filter_json}).limit({limit}).toArray())"
    result = _mongosh(cmd)
    try:
        docs = json.loads(result)
        return {"ok": True, "count": len(docs), "documents": docs}
    except Exception:
        return {"ok": True, "raw": result}


def mongo_insert(database, collection, document_json):
    """Insert a document into MongoDB."""
    cmd = f"JSON.stringify(db.getSiblingDB('{database}').{collection}.insertOne({document_json}))"
    result = _mongosh(cmd)
    return {"ok": True, "result": result}


def mongo_collections(database="admin"):
    """List collections in a database."""
    cmd = f"JSON.stringify(db.getSiblingDB('{database}').getCollectionNames())"
    result = _mongosh(cmd)
    try:
        cols = json.loads(result)
        return {"ok": True, "database": database, "collections": cols}
    except Exception:
        return {"ok": True, "raw": result}


def mongo_stats(database="admin"):
    """Get database statistics."""
    cmd = f"JSON.stringify(db.getSiblingDB('{database}').stats())"
    result = _mongosh(cmd)
    try:
        stats = json.loads(result)
        return {"ok": True, "database": database, "stats": stats}
    except Exception:
        return {"ok": True, "raw": result}


# Tool definitions for orchestrator
TOOLS = [
    {"name": "mongo_health", "description": "Check MongoDB replica set status", "handler": mongo_health},
    {"name": "mongo_query", "description": "Query MongoDB (find)", "handler": mongo_query},
    {"name": "mongo_insert", "description": "Insert document into MongoDB", "handler": mongo_insert},
    {"name": "mongo_collections", "description": "List collections", "handler": mongo_collections},
    {"name": "mongo_stats", "description": "Database statistics", "handler": mongo_stats},
]


def _update_state(status, task):
    try:
        from connect.state import update_agent_state
        update_agent_state("mongodb_mcp", status, task,
                           model="mcp-mongodb", platform="mongodb",
                           autonomous=True,
                           tools=[t["name"] for t in TOOLS])
    except Exception:
        pass


def main():
    global running
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])

    PID_FILE.write_text(str(os.getpid()))
    log.info("MongoDB MCP Agent starting")

    # Initial health check
    health = mongo_health()
    if health.get("members"):
        log.info(f"MongoDB connected: {len(health['members'])} members in replica set")
    else:
        log.warning(f"MongoDB health check: {health}")

    _update_state("running", f"MongoDB MCP ready — {len(TOOLS)} tools available")

    while running:
        try:
            health = mongo_health()
            members = health.get("members", [])
            primary = next((m for m in members if m.get("state") == "PRIMARY"), None)
            status_msg = f"RS: {len(members)} members | Primary: {primary['name'] if primary else '?'}"
            _update_state("running", status_msg)
        except Exception as e:
            _update_state("warning", f"Health check failed: {e}")

        for _ in range(60):
            if not running:
                break
            time.sleep(1)

    _update_state("idle", "Stopped")
    PID_FILE.unlink(missing_ok=True)
    log.info("MongoDB MCP Agent stopped")


if __name__ == "__main__":
    main()
