from flask import Flask, render_template, request, redirect, url_for, Response, send_file
from ytmusicapi import YTMusic, setup
import yt_dlp
import os
import json
import threading
import requests as req_lib
import hashlib
import time

app = Flask(__name__)

# Initialize YTMusic with premium headers if available, otherwise unauthenticated
auth_file = 'headers_auth.json'
if os.path.exists(auth_file):
    ytmusic = YTMusic(auth_file)
else:
    ytmusic = YTMusic()

import shutil
NODE_PATH = shutil.which('node') or shutil.which('nodejs') or 'node'
YTDLP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'venv', 'bin', 'yt-dlp')
if not os.path.exists(YTDLP_PATH):
    YTDLP_PATH = shutil.which('yt-dlp')

def make_ytdl_opts():
    """Build yt-dlp Python API options for metadata only (no download)."""
    opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio',
        'quiet': True,
        'no_warnings': True,
    }
    if os.path.exists('cookies.txt'):
        opts['cookiefile'] = 'cookies.txt'
    elif os.path.exists('headers_auth.json'):
        try:
            with open('headers_auth.json', 'r') as f:
                opts['http_headers'] = json.load(f)
        except Exception as e:
            print(f"Failed to load headers: {e}")
    return opts

# yt-dlp opts for metadata extraction (no download)
ytdl_opts = make_ytdl_opts()

# Cache directory for downloaded audio
CACHE_DIR = 'audio_cache'
os.makedirs(CACHE_DIR, exist_ok=True)
IMAGE_CACHE_DIR = 'image_cache'
os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)
METADATA_CACHE_DIR = 'metadata_cache'
os.makedirs(METADATA_CACHE_DIR, exist_ok=True)

# Helper for caching metadata
def get_cached_metadata(key, fetch_func, expiry_seconds=86400):
    cache_path = os.path.join(METADATA_CACHE_DIR, f"{hashlib.md5(key.encode()).hexdigest()}.json")
    if os.path.exists(cache_path):
        if time.time() - os.path.getmtime(cache_path) < expiry_seconds:
            try:
                with open(cache_path, 'r') as f:
                    return json.load(f)
            except:
                pass
    
    data = fetch_func()
    try:
        with open(cache_path, 'w') as f:
            json.dump(data, f)
    except:
        pass
    return data

def get_dir_size(path):
    total = 0
    if not os.path.exists(path): return 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total += os.path.getsize(fp)
    return total

@app.context_processor
def inject_image_proxy():
    def proxy_image(url):
        if not url: return ''
        import urllib.parse
        return url_for('proxy_image_route', url=url)
    return dict(proxy_image=proxy_image)

# Track files being downloaded (to avoid double-downloading)
download_locks = {}
download_locks_lock = threading.Lock()

# Progress tracking: {video_id: {'percent': 0-100, 'status': 'queued|downloading|done|error'}}
download_progress = {}

def get_auth_headers():
    """Get auth headers with Accept-Encoding stripped for raw byte serving."""
    headers = {}
    if os.path.exists('headers_auth.json'):
        with open('headers_auth.json', 'r') as f:
            headers = json.load(f)
    headers.pop('Accept-Encoding', None)
    return headers

def get_cached_audio_path(video_id):
    """Return path to cached audio file if it exists."""
    for ext in ['m4a', 'mp3', 'webm']:
        path = os.path.join(CACHE_DIR, f'{video_id}.{ext}')
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
    return None

