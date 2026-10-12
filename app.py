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

from ytmusicapi.auth.oauth.credentials import OAuthCredentials

# Initialize YTMusic with permanent OAuth if available, otherwise headers, otherwise unauthenticated
oauth_file = 'oauth.json'
auth_file = 'headers_auth.json'

def get_client_credentials():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for f in os.listdir(base_dir):
        if f.startswith('client_secret') and f.endswith('.json'):
            try:
                with open(os.path.join(base_dir, f), 'r') as cf:
                    data = json.load(cf)
                    cs = data.get('installed') or data.get('web')
                    if cs and 'client_id' in cs and 'client_secret' in cs:
                        return cs['client_id'], cs['client_secret']
            except Exception as e:
                print(f"[oauth] Error reading {f}: {e}")
    return None, None

def get_active_auth_file():
    if os.path.exists(oauth_file):
        return oauth_file
    if os.path.exists(auth_file):
        return auth_file
    return None

def init_ytmusic():
    if os.path.exists(oauth_file):
        client_id, client_secret = get_client_credentials()
        if client_id and client_secret:
            try:
                creds = OAuthCredentials(client_id=client_id, client_secret=client_secret)
                yt = YTMusic(oauth_file, oauth_credentials=creds)
                yt.context['context']['client']['clientName'] = 'TVHTML5'
                yt.context['context']['client']['clientVersion'] = '7.20240101.00.00'
                return yt, 'oauth'
            except Exception as e:
                print(f"[auth] OAuth init failed: {e}")
    if os.path.exists(auth_file):
        try:
            return YTMusic(auth_file), 'headers'
        except Exception as e:
            print(f"[auth] Headers init failed: {e}")
    return YTMusic(), None

ytmusic, _current_auth_type = init_ytmusic()
yt_public = YTMusic()

_auth_state = {
    'logged_in': False,
    'auth_type': _current_auth_type,
    'last_checked': 0,
    'error': None
}

def extract_tv_playlists(data):
    results = []
    def find_tiles(node):
        if isinstance(node, dict):
            if 'tileRenderer' in node:
                yield node['tileRenderer']
            for v in node.values():
                yield from find_tiles(v)
        elif isinstance(node, list):
            for item in node:
                yield from find_tiles(item)

    for tile in find_tiles(data):
        meta = tile.get('metadata', {}).get('tileMetadataRenderer', {})
        runs = meta.get('title', {}).get('runs', [])
        title = runs[0].get('text') if runs else None
        
        nav = runs[0].get('navigationEndpoint', {}) if runs else {}
        browse_id = nav.get('browseEndpoint', {}).get('browseId', '')
        if not browse_id:
            browse_id = tile.get('onSelectCommand', {}).get('browseEndpoint', {}).get('browseId', '')
            
        playlist_id = browse_id
        if playlist_id.startswith('VL'):
            playlist_id = playlist_id[2:]
            
        thumbs = tile.get('header', {}).get('tileHeaderRenderer', {}).get('thumbnail', {}).get('thumbnails', [])
        
        subtitle = ''
        lines = meta.get('lines', [])
        if lines:
            items = lines[0].get('lineRenderer', {}).get('items', [])
            if items:
                subtitle = items[0].get('lineItemRenderer', {}).get('text', {}).get('simpleText', '')
        
        if title and playlist_id:
            results.append({
                'title': title,
                'playlistId': playlist_id,
                'thumbnails': thumbs,
                'count': subtitle
            })
    return results

