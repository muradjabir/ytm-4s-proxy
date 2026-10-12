# YTM Proxy Cookie Sync (Mac Browser Extension)

A lightweight browser extension that automatically exports YouTube Music session cookies from your Mac browser to the Ubuntu proxy server.

## Features
- **1-Click Sync**: Click the extension icon and hit "Sync YouTube Cookies Now".
- **Automatic Background Sync**: Automatically updates the proxy server whenever you browse YouTube Music.
- **Direct Netscape Export**: Ensures yt-dlp receives unexpired, rotated cookies (including `__Secure-3PSID`, `SAPISID`, and `LOGIN_INFO`).

## How to Install on Mac (Chrome / Brave / Edge / Arc)
1. Open your browser and go to `chrome://extensions` (or `brave://extensions`, `edge://extensions`).
2. Toggle on **"Developer mode"** in the top right corner.
3. Click **"Load unpacked"** in the top left.
4. Select this `extension` folder.
5. Click the extension icon in your browser toolbar, confirm your Ubuntu Server URL (e.g., `http://192.168.2.2:5000`), and click **"Sync YouTube Cookies Now"**.

Done! Your proxy server is now equipped with live cookies from your Mac browser.
