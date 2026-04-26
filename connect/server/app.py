"""
CH8 Control Server — FastAPI application + Web Dashboard.
State is persisted to /data/state.json — survives container restarts.
"""

import os
import time
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Header, Depends
from fastapi.responses import HTMLResponse

from .models import (
    NodeRegisterRequest, NodeHeartbeatRequest,
    PreauthTokenCreate, PreauthTokenUse,
    DeviceCodeRequest, DeviceTokenPoll,
)
from .store import NodeStore, AuthStore

app  = FastAPI(title="CH8 Control", version="1.0.0", docs_url="/api/docs")
_auth  = AuthStore()
_nodes = NodeStore()

BASE_URL = os.environ.get("CH8_CONTROL_BASE_URL", "https://control.ch8ai.com.br")


# ── auth helper ────────────────────────────────────────────────────────────

def _require_session(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    session = _auth.get_session(token)
    if not session:
        raise HTTPException(401, "Invalid or expired token")
    return session


# ── dashboard ──────────────────────────────────────────────────────────────

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='20' fill='%230070f3'/><text y='.9em' font-size='70' x='15'>⬡</text></svg>">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CH8 Control</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --bg:#050505; --bg1:#0a0a0a; --bg2:#111; --bg3:#1a1a1a;
  --border:rgba(255,255,255,0.07);
  --blue:#0070f3; --green:#10b981; --yellow:#f59e0b;
  --red:#ef4444; --purple:#7928ca; --cyan:#00b4d8;
  --text:#f0f0f0; --text2:#a1a1aa; --text3:#52525b;
  --mono:'JetBrains Mono',monospace; --sans:'Inter',sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:var(--sans);min-height:100vh}

.topbar{display:flex;align-items:center;gap:1rem;padding:0 2rem;height:56px;
  background:var(--bg1);border-bottom:1px solid var(--border);
  position:sticky;top:0;z-index:100}
.logo{display:flex;align-items:center;gap:.5rem;font-family:var(--mono);
  font-weight:600;font-size:1rem;letter-spacing:.05em}
.logo-dot{width:8px;height:8px;border-radius:50%;background:var(--blue)}
.topbar-title{color:var(--text2);font-size:.8rem}
.topbar-right{margin-left:auto;display:flex;align-items:center;gap:1rem}
.conn-badge{display:flex;align-items:center;gap:.4rem;
  font-family:var(--mono);font-size:.75rem;color:var(--text2)}
.pulse{width:7px;height:7px;border-radius:50%;background:var(--green);
  animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.last-upd{font-family:var(--mono);font-size:.7rem;color:var(--text3)}

.container{max-width:1400px;margin:0 auto;padding:2rem}

.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:1rem;margin-bottom:2rem}
.metric{background:var(--bg2);border:1px solid var(--border);
  border-radius:10px;padding:1.25rem 1.5rem}
.metric-value{font-family:var(--mono);font-size:2rem;font-weight:600;
  line-height:1;margin-bottom:.35rem}
.metric-label{font-size:.75rem;color:var(--text2);text-transform:uppercase;
  letter-spacing:.08em}
.metric.green .metric-value{color:var(--green)}
.metric.blue  .metric-value{color:var(--blue)}
.metric.yellow .metric-value{color:var(--yellow)}
.metric.red   .metric-value{color:var(--red)}

.section-hdr{display:flex;align-items:center;justify-content:space-between;
  margin-bottom:1rem}
.section-title{font-size:.8rem;font-weight:600;text-transform:uppercase;
  letter-spacing:.1em;color:var(--text2)}
.filter-group{display:flex;gap:.5rem}
.filter-btn{padding:.3rem .75rem;border-radius:6px;border:1px solid var(--border);
  background:transparent;color:var(--text2);font-size:.75rem;cursor:pointer;
  transition:all .15s}
.filter-btn:hover,.filter-btn.active{background:var(--blue);
  border-color:var(--blue);color:#fff}

.node-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(390px,1fr));gap:1rem}

.node-card{background:var(--bg2);border:1px solid var(--border);border-radius:12px;
  padding:1.25rem;transition:border-color .2s,opacity .3s}
.node-card:hover{border-color:rgba(255,255,255,.15)}
.node-card.online {border-top:2px solid var(--green)}
.node-card.offline{border-top:2px solid var(--text3);opacity:.55}

.node-header{display:flex;align-items:flex-start;justify-content:space-between;
  margin-bottom:.9rem}
.node-name{font-family:var(--mono);font-weight:600;font-size:.95rem;margin-bottom:.25rem}
.node-id{font-family:var(--mono);font-size:.65rem;color:var(--text3)}
.status-badge{display:inline-flex;align-items:center;gap:.3rem;
  padding:.25rem .6rem;border-radius:20px;font-size:.7rem;font-weight:600;
  font-family:var(--mono);text-transform:uppercase;letter-spacing:.05em;flex-shrink:0}
.status-badge.online {background:rgba(16,185,129,.12);color:var(--green)}
.status-badge.offline{background:rgba(82,82,91,.2);color:var(--text3)}
.status-dot{width:5px;height:5px;border-radius:50%;background:currentColor}

.node-meta{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:.9rem}
.meta-tag{background:var(--bg3);border:1px solid var(--border);border-radius:5px;
  padding:.15rem .5rem;font-family:var(--mono);font-size:.68rem;color:var(--text2)}
.meta-tag.addr  {color:var(--cyan);border-color:rgba(0,180,216,.2);background:rgba(0,180,216,.05)}
.meta-tag.cap   {color:var(--purple);border-color:rgba(121,40,202,.2);background:rgba(121,40,202,.05)}
.meta-tag.model {color:var(--yellow);border-color:rgba(245,158,11,.2);background:rgba(245,158,11,.05)}

.node-metrics{margin-bottom:.9rem}
.meter-row{display:flex;align-items:center;gap:.5rem;margin-bottom:.4rem}
.meter-label{font-family:var(--mono);font-size:.65rem;color:var(--text3);
  width:32px;text-transform:uppercase}
.meter-bar{flex:1;height:3px;background:var(--bg3);border-radius:2px;overflow:hidden}
.meter-fill{height:100%;border-radius:2px;transition:width .6s ease}
.meter-fill.cpu {background:var(--blue)}
.meter-fill.mem {background:var(--purple)}
.meter-fill.disk{background:var(--yellow)}
.meter-fill.hi  {background:var(--red)}
.meter-value{font-family:var(--mono);font-size:.65rem;color:var(--text2);
  width:32px;text-align:right}

