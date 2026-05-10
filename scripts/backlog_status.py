#!/usr/bin/env python3
"""Output backlog status as JSON to stdout."""
import json
from pathlib import Path

backlog = Path("/data2/backlog")
items = []
for f in sorted(backlog.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:15]:
    try:
        d = json.loads(f.read_text())
        items.append({
            "file": f.name,
            "project": d.get("project", f.stem),
            "status": d.get("status", "unknown"),
            "severity": d.get("severity", "medium"),
            "category": d.get("category", ""),
            "node": d.get("node", ""),
            "error": d.get("error", "")[:80],
            "attempts": d.get("attempts", 0),
            "auto_generated": d.get("auto_generated", False),
            "created_at": d.get("created_at", "")[:19],
        })
    except Exception:
        pass

counts = {}
for i in items:
    counts[i["status"]] = counts.get(i["status"], 0) + 1

print(json.dumps({
    "items": items,
    "counts": counts,
    "total": len(items),
}))
