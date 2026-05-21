
import logging, os, base64
log = logging.getLogger("ch8.image")

def image_generate(prompt: str, size: str = "1024x1024", quality: str = "standard") -> dict:
    """Gera imagem via DALL-E 3 (requer OPENAI_API_KEY) ou retorna fallback."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        try:
            import sys; sys.path.insert(0, '/data/ch8-agent')
            from connect.vault import get
            api_key = get("openai/api_key")
        except: pass
    if not api_key:
        return {"ok": False, "error": "OPENAI_API_KEY not configured. Add to vault: vault set openai/api_key <key>"}
    try:
        import httpx
        r = httpx.post("https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model":"dall-e-3","prompt":prompt,"n":1,"size":size,"quality":quality},
            timeout=60)
        d = r.json()
        url = d["data"][0]["url"]
        return {"ok": True, "url": url, "prompt": prompt, "revised_prompt": d["data"][0].get("revised_prompt","")}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def vision_analyze(image_url: str, question: str = "Descreva esta imagem em detalhes") -> dict:
    """Analisa imagem com Claude Vision."""
    try:
        import httpx, json
        from pathlib import Path
        auth = json.load(open('/root/.config/ch8/auth.json'))['access_token']
        r = httpx.post("http://127.0.0.1:8081/api/chat",
            headers={"Authorization": f"Bearer {auth}", "Content-Type": "application/json"},
            json={"messages":[{"role":"user","content":[
                {"type":"image_url","image_url":{"url":image_url}},
                {"type":"text","text":question}
            ]}]}, timeout=30)
        d = r.json()
        return {"ok": True, "analysis": d.get('reply', d.get('response',''))}
    except Exception as e:
        return {"ok": False, "error": str(e)}