.agents-section{margin-bottom:.75rem}
.agents-header{display:flex;align-items:center;gap:.5rem;margin-bottom:.4rem}
.agents-title{font-size:.7rem;font-weight:600;text-transform:uppercase;
  letter-spacing:.08em;color:var(--text3)}
.agents-count{font-family:var(--mono);font-size:.65rem;background:var(--bg3);
  border-radius:10px;padding:.1rem .4rem;color:var(--blue)}
.agent-list{display:flex;flex-direction:column;gap:.3rem}
.agent-item{display:flex;align-items:center;gap:.5rem;background:var(--bg3);
  border-radius:6px;padding:.4rem .6rem}
.agent-dot{width:5px;height:5px;border-radius:50%;flex-shrink:0}
.agent-dot.running{background:var(--green)}
.agent-dot.idle   {background:var(--yellow)}
.agent-dot.error  {background:var(--red)}
.agent-name{font-family:var(--mono);font-size:.72rem;flex:1;min-width:0}
.agent-model{font-family:var(--mono);font-size:.63rem;color:var(--cyan);
  background:rgba(0,180,216,.08);border-radius:4px;padding:.1rem .35rem;
  white-space:nowrap}
.agent-platform{font-family:var(--mono);font-size:.63rem;color:var(--text3);
  white-space:nowrap}
.agent-task{font-family:var(--mono);font-size:.63rem;color:var(--text3);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0}
.no-agents{font-family:var(--mono);font-size:.72rem;color:var(--text3);padding:.3rem 0}

.node-footer{padding-top:.75rem;border-top:1px solid var(--border);
  display:flex;justify-content:space-between;align-items:center}
.node-uptime{font-family:var(--mono);font-size:.65rem;color:var(--text3)}
.node-network{font-family:var(--mono);font-size:.65rem;color:var(--text3)}

.empty-state{grid-column:1/-1;text-align:center;padding:4rem 2rem;color:var(--text3)}
.empty-state h3{font-family:var(--mono);font-size:1rem;margin-bottom:.5rem;color:var(--text2)}
.empty-state p{font-size:.85rem;margin-bottom:1.5rem}
.empty-code{display:inline-block;font-family:var(--mono);font-size:.8rem;
  background:var(--bg2);border:1px solid var(--border);border-radius:8px;
  padding:.75rem 1.5rem;color:var(--cyan)}


/* ── Modal ── */

/* ── Chat modal ── */
.chat-modal{width:min(740px,96vw);max-height:90vh}
.chat-topbar{display:flex;align-items:center;gap:.75rem;padding:.75rem 1.25rem;
  border-bottom:1px solid var(--border);background:var(--bg3);border-radius:0 0 0 0}
.chat-node-name{font-family:var(--mono);font-weight:600;font-size:.9rem;flex:1}
.chat-model-sel{font-family:var(--mono);font-size:.75rem;background:var(--bg2);
  border:1px solid var(--border);border-radius:7px;color:var(--text2);
  padding:.3rem .6rem;cursor:pointer;outline:none}
.chat-model-sel:focus{border-color:var(--blue)}
.chat-messages{flex:1;overflow-y:auto;padding:1.25rem;
  display:flex;flex-direction:column;gap:.85rem;min-height:320px}
.chat-msg{max-width:82%;display:flex;flex-direction:column;gap:.25rem}
.chat-msg.user{align-self:flex-end;align-items:flex-end}
.chat-msg.assistant{align-self:flex-start;align-items:flex-start}
.chat-bubble{padding:.65rem 1rem;border-radius:12px;
  font-size:.875rem;line-height:1.55;white-space:pre-wrap;word-break:break-word}
.chat-msg.user .chat-bubble{background:var(--blue);color:#fff;
  border-bottom-right-radius:3px}
.chat-msg.assistant .chat-bubble{background:var(--bg3);
  border:1px solid var(--border);border-bottom-left-radius:3px}
.chat-msg.assistant.streaming .chat-bubble::after{
  content:'▋';animation:blink .7s step-end infinite;color:var(--blue)}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}
.chat-role{font-family:var(--mono);font-size:.65rem;color:var(--text3)}
.chat-footer{padding:.9rem 1.25rem;border-top:1px solid var(--border);
  display:flex;gap:.6rem;align-items:flex-end}
.chat-input{flex:1;background:var(--bg3);border:1px solid var(--border);
  border-radius:10px;color:var(--text);font-family:var(--sans);font-size:.875rem;
  padding:.65rem .9rem;resize:none;outline:none;max-height:120px;
  transition:border-color .15s;line-height:1.4}
.chat-input:focus{border-color:var(--blue)}
.chat-send{background:var(--blue);border:none;border-radius:9px;
  color:#fff;padding:.65rem 1rem;cursor:pointer;font-size:.85rem;
  font-weight:600;transition:background .15s;white-space:nowrap;
  display:flex;align-items:center;gap:.4rem}
.chat-send:hover{background:#0051cc}
.chat-send:disabled{opacity:.4;cursor:not-allowed}
.chat-empty{text-align:center;padding:2.5rem 1rem;color:var(--text3);
  font-size:.85rem;flex:1;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:.5rem}
.chat-empty .e-icon{font-size:2rem;opacity:.4}
.chat-icon-btn{display:none;background:transparent;border:none;
  color:var(--text3);cursor:pointer;padding:.2rem .35rem;border-radius:5px;
  font-size:.85rem;transition:color .15s;line-height:1}
.node-card.online .chat-icon-btn{display:inline-flex;align-items:center}
.chat-icon-btn:hover{color:var(--blue)}
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);
  z-index:1000;align-items:center;justify-content:center}
.modal-overlay.open{display:flex}
.modal{background:var(--bg2);border:1px solid rgba(255,255,255,.12);border-radius:14px;
  width:min(680px,95vw);max-height:80vh;display:flex;flex-direction:column;
  box-shadow:0 24px 64px rgba(0,0,0,.6)}
.modal-header{display:flex;align-items:center;justify-content:space-between;
  padding:1.25rem 1.5rem;border-bottom:1px solid var(--border)}
