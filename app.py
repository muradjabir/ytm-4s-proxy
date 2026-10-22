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

def find_node_binary():
    """Locate modern Node.js binary (v20+) for YouTube challenge solver."""
    # Check standard PATH first (e.g. inside Docker container)
    for name in ['node', 'nodejs']:
        cand = shutil.which(name)
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand

    nvm_dir = os.path.expanduser('~/.nvm/versions/node')
    if os.path.isdir(nvm_dir):
        try:
            versions = sorted(os.listdir(nvm_dir), reverse=True)
            for v in versions:
                cand = os.path.join(nvm_dir, v, 'bin', 'node')
                if os.path.isfile(cand) and os.access(cand, os.X_OK):
                    return cand
        except Exception:
            pass
    for cand in [
        '/home/murad/.nvm/versions/node/v24.11.1/bin/node',
        '/usr/local/bin/node',
        os.path.expanduser('~/.local/bin/node'),
        '/usr/bin/node',
    ]:
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return 'node'

NODE_PATH = find_node_binary()
node_dir = os.path.dirname(NODE_PATH)
if node_dir and node_dir not in os.environ.get('PATH', ''):
    os.environ['PATH'] = f"{node_dir}:{os.environ.get('PATH', '')}"

print(f"[node] Using Node binary at: {NODE_PATH}")

YTDLP_PATH = shutil.which('yt-dlp')
if not YTDLP_PATH:
    venv_ytdlp = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'venv', 'bin', 'yt-dlp')
    if os.path.exists(venv_ytdlp):
        YTDLP_PATH = venv_ytdlp
    else:
        YTDLP_PATH = 'yt-dlp'

def make_ytdl_opts():
    """Build yt-dlp Python API options for metadata only (no download)."""
    opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio',
        'quiet': True,
        'no_warnings': True,
        'js_runtimes': {'node': {'path': NODE_PATH}},
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

def save_cookies_netscape(cookies_input):
    """
    Takes cookie data (list of cookie dicts from browser extension, raw Netscape text,
    or raw header string) and updates cookies.txt and headers_auth.json.
    Returns (count, essential_found).
    """
    global ytmusic, _auth_state
    import time
    cookies_list = []
    
    # 1. If it's a list of dicts (from Chrome extension)
    if isinstance(cookies_input, list):
        for item in cookies_input:
            if not isinstance(item, dict): continue
            name = str(item.get('name', '')).strip()
            val = str(item.get('value', '')).strip()
            if not name: continue
            
            domain = str(item.get('domain', '.youtube.com')).strip()
            if not domain.startswith('.'):
                domain = '.' + domain
            path = str(item.get('path', '/'))
            secure = 'TRUE' if item.get('secure', True) else 'FALSE'
            exp = item.get('expirationDate')
            if not exp:
                exp = int(time.time()) + 31536000
            else:
                try:
                    exp = int(float(exp))
                except Exception:
                    exp = int(time.time()) + 31536000
                
            cookies_list.append({
                'domain': domain,
                'path': path,
                'secure': secure,
                'expiration': exp,
                'name': name,
                'value': val
            })
            
    # 2. If it's raw text
    elif isinstance(cookies_input, str):
        text = cookies_input.strip()
        lines = text.splitlines()
        is_netscape = any('\t' in line for line in lines if not line.startswith('#'))
        
        if is_netscape:
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'): continue
                parts = line.split('\t')
                if len(parts) >= 7:
                    try:
                        exp = int(parts[4]) if parts[4].isdigit() else int(time.time()) + 31536000
                    except Exception:
                        exp = int(time.time()) + 31536000
                    cookies_list.append({
                        'domain': parts[0],
                        'path': parts[2],
                        'secure': parts[3].upper(),
                        'expiration': exp,
                        'name': parts[5],
                        'value': parts[6]
                    })
        else:
            cookie_str = text
            if 'Cookie:' in text or 'cookie:' in text:
                for line in lines:
                    if line.lower().startswith('cookie:'):
                        cookie_str = line.split(':', 1)[1]
                        break
            for pair in cookie_str.split(';'):
                pair = pair.strip()
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    k = k.strip()
                    v = v.strip()
                    if k:
                        cookies_list.append({
                            'domain': '.youtube.com',
                            'path': '/',
                            'secure': 'TRUE' if 'Secure' in k else 'FALSE',
                            'expiration': int(time.time()) + 31536000,
                            'name': k,
                            'value': v
                        })

    if not cookies_list:
        return 0, []

    # Write cookies.txt in project root
    cookies_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')
    with open(cookies_file, 'w', encoding='utf-8') as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write("# This file is generated by YTM 4S Proxy Cookie Sync.\n\n")
        for c in cookies_list:
            f.write(f"{c['domain']}\tTRUE\t{c['path']}\t{c['secure']}\t{c['expiration']}\t{c['name']}\t{c['value']}\n")

    # Build Cookie header string and update headers_auth.json
    cookie_header_parts = [f"{c['name']}={c['value']}" for c in cookies_list]
    cookie_header_str = "; ".join(cookie_header_parts)
    
    auth_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'headers_auth.json')
    current_headers = {}
    if os.path.exists(auth_file_path):
        try:
            with open(auth_file_path, 'r', encoding='utf-8') as f:
                current_headers = json.load(f)
        except Exception:
            pass
            
    current_headers['Cookie'] = cookie_header_str
    current_headers.setdefault('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')
    current_headers.setdefault('Accept', '*/*')
    current_headers.setdefault('Origin', 'https://music.youtube.com')
    current_headers.setdefault('Referer', 'https://music.youtube.com/')
    
    with open(auth_file_path, 'w', encoding='utf-8') as f:
        json.dump(current_headers, f, indent=2)

    # Re-initialize ytmusic with fresh headers if not using oauth
    try:
        if _auth_state.get('auth_type') != 'oauth':
            ytmusic = YTMusic(auth_file_path)
            _auth_state['logged_in'] = True
            _auth_state['last_checked'] = time.time()
            _auth_state['error'] = None
    except Exception as e:
        print(f"[cookies] Error updating ytmusic instance: {e}")

    essential = {'SID', '__Secure-3PSID', 'SAPISID', 'LOGIN_INFO'}
    found_essential = list(essential.intersection({c['name'] for c in cookies_list}))
    return len(cookies_list), found_essential

