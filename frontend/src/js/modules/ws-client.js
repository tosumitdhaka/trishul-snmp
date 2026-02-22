window.WsClient = (function () {
    const PING_MS = 30000, BACKOFF_BASE = 1000, BACKOFF_MAX = 30000, PONG_TIMEOUT = 5000;
    let _ws, _token, _pingTimer, _pongTimer, _reconnTimer;
    let _reconnDelay = BACKOFF_BASE, _intentional = false;

    function _url(t) {
        const p = location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${p}//${location.host}/api/ws?token=${encodeURIComponent(t)}`;
    }

    function _dot(state) {
        const el = document.getElementById('ws-status-dot');
        if (!el) return;
        el.className = 'ws-dot ws-dot-' + state;
        const labels = {
            connecting:   'WS: Connecting…',
            online:       'WS: Live',
            offline:      'WS: Offline',
            unauthorized: 'WS: Unauthorized'
        };
        el.title = labels[state] || '';
    }

    function _emit(type, detail) {
        window.dispatchEvent(new CustomEvent('trishul:ws:' + type, { detail }));
    }

    function _startPing() {
        _stopPing();
        _pingTimer = setInterval(() => {
            if (_ws && _ws.readyState === WebSocket.OPEN) {
                _ws.send('ping');
                _pongTimer = setTimeout(() => {
                    if (_ws) _ws.close(4000, 'pong timeout');
                }, PONG_TIMEOUT);
            }
        }, PING_MS);
    }

    function _stopPing() {
        clearInterval(_pingTimer);
        clearTimeout(_pongTimer);
        _pingTimer = _pongTimer = null;
    }

    function _scheduleReconnect() {
        if (_intentional) return;
        clearTimeout(_reconnTimer);
        _reconnTimer = setTimeout(() => {
            if (_token) _connect(_token);
        }, _reconnDelay);
        _reconnDelay = Math.min(_reconnDelay * 2, BACKOFF_MAX);
    }

    function _connect(token) {
        _dot('connecting');
        try {
            _ws = new WebSocket(_url(token));
        } catch (e) {
            _scheduleReconnect();
            return;
        }

        _ws.onopen = () => {
            _reconnDelay = BACKOFF_BASE;
            _dot('online');
            _startPing();
            _emit('open', null);
        };

        _ws.onmessage = (evt) => {
            if (evt.data === 'pong') {
                clearTimeout(_pongTimer);
                _pongTimer = null;
                return;
            }
            try {
                const msg = JSON.parse(evt.data);
                if (msg && msg.type) _emit(msg.type, msg);
            } catch (e) {}
        };

        _ws.onclose = (evt) => {
            _stopPing();
            _dot(evt.code === 4001 ? 'unauthorized' : 'offline');
            _emit('close', { code: evt.code, reason: evt.reason });
            if (evt.code !== 4001) _scheduleReconnect();
        };

        _ws.onerror = () => {};
    }

    return {
        connect: function (token) {
            if (!token) return;
            _token = token;
            _intentional = false;
            if (_ws && _ws.readyState !== WebSocket.CLOSED) _ws.close(1000, 'reconnect');
            _connect(token);
        },
        disconnect: function () {
            _intentional = true;
            _token = null;
            _stopPing();
            clearTimeout(_reconnTimer);
            if (_ws) { _ws.close(1000, 'logout'); _ws = null; }
            _dot('offline');
        },
        isConnected: function () {
            return _ws !== undefined && _ws !== null && _ws.readyState === WebSocket.OPEN;
        }
    };
})();
