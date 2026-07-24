class WebSocketClient {
    constructor(url) {
        this.url = url;
        this.handlers = {};
        this.reconnectDelay = 1000;
        this.maxDelay = 5000;
        this.shouldReconnect = true;
        this.connect();
    }

    connect() {
        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
            this.reconnectDelay = 1000;
            this.emit('connected');
        };

        this.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (this.handlers[msg.type]) {
                    this.handlers[msg.type].forEach(fn => fn(msg));
                }
            } catch (e) {
                console.error('WS parse error:', e);
            }
        };

        this.ws.onclose = () => {
            this.emit('disconnected');
            if (this.shouldReconnect) {
                setTimeout(() => this.connect(), this.reconnectDelay);
                this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxDelay);
            }
        };

        this.ws.onerror = (e) => {
            console.error('WebSocket error:', e);
        };
    }

    on(type, handler) {
        if (!this.handlers[type]) this.handlers[type] = [];
        this.handlers[type].push(handler);
    }

    send(type, data = {}) {
        if (this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type, ...data }));
        }
    }

    emit(type, data = {}) {
        if (this.handlers[type]) {
            this.handlers[type].forEach(fn => fn(data));
        }
    }

    close() {
        this.shouldReconnect = false;
        this.ws.close();
    }
}