def extract_tv_playlist(data, default_title='Playlist'):
    playlist_info = {
        'title': default_title,
        'tracks': [],
        'thumbnails': []
    }
    def find_key(node, key):
        if isinstance(node, dict):
            if key in node:
                yield node[key]
            for v in node.values():
                yield from find_key(v, key)
        elif isinstance(node, list):
            for item in node:
                yield from find_key(item, key)

    for em in find_key(data, 'entityMetadataRenderer'):
        t = em.get('title', {})
        t_text = t.get('simpleText') or (t.get('runs', [{}])[0].get('text') if t.get('runs') else None)
        if t_text:
            playlist_info['title'] = t_text
        thumbs = em.get('thumbnail', {}).get('thumbnails', [])
        if thumbs:
            playlist_info['thumbnails'] = thumbs

    for tile in find_key(data, 'tileRenderer'):
        header = tile.get('header', {}).get('tileHeaderRenderer', {})
        meta = tile.get('metadata', {}).get('tileMetadataRenderer', {})
        
        video_id = tile.get('contentId')
        title = meta.get('title', {}).get('simpleText')
        if not title:
            runs = meta.get('title', {}).get('runs', [])
            title = runs[0].get('text') if runs else 'Unknown'
            
        artist = meta.get('subtitle', {}).get('simpleText')
        if not artist:
            lines = meta.get('lines', [])
            if lines:
                artist_items = lines[0].get('lineRenderer', {}).get('items', [])
                if artist_items:
                    t_obj = artist_items[0].get('lineItemRenderer', {}).get('text', {})
                    artist = t_obj.get('simpleText') or (t_obj.get('runs', [{}])[0].get('text') if t_obj.get('runs') else 'Unknown')
        
        duration = None
        for ov in header.get('thumbnailOverlays', []):
            time_txt = ov.get('thumbnailOverlayTimeStatusRenderer', {}).get('text', {}).get('simpleText')
            if time_txt:
                duration = time_txt
                break
                
        thumbs = header.get('thumbnail', {}).get('thumbnails', [])
        
        if video_id and title:
            playlist_info['tracks'].append({
                'videoId': video_id,
                'title': title,
                'artists': [{'name': artist or 'Unknown'}],
                'duration': duration or '',
                'thumbnails': thumbs
            })
    return playlist_info

def check_yt_session_valid():
    """Verify if YouTube Music backend actually considers this session authenticated."""
    if not get_active_auth_file():
        return False
    try:
        response = ytmusic._send_request('browse', {'browseId': 'FEmusic_liked_playlists'})
        for stp in response.get('responseContext', {}).get('serviceTrackingParams', []):
            for param in stp.get('params', []):
                if param.get('key') == 'logged_in':
                    return param.get('value') == '1'
        return False
    except Exception as e:
        print(f"[auth] Verification error: {e}")
        return False

def verify_auth_background():
    """Verify auth in background to avoid blocking server start or requests."""
    global _auth_state
    f = get_active_auth_file()
    if not f:
        _auth_state['logged_in'] = False
        _auth_state['auth_type'] = None
        _auth_state['last_checked'] = time.time()
        _auth_state['error'] = 'No credentials configured'
        return
    is_valid = check_yt_session_valid()
    _auth_state['logged_in'] = is_valid
    _auth_state['auth_type'] = 'oauth' if f == oauth_file else 'headers'
    _auth_state['error'] = None if is_valid else 'Session expired or invalid (YouTube returned guest mode)'
    _auth_state['last_checked'] = time.time()
    print(f"[auth] Checked YouTube auth state: logged_in={is_valid} (type={_auth_state['auth_type']})")

# Background check on startup
threading.Thread(target=verify_auth_background, daemon=True).start()

def is_user_logged_in():
    """Return cached auth status, triggering background refresh if older than 10 mins."""
    if not get_active_auth_file():
        return False
    now = time.time()
    if now - _auth_state['last_checked'] > 600:
        threading.Thread(target=verify_auth_background, daemon=True).start()
    return bool(_auth_state['logged_in'])

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
    
    logged_in = is_user_logged_in()
    msg_param = request.args.get('msg', '')
    
    banner_message = None
    banner_type = None
    if msg_param == 'logged_in':
        banner_message = "Successfully logged in to YouTube Music."
        banner_type = "success"
    elif msg_param == 'logged_out':
        banner_message = "You have logged out. Proxy is in guest mode."
        banner_type = "info"
    elif msg_param == 'auth_required':
        banner_message = "Please log in to access your library."
        banner_type = "warning"
    elif msg_param == 'session_expired':
        banner_message = "Your session expired. Please paste fresh headers from music.youtube.com."
        banner_type = "warning"
        
    return dict(
        proxy_image=proxy_image,
        is_logged_in=logged_in,
        auth_type=_auth_state.get('auth_type'),
        auth_error=_auth_state.get('error'),
        banner_message=banner_message,
        banner_type=banner_type
    )

