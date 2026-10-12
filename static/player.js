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
    audio.addEventListener('pause', function() {
        document.getElementById('play-pause-icon').src = '/static/play.svg';
    });

    // Buffering indicator
    audio.addEventListener('waiting', function() {
        progressBar.style.background = '#888';
        playerTime.textContent = 'Loading\u2026';
    });
    audio.addEventListener('canplay', function() {
        progressBar.style.background = '#f00';
    });

    audio.addEventListener('timeupdate', function() {
        if (audio.duration) {
            var pct = (audio.currentTime / audio.duration) * 100;
            progressBar.style.width = pct + '%';
            var m = Math.floor(audio.currentTime / 60);
            var s = Math.floor(audio.currentTime % 60);
            if (s < 10) s = '0' + s;
            playerTime.textContent = m + ':' + s;
        }
    });

    audio.addEventListener('ended', function() {
        playNext();
    });

    btnPlayPause.addEventListener('click', function() {
        if (audio.paused) { audio.play(); } else { audio.pause(); }
    });

    var silentMp3 = 'data:audio/mpeg;base64,SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjYwLjE2LjEwMAAAAAAAAAAAAAAA//tAwAAAAAAAAAAAAAAAAAAAAAAASW5mbwAAAA8AAAAoAAAQ9gAQEBYWHR0dIyMpKSkvLzU1NTs7QUFBSEhOTk5UVFpaWmBgZmZmbGxycnJ5eX9/f4WFi4uLkZGXl5ednaSkpKqqsLCwtra8vLzCwsjIyM7O1dXV29vh4eHn5+3t7fPz+fn5//8AAAAATGF2YzYwLjMxAAAAAAAAAAAAAAAAJAV8AAAAAAAAEPYp+NOpAAAAAAD/+xDEAAPAAAGkAAAAIAAANIAAAARMQU1FMy4xMDBVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMuMTAwVVVVVf/7EMQpg8AAAaQAAAAgAAA0gAAABFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVV//sQxFMDwAABpAAAACAAADSAAAAEVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVUxBTUUzLjEwMFVVVVX/+xDEfIPAAAGkAAAAIAAANIAAAARVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMuMTAwVVVVVf/7EMSmA8AAAaQAAAAgAAA0gAAABFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVV//sQxM+DwAABpAAAACAAADSAAAAEVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVUxBTUUzLjEwMFVVVVX/+xDE1gPAAAGkAAAAIAAANIAAAARVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMuMTAwVVVVVf/7EMTWA8AAAaQAAAAgAAA0gAAABFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVV//sQxNYDwAABpAAAACAAADSAAAAEVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVUxBTUUzLjEwMFVVVVX/+xDE1gPAAAGkAAAAIAAANIAAAARVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMuMTAwVVVVVf/7EMTWA8AAAaQAAAAgAAA0gAAABFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVV//sQxNYDwAABpAAAACAAADSAAAAEVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVUxBTUUzLjEwMFVVVVX/+xDE1gPAAAGkAAAAIAAANIAAAARVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMuMTAwVVVVVf/7EMTWA8AAAaQAAAAgAAA0gAAABFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVV//sQxNYDwAABpAAAACAAADSAAAAEVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVUxBTUUzLjEwMFVVVVX/+xDE1gPAAAGkAAAAIAAANIAAAARVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMuMTAwVVVVVf/7EMTWA8AAAaQAAAAgAAA0gAAABFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVV//sQxNYDwAABpAAAACAAADSAAAAEVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVX/+xDE1gPAAAGkAAAAIAAANIAAAARVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVf/7EMTWA8AAAaQAAAAgAAA0gAAABFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV//sQxNYDwAABpAAAACAAADSAAAAEVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVX/+xDE1gPAAAGkAAAAIAAANIAAAARVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVQ==';
    var pollTimer = null;

    function stopProgressPoll() {
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    }

    // ---- Play a song ----
    // We set audio.src immediately. If it's cached, the server sends the file.
    // If not, the server redirects to a direct YouTube URL for instant playback,
    // while the /preload endpoint caches it in the background!
    window.playSong = function(videoId, title, thumbUrl) {
        stopProgressPoll();

        playerTitle.textContent = title || 'Loading\u2026';
        playerThumb.src = thumbUrl || '';
        playerTime.textContent = 'Loading\u2026';
        progressBar.style.width = '100%';
        progressBar.className = 'loading'; // use CSS shimmer animation
        bottomPlayer.style.display = 'block';

        // 1. Trigger preload in the background to ensure it gets cached
        var xhrInit = new XMLHttpRequest();
        xhrInit.open('GET', '/preload/' + videoId, true);
        xhrInit.send();

        // 2. Play immediately!
        audio.loop = false;
        audio.src = '/stream/' + videoId;
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

    // ---- Auth notification & status management ----
    var authNotification = document.getElementById('auth-notification');
    var btnDismissNotification = document.getElementById('btn-dismiss-notification');
    var navAuthStatus = document.getElementById('nav-auth-status');

    function dismissNotification() {
        if (authNotification && authNotification.className.indexOf('is-dismissed') === -1) {
            authNotification.className += ' is-dismissed';
            try {
                sessionStorage.setItem('auth_notif_dismissed', '1');
            } catch(e) {}
        }
    }

    function showNotification() {
        if (authNotification) {
            authNotification.className = authNotification.className.replace(/\bis-dismissed\b/g, '').trim();
        }
    }

    if (btnDismissNotification) {
        btnDismissNotification.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            dismissNotification();
        });
    }

    // Auto-dismiss positive notifications / flash banners after 4.5 seconds
    if (authNotification) {
        var notifClass = authNotification.className;
        if (notifClass.indexOf('is-online') > -1 || notifClass.indexOf('banner-flash') > -1) {
            setTimeout(function() {
                dismissNotification();
            }, 4500);
        } else if (notifClass.indexOf('is-offline') > -1) {
            try {
                if (sessionStorage.getItem('auth_notif_dismissed') === '1') {
                    authNotification.className += ' is-dismissed';
                }
            } catch(e) {}
        }
    }

    if (navAuthStatus) {
        navAuthStatus.addEventListener('click', function() {
            if (authNotification && authNotification.className.indexOf('is-dismissed') > -1) {
                showNotification();
            }
        });
    }

    // ---- AJAX (PJAX) navigation ----
    function loadPage(url, pushState) {
        var xhr = new XMLHttpRequest();
        xhr.open('GET', url, true);
        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4 && xhr.status === 200) {
                mainContent.innerHTML = xhr.responseText;
                queue = buildQueueFromPage();
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
})();
