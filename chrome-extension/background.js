// CH8 Cluster Extension — Background Service Worker (MV3)

const API_BASE = 'https://control.ch8ai.com.br';
const REFRESH_INTERVAL = 0.5; // minutes (30s)

// Create alarm only on install/startup (not at top level)
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create('refresh', { periodInMinutes: REFRESH_INTERVAL });
  updateBadge();
});

chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create('refresh', { periodInMinutes: REFRESH_INTERVAL });
  updateBadge();
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'refresh') {
    await updateBadge();
  }
});

async function updateBadge() {
  try {
    const { session, serverUrl } = await chrome.storage.local.get(['session', 'serverUrl']);
    const base = serverUrl || API_BASE;
    const headers = {};

    if (session) {
      if (session.startsWith('tk_') || session.length > 30) {
        headers['Authorization'] = `Bearer ${session}`;
      } else {
        headers['Cookie'] = `session=${session}`;
      }
    }

    const r = await fetch(`${base}/api/admin/nodes`, { headers });
    if (!r.ok) {
      chrome.action.setBadgeText({ text: '!' });
      chrome.action.setBadgeBackgroundColor({ color: '#ef4444' });
      return;
    }
    const nodes = await r.json();
    const online = nodes.filter(n => n.status === 'online').length;

    chrome.action.setBadgeText({ text: String(online) });
    chrome.action.setBadgeBackgroundColor({ color: online > 0 ? '#10b981' : '#ef4444' });
    chrome.storage.local.set({ cachedNodes: nodes, lastUpdate: Date.now() });
  } catch (e) {
    chrome.action.setBadgeText({ text: '?' });
    chrome.action.setBadgeBackgroundColor({ color: '#6b7280' });
  }
}
