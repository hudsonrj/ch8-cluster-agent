#!/usr/bin/env python3
"""
RAG Metrics Collector — expõe métricas via /api/metrics
Coleta de:
  - avg_query_latency_ms
  - embeddings_count
  - last_indexed_at
  - similarity_threshold (configurável)
  - cache_hit_rate
  - freshness_hours
"""

import json
import logging
import os
import psycopg2
import time
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pathlib import Path
import asyncio

log = logging.getLogger("ch8.rag_metrics")

# PostgreSQL RAG DB
PG_HOST = os.environ.get("RAG_POSTGRES_HOST", "rag-postgres")
PG_PORT = int(os.environ.get("RAG_POSTGRES_PORT", "5432"))
PG_DB = os.environ.get("RAG_POSTGRES_DB", "ragdb")
PG_USER = os.environ.get("RAG_POSTGRES_USER", "raguser")
PG_PASS = os.environ.get("RAG_POSTGRES_PASS", "rag_secure_pass_2026")

SIMILARITY_THRESHOLD = float(os.environ.get("RAG_SIMILARITY_THRESHOLD", "0.7"))

app = FastAPI(title="RAG Metrics API", version="1.0")

class RAGMetrics:
    def __init__(self):
        self.query_times = []
        self.cache_hits = 0
        self.cache_misses = 0
        self.last_query_time = None
    
    def record_query(self, latency_ms: float, cache_hit: bool = False):
        self.query_times.append(latency_ms)
        if len(self.query_times) > 1000:
            self.query_times = self.query_times[-1000:]
        if cache_hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1
        self.last_query_time = datetime.utcnow()
    
    def get_avg_latency(self) -> float:
        return sum(self.query_times) / len(self.query_times) if self.query_times else 0.0
    
    def get_p95_latency(self) -> float:
        if not self.query_times:
            return 0.0
        sorted_times = sorted(self.query_times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[idx]
    
    def get_cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total * 100) if total > 0 else 0.0

metrics = RAGMetrics()

def get_pg_connection():
    try:
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            database=PG_DB,
            user=PG_USER,
            password=PG_PASS
        )
        return conn
    except Exception as e:
        log.error(f"Failed to connect to RAG PostgreSQL: {e}")
        return None

@app.get("/api/metrics")
async def get_rag_metrics():
    """Return RAG system metrics."""
    try:
        conn = get_pg_connection()
        if not conn:
            return JSONResponse(
                status_code=503,
                content={"error": "Cannot connect to RAG DB", "status": "degraded"}
            )
        
        cur = conn.cursor()
        
        # Count embeddings
        cur.execute("SELECT COUNT(*) FROM kb_embeddings;")
        embeddings_count = cur.fetchone()[0]
        
        # Get last indexed time
        cur.execute("SELECT MAX(created_at) FROM kb_embeddings;")
        last_indexed_raw = cur.fetchone()[0]
        last_indexed_at = last_indexed_raw.isoformat() if last_indexed_raw else None
        
        # Calculate freshness
        freshness_hours = 0
        if last_indexed_raw:
            delta = datetime.utcnow() - last_indexed_raw.replace(tzinfo=None)
            freshness_hours = delta.total_seconds() / 3600
        
        # Get unique articles
        cur.execute("SELECT COUNT(DISTINCT article_id) FROM kb_embeddings;")
        unique_articles = cur.fetchone()[0]
        
        cur.close()
        conn.close()
        
        return {
            "status": "ok",
            "timestamp": datetime.utcnow().isoformat(),
            "rag": {
                "embeddings_count": embeddings_count,
                "unique_articles": unique_articles,
                "last_indexed_at": last_indexed_at,
                "freshness_hours": round(freshness_hours, 2),
                "avg_query_latency_ms": round(metrics.get_avg_latency(), 2),
                "p95_query_latency_ms": round(metrics.get_p95_latency(), 2),
                "cache_hit_rate_percent": round(metrics.get_cache_hit_rate(), 2),
                "similarity_threshold": SIMILARITY_THRESHOLD
            }
        }
    except Exception as e:
        log.error(f"Error collecting metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/metrics/query")
async def record_query(latency_ms: float, cache_hit: bool = False):
    """Record a query latency."""
    metrics.record_query(latency_ms, cache_hit)
    return {"status": "recorded", "latency_ms": latency_ms}

@app.get("/health")
async def health():
    return {"status": "ok", "service": "rag_metrics_collector"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8096)
