"""
CH8 Web Tools — web_search e web_extract para agents
Suporte primario: Brave Search API (vault: brave/api_key)
Fallback: DuckDuckGo (sem API key)
"""
import logging
import json
from typing import Optional

log = logging.getLogger("ch8.web_tools")


def _get_brave_api_key() -> Optional[str]:
    try:
        from connect.vault import get as vault_get
        return vault_get("brave/api_key")
    except Exception:
        return None


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


def _brave_search(query: str, max_results: int, api_key: str) -> list:
    """Busca via Brave Search API."""
    import httpx
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    params = {"q": query, "count": min(max_results, 20)}
    r = httpx.get("https://api.search.brave.com/res/v1/web/search",
                  headers=headers, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    results = []
    for item in data.get("web", {}).get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": (item.get("description") or "")[:300],
        })
    return results


def _ddg_search(query: str, max_results: int) -> list:
    """Fallback: busca via DuckDuckGo."""
    from duckduckgo_search import DDGS
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", "")[:300],
            })
    return results


def web_search(query: str, max_results: int = 5) -> dict:
    """Busca na web. Usa Brave Search API se disponivel, senao DuckDuckGo."""
    cached = _get_cache(f"search:{query}")
    if cached:
        return json.loads(cached)

    results = []
    engine = "unknown"

    # Try Brave first
    api_key = _get_brave_api_key()
    if api_key:
        try:
            results = _brave_search(query, max_results, api_key)
            engine = "brave"
            log.info(f"web_search (brave): {len(results)} results for '{query[:50]}'")
        except Exception as e:
            log.warning(f"Brave search failed, falling back to DDG: {e}")

    # Fallback to DuckDuckGo
    if not results:
        try:
            results = _ddg_search(query, max_results)
            engine = "duckduckgo"
            log.info(f"web_search (ddg): {len(results)} results for '{query[:50]}'")
        except ImportError:
            return {"ok": False, "error": "No search engine available. Install duckduckgo-search or configure Brave API key."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    out = {"ok": True, "query": query, "results": results, "count": len(results), "engine": engine}
    _set_cache(f"search:{query}", json.dumps(out), ttl=1800)
    return out

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web using Brave Search API (primary) or DuckDuckGo (fallback). Returns list of results with title, url, and snippet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Maximum results to return (default: 5)", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_extract",
            "description": "Extract clean text content from a web page URL. Useful for reading articles, docs, or any webpage in detail.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to extract content from"},
                },
                "required": ["url"],
            },
        },
    },
]


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
