
import logging, os
from typing import Optional, List
log = logging.getLogger("ch8.skills")
SKILLS_DIR = '/root/.config/ch8/skills'

def skills_list(query: Optional[str] = None) -> dict:
    try:
        import psycopg2
        db_url = os.environ.get("CH8_DB_URL","postgresql://ch8app:ch8cluster2024@127.0.0.1:5432/ch8_cluster")
        conn = psycopg2.connect(db_url); cur = conn.cursor()
        if query:
            q = " & ".join(w for w in query.split() if len(w) > 2)
            cur.execute("SELECT name,description,author,uses FROM ch8_skills WHERE to_tsvector('portuguese',name||' '||COALESCE(description,'')) @@ to_tsquery('portuguese',%s) ORDER BY uses DESC LIMIT 20", (q,))
        else:
            cur.execute("SELECT name,description,author,uses FROM ch8_skills ORDER BY uses DESC LIMIT 50")
        skills = [{"name":r[0],"description":r[1],"author":r[2],"uses":r[3]} for r in cur.fetchall()]
        conn.close()
        return {"ok": True, "skills": skills, "count": len(skills)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def skill_view(name: str) -> dict:
    try:
        import psycopg2
        db_url = os.environ.get("CH8_DB_URL","postgresql://ch8app:ch8cluster2024@127.0.0.1:5432/ch8_cluster")
        conn = psycopg2.connect(db_url); cur = conn.cursor()
        cur.execute("UPDATE ch8_skills SET uses=uses+1 WHERE name=%s RETURNING name,description,content,author,uses", (name,))
        row = cur.fetchone(); conn.commit(); conn.close()
        if not row: return {"ok": False, "error": f"Skill '{name}' not found"}
        return {"ok": True, "name": row[0], "description": row[1], "content": row[2], "author": row[3], "uses": row[4]}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def skill_save(name: str, description: str, content: str, triggers: List[str] = None, author: str = "agent") -> dict:
    try:
        import psycopg2
        from pathlib import Path
        db_url = os.environ.get("CH8_DB_URL","postgresql://ch8app:ch8cluster2024@127.0.0.1:5432/ch8_cluster")
        conn = psycopg2.connect(db_url); cur = conn.cursor()
        cur.execute("INSERT INTO ch8_skills (name,description,triggers,content,author) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (name) DO UPDATE SET description=EXCLUDED.description,content=EXCLUDED.content,updated_at=NOW() RETURNING id", (name,description,triggers or [],content,author))
        sid = cur.fetchone()[0]; conn.commit(); conn.close()
        p = Path(SKILLS_DIR) / name; p.mkdir(parents=True, exist_ok=True)
        (p / "SKILL.md").write_text(content)
        return {"ok": True, "name": name, "id": sid}
    except Exception as e:
        return {"ok": False, "error": str(e)}
