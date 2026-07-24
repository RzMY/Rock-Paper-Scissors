class StatsUI {
    constructor(wsClient) {
        this.ws = wsClient;
        this.stats = { wins: 0, losses: 0, draws: 0, total_games: 0, win_rate: 0, class_stats: {}, strategy_stats: {} };

        // Win rate gauge canvas
        this.gaugeCanvas = document.getElementById('win-rate-canvas');
        this.gaugeCtx = this.gaugeCanvas.getContext('2d');

        // DOM refs
        this.el = {
            winRateText: document.getElementById('win-rate-text'),
            barWin: document.getElementById('bar-win'),
            barLose: document.getElementById('bar-lose'),
            barDraw: document.getElementById('bar-draw'),
            valWin: document.getElementById('val-win'),
            valLose: document.getElementById('val-lose'),
            valDraw: document.getElementById('val-draw'),
            countRock: document.getElementById('count-rock'),
            countPaper: document.getElementById('count-paper'),
            countScissors: document.getElementById('count-scissors'),
            stratMarkov: document.getElementById('strat-markov'),
            stratFrequency: document.getElementById('strat-frequency'),
            stratAntiRotate: document.getElementById('strat-anti_rotate'),
            historyTbody: document.getElementById('history-tbody'),
            btnReset: document.getElementById('btn-reset'),
        };

        this.setupWSHandlers();
        this.setupEvents();
        this.fetchInitial();
    }

    setupWSHandlers() {
        this.ws.on('score_update', (msg) => {
            this.stats.wins = Number(msg.player) || 0;
            this.stats.losses = Number(msg.computer) || 0;
            this.stats.draws = Number(msg.draws) || 0;
            this.stats.total_games = this.stats.wins + this.stats.losses + this.stats.draws;
            this.updateAll();
        });

        this.ws.on('stats', (msg) => {
            this.stats = msg;
            this.updateAll();
        });

        this.ws.on('reset_ok', () => {
            this.stats = { wins: 0, losses: 0, draws: 0, total_games: 0, win_rate: 0, class_stats: {}, strategy_stats: {} };
            this.updateAll();
        });

        // After each round, fetch refreshed stats
        this.ws.on('game_state', (msg) => {
            if (msg.state === 'result' || msg.state === 'waiting') {
                this.refresh();
            }
        });

        this.ws.on('connected', () => { this.refresh(); });
    }

    setupEvents() {
        this.el.btnReset.addEventListener('click', () => {
            if (confirm('Reset all scores and history?')) {
                this.ws.send('reset');
            }
        });
    }

    fetchInitial() {
        fetch('/api/stats')
            .then(r => r.json())
            .then(data => {
                if (data.total_games !== undefined) {
                    this.stats = data;
                    this.updateAll();
                }
                return fetch('/api/history?limit=20');
            })
            .then(r => r.json())
            .then(history => {
                if (Array.isArray(history)) {
                    this.renderHistory(history);
                }
            })
            .catch(() => {});
    }

    refresh() {
        fetch('/api/stats')
            .then(r => r.json())
            .then(data => {
                this.stats = data;
                this.updateAll();
            })
            .catch(() => {});
        fetch('/api/history?limit=20')
            .then(r => r.json())
            .then(data => {
                if (Array.isArray(data)) this.renderHistory(data);
            })
            .catch(() => {});
    }

    updateAll() {
        this.drawGauge();
        this.updateBars();
        this.updateMoveDist();
        this.updateStrategies();
    }

    drawGauge() {
        const ctx = this.gaugeCtx;
        const canvas = this.gaugeCanvas;
        const cx = canvas.width / 2;
        const cy = canvas.height / 2;
        const radius = 50;
        const lineWidth = 8;

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Background arc
        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(255,255,255,0.08)';
        ctx.lineWidth = lineWidth;
        ctx.stroke();

        // Win rate = wins / (wins + losses) — draws are explicitly excluded
        const wins = Number(this.stats.wins) || 0;
        const losses = Number(this.stats.losses) || 0;
        const decisive = wins + losses;
        const rate = decisive > 0 ? wins / decisive : 0;
        const startAngle = -Math.PI / 2;
        const endAngle = startAngle + Math.PI * 2 * Math.min(rate, 1);

        ctx.beginPath();
        ctx.arc(cx, cy, radius, startAngle, endAngle);
        ctx.strokeStyle = rate >= 0.5 ? '#4caf50' : rate >= 0.3 ? '#ff9800' : '#f44336';
        ctx.lineWidth = lineWidth;
        ctx.lineCap = 'round';
        ctx.stroke();

        // Text
        this.el.winRateText.textContent = `${(rate * 100).toFixed(0)}%`;
    }

    updateBars() {
        const total = Math.max(this.stats.total_games, 1);
        const wins = this.stats.wins || 0;
        const losses = this.stats.losses || 0;
        const draws = this.stats.draws || 0;

        this.el.barWin.style.width = `${(wins / total * 100).toFixed(1)}%`;
        this.el.barLose.style.width = `${(losses / total * 100).toFixed(1)}%`;
        this.el.barDraw.style.width = `${(draws / total * 100).toFixed(1)}%`;

        this.el.valWin.textContent = wins;
        this.el.valLose.textContent = losses;
        this.el.valDraw.textContent = draws;
    }

    updateMoveDist() {
        const cs = this.stats.class_stats || {};
        this.el.countRock.textContent = cs.Rock || 0;
        this.el.countPaper.textContent = cs.Paper || 0;
        this.el.countScissors.textContent = cs.Scissors || 0;
    }

    updateStrategies() {
        const ss = this.stats.strategy_stats || {};
        this.el.stratMarkov.textContent = ss.markov ? `${(ss.markov.accuracy * 100).toFixed(0)}%` : '--';
        this.el.stratFrequency.textContent = ss.frequency ? `${(ss.frequency.accuracy * 100).toFixed(0)}%` : '--';
        this.el.stratAntiRotate.textContent = ss.anti_rotate ? `${(ss.anti_rotate.accuracy * 100).toFixed(0)}%` : '--';
    }

    renderHistory(history) {
        const MOVE_ICONS = { Rock: '✊', Paper: '✋', Scissors: '✌' };
        const RESULT_CLASS = { win: 'result-win', lose: 'result-lose', draw: 'result-draw' };
        const RESULT_TEXT = { win: 'WIN', lose: 'LOSE', draw: 'DRAW' };

        this.el.historyTbody.innerHTML = history.map(r => `
            <tr>
                <td>${r.round_number}</td>
                <td>${MOVE_ICONS[r.player_move] || ''} ${r.player_move || ''}</td>
                <td>${MOVE_ICONS[r.computer_move] || ''} ${r.computer_move || ''}</td>
                <td class="${RESULT_CLASS[r.result] || ''}">${RESULT_TEXT[r.result] || r.result}</td>
            </tr>
        `).join('');
    }
}
