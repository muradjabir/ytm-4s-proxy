// Background service worker for YTM Proxy Cookie Sync

chrome.tabs.onUpdated.addListener(function(tabId, changeInfo, tab) {
  if (changeInfo.status === 'complete' && tab.url && (tab.url.indexOf('music.youtube.com') > -1 || tab.url.indexOf('youtube.com') > -1)) {
    chrome.storage.local.get(['serverUrl', 'autoSync', 'lastAutoSyncTime'], function(data) {
      if (data.autoSync === false || !data.serverUrl) return;

      var now = Date.now();
      // Throttle auto-sync to once every 10 minutes
      if (data.lastAutoSyncTime && (now - data.lastAutoSyncTime) < 10 * 60 * 1000) {
        return;
      }

      syncCookiesInBackground(data.serverUrl);
    });
  }
});

function syncCookiesInBackground(serverUrl) {
  Promise.all([
    chrome.cookies.getAll({ domain: 'youtube.com' }),
    chrome.cookies.getAll({ domain: 'google.com' })
  ]).then(function(results) {
    var ytCookies = results[0] || [];
    var googleCookies = results[1] || [];

    var map = {};
    ytCookies.forEach(function(c) { map[c.name + '@' + c.domain] = c; });
    googleCookies.forEach(function(c) {
      if (['SID', 'HSID', 'SSID', 'APISID', 'SAPISID', 'LOGIN_INFO', '__Secure-1PSID', '__Secure-3PSID'].indexOf(c.name) > -1) {
        var key = c.name + '@' + c.domain;
        if (!map[key]) map[key] = c;
      }
    });

    var cookiesList = Object.values(map);
    if (!cookiesList.length) return;

    fetch(serverUrl.replace(/\/+$/, '') + '/api/cookies/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source: 'background_auto_sync',
        timestamp: Date.now(),
        cookies: cookiesList
      })
    })
    .then(function(res) {
      if (res.ok) {
        chrome.storage.local.set({ lastAutoSyncTime: Date.now() });
      }
    })
    .catch(function(e) {
      console.warn('YTM background auto-sync failed:', e);
    });
  });
}