@app.after_request
def add_auth_header(response):
    response.headers['X-Auth-Status'] = 'logged_in' if is_user_logged_in() else 'not_logged_in'
    return response

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
    """Download audio to cache using yt-dlp CLI with rich progress and speed tracking."""
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
            download_progress[video_id] = {
                'percent': 100,
                'status': 'done',
                'state': 'Ready',
                'message': 'Loaded from cache',
                'speed': '',
                'eta': '',
                'total_bytes': os.path.getsize(cached)
            }
            return cached

        download_progress[video_id] = {
            'percent': 0,
            'status': 'starting',
            'state': 'Connecting…',
            'message': 'Connecting to YouTube…',
            'speed': '',
            'eta': ''
        }

        url = f'https://music.youtube.com/watch?v={video_id}'
        out_tmpl = os.path.join(CACHE_DIR, f'{video_id}.%(ext)s')

        cmd = [
            YTDLP_PATH,
            '--format', 'bestaudio[ext=m4a]/bestaudio',
            '--js-runtimes', 'node',
            '--remote-components', 'ejs:github',
            '--concurrent-fragments', '4',  # Download fragments concurrently for faster playback
            '--buffer-size', '16K',
            '--output', out_tmpl,
            '--no-playlist',
            '--no-part',  # Write directly to destination so stream can read it immediately
            '--newline',  # Force one progress line per update (parseable)
        ]
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
                
                if '[youtube]' in line:
                    if 'Downloading webpage' in line:
                        download_progress[video_id]['state'] = 'Fetching info…'
                        download_progress[video_id]['message'] = 'Fetching track metadata…'
                    elif 'player API' in line:
                        download_progress[video_id]['state'] = 'Getting stream…'
                        download_progress[video_id]['message'] = 'Resolving audio stream…'
                elif '[jsc:' in line:
                    download_progress[video_id]['state'] = 'Solving…'
                    download_progress[video_id]['message'] = 'Solving audio challenge…'
                elif '[download] Destination:' in line:
                    download_progress[video_id]['state'] = 'Starting…'
                    download_progress[video_id]['message'] = 'Starting audio download…'
                elif '[Fixup' in line:
                    download_progress[video_id]['state'] = 'Finalizing…'
                    download_progress[video_id]['message'] = 'Finalizing audio container…'
                
                # Parse: [download]  37.5% of    5.84MiB at    1.20MiB/s ETA 00:03
                m = re.search(r'\[download\]\s+(\d+\.?\d*)%', line)
                if m:
                    pct = float(m.group(1))
                    download_progress[video_id]['percent'] = pct
                    download_progress[video_id]['status'] = 'downloading'
                    
                    sp_m = re.search(r'at\s+([~]?\d+\.?\d*(?:KiB|MiB|GiB|B)/s)', line)
                    speed = sp_m.group(1) if sp_m else ''
                    if speed:
                        download_progress[video_id]['speed'] = speed
                    
                    eta_m = re.search(r'ETA\s+(\d+:\d+)', line)
                    eta = eta_m.group(1) if eta_m else ''
                    if eta:
                        download_progress[video_id]['eta'] = eta
                        
                    short_spd = speed.replace('/s', '').strip()
                    if speed:
                        download_progress[video_id]['state'] = f"{int(pct)}% ({short_spd})"
                    else:
                        download_progress[video_id]['state'] = f"{int(pct)}%"
                        
                    msg_parts = [f"Downloading {int(pct)}%"]
                    if speed:
                        msg_parts.append(speed)
                    if eta:
                        msg_parts.append(f"ETA {eta}")
                    download_progress[video_id]['message'] = " • ".join(msg_parts)
                    
                # Parse total size
                if 'total_bytes' not in download_progress[video_id] or not download_progress[video_id]['total_bytes']:
                    sz_m = re.search(r'of\s+[~]?(\d+\.?\d*)(KiB|MiB|GiB|B)', line)
                    if sz_m:
                        val = float(sz_m.group(1))
                        unit = sz_m.group(2)
                        mult = {'B': 1, 'KiB': 1024, 'MiB': 1024**2, 'GiB': 1024**3}
                        download_progress[video_id]['total_bytes'] = int(val * mult[unit])
            proc.wait(timeout=300)
            if proc.returncode != 0:
                download_progress[video_id] = {
                    'percent': 0,
                    'status': 'error',
                    'state': 'Failed',
                    'message': 'Audio download failed'
                }
                print(f'[download] yt-dlp error for {video_id}')
                print("\n".join(error_log))
                return None
            download_progress[video_id] = {
                'percent': 100,
                'status': 'done',
                'state': 'Ready',
                'message': 'Download complete'
            }
            print(f'[download] Done: {video_id}')
        except Exception as e:
            download_progress[video_id] = {
                'percent': 0,
                'status': 'error',
                'state': 'Error',
                'message': str(e)
            }
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
        results = get_cached_metadata(f"search_{query}", lambda: yt_public.search(query, filter='songs'))
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
        return json.dumps({
            'percent': 100,
            'status': 'done',
            'state': 'Ready',
            'message': 'Loaded from cache',
            'cached': True,
            'speed': '',
            'eta': ''
        }), 200, {'Content-Type': 'application/json'}
        
    prog = download_progress.get(video_id, {
        'percent': 0,
        'status': 'queued',
        'state': 'Queued…',
        'message': 'Queued…',
        'cached': False,
        'speed': '',
        'eta': ''
    })
    return json.dumps(prog), 200, {'Content-Type': 'application/json'}

