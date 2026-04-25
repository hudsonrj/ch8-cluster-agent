"""
CH8 Control Server — FastAPI application.

Acts as the coordination plane for CH8 Connect.
Nodes register here, discover peers, and exchange auth.

Run with:
    uvicorn connect.server.app:app --host 0.0.0.0 --port 8000
Or via Docker:
    docker compose up control-server
"""

import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Header, Depends
from fastapi.responses import HTMLResponse
import time

from .models import (
    NodeRegisterRequest, NodeHeartbeatRequest,
    PreauthTokenCreate, PreauthTokenUse,
    DeviceCodeRequest, DeviceTokenPoll,
)
from .store import NodeStore, AuthStore

app = FastAPI(title="CH8 Control Server", version="1.0.0")

_nodes = NodeStore()
_auth  = AuthStore()

BASE_URL = os.environ.get("CH8_CONTROL_BASE_URL", "https://control.ch8ai.com.br")


# ------------------------------------------------------------------ #
# Auth helpers

def _require_session(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    session = _auth.get_session(token)
    if not session:
        raise HTTPException(401, "Invalid or expired token")
    return session


# ------------------------------------------------------------------ #
# Authentication endpoints

@app.post("/auth/device")
async def auth_device(body: DeviceCodeRequest):
    """Start device-code flow — returns code for user to enter in browser."""
    return _auth.create_device_code(body.node_id, BASE_URL)


@app.post("/auth/token")
async def auth_token(body: DeviceTokenPoll):
    """Poll for device code result."""
    if body.grant_type != "urn:ietf:params:oauth:grant-type:device_code":
        raise HTTPException(400, "unsupported_grant_type")
    result = _auth.poll_device(body.device_code)
    if result is None:
        raise HTTPException(428, "authorization_pending")
    return result


@app.post("/auth/preauth")
async def auth_preauth(body: PreauthTokenUse):
    """Authenticate using a pre-auth token."""
    result = _auth.use_preauth_token(body.token, body.node_id)
    if not result:
        raise HTTPException(401, "Invalid, expired, or revoked token")
    return result


@app.post("/auth/preauth/create")
async def create_preauth_token(body: PreauthTokenCreate,
                               session: dict = Depends(_require_session)):
    """Create a reusable pre-auth token for the caller's network."""
    if session["network_id"] != body.network_id:
        raise HTTPException(403, "Cannot create token for another network")
    return _auth.create_preauth_token(body.network_id, body.label, body.ttl_hours)


# ------------------------------------------------------------------ #
# Browser activation page

@app.get("/connect/activate", response_class=HTMLResponse)
async def activate_page(code: str = ""):
    """Simple page where user enters/confirms device code."""
    return f"""
    <!DOCTYPE html><html><head>
    <title>CH8 Agent — Activate</title>
    <style>
      body {{ font-family: system-ui; background: #050505; color: #f5f5f5;
             display: flex; align-items: center; justify-content: center;
             min-height: 100vh; margin: 0; }}
      .box {{ background: #111; border: 1px solid #222; border-radius: 12px;
              padding: 2.5rem; width: 400px; text-align: center; }}
      h1 {{ font-size: 1.5rem; margin-bottom: 0.5rem; }}
      p  {{ color: #888; margin-bottom: 1.5rem; font-size: 0.95rem; }}
      input {{ width: 100%; padding: 0.75rem 1rem; border-radius: 8px;
               border: 1px solid #333; background: #1a1a1a; color: #fff;
               font-size: 1.1rem; letter-spacing: 0.15em; text-align: center;
               text-transform: uppercase; box-sizing: border-box; }}
      button {{ width: 100%; margin-top: 1rem; padding: 0.75rem;
                background: #0070f3; border: none; border-radius: 8px;
                color: #fff; font-size: 1rem; font-weight: 600; cursor: pointer; }}
      button:hover {{ background: #0051cc; }}
    </style>
    </head><body>
    <div class="box">
      <h1>CH8 Agent</h1>
      <p>Enter the code shown in your terminal to connect this node to your network.</p>
      <form method="POST" action="/connect/activate">
        <input name="code" value="{code}" placeholder="XXXX-0000" maxlength="9" />
        <button type="submit">Activate Node</button>
      </form>
    </div>
    </body></html>
    """


@app.post("/connect/activate")
async def activate_node(request: Request):
    """Process device code activation (form submission)."""
    form = await request.form()
    code = str(form.get("code", "")).strip().upper()
    # In production: validate user is logged in via session cookie.
    # For demo: auto-approve to a default network.
    network_id = "net_default"
    ok = _auth.approve_device(code, network_id)
    if ok:
        return HTMLResponse("<h2 style='color:#10b981;font-family:system-ui'>Node activated! You can close this tab.</h2>")
    return HTMLResponse("<h2 style='color:#ef4444;font-family:system-ui'>Code not found or expired.</h2>", 400)


# ------------------------------------------------------------------ #
# Node endpoints

@app.post("/nodes/register")
async def register_node(body: NodeRegisterRequest,
                        session: dict = Depends(_require_session)):
    if session["network_id"] != body.network_id:
        raise HTTPException(403, "Token does not match network")
    _nodes.register(body.model_dump())
    return {"ok": True, "node_id": body.node_id}


@app.put("/nodes/{node_id}/heartbeat")
async def node_heartbeat(node_id: str,
                         body: NodeHeartbeatRequest,
                         session: dict = Depends(_require_session)):
    ok = _nodes.heartbeat(node_id, body.network_id, body.model_dump())
    if not ok:
        raise HTTPException(404, "Node not registered")
    return {"ok": True}


@app.get("/nodes")
async def list_nodes(network_id: str,
                     session: dict = Depends(_require_session)):
    if session["network_id"] != network_id:
        raise HTTPException(403, "Access denied")
    return {"nodes": _nodes.get_nodes(network_id)}


@app.delete("/nodes/{node_id}")
async def deregister_node(node_id: str,
                          network_id: str,
                          session: dict = Depends(_require_session)):
    if session["network_id"] != network_id:
        raise HTTPException(403, "Access denied")
    _nodes.deregister(node_id, network_id)
    return {"ok": True}


# ------------------------------------------------------------------ #
# Health check

@app.get("/health")
async def health():
    return {"status": "ok", "ts": int(time.time())}