.modal-title{font-family:var(--mono);font-weight:600;font-size:.95rem}
.modal-sub{font-size:.75rem;color:var(--text3);margin-top:.2rem}
.modal-close{background:transparent;border:none;color:var(--text3);
  font-size:1.25rem;cursor:pointer;padding:.25rem .5rem;border-radius:6px;
  transition:color .15s}
.modal-close:hover{color:var(--text)}
.modal-body{overflow-y:auto;padding:1.25rem 1.5rem;flex:1}
.svc-row{display:flex;align-items:center;gap:.75rem;padding:.6rem .75rem;
  border-radius:8px;background:var(--bg3);margin-bottom:.5rem}
.svc-row:last-child{margin-bottom:0}
.svc-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.svc-dot.running{background:var(--green)}
.svc-dot.stopped{background:var(--red)}
.svc-name{font-family:var(--mono);font-size:.8rem;font-weight:500;flex:1;min-width:0}
.svc-image{font-family:var(--mono);font-size:.68rem;color:var(--text3);
  max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.svc-type{font-family:var(--mono);font-size:.63rem;padding:.15rem .45rem;
  border-radius:4px;white-space:nowrap}
.svc-type.docker {background:rgba(0,180,216,.1);color:var(--cyan)}
.svc-type.process{background:rgba(121,40,202,.1);color:var(--purple)}
.svc-ports{font-family:var(--mono);font-size:.63rem;color:var(--text3);
  max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.svc-badge{display:inline-flex;align-items:center;gap:.35rem;
  background:var(--bg3);border:1px solid var(--border);border-radius:7px;
  padding:.25rem .65rem;font-family:var(--mono);font-size:.72rem;
  color:var(--text2);cursor:pointer;transition:all .15s;white-space:nowrap}
.svc-badge:hover{border-color:var(--blue);color:var(--blue)}
.svc-badge .dot{width:6px;height:6px;border-radius:50%;background:var(--green)}

/* ── Agent detail modal ── */
.agent-modal{width:min(780px,96vw);max-height:90vh}
.agent-item{cursor:pointer;transition:background .15s}
.agent-item:hover{background:rgba(255,255,255,.05)}
.agent-section{margin-bottom:1.25rem}
.agent-section-title{font-family:var(--mono);font-size:.72rem;font-weight:600;
  text-transform:uppercase;letter-spacing:.08em;color:var(--text3);
  margin-bottom:.5rem;display:flex;align-items:center;gap:.5rem}
.agent-section-title .count{font-size:.65rem;background:var(--bg3);
  border-radius:10px;padding:.1rem .4rem;color:var(--blue)}
.alert-row{display:flex;align-items:flex-start;gap:.6rem;padding:.5rem .7rem;
  border-radius:8px;background:var(--bg3);margin-bottom:.4rem;font-size:.8rem;
  line-height:1.4}
.alert-icon{flex-shrink:0;font-size:.85rem;margin-top:.05rem}
.alert-text{flex:1;font-family:var(--mono);font-size:.75rem;word-break:break-word}
.alert-sev{font-family:var(--mono);font-size:.63rem;padding:.15rem .45rem;
  border-radius:4px;white-space:nowrap;flex-shrink:0}
.alert-sev.critical{background:rgba(239,68,68,.15);color:var(--red)}
.alert-sev.high{background:rgba(245,158,11,.15);color:var(--yellow)}
.alert-sev.medium{background:rgba(0,180,216,.15);color:var(--cyan)}
.alert-sev.warning{background:rgba(245,158,11,.15);color:var(--yellow)}
.alert-sev.low{background:rgba(82,82,91,.2);color:var(--text3)}
.predict-row{display:flex;align-items:center;gap:.5rem;padding:.45rem .7rem;
  border-radius:8px;background:rgba(245,158,11,.06);border:1px solid rgba(245,158,11,.12);
  margin-bottom:.4rem}
.predict-icon{font-size:.85rem;flex-shrink:0}
.predict-text{font-family:var(--mono);font-size:.75rem;color:var(--yellow);flex:1}
.proc-row{display:flex;align-items:center;gap:.6rem;padding:.4rem .7rem;
  border-radius:8px;background:var(--bg3);margin-bottom:.3rem;
  font-family:var(--mono);font-size:.72rem}
.proc-pid{color:var(--text3);width:50px}
.proc-name{color:var(--text);font-weight:500;width:120px;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.proc-cpu{width:55px;text-align:right}
.proc-mem{width:55px;text-align:right}
.proc-cmd{flex:1;color:var(--text3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.action-row{display:flex;align-items:center;gap:.6rem;padding:.55rem .7rem;
  border-radius:8px;background:var(--bg3);border:1px solid var(--border);
  margin-bottom:.4rem}
.action-desc{flex:1;font-family:var(--mono);font-size:.75rem}
.action-cmd{font-family:var(--mono);font-size:.65rem;color:var(--text3);
  padding:.2rem .5rem;background:var(--bg);border-radius:4px;max-width:250px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.action-btn{background:var(--blue);border:none;border-radius:6px;color:#fff;
  padding:.3rem .7rem;font-family:var(--mono);font-size:.7rem;cursor:pointer;
  white-space:nowrap;transition:background .15s}
.action-btn:hover{background:#0051cc}
.action-btn.danger{background:var(--red)}
.action-btn.danger:hover{background:#c92a2a}
.agent-status-banner{display:flex;align-items:center;gap:.6rem;padding:.65rem 1rem;
  border-radius:8px;margin-bottom:1rem}
.agent-status-banner.idle{background:rgba(245,158,11,.08);border:1px solid rgba(245,158,11,.15)}
.agent-status-banner.running{background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.15)}
.agent-status-banner.error{background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.15)}
.agent-status-text{font-family:var(--mono);font-size:.8rem;flex:1}
.agent-status-time{font-family:var(--mono);font-size:.65rem;color:var(--text3)}
@media(max-width:600px){
  .container{padding:1rem}
  .node-grid{grid-template-columns:1fr}
  .metrics{grid-template-columns:repeat(2,1fr)}
}
</style>
</head>
<body>

<header class="topbar">
  <div class="logo"><div class="logo-dot"></div>CH8 Control</div>
  <span class="topbar-title">Coordination Plane</span>
  <div class="topbar-right">
    <div class="conn-badge">
      <div class="pulse" id="pulse"></div>
      <span id="connStatus">connecting</span>
    </div>
    <span class="last-upd" id="lastUpdate">—</span>
  </div>
</header>

<div class="container">
  <div class="metrics" id="metrics">
    <div class="metric blue">  <div class="metric-value" id="mNetworks">—</div><div class="metric-label">Networks</div></div>
    <div class="metric green"> <div class="metric-value" id="mOnline">—</div>  <div class="metric-label">Online Nodes</div></div>
    <div class="metric red">   <div class="metric-value" id="mOffline">—</div> <div class="metric-label">Offline Nodes</div></div>
    <div class="metric yellow"><div class="metric-value" id="mAgents">—</div>  <div class="metric-label">Active Agents</div></div>
  </div>

  <div class="section-hdr">
    <span class="section-title">Nodes</span>
    <div class="filter-group">
      <button class="filter-btn active" onclick="setFilter('all',this)">All</button>
      <button class="filter-btn" onclick="setFilter('online',this)">Online</button>
      <button class="filter-btn" onclick="setFilter('offline',this)">Offline</button>
    </div>
  </div>

  <div class="node-grid" id="nodeGrid">
    <div class="empty-state">
      <h3>Connecting…</h3>
      <p>Waiting for first data from the control server.</p>
    </div>
  </div>
</div>

<script>
let currentFilter = 'all';
let allNodes      = [];
let firstLoad     = true;
const cardMap     = new Map();

function setFilter(f, btn) {
  currentFilter = f;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyFilter();
}

function applyFilter() {
  let anyVisible = false;
  cardMap.forEach((el, id) => {
    const node = allNodes.find(n => n.node_id === id);
    if (!node) return;
    const visible = currentFilter === 'all' || node.status === currentFilter;
    el.style.display = visible ? '' : 'none';
    if (visible) anyVisible = true;
  });
  const grid = document.getElementById('nodeGrid');
  let empty  = grid.querySelector('.empty-state');
  if (!anyVisible && !firstLoad) {
    if (!empty) { empty = document.createElement('div'); empty.className='empty-state'; grid.appendChild(empty); }
    empty.innerHTML = currentFilter !== 'all'
      ? `<h3>No ${currentFilter} nodes</h3>`
      : `<h3>No nodes yet</h3><p>Run <code>ch8 up --token &lt;token&gt;</code> on any machine.</p>`;
  } else if (empty) { empty.remove(); }
}

function ago(ts) {
  const s = Math.floor(Date.now()/1000) - ts;
  if (s<5)    return 'just now';
  if (s<60)   return s+'s ago';
  if (s<3600) return Math.floor(s/60)+'m ago';
  return Math.floor(s/3600)+'h ago';
}
function uptime(ts) {
  const s = Math.floor(Date.now()/1000) - ts;
  if (s<60)   return s+'s';
  if (s<3600) return Math.floor(s/60)+'m';
  const h=Math.floor(s/3600), d=Math.floor(h/24);
  return d>0 ? d+'d '+(h%24)+'h' : h+'h '+Math.floor((s%3600)/60)+'m';
}

function meterFill(pct, cls) {
  const hi = pct > 85 ? ' hi' : '';
  return `<div class="meter-row">
    <span class="meter-label">${cls.toUpperCase()}</span>
    <div class="meter-bar"><div class="meter-fill ${cls}${hi}" style="width:${Math.min(pct,100).toFixed(0)}%"></div></div>
    <span class="meter-value" style="${pct>85?'color:var(--red)':''}">${pct.toFixed(0)}%</span>
  </div>`;
}

function cardHTML(n) {
  const caps = (n.capabilities||[]).filter(c=>c!=='tailscale'&&c!=='worker').map(c=>`<span class="meta-tag cap">${c}</span>`).join('');
  const models = (n.models||[]).map(m=>`<span class="meta-tag model">⬡ ${m}</span>`).join('');
  const agents = n.agents||[];
  const agentRows = agents.length===0
    ? `<div class="no-agents">no active agents</div>`
    : agents.map(a=>`
      <div class="agent-item" data-agent="${a.name}" data-nodeid="${n.node_id}">
        <div class="agent-dot ${a.status||'idle'}"></div>
        <span class="agent-name">${a.name}</span>
        ${a.model    ? `<span class="agent-model">${a.model}</span>` : ''}
        ${a.platform ? `<span class="agent-platform">${a.platform}</span>` : ''}
        <span class="agent-task">${a.task||''}</span>
      </div>`).join('');

  const services = n.services||[];
  const svcRows = services.length===0 ? '' : `
    <div style="margin-top:.6rem">
      <span class="svc-badge" data-nodeid="${n.node_id}">
        <span class="dot"></span>
        ${services.length} service${services.length!==1?'s':''}
      </span>
    </div>`;

  return `
    <div class="node-header">
      <div>
        <div class="node-name">${n.hostname||n.node_id}</div>
        <div class="node-id">${n.node_id}</div>
      </div>
      <div style="display:flex;align-items:center;gap:.5rem">
        <span class="status-badge ${n.status}"><span class="status-dot"></span>${n.status}</span>
        <button class="chat-icon-btn" data-nodeid="${n.node_id}" title="Chat with ${n.hostname||n.node_id}">💬</button>
      </div>
    </div>
    <div class="node-meta">
      <span class="meta-tag addr">${n.address}:${n.port}</span>
      <span class="meta-tag">${n.os||'?'} / ${n.arch||'?'}</span>
      ${n.version ? `<span class="meta-tag">v${n.version}</span>` : ''}
      ${caps}${models}
    </div>
    <div class="node-metrics">
      ${meterFill(n.cpu_pct||0,'cpu')}
      ${meterFill(n.mem_pct||0,'mem')}
      ${meterFill(n.disk_pct||0,'disk')}
    </div>
    <div class="agents-section">
      <div class="agents-header">
        <span class="agents-title">Agents</span>
        <span class="agents-count">${agents.length}</span>
      </div>
      <div class="agent-list">${agentRows}</div>
    </div>
    <div class="node-footer">
      <span class="node-uptime">up ${uptime(n.registered_at)} · seen ${ago(n.last_seen)}</span>
      <span class="node-network">${n.network_id}</span>
    </div>
    ${svcRows}`;
}

function syncGrid(nodes) {
  const grid = document.getElementById('nodeGrid');
  const ids  = new Set(nodes.map(n => n.node_id));

  for (const n of nodes) {
    let el = cardMap.get(n.node_id);
    if (!el) {
      el = document.createElement('div');
      el.dataset.nodeId = n.node_id;
      cardMap.set(n.node_id, el);
      grid.appendChild(el);
    }
    el.className = `node-card ${n.status}`;
    el.innerHTML  = cardHTML(n);
  }

  for (const [id, el] of cardMap) {
    if (!ids.has(id)) { el.remove(); cardMap.delete(id); }
  }

  applyFilter();
}

function tickTimestamps() {
  for (const [id, el] of cardMap) {
    const node = allNodes.find(n => n.node_id === id);
    if (!node) continue;
    const f = el.querySelector('.node-uptime');
    if (f) f.textContent = `up ${uptime(node.registered_at)} · seen ${ago(node.last_seen)}`;
  }
}

function openSvcModal(nodeId) {
  const node     = allNodes.find(n => n.node_id === nodeId);
  if (!node) return;
  const services = node.services || [];

  document.getElementById('modalTitle').textContent =
    `${node.hostname || nodeId} — Services`;
  document.getElementById('modalSub').textContent =
    `${services.filter(s=>s.status==='running').length} running · ${services.length} total`;

  const body = document.getElementById('modalBody');
  if (services.length === 0) {
    body.innerHTML = '<p style="color:var(--text3);font-family:var(--mono);font-size:.85rem">No services detected</p>';
  } else {
    // Group: docker first, then process
    const docker  = services.filter(s=>s.type==='docker');
    const procs   = services.filter(s=>s.type!=='docker');
    const sections = [];
    if (docker.length) {
      sections.push(`<div style="font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;color:var(--text3);margin-bottom:.5rem;font-weight:600">Docker Containers</div>`);
      sections.push(...docker.map(s=>`
        <div class="svc-row">
          <div class="svc-dot ${s.status}"></div>
          <span class="svc-name">${s.name}</span>
          <span class="svc-image">${s.image||''}</span>
          <span class="svc-type docker">docker</span>
          ${s.ports ? `<span class="svc-ports">${s.ports.split(',')[0]}</span>` : ''}
        </div>`));
    }
    if (procs.length) {
      sections.push(`<div style="font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;color:var(--text3);margin:.75rem 0 .5rem;font-weight:600">System Processes</div>`);
      sections.push(...procs.map(s=>`
        <div class="svc-row">
          <div class="svc-dot ${s.status}"></div>
          <span class="svc-name">${s.name}</span>
          <span class="svc-type process">process</span>
        </div>`));
    }
    body.innerHTML = sections.join('');
  }
  document.getElementById('svcModal').classList.add('open');
}

function closeModal() {
  document.getElementById('svcModal').classList.remove('open');
}

document.addEventListener('keydown', e => { if (e.key==='Escape') { closeModal(); closeChatModal(); closeAgentModal(); } });
// ── Chat ─────────────────────────────────────────────────────────────────
let chatNodeId  = null;
let chatHistory = [];   // {role, content}
let chatStreaming = false;

function openChatModal(nodeId) {
  const node = allNodes.find(n => n.node_id === nodeId);
  if (!node) return;
  chatNodeId  = nodeId;
  chatHistory = [];

  document.getElementById('chatTitle').textContent    = `Chat — ${node.hostname||nodeId}`;
  document.getElementById('chatNodeName').textContent = node.address;

  // Build model options: Ollama models + agent platform/model
  const sel = document.getElementById('chatModelSel');
  const models = node.models||[];
  const agents = node.agents||[];
  const orchAgent = agents.find(a => a.name === 'orchestrator');
  const agentModel = orchAgent?.model || '';
  const agentPlatform = orchAgent?.platform || 'ollama';

  let options = models.map(m => `<option value="${m}">${m}</option>`);
  if (agentModel && !models.includes(agentModel)) {
    options.unshift(`<option value="${agentModel}">${agentModel} (${agentPlatform})</option>`);
  }
  if (options.length === 0) {
    options = [`<option value="auto">auto (agent default)</option>`];
  }
  sel.innerHTML = options.join('');
  document.getElementById('chatSub').textContent = `${agentPlatform} — ${sel.value}`;

  document.getElementById('chatMessages').innerHTML = `
    <div class="chat-empty">
      <span class="e-icon">💬</span>
      <span>Send a message to start chatting</span>
    </div>`;
  document.getElementById('chatInput').value = '';
  document.getElementById('chatSendBtn').disabled = false;
  document.getElementById('chatModal').classList.add('open');
  document.getElementById('chatInput').focus();
}

function closeChatModal() {
  document.getElementById('chatModal').classList.remove('open');
  chatNodeId  = null;
  chatHistory = [];
}

function appendMsg(role, content, streaming=false) {
  const box = document.getElementById('chatMessages');
  // Remove empty state
  const empty = box.querySelector('.chat-empty');
  if (empty) empty.remove();

  const div = document.createElement('div');
  div.className = `chat-msg ${role}${streaming?' streaming':''}`;
  div.innerHTML = `
    <span class="chat-role">${role==='user'?'You':'Agent'}</span>
    <div class="chat-bubble">${escHtml(content)}</div>`;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return div;
}

function updateMsg(el, content, done=false) {
  el.querySelector('.chat-bubble').textContent = content;
  if (done) el.classList.remove('streaming');
  document.getElementById('chatMessages').scrollTop =
    document.getElementById('chatMessages').scrollHeight;
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function sendChat() {
  if (!chatNodeId || chatStreaming) return;
  const input = document.getElementById('chatInput');
  const text  = input.value.trim();
  if (!text) return;

  input.value = '';
  input.style.height = 'auto';
  const model = document.getElementById('chatModelSel').value;

  chatHistory.push({role:'user', content:text});
  appendMsg('user', text);

  const assistantEl = appendMsg('assistant', '', true);
  chatStreaming = true;
  document.getElementById('chatSendBtn').disabled = true;

  let buffer = '';
  try {
    const resp = await fetch(`/nodes/${chatNodeId}/chat`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({model, messages: chatHistory}),
    });

    const reader = resp.body.getReader();
    const dec    = new TextDecoder();

    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      const text = dec.decode(value);
      for (const line of text.split('\n')) {
        if (!line.startsWith('data:')) continue;
        const raw = line.slice(5).trim();
        if (raw === '[DONE]') break;
        try {
          const obj = JSON.parse(raw);
          if (obj.error) { buffer += `\n[Error: ${obj.error}]`; break; }
          const chunk = obj.message?.content || '';
          buffer += chunk;
          updateMsg(assistantEl, buffer, false);
        } catch {}
      }
    }
  } catch(e) {
    buffer = `Error: ${e.message}`;
  }

  updateMsg(assistantEl, buffer, true);
  chatHistory.push({role:'assistant', content:buffer});
  chatStreaming = false;
  document.getElementById('chatSendBtn').disabled = false;
  document.getElementById('chatInput').focus();
}

// auto-resize textarea + keydown — deferred until DOM is fully parsed
document.addEventListener('DOMContentLoaded', function() {
  const inp = document.getElementById('chatInput');
  if (!inp) return;
  inp.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 120) + 'px';
  });
  inp.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
  });
});

