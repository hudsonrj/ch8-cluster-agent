// CH8 Cluster Extension — Popup Logic

const DEFAULT_URL = 'https://control.ch8ai.com.br';
let API_BASE = DEFAULT_URL;
let SESSION = '';

// ── Init ──
document.addEventListener('DOMContentLoaded', async () => {
  const stored = await chrome.storage.local.get(['serverUrl', 'session']);
  API_BASE = stored.serverUrl || DEFAULT_URL;
  SESSION = stored.session || '';
  document.getElementById('serverUrl').value = API_BASE;
  document.getElementById('sessionKey').value = SESSION;

  // Enter key sends command
  document.getElementById('cmdInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendCommand();
  });

  refresh();
});

// ── API Call ──
async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (SESSION) headers['Cookie'] = `session=${SESSION}`;
  const r = await fetch(`${API_BASE}${path}`, { ...opts, headers });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

// ── Refresh ──
async function refresh() {
  try {
    const nodes = await api('/api/admin/nodes');
    renderNodes(nodes);
    document.getElementById('status').textContent = 'Connected';
    document.getElementById('status').className = 'header-status status-ok';
    document.getElementById('lastUpdate').textContent = `Updated ${new Date().toLocaleTimeString()}`;

    // Cache for background
    chrome.storage.local.set({ cachedNodes: nodes, lastUpdate: Date.now() });
  } catch (e) {
    document.getElementById('status').textContent = 'Offline';
    document.getElementById('status').className = 'header-status status-err';
    document.getElementById('nodes').innerHTML = `<div style="padding:12px;color:#f87171;font-size:11px">Connection failed: ${e.message}<br><br>Check Settings below.</div>`;

    // Try cached data
    const { cachedNodes } = await chrome.storage.local.get('cachedNodes');
    if (cachedNodes) renderNodes(cachedNodes);
  }
}

// ── Render Nodes ──
function renderNodes(nodes) {
  const online = nodes.filter(n => n.status === 'online');
  const offline = nodes.filter(n => n.status !== 'online');
  const allAgents = nodes.reduce((sum, n) => sum + (n.agents || []).length, 0);
  const avgCpu = online.length ? (online.reduce((s, n) => s + (n.cpu_pct || 0), 0) / online.length) : 0;

  document.getElementById('nodesOnline').textContent = `${online.length}/${nodes.length}`;
  document.getElementById('agentsCount').textContent = allAgents;
  document.getElementById('avgCpu').textContent = `${avgCpu.toFixed(0)}%`;

  // Sort: online first, then by CPU desc
  const sorted = [...online.sort((a, b) => (b.cpu_pct || 0) - (a.cpu_pct || 0)), ...offline];

  document.getElementById('nodes').innerHTML = sorted.map(n => {
    const isOnline = n.status === 'online';
    const cpu = n.cpu_pct || 0;
    const mem = n.mem_pct || 0;
    const cpuHigh = cpu > 80;
    const memHigh = mem > 85;
    const agents = (n.agents || []).filter(a => !['orchestrator', 'mesh_relay', 'server-monitor'].includes(a.name));
    const hostname = (n.hostname || 'unknown').slice(0, 16);

    return `<div class="node" style="${!isOnline ? 'opacity:0.5' : ''}">
      <div class="node-header">
        <div class="node-dot ${isOnline ? 'dot-online' : 'dot-offline'}"></div>
        <span class="node-name">${hostname}</span>
        <span class="node-meta">${n.os || ''}/${(n.arch || '').slice(0, 5)}</span>
      </div>
      <div class="node-bars">
        <div class="bar-group">
          <div class="bar-label"><span>CPU</span><span>${cpu.toFixed(0)}%</span></div>
          <div class="bar-track"><div class="bar-fill ${cpuHigh ? 'bar-high' : 'bar-cpu'}" style="width:${cpu}%"></div></div>
        </div>
        <div class="bar-group">
          <div class="bar-label"><span>MEM</span><span>${mem.toFixed(0)}%</span></div>
          <div class="bar-track"><div class="bar-fill ${memHigh ? 'bar-high' : 'bar-mem'}" style="width:${mem}%"></div></div>
        </div>
      </div>
      ${agents.length ? `<div class="node-agents">${agents.map(a => `<span class="agent-badge">${a.name}</span>`).join('')}</div>` : ''}
    </div>`;
  }).join('');
}

// ── Send Command ──
async function sendCommand() {
  const input = document.getElementById('cmdInput');
  const btn = document.getElementById('cmdBtn');
  const result = document.getElementById('cmdResult');
  const cmd = input.value.trim();
  if (!cmd) return;

  btn.disabled = true;
  btn.textContent = '...';
  result.style.display = 'block';
  result.textContent = 'Processing...';

  try {
    const data = await api('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message: cmd, channel: 'extension' }),
    });
    result.textContent = data.response || data.result || JSON.stringify(data, null, 2);
    result.style.color = '#34d399';
  } catch (e) {
    result.textContent = `Error: ${e.message}`;
    result.style.color = '#f87171';
  }

  btn.disabled = false;
  btn.textContent = 'Send';
  input.value = '';
}

// ── Settings ──
function toggleSettings() {
  const panel = document.getElementById('settingsPanel');
  panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
}

function saveSettings() {
  API_BASE = document.getElementById('serverUrl').value.replace(/\/$/, '') || DEFAULT_URL;
  SESSION = document.getElementById('sessionKey').value;
  chrome.storage.local.set({ serverUrl: API_BASE, session: SESSION });
  toggleSettings();
  refresh();
}
