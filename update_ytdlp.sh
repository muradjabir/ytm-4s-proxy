#!/bin/bash
set -e
PROJECT_DIR="/home/murad/ytm_4s_proxy"
cd "$PROJECT_DIR"

OLD_VER=$("$PROJECT_DIR/venv/bin/yt-dlp" --version 2>/dev/null || echo "unknown")
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Checking for yt-dlp updates (Current: $OLD_VER)..."

# Check and update yt-dlp in virtualenv
OUTPUT=$("$PROJECT_DIR/venv/bin/pip" install --upgrade --pre yt-dlp 2>&1)
NEW_VER=$("$PROJECT_DIR/venv/bin/yt-dlp" --version 2>/dev/null || echo "unknown")

if [ "$OLD_VER" != "$NEW_VER" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Successfully updated yt-dlp: $OLD_VER -> $NEW_VER"
    systemctl --user restart ytm-proxy.service 2>/dev/null || true
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Restarted ytm-proxy.service"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] yt-dlp is already up to date ($NEW_VER)"
fi
