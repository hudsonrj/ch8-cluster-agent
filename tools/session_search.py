
import logging, os
log = logging.getLogger("ch8.session_search")

def session_search(query: str, limit: int = 5) -> dict:
    try:
        import psycopg2
        db_url = os.environ.get("CH8_DB_URL","postgresql://ch8app:ch8cluster2024@127.0.0.1:5432/ch8_cluster")
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        q = " & ".join(w for w in query.split() if len(w) > 2)
        if not q:
            return {"ok": False, "error": "Query too short"}
        cur.execute(
            "SELECT node_id, ts_headline('portuguese', content, to_tsquery('portuguese', %s), 'MaxWords=40') as snippet, "
            "logged_at, ts_rank(to_tsvector('portuguese', content), to_tsquery('portuguese', %s)) as score "
            "FROM chat_messages WHERE to_tsvector('portuguese', content) @@ to_tsquery('portuguese', %s) "
            "ORDER BY score DESC LIMIT %s",
            (q, q, q, limit))
        results = [{"node":r[0],"snippet":r[1],"ts":str(r[2]),"score":float(r[3])} for r in cur.fetchall()]
        conn.close()
        return {"ok": True, "query": query, "results": results, "count": len(results)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
