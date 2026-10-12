# YTM 4S Proxy

A lightweight YouTube Music proxy server designed specifically to run perfectly on legacy devices like the iPhone 4S running iOS 9. 

This project bridges the gap between modern YouTube Music APIs and older WebKit browsers by handling all the heavy lifting (API calls, thumbnail proxying, audio downloading, and caching) on the server side, serving a simple, beautiful, and responsive ES5-compatible web interface to the client.

## ✨ Features

- **Legacy Safari Compatible**: Fully functional on iOS 9's Safari browser. Uses pure ES5 JavaScript and legacy CSS techniques (no Flexbox reliance, no modern ES6 features).
- **Instant Server-Side Audio Processing**: Bypasses YouTube's complex streaming, IP-binding, and Range-request problems by utilizing `yt-dlp` to download the audio stream locally to the server. The proxy simulates HTTP Range headers for the growing file, allowing the audio to begin streaming instantly on the iPhone while the background download finishes.
- **Robust Caching System**:
  - **Audio Cache**: Downloaded songs are saved locally. Playing them again is instant and completely bypasses YouTube's servers.
  - **Image Proxy & Cache**: Bypasses Google's CDN CORS/SSL issues by proxying and caching all album art through the server as local JPEGs.
  - **Metadata Cache**: Search queries and track info are cached to dramatically reduce YouTube API calls.
  - **Cache Management**: Includes a dedicated Settings page to monitor cache size and clear them.
- **AJAX Navigation (PJAX)**: Page navigation is handled via AJAX to ensure seamless transitions without interrupting the background audio session.
- **Background Preloading**: Automatically starts pre-fetching the next song in the queue in the background.

---

## 🎧 Important iOS 9 Note: Background Audio vs Fullscreen Mode

Apple places severe limitations on background audio in iOS 9. You have two ways to use this web app on your iPhone 4S, and you must choose based on your preference:

### 1. Normal Safari Mode (Recommended)
- **How to use**: Open the Safari browser, type in your server IP, and use it normally.
- **Pros**: **Background audio works perfectly!** You can lock your screen or switch apps, and the music will continue to play. 
- **Cons**: The Safari top URL bar and bottom navigation bar will be visible.

### 2. Fullscreen Web App Mode (Home Screen Icon)
- **How to use**: Tap the "Share" button in Safari and select "Add to Home Screen". Launch the app from your home screen.
- **Pros**: Completely fullscreen experience with no Safari bars. Looks like a native app.
- **Cons**: **No background audio.** iOS 9 forcefully suspends all audio the exact millisecond the screen is locked or the app is minimized when using fullscreen Home Screen apps. There is no workaround for this.

---

## 🚀 Setup & Running

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   *Note: Ensure you have `ffmpeg` and `nodejs` installed on your system for audio processing and JavaScript extraction.*

2. **Run the Server**:
   ```bash
   ./monitor_logs.sh
   # Or run directly via Python:
   # python app.py
   ```

3. **Access**:
   Find your server's local IP address and navigate to `http://<SERVER_IP>:5000` on your iPhone 4S.

---

## 🔑 Authentication & Cookie Sync (Mac Browser & yt-dlp)

Since YouTube periodically rotates and invalidates cookies, and requires cookies for downloading age-restricted or copyright-protected audio streams via `yt-dlp`, you can sync fresh cookies from your Mac browser directly to the Ubuntu server at any time.

### Method 1: Automatic Mac Browser Extension (Recommended)
1. In your Mac browser (Chrome / Brave / Edge / Arc), download the extension from `http://<SERVER_IP>:5000/extension/download` or use the folder in `extension/`.
2. Open `chrome://extensions` (or `brave://extensions`), toggle on **Developer mode**, and click **Load unpacked**.
3. Select the unzipped `extension/` folder.
4. Click the extension icon in your browser toolbar, enter your Ubuntu server URL (`http://<SERVER_IP>:5000`), and click **Sync YouTube Cookies Now**.
5. Enable **Auto-sync on YouTube visit** to automatically refresh cookies in the background whenever you browse YouTube Music!

### Method 2: Direct Upload in Settings
1. On your Mac or iPhone, open `http://<SERVER_IP>:5000/settings`.
2. Under **YouTube Browser Cookie Sync**, drop your exported `cookies.txt` or paste raw cookies/headers and click **Save**.

### Method 3: Mac Terminal Script
Run from your Mac terminal:
```bash
./sync_cookies_mac.sh http://192.168.2.2:5000 chrome
```

