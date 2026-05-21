
import logging, os, json
from typing import Optional
log = logging.getLogger("ch8.kanban")

def _db():
    import psycopg2
    return psycopg2.connect(os.environ.get("CH8_DB_URL","postgresql://ch8app:ch8cluster2024@127.0.0.1:5432/ch8_cluster"))

def kanban_create(title: str, assignee: str = None, priority: str = "medium", description: str = "") -> dict:
    conn = _db(); cur = conn.cursor()
    cur.execute("INSERT INTO kanban_tasks (title,description,assignee,priority,created_by) VALUES (%s,%s,%s,%s,'agent') RETURNING id", (title,description,assignee,priority))
    tid = cur.fetchone()[0]; conn.commit(); conn.close()
    return {"ok": True, "id": tid, "title": title}

def kanban_show() -> dict:
    conn = _db(); cur = conn.cursor()
    cur.execute("SELECT id,title,assignee,priority,status FROM kanban_tasks WHERE status NOT IN ('done','cancelled') ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, created_at")
    tasks = [{"id":r[0],"title":r[1],"assignee":r[2],"priority":r[3],"status":r[4]} for r in cur.fetchall()]
    conn.close()
    return {"ok": True, "tasks": tasks, "count": len(tasks)}

def kanban_complete(task_id: int, result: str = "") -> dict:
    conn = _db(); cur = conn.cursor()
    cur.execute("UPDATE kanban_tasks SET status='done', result=%s, completed_at=NOW(), updated_at=NOW() WHERE id=%s RETURNING title", (result, task_id))
    row = cur.fetchone(); conn.commit(); conn.close()
    return {"ok": bool(row), "id": task_id, "title": row[0] if row else None}

def kanban_block(task_id: int, reason: str) -> dict:
    conn = _db(); cur = conn.cursor()
    cur.execute("UPDATE kanban_tasks SET status='blocked', blocked_reason=%s, updated_at=NOW() WHERE id=%s", (reason, task_id))
    conn.commit(); conn.close()
    return {"ok": True, "id": task_id}

def kanban_heartbeat(task_id: int) -> dict:
    conn = _db(); cur = conn.cursor()
    cur.execute("UPDATE kanban_tasks SET last_heartbeat=NOW(), status='in_progress', updated_at=NOW() WHERE id=%s", (task_id,))
    conn.commit(); conn.close()
    return {"ok": True}

def kanban_comment(task_id: int, msg: str, author: str = "agent") -> dict:
    conn = _db(); cur = conn.cursor()
    import datetime
    comment = {"author": author, "msg": msg, "ts": datetime.datetime.now().isoformat()}
    cur.execute("UPDATE kanban_tasks SET comments=comments || %s::jsonb, updated_at=NOW() WHERE id=%s", (json.dumps([comment]), task_id))
    conn.commit(); conn.close()
    return {"ok": True}
