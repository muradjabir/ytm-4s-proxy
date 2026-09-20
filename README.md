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

## 🔑 Authentication (Obtaining Cookies/Headers)

To access your personal library, playlists, and age-restricted/premium songs, you must authenticate the proxy with your YouTube Music account. Since YouTube session cookies expire periodically, you may need to repeat this process if you get logged out or encounter 403 Forbidden errors.

**Step-by-Step Instructions:**

1. Open your desktop web browser (Chrome, Firefox, Edge, or Safari).
2. Go to [music.youtube.com](https://music.youtube.com) and ensure you are logged in.
3. Open the **Developer Tools** (Press `F12` or `Ctrl+Shift+I`).
4. Navigate to the **Network** tab.
5. Click on the **"Fetch/XHR"** filter button at the top of the Network tab. *(This is crucial—you must copy headers from an API request, not an image request!)*
6. Refresh the page (`F5`) or click on a playlist to generate some network traffic.
7. Look for a request named **`browse`** or **`next`** in the list and click on it.
8. Scroll down to the **"Request Headers"** section.
9. Right-click anywhere in the Request Headers section and click **"Copy Request Headers"** (or manually select and copy all the text in that section).
10. Open the proxy server URL in a browser: `http://<YOUR-SERVER-IP>:5000/login`
11. Paste the copied headers into the text box and click "Connect Account".

The server will automatically generate the `headers_auth.json` file and redirect you to your library!

*(Note: If you continue to experience playback errors on certain tracks, ensure that your `cookies.txt` file is also exported using a browser extension like "Get cookies.txt LOCALLY" and placed in the project root directory alongside `app.py`, as `yt-dlp` relies on standard cookie formatting for some restricted tracks).*