// event delegation for chat icon buttons
document.getElementById('nodeGrid').addEventListener('click', function(e) {
  const btn = e.target.closest('.chat-icon-btn');
  if (!btn) return;
  e.stopPropagation();
  openChatModal(btn.dataset.nodeid);
});


// ── Agent detail modal ────────────────────────────────────────────────
function openAgentModal(nodeId, agentName) {
  const node = allNodes.find(n => n.node_id === nodeId);
  if (!node) return;
  const agent = (node.agents||[]).find(a => a.name === agentName);
  if (!agent) return;

  document.getElementById('agentModalTitle').textContent = agent.name;
  document.getElementById('agentModalSub').textContent =
    `${node.hostname||nodeId} · ${agent.model||'no model'} · ${agent.platform||''}`;

  const body = document.getElementById('agentModalBody');
  const d = agent.details || {};
  const alerts = d.alerts || [];
  const predictions = d.predictions || [];
  const security = d.security || [];
  const heavy = d.heavy_procs || [];

  let html = '';

  // Status banner
  const statusColors = {error:'var(--red)',running:'var(--green)',idle:'var(--yellow)'};
  const statusLabels = {error:'ALERT',running:'ACTIVE',idle:'IDLE'};
  html += `<div class="agent-status-banner ${agent.status||'idle'}">
    <div class="agent-dot ${agent.status||'idle'}" style="width:8px;height:8px"></div>
    <span class="agent-status-text" style="color:${statusColors[agent.status]||'var(--text2)'}">
      ${statusLabels[agent.status]||agent.status} — ${agent.task||'no current task'}
    </span>
    <span class="agent-status-time">${agent.updated_at ? ago(agent.updated_at) : ''}</span>
  </div>`;

  // Summary counters
  html += `<div style="display:flex;gap:.75rem;margin-bottom:1.25rem;flex-wrap:wrap">
    <span class="meta-tag" style="color:var(--red)">${alerts.length} alert${alerts.length!==1?'s':''}</span>
    <span class="meta-tag" style="color:var(--yellow)">${predictions.length} prediction${predictions.length!==1?'s':''}</span>
    <span class="meta-tag" style="color:var(--cyan)">${security.length} finding${security.length!==1?'s':''}</span>
    <span class="meta-tag" style="color:var(--purple)">${heavy.length} heavy proc${heavy.length!==1?'s':''}</span>
  </div>`;

  // Security findings
  if (security.length) {
    html += `<div class="agent-section">
      <div class="agent-section-title">Security Findings <span class="count">${security.length}</span></div>`;
    for (const f of security) {
      const icon = f.severity==='critical'?'🔴':f.severity==='high'?'🟠':'🔵';
      html += `<div class="alert-row">
        <span class="alert-icon">${icon}</span>
        <span class="alert-text">${escHtml(f.desc||'')}</span>
        <span class="alert-sev ${f.severity||''}">${(f.severity||'').toUpperCase()}</span>
      </div>`;
    }
    html += '</div>';
  }

  // Alerts (non-security)
  const resourceAlerts = alerts.filter(a => a.metric !== 'security');
  if (resourceAlerts.length) {
    html += `<div class="agent-section">
      <div class="agent-section-title">Resource Alerts <span class="count">${resourceAlerts.length}</span></div>`;
    for (const a of resourceAlerts) {
      const icon = a.level==='critical'?'🔴':'🟡';
      html += `<div class="alert-row">
        <span class="alert-icon">${icon}</span>
        <span class="alert-text">${escHtml(a.msg||'')}</span>
        <span class="alert-sev ${a.level||''}">${(a.level||'').toUpperCase()}</span>
      </div>`;
    }
    html += '</div>';
  }

  // Predictions
  if (predictions.length) {
    html += `<div class="agent-section">
      <div class="agent-section-title">Predictions <span class="count">${predictions.length}</span></div>`;
    for (const p of predictions) {
      html += `<div class="predict-row">
        <span class="predict-icon">⚡</span>
        <span class="predict-text">${escHtml(p.msg||'')}</span>
      </div>`;
    }
    html += '</div>';
  }

  // Heavy processes
  if (heavy.length) {
    html += `<div class="agent-section">
      <div class="agent-section-title">Heavy Processes <span class="count">${heavy.length}</span></div>
      <div style="display:flex;gap:.6rem;padding:0 .7rem .2rem;font-family:var(--mono);font-size:.63rem;color:var(--text3)">
        <span style="width:50px">PID</span><span style="width:120px">NAME</span>
        <span style="width:55px;text-align:right">CPU</span>
        <span style="width:55px;text-align:right">MEM</span>
        <span style="flex:1">CMD</span>
      </div>`;
    for (const p of heavy) {
      const cpuColor = p.cpu > 50 ? 'color:var(--red)' : '';
      const memColor = p.mem > 20 ? 'color:var(--red)' : '';
      html += `<div class="proc-row">
        <span class="proc-pid">${p.pid}</span>
        <span class="proc-name">${escHtml(p.name||'')}</span>
        <span class="proc-cpu" style="${cpuColor}">${p.cpu}%</span>
        <span class="proc-mem" style="${memColor}">${p.mem}%</span>
        <span class="proc-cmd">${escHtml((p.cmd||'').slice(0,60))}</span>
      </div>`;
    }
    html += '</div>';
  }

  // Proposed actions from security findings
  const actions = security.filter(f => f.action).map(f => f.action);
  if (actions.length) {
    html += `<div class="agent-section">
      <div class="agent-section-title">Proposed Actions <span class="count">${actions.length}</span></div>`;
    for (const a of actions) {
      html += `<div class="action-row">
        <span class="action-desc">${escHtml(a.desc||'')}</span>
        <span class="action-cmd" title="${escHtml(a.command||'')}">${escHtml(a.command||'')}</span>
      </div>`;
    }
    html += '</div>';
  }

  if (!alerts.length && !security.length && !predictions.length && !heavy.length) {
    html += `<div style="text-align:center;padding:2rem;color:var(--text3);font-family:var(--mono);font-size:.85rem">
      <div style="font-size:2rem;opacity:.3;margin-bottom:.5rem">✓</div>
      All systems nominal — no alerts or findings
    </div>`;
  }

  body.innerHTML = html;
  document.getElementById('agentModal').classList.add('open');
}

