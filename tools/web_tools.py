"""
CH8 Web Tools — web_search e web_extract para agents
Inspirado no Hermes Agent (nousresearch/hermes-agent)
"""
import logging
import json
import time
from typing import Optional

log = logging.getLogger("ch8.web_tools")

# Redis cache
def _get_cache(key: str) -> Optional[str]:
    try:
        import redis
        r = redis.Redis(host='127.0.0.1', port=6379, decode_responses=True)
        return r.get(f"web_cache:{key[:100]}")
    except Exception:
        return None

def _set_cache(key: str, value: str, ttl: int = 1800):
    try:
        import redis
        r = redis.Redis(host='127.0.0.1', port=6379, decode_responses=True)
        r.setex(f"web_cache:{key[:100]}", ttl, value)
    except Exception:
        pass

def web_search(query: str, max_results: int = 5) -> dict:
    """Busca na web via DuckDuckGo (sem API key necessária)."""
    cached = _get_cache(f"search:{query}")
    if cached:
        return json.loads(cached)
    
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", "")[:300]
                })
        
        out = {"ok": True, "query": query, "results": results, "count": len(results)}
        _set_cache(f"search:{query}", json.dumps(out), ttl=1800)
        log.info(f"web_search: {len(results)} results for '{query[:50]}'")
        return out
    except ImportError:
        return {"ok": False, "error": "duckduckgo-search not installed. Run: pip install duckduckgo-search"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def web_extract(url: str) -> dict:
    """Extrai texto limpo de uma URL (sem JS rendering)."""
    cached = _get_cache(f"extract:{url}")
    if cached:
        return json.loads(cached)
    
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded, include_links=False, 
                                        include_images=False, no_fallback=False)
            if text:
                out = {"ok": True, "url": url, "text": text[:5000], "length": len(text)}
                _set_cache(f"extract:{url}", json.dumps(out), ttl=7200)
                return out
    except ImportError:
        pass
    
    # Fallback: requests + BeautifulSoup
    try:
        import requests
        from bs4 import BeautifulSoup
        r = requests.get(url, timeout=15, headers={"User-Agent": "CH8Bot/1.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        # Remove scripts and styles
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())
        out = {"ok": True, "url": url, "text": text[:5000], "length": len(text)}
        _set_cache(f"extract:{url}", json.dumps(out), ttl=7200)
        return out
    except Exception as e:
        return {"ok": False, "url": url, "error": str(e)}