@app.route('/preload/<video_id>')
def preload(video_id):
    """Trigger background download of a video_id. Returns immediately."""
    cached = get_cached_audio_path(video_id)
    if cached:
        return json.dumps({'status': 'done', 'percent': 100, 'cached': True}), 200, {'Content-Type': 'application/json'}
    if video_id not in download_progress:
        download_audio_bg(video_id)
        download_progress[video_id] = {
            'percent': 0,
            'status': 'queued',
            'state': 'Starting…',
            'message': 'Starting…',
            'cached': False
        }
    return json.dumps(download_progress.get(video_id, {'status': 'queued'})), 200, {'Content-Type': 'application/json'}


@app.route('/stream/<video_id>')
def stream(video_id):
    """
    Stream audio to the browser in chunks as soon as initial bytes arrive,
    allowing instant playback while yt-dlp finishes downloading in the background.
    """
    try:
        # If file is already fully downloaded or cached, stream directly with conditional range support
        cached_path = get_cached_audio_path(video_id)
        cur_status = download_progress.get(video_id, {}).get('status')
        if cached_path and os.path.exists(cached_path) and (cur_status == 'done' or cur_status != 'downloading'):
            ext = cached_path.rsplit('.', 1)[-1]
            mime = {'m4a': 'audio/mp4', 'mp3': 'audio/mpeg', 'webm': 'audio/webm', 'ogg': 'audio/ogg'}.get(ext, 'audio/mp4')
            return send_file(cached_path, mimetype=mime, conditional=True)

        if video_id not in download_progress:
            download_audio_bg(video_id)

        # Wait until file starts downloading and we have initial chunks & total size
        import time
        for _ in range(80): # Wait up to 16s (80 * 0.2s)
            cached_path = get_cached_audio_path(video_id)
            status_info = download_progress.get(video_id, {})
            cur_status = status_info.get('status')
            if cur_status == 'error':
                return "Audio download failed internally", 500
            if cached_path and os.path.exists(cached_path):
                file_size = os.path.getsize(cached_path)
                total_size = status_info.get('total_bytes') or file_size
                if cur_status == 'done':
                    total_size = file_size
                    break
                if file_size > 32768 and total_size:
                    break
            time.sleep(0.2)
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
                    chunk_size = min(16384, end - pos + 1)
                    data = f.read(chunk_size)
                    if data:
                        yield data
                        pos += len(data)
                    else:
                        s = download_progress.get(video_id, {}).get('status')
                        if s in ('done', 'error'):
                            break
                        time.sleep(0.04)

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
    global ytmusic, _auth_state
    if request.method == 'POST':
        headers = request.form.get('headers')
        if headers:
            try:
                setup(filepath='headers_auth.json', headers_raw=headers)
                ytmusic = YTMusic('headers_auth.json')
                _auth_state['logged_in'] = True
                _auth_state['last_checked'] = time.time()
                _auth_state['error'] = None
                return redirect(url_for('index', msg='logged_in'))
            except Exception as e:
                return f"Error setting up authentication: {e}", 400
    return render_template('login.html')

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    global ytmusic, _auth_state
    for f in [oauth_file, auth_file]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception as e:
                print(f"Error removing {f}: {e}")
    ytmusic = YTMusic()
    _auth_state['logged_in'] = False
    _auth_state['auth_type'] = None
    _auth_state['last_checked'] = time.time()
    _auth_state['error'] = 'Logged out'
    return redirect(url_for('index', msg='logged_out'))

