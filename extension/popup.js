document.addEventListener('DOMContentLoaded', function() {
  var serverInput = document.getElementById('server-url');
  var autoSyncCheckbox = document.getElementById('auto-sync');
  var btnSync = document.getElementById('btn-sync');
  var statusBox = document.getElementById('status-box');

  // Load saved settings
  chrome.storage.local.get(['serverUrl', 'autoSync', 'lastSyncStatus', 'lastSyncTime'], function(items) {
    if (items.serverUrl) {
      serverInput.value = items.serverUrl;
    }
    if (items.autoSync !== undefined) {
      autoSyncCheckbox.checked = items.autoSync;
    }
    if (items.lastSyncStatus) {
      showStatus(items.lastSyncStatus.msg, items.lastSyncStatus.type);
    }
  });

  serverInput.addEventListener('change', function() {
    chrome.storage.local.set({ serverUrl: serverInput.value.trim().replace(/\/+$/, '') });
  });

  autoSyncCheckbox.addEventListener('change', function() {
    chrome.storage.local.set({ autoSync: autoSyncCheckbox.checked });
  });

  btnSync.addEventListener('click', function() {
    performSync();
  });

  function showStatus(msg, type) {
    statusBox.textContent = msg;
    statusBox.className = 'status-box status-' + (type || 'info');
  }

  function performSync() {
    var rawUrl = serverInput.value.trim().replace(/\/+$/, '');
    if (!rawUrl) {
      showStatus('Please enter your proxy server URL (e.g. http://192.168.2.2:5000)', 'error');
      return;
    }

    btnSync.disabled = true;
    showStatus('Reading YouTube cookies from browser…', 'info');

    // Query both .youtube.com and .google.com cookies
    Promise.all([
      chrome.cookies.getAll({ domain: 'youtube.com' }),
      chrome.cookies.getAll({ domain: 'google.com' })
    ]).then(function(results) {
      var ytCookies = results[0] || [];
      var googleCookies = results[1] || [];
      
      // Combine with priority to youtube.com
      var map = {};
      ytCookies.forEach(function(c) { map[c.name + '@' + c.domain] = c; });
      googleCookies.forEach(function(c) {
        // Only include Google auth cookies if not already present
        if (['SID', 'HSID', 'SSID', 'APISID', 'SAPISID', 'LOGIN_INFO', '__Secure-1PSID', '__Secure-3PSID'].indexOf(c.name) > -1) {
          var key = c.name + '@' + c.domain;
          if (!map[key]) map[key] = c;
        }
      });

      var cookiesList = Object.values(map);

      if (cookiesList.length === 0) {
        btnSync.disabled = false;
        showStatus('No YouTube cookies found. Please make sure you are logged into YouTube in this browser.', 'error');
        return;
      }

      showStatus('Uploading ' + cookiesList.length + ' cookies to proxy…', 'info');

      var targetEndpoint = rawUrl + '/api/cookies/sync';

      fetch(targetEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          source: 'mac_extension',
          timestamp: Date.now(),
          cookies: cookiesList
        })
      })
      .then(function(response) {
        if (!response.ok) {
          throw new Error('Server returned HTTP ' + response.status);
        }
        return response.json();
      })
      .then(function(data) {
        btnSync.disabled = false;
        var now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        var successMsg = '✓ Synced ' + (data.count || cookiesList.length) + ' cookies at ' + now + '! yt-dlp playback is ready.';
        showStatus(successMsg, 'success');
        chrome.storage.local.set({
          serverUrl: rawUrl,
          lastSyncTime: Date.now(),
          lastSyncStatus: { msg: successMsg, type: 'success' }
        });
      })
      .catch(function(err) {
        btnSync.disabled = false;
        var errMsg = 'Sync failed: ' + err.message + '. Ensure ' + rawUrl + ' is reachable.';
        showStatus(errMsg, 'error');
        chrome.storage.local.set({
          lastSyncStatus: { msg: errMsg, type: 'error' }
        });
      });
    }).catch(function(err) {
      btnSync.disabled = false;
      showStatus('Error accessing cookies: ' + err.message, 'error');
    });
  }
});