def download_audio(video_id, background=False):
    """Download audio to cache using yt-dlp CLI with progress tracking."""
    with download_locks_lock:
        if video_id not in download_locks:
            download_locks[video_id] = threading.Lock()
        lock = download_locks[video_id]

    # If already downloading in background, don't block — just return None
    if background and lock.locked():
        return None

    with lock:
        cached = get_cached_audio_path(video_id)
        if cached:
            download_progress[video_id] = {'percent': 100, 'status': 'done'}
            return cached

        download_progress[video_id] = {'percent': 0, 'status': 'downloading'}

        url = f'https://music.youtube.com/watch?v={video_id}'
        out_tmpl = os.path.join(CACHE_DIR, f'{video_id}.%(ext)s')

        cmd = [
            YTDLP_PATH,
            '--format', 'bestaudio[ext=m4a]/bestaudio',
            '--js-runtimes', 'node',
            '--remote-components', 'ejs:github',
            '--output', out_tmpl,
            '--no-playlist',
            '--no-part',  # Write directly to destination so stream can read it immediately
            '--newline',  # Force one progress line per update (parseable)
        ]
        if os.path.exists('cookies.txt'):
            cmd += ['--cookies', 'cookies.txt']
        cmd.append(url)

        print(f'[download] Starting: {video_id}')
        try:
            import subprocess, re
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            error_log = []
            for line in proc.stdout:
                line = line.rstrip()
                error_log.append(line)
                # Parse: [download]  37.5% of    5.84MiB ...
                m = re.search(r'\[download\]\s+(\d+\.?\d*)%', line)
                
                if video_id not in download_progress:
                    download_progress[video_id] = {}
                    
                if m:
                    pct = float(m.group(1))
                    download_progress[video_id]['percent'] = pct
                    download_progress[video_id]['status'] = 'downloading'
                    
                # Parse total size
                if 'total_bytes' not in download_progress[video_id]:
                    sz_m = re.search(r'of\s+[~]?(\d+\.?\d*)(KiB|MiB|GiB|B)', line)
                    if sz_m:
                        val = float(sz_m.group(1))
                        unit = sz_m.group(2)
                        mult = {'B': 1, 'KiB': 1024, 'MiB': 1024**2, 'GiB': 1024**3}
                        download_progress[video_id]['total_bytes'] = int(val * mult[unit])
            proc.wait(timeout=300)
            if proc.returncode != 0:
                download_progress[video_id] = {'percent': 0, 'status': 'error'}
                print(f'[download] yt-dlp error for {video_id}')
                print("\n".join(error_log))
                return None
            download_progress[video_id] = {'percent': 100, 'status': 'done'}
            print(f'[download] Done: {video_id}')
        except Exception as e:
            download_progress[video_id] = {'percent': 0, 'status': 'error'}
            print(f'[download] Exception: {e}')
            return None

        return get_cached_audio_path(video_id)

def download_audio_bg(video_id):
    """Trigger a background download without blocking."""
    t = threading.Thread(target=download_audio, args=(video_id, True), daemon=True)
    t.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/image')
def proxy_image_route():
    url = request.args.get('url')
    if not url: return "No url", 400
    
    hash_key = hashlib.md5(url.encode()).hexdigest()
    # extension from url or default to jpg
    ext = url.split('?')[0].split('.')[-1]
    if ext not in ['jpg', 'jpeg', 'png', 'webp', 'gif']:
        ext = 'jpg'
    filepath = os.path.join(IMAGE_CACHE_DIR, f"{hash_key}.{ext}")
    
    if not os.path.exists(filepath):
        try:
            r = req_lib.get(url, timeout=10, stream=True)
            if r.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in r.iter_content(1024):
                        f.write(chunk)
            else:
                return "Failed to fetch image", 404
        except Exception as e:
            return f"Error fetching image: {e}", 500
            
    return send_file(filepath)

@app.route('/search')
def search():
    query = request.args.get('q', '')
    if not query:
        return redirect(url_for('index'))
    
    try:
        results = get_cached_metadata(f"search_{query}", lambda: ytmusic.search(query, filter='songs'))
    except Exception as e:
        results = []
        print(f"Search error: {e}")
        
    return render_template('search.html', query=query, results=results)

@app.route('/play/<video_id>')
def play(video_id):
    try:
        def fetch_info():
            url = f'https://music.youtube.com/watch?v={video_id}'
            with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
                return ydl.extract_info(url, download=False)
                
        info = get_cached_metadata(f"play_{video_id}", fetch_info)
        
        thumbnail = info.get('thumbnail', '')
        if thumbnail:
            thumbnail = thumbnail.replace('vi_webp', 'vi').replace('.webp', '.jpg')
            
        return render_template('play.html', song_title=info.get('title'), artist=info.get('uploader'), video_id=video_id, thumbnail=thumbnail)
    except Exception as e:
        return f"Error loading song: {str(e)}", 500

@app.route('/status/<video_id>')
def status(video_id):
    """Return download progress as JSON. Polled by the frontend."""
    cached = get_cached_audio_path(video_id)
    if cached:
        return json.dumps({'percent': 100, 'status': 'done'})
    prog = download_progress.get(video_id, {'percent': 0, 'status': 'queued'})
    return json.dumps(prog)

@app.route('/preload/<video_id>')
def preload(video_id):
    """Trigger background download of a video_id. Returns immediately."""
    cached = get_cached_audio_path(video_id)
    if cached:
        return json.dumps({'status': 'done'})
    if video_id not in download_progress:
        download_audio_bg(video_id)
        download_progress[video_id] = {'percent': 0, 'status': 'queued'}
    return json.dumps({'status': download_progress.get(video_id, {}).get('status', 'queued')})


