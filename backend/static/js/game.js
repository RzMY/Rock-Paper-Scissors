const MOVE_ICONS = { Rock: '✊', Paper: '✋', Scissors: '✌' };

class GameUI {
    constructor(wsClient) {
        this.ws = wsClient;
        this.state = 'waiting';
        this.autoPlay = false;
        this._resultTimer = null;  // track client-side result timeout

        // DOM refs
        this.el = {
            btnStart: document.getElementById('btn-start'),
            btnAuto: document.getElementById('btn-auto'),
            countdown: document.getElementById('countdown'),
            countdownNum: document.getElementById('countdown-number'),
            roundResult: document.getElementById('round-result'),
            waitingState: document.getElementById('waiting-state'),
            noDetectState: document.getElementById('no-detect-state'),
            noModelState: document.getElementById('no-model-state'),
            playerMoveIcon: document.getElementById('player-move-icon'),
            playerMoveLabel: document.getElementById('player-move-label'),
            playerMoveConf: document.getElementById('player-move-conf'),
            computerMoveIcon: document.getElementById('computer-move-icon'),
            computerMoveLabel: document.getElementById('computer-move-label'),
            resultBanner: document.getElementById('result-banner'),
            strategyInfo: document.getElementById('strategy-info'),
            scorePlayer: document.getElementById('score-player'),
            scoreComputer: document.getElementById('score-computer'),
            scoreDraws: document.getElementById('score-draws'),
            gameDisplay: document.getElementById('game-display'),
            consoleRound: document.getElementById('console-round'),
            consoleBody: document.getElementById('console-body'),
        };

        this.setupEvents();
        this.setupWSHandlers();
    }

    setupEvents() {
        this.el.btnStart.addEventListener('click', () => this.startRound());
        this.el.btnAuto.addEventListener('click', () => this.toggleAuto());
        document.addEventListener('keydown', (e) => {
            if (e.code === 'Space') {
                e.preventDefault();
                this.startRound();
            } else if (e.code === 'KeyA' && !e.ctrlKey && !e.metaKey) {
                e.preventDefault();
                this.toggleAuto();
            }
        });
    }

    toggleAuto() {
        this.ws.send('toggle_auto');
    }

    _clearResultTimer() {
        if (this._resultTimer) {
            clearTimeout(this._resultTimer);
            this._resultTimer = null;
        }
    }

    setupWSHandlers() {
        this.ws.on('game_state', (msg) => {
            this.state = msg.state;
            // Clear any client-side result timer whenever state changes
            if (msg.state !== 'result') {
                this._clearResultTimer();
            }
            if (msg.state === 'countdown' && msg.count) {
                this.showCountdown(msg.count);
            } else if (msg.state === 'shoot') {
                this.showShoot();
            } else if (msg.state === 'result') {
                this.showResult(msg);
                if (msg.reasoning) {
                    this.showReasoning(msg.reasoning);
                }
            } else if (msg.state === 'waiting') {
                this.showWaiting();
            } else if (msg.state === 'no_detect') {
                this.showNoDetect();
            }
        });

        this.ws.on('auto_play', (msg) => {
            this.autoPlay = msg.enabled;
            this.el.btnAuto.textContent = msg.enabled ? 'Auto: ON' : 'Auto: OFF';
            this.el.btnAuto.classList.toggle('active', msg.enabled);
            // Cancel any client-side result timer when auto is turned on
            if (msg.enabled) {
                this._clearResultTimer();
            }
        });

        this.ws.on('score_update', (msg) => {
            this.updateScores(msg.player, msg.computer, msg.draws);
        });

        this.ws.on('error', (msg) => {
            if (msg.message && msg.message.includes('Model not loaded')) {
                this.showNoModel();
            }
        });

        this.ws.on('connected', () => {
            this.el.btnStart.disabled = false;
            this.el.btnAuto.disabled = false;
        });

        this.ws.on('disconnected', () => {
            this.el.btnStart.disabled = true;
            this.el.btnAuto.disabled = true;
        });
    }

    startRound() {
        if (this.state === 'countdown' || this.state === 'shoot') return;
        this.ws.send('start_round');
    }

    showCountdown(count) {
        this.hideAll();
        this.el.countdown.classList.remove('hidden');
        this.el.btnStart.disabled = true;
        // Only update and pulse when the count actually changes
        const prev = parseInt(this.el.countdownNum.textContent) || 0;
        if (count === prev) return;
        this.el.countdownNum.textContent = count;
        // Trigger a single pulse on number transitions
        this.el.countdownNum.classList.remove('pulse-once');
        void this.el.countdownNum.offsetWidth; // reflow to restart animation
        this.el.countdownNum.classList.add('pulse-once');
    }

