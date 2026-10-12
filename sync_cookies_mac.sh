#!/bin/bash
# sync_cookies_mac.sh
# Run this script on your Mac to sync YouTube cookies to your Ubuntu proxy server.
#
# Usage:
#   ./sync_cookies_mac.sh [SERVER_URL] [BROWSER]
#
# Examples:
#   ./sync_cookies_mac.sh
#   ./sync_cookies_mac.sh http://192.168.2.2:5000 chrome
#   ./sync_cookies_mac.sh http://192.168.2.2:5000 brave

SERVER_URL="${1:-http://192.168.2.2:5000}"
SERVER_URL="${SERVER_URL%/}"
BROWSER="${2:-chrome}"

echo "==========================================="
echo "   YTM 4S Proxy - Mac Cookie Sync"
echo "==========================================="
echo "Target server: $SERVER_URL"
echo "Browser:       $BROWSER"
echo ""

# Check for yt-dlp on Mac to extract browser cookies
if command -v yt-dlp >/dev/null 2>&1; then
    echo "Extracting cookies from $BROWSER using yt-dlp..."
    COOKIE_TMP="$(mktemp -t ytm_cookies.XXXXXX.txt)"
    
    if yt-dlp --cookies-from-browser "$BROWSER" --cookies "$COOKIE_TMP" --simulate "https://www.youtube.com" >/dev/null 2>&1; then
        echo "Successfully extracted cookies. Uploading to proxy server..."
        RESP=$(curl -s -X POST -F "file=@$COOKIE_TMP" "$SERVER_URL/api/cookies/upload")
        rm -f "$COOKIE_TMP"
        echo "Response: $RESP"
        echo ""
        echo "Done! Cookies updated on $SERVER_URL."
        exit 0
    else
        rm -f "$COOKIE_TMP"
        echo "Notice: Could not directly extract from $BROWSER via yt-dlp."
    fi
fi

# Fallback: check if a cookies.txt file already exists locally in Downloads or current folder
for CANDIDATE in "./cookies.txt" "$HOME/Downloads/cookies.txt" "$HOME/Downloads/youtube.com_cookies.txt"; do
    if [ -f "$CANDIDATE" ]; then
        echo "Found local cookie file: $CANDIDATE"
        echo "Uploading to $SERVER_URL..."
        RESP=$(curl -s -X POST -F "file=@$CANDIDATE" "$SERVER_URL/api/cookies/upload")
        echo "Response: $RESP"
        echo ""
        echo "Done! Uploaded $CANDIDATE to $SERVER_URL."
        exit 0
    fi
done

echo "Tip: You can install the Chrome/Brave/Edge extension in the 'extension/' folder"
echo "for instant 1-click & automatic background cookie syncing from your Mac!"
echo "Or visit $SERVER_URL/settings to upload or paste cookies."