function closeAgentModal() {
  document.getElementById('agentModal').classList.remove('open');
}

async function refresh() {
  try {
    const [nr, sr] = await Promise.all([
      fetch('/api/admin/nodes'),
      fetch('/api/admin/summary'),
    ]);
    if (!nr.ok || !sr.ok) throw new Error('bad response');
    const nodes = await nr.json();
    const s     = await sr.json();

    allNodes  = nodes;
    firstLoad = false;

    document.getElementById('mNetworks').textContent = s.networks;
    document.getElementById('mOnline').textContent   = s.online_nodes;
    document.getElementById('mOffline').textContent  = s.offline_nodes;
    document.getElementById('mAgents').textContent   = s.total_agents;

    syncGrid(nodes);

    document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
    document.getElementById('connStatus').textContent = 'live';
    document.getElementById('pulse').style.background = 'var(--green)';
  } catch(e) {
    document.getElementById('connStatus').textContent = 'error';
    document.getElementById('pulse').style.background = 'var(--red)';
  }
}

refresh();
setInterval(refresh, 5000);
setInterval(tickTimestamps, 3000);

// Event delegation — single listener for all svc-badge and agent-item clicks
document.getElementById('nodeGrid').addEventListener('click', function(e) {
  // Agent item click
  const agentItem = e.target.closest('.agent-item[data-agent]');
  if (agentItem) {
    e.stopPropagation();
    openAgentModal(agentItem.dataset.nodeid, agentItem.dataset.agent);
    return;
  }
  // Service badge click
  const badge = e.target.closest('.svc-badge');
  if (!badge) return;
  e.stopPropagation();
  const nodeId = badge.dataset.nodeid;
  if (nodeId) openSvcModal(nodeId);
});
</script>
<!-- Chat modal -->
<div class="modal-overlay" id="chatModal" onclick="if(event.target===this)closeChatModal()">
  <div class="modal chat-modal">
    <div class="modal-header">
      <div>
        <div class="modal-title" id="chatTitle">Chat</div>
        <div class="modal-sub" id="chatSub"></div>
      </div>
      <button class="modal-close" onclick="closeChatModal()">✕</button>
    </div>
    <div class="chat-topbar">
      <span class="chat-node-name" id="chatNodeName"></span>
      <select class="chat-model-sel" id="chatModelSel"></select>
    </div>
    <div class="chat-messages" id="chatMessages">
      <div class="chat-empty">
        <span class="e-icon">💬</span>
        <span>Send a message to start chatting with this node's model</span>
      </div>
    </div>
    <div class="chat-footer">
      <textarea class="chat-input" id="chatInput" rows="1"
        placeholder="Message the agent…"></textarea>
      <button class="chat-send" id="chatSendBtn" onclick="sendChat()">
        Send ↵
      </button>
    </div>
  </div>
