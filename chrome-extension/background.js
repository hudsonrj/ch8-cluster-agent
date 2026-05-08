// CH8 Cluster Extension — Background Service Worker

const API_BASE = 'https://control.ch8ai.com.br';
const REFRESH_INTERVAL = 30; // seconds

// Refresh badge every 30s
chrome.alarms.create('refresh', { periodInMinutes: REFRESH_INTERVAL / 60 });

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'refresh') {
    await updateBadge();
  }
});

// Update on install/startup
chrome.runtime.onInstalled.addListener(() => updateBadge());
chrome.runtime.onStartup.addListener(() => updateBadge());

async function updateBadge() {
  try {
    const { session } = await chrome.storage.local.get('session');
    const headers = session ? { 'Cookie': `session=${session}` } : {};

    const r = await fetch(`${API_BASE}/api/admin/nodes`, { headers });
    if (!r.ok) {
      chrome.action.setBadgeText({ text: '!' });
      chrome.action.setBadgeBackgroundColor({ color: '#ef4444' });
      return;
    }
    const nodes = await r.json();
    const online = nodes.filter(n => n.status === 'online').length;

    chrome.action.setBadgeText({ text: String(online) });
    chrome.action.setBadgeBackgroundColor({ color: online > 0 ? '#10b981' : '#ef4444' });

    // Cache data for popup
    chrome.storage.local.set({ cachedNodes: nodes, lastUpdate: Date.now() });
  } catch (e) {
    chrome.action.setBadgeText({ text: '?' });
    chrome.action.setBadgeBackgroundColor({ color: '#6b7280' });
  }
}