@app.route('/api/auth/status')
def api_auth_status():
    return json.dumps({
        'logged_in': is_user_logged_in(),
        'auth_type': _auth_state.get('auth_type'),
        'error': _auth_state.get('error')
    }), 200, {'Content-Type': 'application/json'}

@app.route('/library')
def library():
    global _auth_state
    if not is_user_logged_in():
        return redirect(url_for('login', msg='session_expired' if get_active_auth_file() else 'auth_required'))
    try:
        if _auth_state.get('auth_type') == 'oauth':
            resp = ytmusic._send_request('browse', {'browseId': 'FEmusic_liked_playlists'})
            playlists = extract_tv_playlists(resp)
        else:
            playlists = ytmusic.get_library_playlists()

        # If playlists returned empty, double-check if YouTube actually considered this session logged in
        if not playlists and not check_yt_session_valid():
            _auth_state['logged_in'] = False
            _auth_state['last_checked'] = time.time()
            _auth_state['error'] = 'Session expired or rejected by YouTube'
            return redirect(url_for('login', msg='session_expired'))
            
        # Ensure Liked Music is present in library list
        has_liked = any(p.get('playlistId') == 'LM' for p in playlists)
        if not has_liked:
            playlists.insert(0, {
                'playlistId': 'LM',
                'title': 'Liked Music',
                'thumbnails': [],
                'count': 'Auto-playlist'
            })

        _auth_state['logged_in'] = True
        _auth_state['last_checked'] = time.time()
        _auth_state['error'] = None
        return render_template('library.html', playlists=playlists)
    except Exception as e:
        print(f"Auth error (redirecting to login): {str(e)}")
        _auth_state['logged_in'] = False
        _auth_state['last_checked'] = time.time()
        _auth_state['error'] = str(e)
        return redirect(url_for('login', msg='session_expired'))

@app.route('/playlist/<playlist_id>')
def playlist(playlist_id):
    try:
        if _auth_state.get('auth_type') == 'oauth':
            browse_id = playlist_id if playlist_id.startswith('VL') else f'VL{playlist_id}'
            resp = ytmusic._send_request('browse', {'browseId': browse_id})
            pl = extract_tv_playlist(resp, default_title='Liked Music' if playlist_id == 'LM' else 'Playlist')
        else:
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