</div>
<!-- Agent detail modal -->
<div class="modal-overlay" id="agentModal" onclick="if(event.target===this)closeAgentModal()">
  <div class="modal agent-modal">
    <div class="modal-header">
      <div>
        <div class="modal-title" id="agentModalTitle">Agent</div>
        <div class="modal-sub" id="agentModalSub"></div>
      </div>
      <button class="modal-close" onclick="closeAgentModal()">✕</button>
    </div>
    <div class="modal-body" id="agentModalBody"></div>
  </div>
</div>
<!-- Services modal -->
<div class="modal-overlay" id="svcModal" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <div class="modal-header">
      <div>
        <div class="modal-title" id="modalTitle">Services</div>
        <div class="modal-sub" id="modalSub"></div>
      </div>
      <button class="modal-close" onclick="closeModal()">✕</button>
    </div>
    <div class="modal-body" id="modalBody"></div>
  </div>
</div>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML


# ── admin API ──────────────────────────────────────────────────────────────

@app.get("/api/admin/nodes")
async def admin_nodes():
    return _nodes.get_all_nodes()

@app.get("/api/admin/summary")
async def admin_summary():
    return _nodes.summary()

@app.post("/api/admin/bootstrap")
async def bootstrap_token(request: Request, network_id: str = "net_default",
                          label: str = "bootstrap", ttl_hours: int = 8760):
    if request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "Only accessible from localhost")
    return _auth.create_preauth_token(network_id, label, ttl_hours)


