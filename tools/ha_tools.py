
import logging, os
log = logging.getLogger("ch8.ha")

def _ha_headers():
    token = os.environ.get("HASS_TOKEN")
    if not token:
        try:
            import sys; sys.path.insert(0,'/data/ch8-agent')
            from connect.vault import get
            token = get("homeassistant/token")
        except: pass
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"} if token else None

def _ha_url():
    return os.environ.get("HASS_URL","http://homeassistant.local:8123")

def ha_list_entities(domain: str = None) -> dict:
    h = _ha_headers()
    if not h: return {"ok":False,"error":"HASS_TOKEN not configured. Add to vault: ha/token"}
    try:
        import httpx
        url = f"{_ha_url()}/api/states"
        r = httpx.get(url, headers=h, timeout=10)
        entities = r.json()
        if domain: entities = [e for e in entities if e['entity_id'].startswith(domain+'.')]
        return {"ok":True,"entities":[{"id":e["entity_id"],"state":e["state"],"name":e["attributes"].get("friendly_name","")} for e in entities[:50]]}
    except Exception as e: return {"ok":False,"error":str(e)}

def ha_call_service(domain: str, service: str, data: dict = None) -> dict:
    h = _ha_headers()
    if not h: return {"ok":False,"error":"HASS_TOKEN not configured"}
    try:
        import httpx
        r = httpx.post(f"{_ha_url()}/api/services/{domain}/{service}", headers=h, json=data or {}, timeout=10)
        return {"ok": r.status_code < 300, "status": r.status_code}
    except Exception as e: return {"ok":False,"error":str(e)}
