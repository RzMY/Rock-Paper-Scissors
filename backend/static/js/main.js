class CameraManager {
    constructor(wsClient) {
        this.ws = wsClient;
        this.stream = null;
        this.active = false;
        this.frameInterval = null;
        this.lastDetection = null;

        // DOM refs
        this.video = document.getElementById('webcam-video');
        this.canvas = document.getElementById('webcam-canvas');
        this.ctx = this.canvas.getContext('2d');
        this.placeholder = document.getElementById('webcam-placeholder');
        this.detectionTag = document.getElementById('detection-tag');
        this.detectionLabel = document.getElementById('detection-label');
        this.detectionConfidence = document.getElementById('detection-confidence');
        this.connectionDot = document.querySelector('.status-dot');
        this.connectionText = document.getElementById('connection-status');
    }

    async start() {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: { width: 640, height: 640, facingMode: 'user' }
            });
            this.video.srcObject = this.stream;
            this.video.play();
            this.placeholder.style.display = 'none';
            this.canvas.classList.add('active');
            this.active = true;

            // Send frames at ~15fps
            this.frameInterval = setInterval(() => this.captureAndSend(), 67);
        } catch (err) {
            console.error('Camera error:', err);
            this.placeholder.querySelector('p').textContent = 'Camera access denied. Please allow camera permissions.';
        }
    }

    captureAndSend() {
        if (!this.active) return;

        // Draw video frame to hidden canvas
        this.ctx.drawImage(this.video, 0, 0, 640, 640);
        const jpeg = this.canvas.toDataURL('image/jpeg', 0.8);
        const base64 = jpeg.split(',')[1];
        this.ws.send('frame', { data: base64 });
    }

    displayAnnotatedFrame(base64Data) {
        const img = new Image();
        img.onload = () => {
            this.ctx.drawImage(img, 0, 0, 640, 640);
        };
        img.src = `data:image/jpeg;base64,${base64Data}`;
    }

    updateDetection(predictions) {
        if (predictions.length > 0) {
            const top = predictions[0];
            this.detectionTag.classList.remove('hidden');
            this.detectionLabel.textContent = top.class_name;
            this.detectionConfidence.textContent = `${(top.confidence * 100).toFixed(0)}%`;
            this.detectionTag.style.color = CLASS_COLORS[top.class_name] || '#fff';
            this.lastDetection = top;
        } else {
            this.detectionTag.classList.add('hidden');
            this.lastDetection = null;
        }
    }

    stop() {
        this.active = false;
        clearInterval(this.frameInterval);
        if (this.stream) {
            this.stream.getTracks().forEach(t => t.stop());
        }
    }
}

const CLASS_COLORS = { Rock: '#4fc3f7', Paper: '#81c784', Scissors: '#ef5350' };

class App {
    constructor() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${location.host}/ws`;

        this.ws = new WebSocketClient(wsUrl);
        this.camera = new CameraManager(this.ws);
        this.game = new GameUI(this.ws);
        this.stats = new StatsUI(this.ws);

        this.init();
    }

    async init() {
        await this.camera.start();

        // Handle annotated frames
        this.ws.on('annotated_frame', (msg) => {
            this.camera.displayAnnotatedFrame(msg.data);
            this.camera.updateDetection(msg.predictions);
        });

        // Connection status
        this.ws.on('connected', () => {
            document.querySelector('.status-dot').classList.remove('disconnected');
            document.getElementById('connection-status').childNodes[1].textContent = ' Connected';
        });

        this.ws.on('disconnected', () => {
            document.querySelector('.status-dot').classList.add('disconnected');
            document.getElementById('connection-status').childNodes[1].textContent = ' Reconnecting...';
        });
    }
}

// Boot
document.addEventListener('DOMContentLoaded', () => {
    new App();
});