    showShoot() {
        this.hideAll();
        this.el.btnStart.disabled = true;
    }

    showResult(msg) {
        this.hideAll();
        this.el.roundResult.classList.remove('hidden');

        this.el.playerMoveIcon.textContent = MOVE_ICONS[msg.player_move] || '?';
        this.el.playerMoveLabel.textContent = msg.player_move || '?';
        this.el.playerMoveConf.textContent = msg.confidence ? `${(msg.confidence * 100).toFixed(0)}%` : '';

        this.el.computerMoveIcon.textContent = MOVE_ICONS[msg.computer_move] || '?';
        this.el.computerMoveLabel.textContent = msg.computer_move || '?';

        const result = msg.result;
        this.el.resultBanner.textContent = result === 'win' ? 'You Win!' : result === 'lose' ? 'Computer Wins!' : 'Draw';
        this.el.resultBanner.className = `result-banner ${result}`;

        if (msg.predicted_player_move && msg.strategy) {
            this.el.strategyInfo.textContent = `AI predicted: ${msg.predicted_player_move} (${msg.strategy})`;
        }

        // In auto mode the server handles the transition;
        // in manual mode use a client-side fallback timer.
        this._clearResultTimer();
        if (!this.autoPlay) {
            this._resultTimer = setTimeout(() => this.showWaiting(), 2000);
        }
    }

    showReasoning(reasoning) {
        if (!reasoning || !reasoning.candidates) {
            this.el.consoleBody.innerHTML = '<div class="console-line empty">No AI data available</div>';
            return;
        }

        const historyLen = Array.isArray(reasoning.history) ? reasoning.history.length : 0;
        this.el.consoleRound.textContent = historyLen > 0
            ? `After ${historyLen} rounds`
            : 'First round';

        let html = '';

        // Show what each strategy predicted
        html += '<div class="console-line"><strong>Candidates:</strong></div>';
        const candidates = reasoning.candidates || {};
        for (const [name, pred] of Object.entries(candidates)) {
            const isSelected = name === reasoning.strategy_selected;
            const marker = isSelected ? ' ▶' : '';
            const cls = isSelected ? 'strat' : '';
            html += `<div class="console-line">
              <span class="${cls}">${name}${marker}</span>: ${pred}
            </div>`;
        }

        // Show accuracy of each strategy
        html += '<div class="console-line"><strong>Accuracy:</strong></div>';
        const acc = reasoning.strategy_accuracies || {};
        const accEntries = Object.entries(acc);
        if (accEntries.length === 0) {
            html += '<div class="console-line">--</div>';
        } else {
            for (const [name, val] of accEntries) {
                html += `<div class="console-line">
                  ${name}: ${typeof val === 'number' && val > 0 ? (val * 100).toFixed(0) + '%' : '--'}
                </div>`;
            }
        }

        // Decision summary
        html += `<div class="console-line" style="margin-top:4px;border-top:1px solid rgba(255,255,255,0.08);padding-top:4px;">
          <span class="pred">Predict:</span> <span class="move-name">${reasoning.predicted_player_move || '?'}</span>
          →
          <span class="actual">Counter:</span> <span class="move-name">${reasoning.computer_move || '?'}</span>
          via <span class="strat">${reasoning.strategy_selected || '?'}</span>
        </div>`;

        this.el.consoleBody.innerHTML = html;
        // Auto-scroll to bottom
        this.el.consoleBody.scrollTop = this.el.consoleBody.scrollHeight;
    }

    showWaiting() {
        this.hideAll();
        this.el.waitingState.classList.remove('hidden');
        this.el.btnStart.disabled = false;
    }

    showNoDetect() {
        this.hideAll();
        this.el.noDetectState.classList.remove('hidden');
        this.el.btnStart.disabled = false;
    }

    showNoModel() {
        this.hideAll();
        this.el.noModelState.classList.remove('hidden');
        this.el.btnStart.disabled = true;
    }

    hideAll() {
        this.el.countdown.classList.add('hidden');
        this.el.roundResult.classList.add('hidden');
        this.el.waitingState.classList.add('hidden');
        this.el.noDetectState.classList.add('hidden');
        this.el.noModelState.classList.add('hidden');
    }

    updateScores(player, computer, draws) {
        animateNumber(this.el.scorePlayer, player);
        animateNumber(this.el.scoreComputer, computer);
        animateNumber(this.el.scoreDraws, draws);
    }
}

function animateNumber(el, target) {
    const current = parseInt(el.textContent) || 0;
    if (current === target) return;
    el.textContent = target;
    el.style.transform = 'scale(1.3)';
    el.style.transition = 'transform 0.15s ease';
    setTimeout(() => { el.style.transform = 'scale(1)'; }, 150);
}