def get_cookies_status():
    """Returns metadata regarding active cookies.txt."""
    import datetime
    cookies_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')
    if not os.path.exists(cookies_path) or os.path.getsize(cookies_path) == 0:
        return {
            'exists': False,
            'count': 0,
            'last_modified': None,
            'last_modified_str': 'Never',
            'has_essential': False,
            'essential_found': []
        }
    
    count = 0
    found_keys = set()
    mtime = os.path.getmtime(cookies_path)
    try:
        with open(cookies_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'): continue
                parts = line.split('\t')
                if len(parts) >= 7:
                    count += 1
                    found_keys.add(parts[5])
    except Exception:
        pass
        
    essential = {'SID', '__Secure-3PSID', 'SAPISID', 'LOGIN_INFO'}
    present_essential = list(essential.intersection(found_keys))
    return {
        'exists': True,
        'count': count,
        'last_modified': mtime,
        'last_modified_str': datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S'),
        'has_essential': len(present_essential) >= 2,
        'essential_found': present_essential
    }

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
        tmp_dir = os.path.join(CACHE_DIR, '.tmp')
        os.makedirs(tmp_dir, exist_ok=True)
        out_tmpl = os.path.join(tmp_dir, f'{video_id}.%(ext)s')

        cmd = [
            YTDLP_PATH,
            '--format', 'bestaudio[ext=m4a]/bestaudio',
            '--js-runtimes', f'node:{NODE_PATH}',
            '--remote-components', 'ejs:github',
            '--concurrent-fragments', '4',  # Download fragments concurrently for fast completion
            '--buffer-size', '16K',
            '--output', out_tmpl,
            '--no-playlist',
            '--newline',  # Force one progress line per update (parseable)
        ]

        # Use browser cookies if present
        cookies_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')
        if os.path.exists(cookies_file) and os.path.getsize(cookies_file) > 0:
            cmd.extend(['--cookies', cookies_file])

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
            # Move finalized & ffmpeg-fixed file atomically to CACHE_DIR
            tmp_files = [f for f in os.listdir(tmp_dir) if f.startswith(f"{video_id}.")]
            if tmp_files:
                src_file = os.path.join(tmp_dir, tmp_files[0])
                final_ext = tmp_files[0].rsplit('.', 1)[-1]
                dest_file = os.path.join(CACHE_DIR, f"{video_id}.{final_ext}")
                os.replace(src_file, dest_file)

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
    Serve fully repaired M4A/AAC stream to iOS Safari with HTTP 206 byte-range support.
    If cached, serves immediately. If not yet downloaded, triggers background download and waits.
    """
    try:
        cached_path = get_cached_audio_path(video_id)
        cur_status = download_progress.get(video_id, {}).get('status')
        # If file is already fully cached and not actively downloading, serve immediately
        if cached_path and os.path.exists(cached_path) and cur_status not in ('downloading', 'starting'):
            ext = cached_path.rsplit('.', 1)[-1]
            mime = {'m4a': 'audio/mp4', 'mp3': 'audio/mpeg', 'webm': 'audio/webm', 'ogg': 'audio/ogg'}.get(ext, 'audio/mp4')
            return send_file(cached_path, mimetype=mime, conditional=True)

        # File is not cached yet: start download
        if video_id not in download_progress or cur_status == 'error':
            download_audio_bg(video_id)

        # Wait up to 35s for yt-dlp download & container fixup to 100% complete
        import time
        for _ in range(175):  # 175 * 0.2s = 35 seconds
            status_info = download_progress.get(video_id, {})
            cur_status = status_info.get('status')
            cached_path = get_cached_audio_path(video_id)
            # ONLY break when status is 'done' and the atomically moved file exists!
            if cur_status == 'done' and cached_path and os.path.exists(cached_path):
                break
            if cur_status == 'error':
                err_msg = status_info.get('message', 'Audio download failed')
                return f"Audio download failed: {err_msg}", 500
            time.sleep(0.2)
        else:
            return "Audio download timed out", 504

        ext = cached_path.rsplit('.', 1)[-1]
        mime = {'m4a': 'audio/mp4', 'mp3': 'audio/mpeg', 'webm': 'audio/webm', 'ogg': 'audio/ogg'}.get(ext, 'audio/mp4')
        return send_file(cached_path, mimetype=mime, conditional=True)

    except Exception as e:
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            raise e
        print(f"[stream] Error serving {video_id}: {e}")
        return f"Stream error: {str(e)}", 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    global ytmusic, _auth_state
    if request.method == 'POST':
        headers = request.form.get('headers')
        if headers:
            try:
                setup(filepath='headers_auth.json', headers_raw=headers)
                save_cookies_netscape(headers)
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

@app.route('/api/cookies/sync', methods=['POST', 'OPTIONS'])
def api_cookies_sync():
    cors_headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With'
    }
    if request.method == 'OPTIONS':
        return Response('', status=204, headers=cors_headers)
        
    try:
        payload = request.get_json(silent=True) or {}
        cookies_data = payload.get('cookies') or payload.get('cookie_string') or payload.get('cookies_text')
        
        if not cookies_data:
            cookies_data = request.get_data(as_text=True)
            
        if not cookies_data:
            return json.dumps({'status': 'error', 'message': 'No cookies received in request'}), 400, {**cors_headers, 'Content-Type': 'application/json'}
            
        count, essential = save_cookies_netscape(cookies_data)
        if count == 0:
            return json.dumps({'status': 'error', 'message': 'Could not parse any valid cookies'}), 400, {**cors_headers, 'Content-Type': 'application/json'}
            
        return json.dumps({
            'status': 'ok',
            'count': count,
            'essential': essential,
            'message': f'Successfully synced {count} cookies! yt-dlp playback ready.'
        }), 200, {**cors_headers, 'Content-Type': 'application/json'}
        
    except Exception as e:
        return json.dumps({'status': 'error', 'message': str(e)}), 500, {**cors_headers, 'Content-Type': 'application/json'}

@app.route('/api/cookies/upload', methods=['POST'])
def api_cookies_upload():
    try:
        if 'file' in request.files:
            file = request.files['file']
            content = file.read().decode('utf-8', errors='ignore')
        else:
            content = request.form.get('cookies_text') or request.form.get('headers') or ''
            
        if not content.strip():
            return redirect(url_for('settings', error='empty_cookies'))
            
        count, essential = save_cookies_netscape(content)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return json.dumps({'status': 'ok', 'count': count, 'essential': essential}), 200, {'Content-Type': 'application/json'}
            
        return redirect(url_for('settings', msg='cookies_updated', count=count))
    except Exception as e:
        return f"Error uploading cookies: {str(e)}", 400

@app.route('/api/cookies/status')
def api_cookies_status():
    return json.dumps(get_cookies_status()), 200, {'Content-Type': 'application/json'}

@app.route('/extension/download')
def extension_download():
    zip_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'ytm-cookie-sync-extension.zip')
    if os.path.exists(zip_path):
        return send_file(zip_path, as_attachment=True, download_name='ytm-cookie-sync-extension.zip', mimetype='application/zip')
    return "Extension package not found", 404

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
                          total_size=format_size(total_size),
                          cookies_status=get_cookies_status())

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
