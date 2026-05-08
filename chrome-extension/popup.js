// CH8 Cluster Extension — Popup Logic (v2)

const DEFAULT_URL = 'https://control.ch8ai.com.br';
let API_BASE = DEFAULT_URL;
let SESSION = '';
let cachedNodes = [];

// ══════════════════════════════════════════════════════════════
// Init
// ══════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', async () => {
  const stored = await chrome.storage.local.get(['serverUrl', 'session', 'alertLevel']);
  API_BASE = stored.serverUrl || DEFAULT_URL;
  SESSION = stored.session || '';
  document.getElementById('serverUrl').value = API_BASE;
  document.getElementById('sessionKey').value = SESSION;
  document.getElementById('alertLevel').value = stored.alertLevel || 'high';
  document.getElementById('dashLink').href = API_BASE;

  // Tab switching
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => switchTab(tab.dataset.tab));
  });

  // Chat enter key
  document.getElementById('chatInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
  });
  document.getElementById('chatSend').addEventListener('click', sendChat);

  refresh();
});

function switchTab(tabId) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tabId));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === `panel-${tabId}`));

  // Load tab data on switch
  if (tabId === 'alerts') loadAlerts();
}

// ══════════════════════════════════════════════════════════════
// API
// ══════════════════════════════════════════════════════════════

async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (SESSION) headers['Cookie'] = `session=${SESSION}`;
  const r = await fetch(`${API_BASE}${path}`, { ...opts, headers });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

// ══════════════════════════════════════════════════════════════
// Overview Tab
// ══════════════════════════════════════════════════════════════

async function refresh() {
  try {
    const nodes = await api('/api/admin/nodes');
    cachedNodes = nodes;
    renderNodes(nodes);
    document.getElementById('status').textContent = 'Connected';
    document.getElementById('status').className = 'header-status status-ok';
    chrome.storage.local.set({ cachedNodes: nodes, lastUpdate: Date.now() });
  } catch (e) {
    document.getElementById('status').textContent = 'Offline';
    document.getElementById('status').className = 'header-status status-err';

    const { cachedNodes: cached } = await chrome.storage.local.get('cachedNodes');
    if (cached) { cachedNodes = cached; renderNodes(cached); }
    else document.getElementById('nodes').innerHTML = `<div style="padding:16px;color:#f87171;font-size:11px">Connection failed: ${e.message}</div>`;
  }
}