@app.route('/stream/<video_id>')
def stream(video_id):
    """
    If the file is already cached locally, stream it using send_file.
    If it's not cached yet, redirect the browser to the direct YouTube stream URL
    so it plays instantly while the background preload task finishes caching it.
    """
    try:
        # If file is fully downloaded, use standard send_file
        cached_path = get_cached_audio_path(video_id)
        status_info = download_progress.get(video_id, {})
        status = status_info.get('status')
        total_size = status_info.get('total_bytes')

        if cached_path and os.path.exists(cached_path) and status == 'done':
            ext = cached_path.rsplit('.', 1)[-1]
            mime = {'m4a': 'audio/mp4', 'mp3': 'audio/mpeg', 'webm': 'audio/webm', 'ogg': 'audio/ogg'}.get(ext, 'audio/mp4')
            return send_file(cached_path, mimetype=mime, conditional=True)

        # Wait until file starts downloading and we know its total size
        import time
        for _ in range(60): # Wait up to 30s for yt-dlp to start outputting size
            cached_path = get_cached_audio_path(video_id)
            status_info = download_progress.get(video_id, {})
            total_size = status_info.get('total_bytes')
            if status_info.get('status') == 'error':
                return "Audio download failed internally", 500
            if cached_path and os.path.exists(cached_path) and total_size:
                break
            time.sleep(0.5)
        else:
            return "Audio is still preparing...", 500

        ext = cached_path.rsplit('.', 1)[-1]
        mime = {'m4a': 'audio/mp4', 'mp3': 'audio/mpeg', 'webm': 'audio/webm', 'ogg': 'audio/ogg'}.get(ext, 'audio/mp4')

        # Handle Range requests for the growing file
        range_header = request.headers.get('Range', None)
        start = 0
        end = total_size - 1
        
        if range_header:
            match = re.search(r'bytes=(\d+)-(\d*)', range_header)
            if match:
                start = int(match.group(1))
                if match.group(2):
                    end = int(match.group(2))
                    
        length = end - start + 1
        
        def generate():
            with open(cached_path, 'rb') as f:
                f.seek(start)
                pos = start
                while pos <= end:
                    chunk_size = min(8192, end - pos + 1)
                    data = f.read(chunk_size)
                    if data:
                        yield data
                        pos += len(data)
                    else:
                        s = download_progress.get(video_id, {}).get('status')
                        if s in ('done', 'error'):
                            break
                        time.sleep(0.1)

        headers = {
            'Content-Type': mime,
            'Content-Length': str(length),
            'Accept-Ranges': 'bytes',
        }
        status_code = 200
        if range_header:
            headers['Content-Range'] = f'bytes {start}-{end}/{total_size}'
            status_code = 206
            
        return Response(generate(), status=status_code, headers=headers)

    except Exception as e:
        return f"Stream error: {str(e)}", 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    global ytmusic
    if request.method == 'POST':
        headers = request.form.get('headers')
        if headers:
            try:
                setup(filepath='headers_auth.json', headers_raw=headers)
                ytmusic = YTMusic('headers_auth.json')
                return redirect(url_for('library'))
            except Exception as e:
                return f"Error setting up authentication: {e}", 400
    return render_template('login.html')

@app.route('/library')
def library():
    try:
        playlists = ytmusic.get_library_playlists()
        return render_template('library.html', playlists=playlists)
    except Exception as e:
        print(f"Auth error (redirecting to login): {str(e)}")
        return redirect(url_for('login'))

@app.route('/playlist/<playlist_id>')
def playlist(playlist_id):
    try:
        pl = ytmusic.get_playlist(playlist_id)
        return render_template('playlist.html', playlist=pl)
    except Exception as e:
        return f"Error loading playlist: {str(e)}", 500

@app.route('/settings')
def settings():
    audio_size = get_dir_size(CACHE_DIR)
    image_size = get_dir_size(IMAGE_CACHE_DIR)
    metadata_size = get_dir_size(METADATA_CACHE_DIR)
    total_size = audio_size + image_size + metadata_size
    
    def format_size(size_bytes):
        if size_bytes == 0: return "0 B"
        size_name = ("B", "KB", "MB", "GB", "TB")
        import math
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return "%s %s" % (s, size_name[i])
        
    return render_template('settings.html', 
                          audio_size=format_size(audio_size),
                          image_size=format_size(image_size),
                          metadata_size=format_size(metadata_size),
                          total_size=format_size(total_size))

@app.route('/settings/clear', methods=['POST'])
def clear_cache():
    cache_type = request.form.get('type')
    dirs_to_clear = []
    if cache_type == 'audio': dirs_to_clear = [CACHE_DIR]
    elif cache_type == 'image': dirs_to_clear = [IMAGE_CACHE_DIR]
    elif cache_type == 'metadata': dirs_to_clear = [METADATA_CACHE_DIR]
    elif cache_type == 'all': dirs_to_clear = [CACHE_DIR, IMAGE_CACHE_DIR, METADATA_CACHE_DIR]
    
    for d in dirs_to_clear:
        if not os.path.exists(d): continue
        for f in os.listdir(d):
            fp = os.path.join(d, f)
            try:
                if os.path.isfile(fp) or os.path.islink(fp):
                    os.unlink(fp)
            except Exception as e:
                pass
    return redirect(url_for('settings'))

if __name__ == '__main__':
    # threaded=True is critical — Safari sends parallel range requests
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