# ── auth ───────────────────────────────────────────────────────────────────

@app.post("/auth/device")
async def auth_device(body: DeviceCodeRequest):
    return _auth.create_device_code(body.node_id, BASE_URL)

@app.post("/auth/token")
async def auth_token(body: DeviceTokenPoll):
    if body.grant_type != "urn:ietf:params:oauth:grant-type:device_code":
        raise HTTPException(400, "unsupported_grant_type")
    result = _auth.poll_device(body.device_code)
    if result is None:
        raise HTTPException(428, "authorization_pending")
    return result

@app.post("/auth/preauth")
async def auth_preauth(body: PreauthTokenUse):
    result = _auth.use_preauth_token(body.token, body.node_id)
    if not result:
        raise HTTPException(401, "Invalid or expired token")
    return result

@app.post("/auth/preauth/create")
async def create_preauth_token(body: PreauthTokenCreate,
                               session: dict = Depends(_require_session)):
    if session["network_id"] != body.network_id:
        raise HTTPException(403, "Cannot create token for another network")
    return _auth.create_preauth_token(body.network_id, body.label, body.ttl_hours)


# ── activation page ────────────────────────────────────────────────────────

@app.get("/connect/activate", response_class=HTMLResponse)
async def activate_page(code: str = ""):
    return f"""<!DOCTYPE html><html><head>
    <title>CH8 — Activate Node</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500&family=Inter:wght@400;600&display=swap" rel="stylesheet">
    <style>*{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Inter',sans-serif;background:#050505;color:#f0f0f0;
         display:flex;align-items:center;justify-content:center;min-height:100vh}}
    .box{{background:#111;border:1px solid rgba(255,255,255,.08);border-radius:16px;
          padding:2.5rem;width:420px;text-align:center}}
    .logo{{font-family:'JetBrains Mono',monospace;font-size:.85rem;color:#0070f3;
           letter-spacing:.1em;margin-bottom:1.5rem}}
    h1{{font-size:1.4rem;font-weight:600;margin-bottom:.5rem}}
    p{{color:#71717a;font-size:.9rem;margin-bottom:1.75rem;line-height:1.5}}
    input{{width:100%;padding:.85rem 1rem;border-radius:10px;
           border:1px solid rgba(255,255,255,.1);background:#1a1a1a;color:#fff;
           font-family:'JetBrains Mono',monospace;font-size:1.2rem;
           letter-spacing:.2em;text-align:center;text-transform:uppercase}}
    input:focus{{outline:none;border-color:#0070f3}}
    button{{width:100%;margin-top:1rem;padding:.85rem;background:#0070f3;
            border:none;border-radius:10px;color:#fff;font-size:.95rem;
            font-weight:600;cursor:pointer}}
    button:hover{{background:#0051cc}}</style></head><body>
    <div class="box">
      <div class="logo">CH8 CONTROL</div>
      <h1>Activate Node</h1>
      <p>Enter the code shown in your terminal to connect this machine to your network.</p>
      <form method="POST" action="/connect/activate">
        <input name="code" value="{code}" placeholder="XXXX-0000" maxlength="9" autofocus/>
        <button type="submit">Connect Node</button>
      </form>
    </div></body></html>"""