function renderNodes(nodes) {
  const online = nodes.filter(n => n.status === 'online');
  const offline = nodes.filter(n => n.status !== 'online');
  const allAgents = nodes.reduce((sum, n) => sum + (n.agents || []).length, 0);
  const avgCpu = online.length ? (online.reduce((s, n) => s + (n.cpu_pct || 0), 0) / online.length) : 0;
  const avgMem = online.length ? (online.reduce((s, n) => s + (n.mem_pct || 0), 0) / online.length) : 0;

  document.getElementById('nodesOnline').textContent = `${online.length}/${nodes.length}`;
  document.getElementById('agentsCount').textContent = allAgents;

  const cpuEl = document.getElementById('avgCpu');
  cpuEl.textContent = `${avgCpu.toFixed(0)}%`;
  cpuEl.className = `stat-value ${avgCpu > 80 ? 'red' : avgCpu > 60 ? 'yellow' : 'green'}`;

  const memEl = document.getElementById('avgMem');
  memEl.textContent = `${avgMem.toFixed(0)}%`;
  memEl.className = `stat-value ${avgMem > 85 ? 'red' : avgMem > 70 ? 'yellow' : 'green'}`;

  const sorted = [...online.sort((a, b) => (b.cpu_pct || 0) - (a.cpu_pct || 0)), ...offline];

  document.getElementById('nodes').innerHTML = sorted.map(n => {
    const isOnline = n.status === 'online';
    const cpu = n.cpu_pct || 0;
    const mem = n.mem_pct || 0;
    const disk = n.disk_pct || 0;
    const hostname = (n.hostname || 'unknown').slice(0, 16);
    const agents = (n.agents || []).filter(a => !['orchestrator', 'mesh_relay', 'server-monitor'].includes(a.name));
    const model = n.ai_model ? n.ai_model.split('/').pop()?.split(':')[0]?.slice(0, 25) : '';

    return `<div class="node" style="${!isOnline ? 'opacity:0.5' : ''}">
      <div class="node-header">
        <div class="node-dot ${isOnline ? 'dot-online' : 'dot-offline'}"></div>
        <span class="node-name">${hostname}</span>
        <span class="node-meta">${n.os || ''}/${(n.arch || '').slice(0, 5)}</span>
      </div>
      <div class="node-bars">
        <div class="bar-group">
          <div class="bar-label"><span>CPU</span><span>${cpu.toFixed(0)}%</span></div>
          <div class="bar-track"><div class="bar-fill ${cpu > 80 ? 'bar-high' : 'bar-cpu'}" style="width:${cpu}%"></div></div>
        </div>
        <div class="bar-group">
          <div class="bar-label"><span>MEM</span><span>${mem.toFixed(0)}%</span></div>
          <div class="bar-track"><div class="bar-fill ${mem > 85 ? 'bar-high' : 'bar-mem'}" style="width:${mem}%"></div></div>
        </div>
        <div class="bar-group">
          <div class="bar-label"><span>DSK</span><span>${disk.toFixed(0)}%</span></div>
          <div class="bar-track"><div class="bar-fill ${disk > 90 ? 'bar-high' : 'bar-disk'}" style="width:${disk}%"></div></div>
        </div>
      </div>
      ${model ? `<div class="node-model">☁️ ${model}</div>` : ''}
      ${agents.length ? `<div class="node-agents">${agents.map(a => `<span class="agent-badge">${a.name}</span>`).join('')}</div>` : ''}
    </div>`;
  }).join('');
}

// ══════════════════════════════════════════════════════════════
// AI Chat Tab
// ══════════════════════════════════════════════════════════════

async function sendChat() {
  const input = document.getElementById('chatInput');
  const btn = document.getElementById('chatSend');
  const messages = document.getElementById('chatMessages');
  const msg = input.value.trim();
  if (!msg) return;

  // Add user message
  messages.innerHTML += `<div class="chat-msg chat-user">${escapeHtml(msg)}</div>`;
  input.value = '';
  btn.disabled = true;
  messages.scrollTop = messages.scrollHeight;

  // Show typing
  const typingId = `typing-${Date.now()}`;
  messages.innerHTML += `<div class="chat-msg chat-ai" id="${typingId}"><span class="spin">&#9696;</span> Thinking...</div>`;
  messages.scrollTop = messages.scrollHeight;

  try {
    const data = await api('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message: msg, channel: 'chrome-extension' }),
    });
    const response = data.response || data.result || JSON.stringify(data, null, 2);
    document.getElementById(typingId).innerHTML = formatResponse(response);
  } catch (e) {
    document.getElementById(typingId).innerHTML = `<span style="color:#f87171">Error: ${e.message}</span>`;
  }

  btn.disabled = false;
  messages.scrollTop = messages.scrollHeight;
}

function formatResponse(text) {
  // Basic markdown-like formatting
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, '<code style="background:#0f172a;padding:1px 4px;border-radius:3px;font-size:10px">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
}

