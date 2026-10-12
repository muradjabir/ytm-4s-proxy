(function() {
    var audio = document.getElementById('global-audio');
    var btnPlayPause = document.getElementById('btn-play-pause');
    var bottomPlayer = document.getElementById('bottom-player');
    var playerTitle = document.getElementById('player-title');
    var playerThumb = document.getElementById('player-thumb');
    var playerTime = document.getElementById('player-time');
    var progressBar = document.getElementById('progress-bar');
    var mainContent = document.getElementById('main-content');

    // Queue state
    var queue = [];
    var queueIndex = -1;

    // ---- Playback state ----
    audio.addEventListener('play', function() {
        document.getElementById('play-pause-icon').src = '/static/pause.svg';
        progressBar.style.background = '#f00';
    });
    var downloadBar = document.getElementById('download-bar');
    var pollTimer = null;
    var currentPollVideoId = null;

    function stopProgressPoll() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
        currentPollVideoId = null;
    }

    function startProgressPoll(videoId) {
        stopProgressPoll();
        currentPollVideoId = videoId;

        function poll() {
            if (!currentPollVideoId || currentPollVideoId !== videoId) return;
            var xhr = new XMLHttpRequest();
            xhr.open('GET', '/status/' + encodeURIComponent(videoId), true);
            xhr.onreadystatechange = function() {
                if (xhr.readyState === 4 && xhr.status === 200) {
                    try {
                        var data = JSON.parse(xhr.responseText);
                        var pct = data.percent || 0;
                        var stateText = data.state || (pct > 0 ? (Math.round(pct) + '%') : 'Connecting…');

                        if (downloadBar) {
                            downloadBar.style.width = pct + '%';
                        }

                        // Full-page player status elements if open
                        var playStatusText = document.getElementById('play-status-text');
                        var playStatusBar = document.getElementById('play-status-bar');
                        if (playStatusText && (data.message || data.state)) {
                            playStatusText.textContent = data.message || data.state;
                        }
                        if (playStatusBar) {
                            playStatusBar.style.width = pct + '%';
                        }

                        var pageAudio = document.getElementById('audio-player');
                        var isAudioPlaying = (!audio.paused && audio.currentTime > 0) || (pageAudio && !pageAudio.paused && pageAudio.currentTime > 0);

                        // While audio has not yet started or is buffering at start
                        if (!isAudioPlaying) {
                            if (data.cached) {
                                playerTime.textContent = 'Cached';
                                if (audio.paused && (!audio.currentTime || audio.currentTime === 0)) {
                                    try { audio.play(); } catch(e) {}
                                }
                            } else if (data.status === 'done') {
                                playerTime.textContent = 'Ready';
                                if (audio.paused && (!audio.currentTime || audio.currentTime === 0)) {
                                    try { audio.play(); } catch(e) {}
                                }
                            } else if (data.status === 'error') {
                                playerTime.textContent = 'Failed';
                                stopProgressPoll();
                            } else {
                                playerTime.textContent = stateText;
                            }
                        } else {
                            // If audio is actively playing, stop polling once 100% or cached
                            if (pct >= 100 || data.cached) {
                                stopProgressPoll();
                            }
                        }
                    } catch(e) {}
                }
            };
            xhr.send();
        }

        poll();
        pollTimer = setInterval(poll, 400);
    }

    window.startProgressPoll = startProgressPoll;
    window.stopProgressPoll = stopProgressPoll;

    function checkPageAudio() {
        var pageAudio = document.getElementById('audio-player');
        if (pageAudio) {
            var src = pageAudio.currentSrc || '';
            if (!src) {
                var sElem = pageAudio.querySelector('source');
                if (sElem) src = sElem.src || sElem.getAttribute('src') || '';
            }
            var m = src.match(/\/stream\/([^/?#]+)/);
            if (m) {
                var vid = decodeURIComponent(m[1]);
                startProgressPoll(vid);
            }
        }
    }

    // Audio error & buffering indicators
    audio.addEventListener('error', function() {
        var err = audio.error;
        console.log('Audio playback status:', err ? ('Code ' + err.code) : 'error');
    });

    audio.addEventListener('waiting', function() {
        if (audio.currentTime > 0) {
            playerTime.textContent = 'Buffering…';
        }
    });

    audio.addEventListener('canplay', function() {
        progressBar.style.background = '#ff0000';
    });

    audio.addEventListener('timeupdate', function() {
        if (audio.currentTime > 0) {
            if (audio.duration) {
                var pct = (audio.currentTime / audio.duration) * 100;
                progressBar.style.width = pct + '%';
                var m = Math.floor(audio.currentTime / 60);
                var s = Math.floor(audio.currentTime % 60);
                if (s < 10) s = '0' + s;
                playerTime.textContent = m + ':' + s;
            }
        }
    });

    audio.addEventListener('ended', function() {
        playNext();
    });

    btnPlayPause.addEventListener('click', function() {
        if (audio.paused) { audio.play(); } else { audio.pause(); }
    });

    // ---- Play a song ----
    window.playSong = function(videoId, title, thumbUrl) {
        stopProgressPoll();

        playerTitle.textContent = title || 'Connecting…';
        playerThumb.src = thumbUrl || '';
        playerTime.textContent = 'Connecting…';
        progressBar.style.width = '0%';
        progressBar.className = '';
        if (downloadBar) downloadBar.style.width = '0%';
        bottomPlayer.style.display = 'block';

        // 1. Start live yt-dlp download state polling
        startProgressPoll(videoId);

        // 2. Trigger preload in the background to ensure yt-dlp starts caching immediately
        var xhrInit = new XMLHttpRequest();
        xhrInit.open('GET', '/preload/' + encodeURIComponent(videoId), true);
        xhrInit.send();

        // 3. Play stream
        audio.loop = false;
        audio.src = '/stream/' + encodeURIComponent(videoId);
        audio.play();

        // Preload next song 10s after starting
        setTimeout(function() { preloadNext(); }, 10000);
    };

    // ---- Queue management ----
    function buildQueueFromPage() {
        var links = mainContent.querySelectorAll('a.song-link[data-video-id]');
        var q = [];
        for (var i = 0; i < links.length; i++) {
            var a = links[i];
            if (a.getAttribute('data-video-id')) {
                q.push({
                    videoId: a.getAttribute('data-video-id'),
                    title: a.getAttribute('data-title') || '',
                    thumb: a.getAttribute('data-thumb') || ''
                });
            }
        }
        return q;
    }

    function playNext() {
        if (!queue.length || queueIndex < 0) return;
        var next = queueIndex + 1;
        if (next < queue.length) {
            queueIndex = next;
            var song = queue[next];
            playSong(song.videoId, song.title, song.thumb);
        }
    }

    function preloadNext() {
        if (!queue.length || queueIndex < 0) return;
        var next = queueIndex + 1;
        if (next < queue.length) {
            var xhr = new XMLHttpRequest();
            xhr.open('GET', '/preload/' + queue[next].videoId, true);
            xhr.send();
        }
    }

    // Auth notification removed (login status no longer needed)

    // ---- AJAX (PJAX) navigation ----
    function loadPage(url, pushState) {
        var xhr = new XMLHttpRequest();
        xhr.open('GET', url, true);
        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4 && xhr.status === 200) {
                mainContent.innerHTML = xhr.responseText;
                queue = buildQueueFromPage();
                checkPageAudio();
                if (pushState !== false) {
                    window.history.pushState(null, '', url);
                }

                // Sync auth status badge from response header
                var authHeader = xhr.getResponseHeader('X-Auth-Status');
                if (authHeader && navAuthStatus) {
                    if (authHeader === 'logged_in') {
                        navAuthStatus.className = 'nav-auth-badge badge-online';
                        navAuthStatus.setAttribute('href', '/settings');
                        navAuthStatus.setAttribute('title', 'Logged in to YouTube Music');
                        navAuthStatus.innerHTML = '<span class="auth-dot"></span><span class="auth-label"><span class="auth-label-full">Logged In</span><span class="auth-label-short">In</span></span>';
                    } else {
                        navAuthStatus.className = 'nav-auth-badge badge-offline';
                        navAuthStatus.setAttribute('href', '/login');
                        navAuthStatus.setAttribute('title', 'Not logged in - Tap to connect');
                        navAuthStatus.innerHTML = '<span class="auth-dot"></span><span class="auth-label"><span class="auth-label-full">Not Logged In</span><span class="auth-label-short">Login</span></span>';
                    }
                }
            }
        };
        xhr.send();
    }

    // ---- Click interception ----
    document.addEventListener('click', function(e) {
        var a = e.target;
        while (a && a.tagName !== 'A' && a.tagName !== 'BODY') { a = a.parentNode; }
        if (!a || a.tagName !== 'A') return;

        var cls = a.className || '';
        var videoId = a.getAttribute('data-video-id');

        if (cls.indexOf('song-link') > -1 && videoId) {
            e.preventDefault();
            queue = buildQueueFromPage();
            queueIndex = -1;
            for (var i = 0; i < queue.length; i++) {
                if (queue[i].videoId === videoId) { queueIndex = i; break; }
            }
            playSong(videoId, a.getAttribute('data-title'), a.getAttribute('data-thumb'));
            return;
        }

        var href = a.getAttribute('href');
        if (href && href.charAt(0) === '/') {
            e.preventDefault();
            loadPage(href);
        }
    });

    // ---- Form interception (search) ----
    document.addEventListener('submit', function(e) {
        var form = e.target;
        if (form.tagName === 'FORM' && form.getAttribute('method').toUpperCase() === 'GET') {
            e.preventDefault();
            var action = form.getAttribute('action') || '';
            var input = form.querySelector('input[name="q"]');
            loadPage(action + '?q=' + encodeURIComponent(input.value));
        }
    });

    // ---- Back/forward ----
    window.addEventListener('popstate', function() {
        loadPage(window.location.href, false);
    });

    // Check page audio on initial load
    checkPageAudio();
})();