@app.post("/connect/activate")
async def activate_node(request: Request):
    form = await request.form()
    code = str(form.get("code", "")).strip().upper()
    ok   = _auth.approve_device(code, "net_default")
    msg  = ("Node Connected", "#10b981", "You can close this tab.") if ok else \
           ("Code Not Found", "#ef4444", "The code may have expired. Run <code>ch8 up</code> again.")
    return HTMLResponse(f"""<html><body style="background:#050505;color:#f0f0f0;font-family:Inter,sans-serif;
        display:flex;align-items:center;justify-content:center;min-height:100vh;">
        <div style="text-align:center">
          <h2 style="color:{msg[1]};margin-bottom:.5rem">{msg[0]}</h2>
          <p style="color:#71717a">{msg[2]}</p>
        </div></body></html>""", status_code=200 if ok else 400)


# ── nodes API ──────────────────────────────────────────────────────────────

@app.post("/nodes/register")
async def register_node(body: NodeRegisterRequest,
                        session: dict = Depends(_require_session)):
    if session["network_id"] != body.network_id:
        raise HTTPException(403, "Token does not match network")
    _nodes.register(body.model_dump(), _auth)
    return {"ok": True, "node_id": body.node_id}

@app.put("/nodes/{node_id}/heartbeat")
async def node_heartbeat(node_id: str, body: NodeHeartbeatRequest,
                         session: dict = Depends(_require_session)):
    metrics = body.model_dump()
    metrics["agents"] = [a.model_dump() if hasattr(a, "model_dump") else a
                         for a in (body.agents or [])]
    metrics["services"] = body.services if hasattr(body, "services") else []
    ok = _nodes.heartbeat(node_id, body.network_id, metrics, _auth)
    if not ok:
        raise HTTPException(404, "Node not registered")
    return {"ok": True}

@app.get("/nodes")
async def list_nodes(network_id: str, session: dict = Depends(_require_session)):
    if session["network_id"] != network_id:
        raise HTTPException(403, "Access denied")
    return {"nodes": _nodes.get_nodes(network_id)}

@app.delete("/nodes/{node_id}")
async def deregister_node(node_id: str, network_id: str,
                          session: dict = Depends(_require_session)):
    if session["network_id"] != network_id:
        raise HTTPException(403, "Access denied")
    _nodes.deregister(node_id, network_id, _auth)
    return {"ok": True}



# ── chat proxy ─────────────────────────────────────────────────────────────

import httpx as _httpx
from fastapi.responses import StreamingResponse

_OLLAMA_PORT = int(os.environ.get("OLLAMA_PORT", "11434"))


@app.post("/nodes/{node_id}/chat")
async def chat_proxy(node_id: str, request: Request):
    node = next((n for n in _nodes.get_all_nodes() if n["node_id"] == node_id), None)
    if not node:
        raise HTTPException(404, "Node not found")
    if node["status"] != "online":
        raise HTTPException(503, "Node is offline")

    body     = await request.json()
    model    = body.get("model") or (node.get("models") or ["llama3.2"])[0]
    messages = body.get("messages", [])
    addr     = node["address"]
    _AGENT_PORT = int(os.environ.get("CH8_AGENT_PORT", "7879"))
    agent_url   = f"http://{addr}:{_AGENT_PORT}/chat"
    ollama_url  = f"http://{addr}:{_OLLAMA_PORT}/api/chat"

    async def stream_gen():
        # Probe orchestrator agent (port 7879); fall back to raw Ollama
        use_agent = False
        try:
            async with _httpx.AsyncClient(timeout=2) as probe:
                r = await probe.get(f"http://{addr}:{_AGENT_PORT}/health")
                use_agent = r.status_code == 200
        except Exception:
            pass

        target  = agent_url if use_agent else ollama_url
        payload = {"model": model, "messages": messages}
        if not use_agent:
            payload["stream"] = True

        try:
            async with _httpx.AsyncClient(timeout=120) as client:
                async with client.stream("POST", target, json=payload) as resp:
                    if resp.status_code != 200:
                        yield "data: " + '{"error":"node error ' + str(resp.status_code) + '"}' + "\n\n"
                        return
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        # Line already has "data: " prefix from upstream SSE
                        if line.startswith("data: "):
                            yield line + "\n\n"
                        else:
                            yield "data: " + line + "\n\n"
        except _httpx.ConnectError:
            yield "data: " + '{"error":"cannot reach ' + addr + '"}' + "\n\n"
        except Exception as ex:
            yield "data: " + '{"error":"' + str(ex) + '"}' + "\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── health ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    s = _nodes.summary()
    return {"status": "ok", "ts": int(time.time()), **s}
