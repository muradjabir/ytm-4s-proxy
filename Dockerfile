# Multi-stage Dockerfile: Node 22 for JS challenge solver + Python 3.12 with ffmpeg
FROM node:22-slim AS node-source

FROM python:3.12-slim

# Install system runtime dependencies: ffmpeg, curl, ca-certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy modern Node.js 22 binary & runtime from node-source stage
COPY --from=node-source /usr/local/bin/node /usr/local/bin/node
COPY --from=node-source /usr/local/lib/node_modules /usr/local/lib/node_modules

# Verify node & ffmpeg
RUN node -v && ffmpeg -version | head -n 1

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensure latest yt-dlp nightly is used for YouTube compatibility
RUN pip install --no-cache-dir -U --pre "yt-dlp[default]"

# Copy application source
COPY . .

# Create cache directories
RUN mkdir -p audio_cache/.tmp image_cache metadata_cache

ENV PYTHONUNBUFFERED=1
EXPOSE 5000

CMD ["python", "app.py"]
