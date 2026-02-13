// Dashboard state
let ws = null;
let reconnectDelay = 1000;
let pendingRequests = new Set();
let demoRunning = false;

// DOM elements
const boardsContainer = document.getElementById('boards-container');
const connectionStatus = document.getElementById('connection-status');
const statusDot = connectionStatus.querySelector('.status-dot');
const statusText = connectionStatus.querySelector('.status-text');
const emergencyStop = document.getElementById('emergency-stop');
const demoBtn = document.getElementById('demo-btn');
const demoDelaySelect = document.getElementById('demo-delay');
const lastUpdateSpan = document.getElementById('last-update');
const totalBoardsSpan = document.getElementById('total-boards');
const relaysOnSpan = document.getElementById('relays-on');
const relaysOffSpan = document.getElementById('relays-off');
const relaysUnknownSpan = document.getElementById('relays-unknown');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    emergencyStop.addEventListener('click', handleEmergencyStop);
    demoBtn.addEventListener('click', handleDemo);
    connectWebSocket();
    fetchVersion();
});

async function fetchVersion() {
    try {
        const response = await fetch('/version');
        const data = await response.json();
        document.getElementById('version').textContent = data.commit.slice(0, 7);
    } catch {
        document.getElementById('version').textContent = 'unknown';
    }
}

function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws`);

    ws.onopen = () => {
        reconnectDelay = 1000;
        setConnectionStatus(false, true);
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        updateDashboard(data);
        setConnectionStatus(data.ioexpander_connected, true);
    };

    ws.onclose = () => {
        setConnectionStatus(false, false);
        setTimeout(() => {
            reconnectDelay = Math.min(reconnectDelay * 2, 30000);
            connectWebSocket();
        }, reconnectDelay);
    };

    ws.onerror = () => {
        ws.close();
    };
}

function setConnectionStatus(ioConnected, apiConnected) {
    statusDot.classList.remove('connected', 'disconnected');

    if (!apiConnected) {
        statusDot.classList.add('disconnected');
        statusText.textContent = 'Disconnected';
    } else if (ioConnected) {
        statusDot.classList.add('connected');
        statusText.textContent = 'Connected';
    } else {
        statusText.textContent = 'Simulation Mode';
    }
}

function updateDashboard(data) {
    // Update summary
    totalBoardsSpan.textContent = data.summary.total_boards;
    relaysOnSpan.textContent = data.summary.relays_on;
    relaysOffSpan.textContent = data.summary.relays_off;
    relaysUnknownSpan.textContent = data.summary.relays_unknown;

    // Update timestamp
    const timestamp = new Date(data.timestamp);
    lastUpdateSpan.textContent = timestamp.toLocaleTimeString();

    // Update boards
    updateBoards(data.boards);
}

function updateBoards(boards) {
    // Check if we need to rebuild the structure
    const existingBoards = boardsContainer.querySelectorAll('.board');
    const needsRebuild = existingBoards.length !== boards.length ||
        boards.some((board, i) => {
            const existing = existingBoards[i];
            return !existing ||
                existing.dataset.addr !== String(board.board_addr) ||
                existing.querySelectorAll('.relay').length !== board.relay_count;
        });

    if (needsRebuild) {
        rebuildBoards(boards);
    } else {
        // Just update relay states
        boards.forEach(board => {
            board.relays.forEach(relay => {
                updateRelayState(board.board_addr, relay.relay_num, relay.state, relay.simulated);
            });
        });
    }
}

function rebuildBoards(boards) {
    boardsContainer.innerHTML = '';

    boards.forEach(board => {
        const boardEl = document.createElement('div');
        boardEl.className = 'board';
        boardEl.dataset.addr = board.board_addr;

        const nameDisplay = board.name ? `<span class="board-name">(${board.name})</span>` : '';

        boardEl.innerHTML = `
            <div class="board-header">
                <div class="board-title">
                    Board ${board.board_addr} ${nameDisplay}
                </div>
                <div class="board-stats">
                    ${board.relay_count} relays
                </div>
            </div>
            <div class="relay-grid">
                ${board.relays.map(relay => {
                    const classes = ['relay', relay.state];
                    if (relay.simulated) classes.push('simulated');
                    return `
                        <div class="${classes.join(' ')}"
                             data-addr="${board.board_addr}"
                             data-num="${relay.relay_num}"
                             title="Relay ${relay.relay_num}: ${relay.state}${relay.simulated ? ' (simulated)' : ''}">
                            ${relay.relay_num}
                        </div>
                    `;
                }).join('')}
            </div>
        `;

        // Add click handlers for relays
        boardEl.querySelectorAll('.relay').forEach(relayEl => {
            relayEl.addEventListener('click', () => handleRelayClick(relayEl));
        });

        boardsContainer.appendChild(boardEl);
    });
}

function updateRelayState(boardAddr, relayNum, state, simulated) {
    const relayEl = document.querySelector(
        `.relay[data-addr="${boardAddr}"][data-num="${relayNum}"]`
    );

    if (relayEl) {
        relayEl.classList.remove('on', 'off', 'unknown', 'simulated', 'pending');
        relayEl.classList.add(state);
        if (simulated) {
            relayEl.classList.add('simulated');
        }
        relayEl.title = `Relay ${relayNum}: ${state}${simulated ? ' (simulated)' : ''}`;
    }
}

async function handleRelayClick(relayEl) {
    const boardAddr = relayEl.dataset.addr;
    const relayNum = relayEl.dataset.num;
    const requestKey = `${boardAddr}-${relayNum}`;

    // Prevent duplicate requests
    if (pendingRequests.has(requestKey)) {
        return;
    }

    // Determine action based on current state
    const isOn = relayEl.classList.contains('on');
    const action = isOn ? 'close' : 'open';

    // Mark as pending
    relayEl.classList.add('pending');
    pendingRequests.add(requestKey);

    try {
        const response = await fetch(
            `/boards/${boardAddr}/relays/${relayNum}/${action}`,
            { method: 'POST' }
        );

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        // WebSocket push will update the UI state

    } catch (error) {
        console.error(`Failed to ${action} relay:`, error);
    } finally {
        relayEl.classList.remove('pending');
        pendingRequests.delete(requestKey);
    }
}

async function handleDemo() {
    if (demoRunning) {
        return;
    }

    demoRunning = true;
    demoBtn.disabled = true;
    demoBtn.classList.add('running');
    demoBtn.textContent = 'Running...';

    const delayMs = parseInt(demoDelaySelect.value, 10);

    try {
        const response = await fetch(`/boards/demo?delay_ms=${delayMs}`, { method: 'POST' });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        if (data.simulated) {
            console.log('Demo completed in simulation mode');
        }

    } catch (error) {
        console.error('Demo failed:', error);
        alert('Demo failed! Check console for details.');
    } finally {
        demoRunning = false;
        demoBtn.disabled = false;
        demoBtn.classList.remove('running');
        demoBtn.textContent = 'Run Demo';
    }
}

async function handleEmergencyStop() {
    if (!confirm('Are you sure you want to close ALL relays?')) {
        return;
    }

    emergencyStop.disabled = true;
    emergencyStop.textContent = 'STOPPING...';

    try {
        const response = await fetch('/boards/close-all', { method: 'POST' });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        // WebSocket push will update the UI state

    } catch (error) {
        console.error('Emergency stop failed:', error);
        alert('Emergency stop failed! Check console for details.');
    } finally {
        emergencyStop.disabled = false;
        emergencyStop.textContent = 'EMERGENCY STOP';
    }
}