function escapeHtml(text) {
  return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ══════════════════════════════════════════════════════════════
// Alerts Tab
// ══════════════════════════════════════════════════════════════

async function loadAlerts() {
  const el = document.getElementById('alertsList');
  try {
    // Get alerts from nodes' server-monitor agent
    const alerts = [];
    for (const node of cachedNodes) {
      for (const agent of (node.agents || [])) {
        if (agent.name === 'server-monitor' && agent.details?.alerts) {
          for (const alert of agent.details.alerts) {
            alerts.push({ ...alert, node: node.hostname });
          }
        }
        if (agent.name === 'server-monitor' && agent.details?.security) {
          for (const sec of agent.details.security) {
            alerts.push({ level: sec.severity, msg: sec.desc, node: node.hostname, action: sec.action });
          }
        }
      }
    }

    if (!alerts.length) {
      el.innerHTML = '<div class="alert-empty">✅ No alerts — all systems nominal</div>';
      return;
    }

    // Sort by severity
    const order = { high: 0, critical: 0, medium: 1, low: 2 };
    alerts.sort((a, b) => (order[a.level] ?? 3) - (order[b.level] ?? 3));

    el.innerHTML = alerts.map(a => {
      const sev = a.level === 'high' || a.level === 'critical' ? 'high' : a.level === 'medium' ? 'medium' : 'low';
      return `<div class="alert-item ${sev}">
        <div class="alert-header">
          <span class="alert-severity sev-${sev}">${a.level}</span>
          <span style="font-size:10px;color:#64748b">${(a.node || '').slice(0, 12)}</span>
        </div>
        <div class="alert-text">${escapeHtml(a.msg || a.desc || '')}</div>
        ${a.action ? `<div class="alert-action"><button onclick="runFix('${escapeHtml(a.action.command || '')}')">⚡ ${escapeHtml(a.action.desc || 'Fix').slice(0, 40)}</button></div>` : ''}
      </div>`;
    }).join('');
  } catch (e) {
    el.innerHTML = `<div style="padding:16px;color:#f87171;font-size:11px">Failed to load alerts: ${e.message}</div>`;
  }
}

async function runFix(command) {
  if (!command || !confirm(`Execute fix?\n\n${command}`)) return;
  try {
    const data = await api('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message: `Execute: ${command}`, channel: 'chrome-extension' }),
    });
    alert(data.response || data.result || 'Done');
  } catch (e) {
    alert(`Error: ${e.message}`);
  }
}

// ══════════════════════════════════════════════════════════════
// Quick Actions Tab
// ══════════════════════════════════════════════════════════════

const ACTION_PROMPTS = {
  health: 'Give me a full health check of the cluster. Include CPU, memory, disk for each node, any alerts, and overall health score. Be concise.',
  deploy: 'List all Docker containers running across the cluster with their status, image, and ports. Flag any that are unhealthy or restarting.',
  security: 'Run a security assessment: list exposed ports, databases without auth, containers with public ports that should be internal. Give severity ratings.',
  costs: 'Show current AI token costs: burn rate per hour/day/month, cost by model, cost by agent. Include projections.',
  logs: 'Show recent error logs across all nodes. Group by severity. Only show the last hour. Be concise.',
  network: 'Check network connectivity between all nodes. Show latency, any unreachable nodes, and mesh relay status.',
  backup: 'Check backup status: last backup time, disk space remaining on each volume, any volumes above 90% usage.',
  restart: 'Restart the orchestrator agent on manager1. Confirm it comes back online.',
};

async function runAction(action) {
  const result = document.getElementById('actionResult');
  result.style.display = 'block';
  result.textContent = `Running ${action}...`;
  result.style.color = '#94a3b8';

  try {
    const data = await api('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message: ACTION_PROMPTS[action], channel: 'chrome-extension' }),
    });
    result.textContent = data.response || data.result || JSON.stringify(data, null, 2);
    result.style.color = '#34d399';
  } catch (e) {
    result.textContent = `Error: ${e.message}`;
    result.style.color = '#f87171';
  }
}

// ══════════════════════════════════════════════════════════════
// Settings
// ══════════════════════════════════════════════════════════════

function saveSettings() {
  API_BASE = document.getElementById('serverUrl').value.replace(/\/$/, '') || DEFAULT_URL;
  SESSION = document.getElementById('sessionKey').value;
  const alertLevel = document.getElementById('alertLevel').value || 'high';
  chrome.storage.local.set({ serverUrl: API_BASE, session: SESSION, alertLevel });
  document.getElementById('dashLink').href = API_BASE;
  refresh();
  switchTab('overview');
}
