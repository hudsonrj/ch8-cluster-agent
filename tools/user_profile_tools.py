
import logging, os
log = logging.getLogger("ch8.user_profile")

def profile_get(key: str):
    try:
        import psycopg2
        db_url = os.environ.get("CH8_DB_URL","postgresql://ch8app:ch8cluster2024@127.0.0.1:5432/ch8_cluster")
        conn = psycopg2.connect(db_url); cur = conn.cursor()
        cur.execute("SELECT value FROM user_profile WHERE key=%s", (key,))
        row = cur.fetchone(); conn.close()
        return row[0] if row else None
    except: return None

def profile_set(key: str, value: str, source: str = "agent", confidence: float = 1.0) -> dict:
    try:
        import psycopg2
        db_url = os.environ.get("CH8_DB_URL","postgresql://ch8app:ch8cluster2024@127.0.0.1:5432/ch8_cluster")
        conn = psycopg2.connect(db_url); cur = conn.cursor()
        cur.execute("INSERT INTO user_profile (key,value,confidence,source) VALUES (%s,%s,%s,%s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value,confidence=EXCLUDED.confidence,updated_at=NOW()", (key,value,confidence,source))
        conn.commit(); conn.close()
        return {"ok": True, "key": key}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def profile_context() -> str:
    try:
        import psycopg2
        db_url = os.environ.get("CH8_DB_URL","postgresql://ch8app:ch8cluster2024@127.0.0.1:5432/ch8_cluster")
        conn = psycopg2.connect(db_url); cur = conn.cursor()
        cur.execute("SELECT key, value FROM user_profile WHERE confidence >= 0.7 ORDER BY updated_at DESC LIMIT 12")
        prefs = dict(cur.fetchall()); conn.close()
        if not prefs: return ""
        return "[Contexto do usuário]\n" + "\n".join(f"- {k}: {v}" for k,v in prefs.items())
    except: return ""
