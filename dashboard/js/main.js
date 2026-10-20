/**
 * Project Nexus — Main Entry Point
 * Connects to Python backend via WebSocket (ws://localhost:9001)
 * Falls back to full simulation when backend is offline.
 */

// ─── Global log helper ──────────────────────────────────────────────
window.nexusLog = function (source, message, level = 'info') {
  window.__ui?.addLog({ source, message, level, timestamp: new Date().toISOString() });
};

// ─── WebSocket Client ───────────────────────────────────────────────
class NexusBackendClient {
  constructor(url = 'ws://localhost:9001') {
    this.url      = url;
    this.ws       = null;
    this.online   = false;
    this.retries  = 0;
    this.handlers = {};
  }

  on(type, fn) {
    if (!this.handlers[type]) this.handlers[type] = [];
    this.handlers[type].push(fn);
  }

  connect() {
    try {
      this.ws = new WebSocket(this.url);
      this.ws.onopen    = () => this._onOpen();
      this.ws.onmessage = (e) => this._onMessage(e);
      this.ws.onclose   = () => this._onClose();
      this.ws.onerror   = () => { this.online = false; };
    } catch (e) { this.online = false; }
  }

  send(obj) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(obj));
    }
  }

  _onOpen() {
    // First-frame session-token handshake. The engine writes the token to
    // %LOCALAPPDATA%/NexusFabric/session.key on startup. The dashboard reads
    // it via window.NEXUS_TOKEN (set by the launcher) or localStorage.
    const token =
      (typeof window !== 'undefined' && window.NEXUS_TOKEN) ||
      (typeof localStorage !== 'undefined' && localStorage.getItem('nexus_token')) ||
      '';
    try { this.ws.send(JSON.stringify({ auth: token })); } catch (e) { /* ignore */ }

    this.online  = true;
    this.retries = 0;
    console.log('[Nexus WS] Connected to backend');
    window.nexusLog('WebSocket', 'Connected to Nexus Engine backend', 'info');
    const statusEl = document.getElementById('status-text');
    if (statusEl) statusEl.textContent = 'BACKEND LIVE';
    this._emit('connected', true);
  }

  _onMessage(e) {
    try {
      const msg = JSON.parse(e.data);
      this._emit(msg.type, msg.data);
      this._emit('any', msg);
    } catch (_) {}
  }

  _onClose() {
    this.online = false;
    this.retries++;
    const delay = Math.min(8000, 1000 * this.retries);
    console.log(`[Nexus WS] Disconnected — retry in ${delay}ms`);
    if (this.retries === 1) {
      window.nexusLog('WebSocket', 'Backend offline — using simulation mode', 'warn');
      document.getElementById('status-text').textContent = 'SIMULATION';
    }
    setTimeout(() => this.connect(), delay);
  }

  _emit(type, data) {
    (this.handlers[type] || []).forEach(fn => { try { fn(data); } catch (e) {} });
  }
}


// ─── Simulation Actions ─────────────────────────────────────────────
const SIM_ACTIONS = [
  { id: 'alpha-1', msg: 'Enumerated dGPU capabilities — VRAM budget computed' },
  { id: 'alpha-2', msg: 'Detected: REDengine 4 — D3D12 — Deferred render path' },
  { id: 'alpha-3', msg: 'Performance Oracle: LOD+1.5 → predicted +14 FPS (conf: 82%)' },
  { id: 'alpha-4', msg: 'Scene: HEAVY — 2.4M triangles — flagging SMRP activation' },
  { id: 'beta-1',  msg: 'FPS Maximizer: Proposed shader nullification — +18 FPS est.' },
  { id: 'beta-2',  msg: 'Latency Minimizer: Render thread isolated to P-Core 0 — StdDev -3ms' },
  { id: 'beta-3',  msg: 'Memory Strategist: Evicted 890MB idle mip tails — VRAM freed' },
  { id: 'beta-4',  msg: 'Bottleneck Hunter: GPU_COMPUTE @94% — primary bottleneck confirmed' },
  { id: 'gamma-1', msg: 'Quality Guardian: Frametime 34ms → switching to PERFORMANCE profile' },
  { id: 'gamma-2', msg: 'LOD Controller: Applied bias +2.5 — VRAM bandwidth -38%' },
  { id: 'gamma-3', msg: 'Shader Arbiter: Nullified volumetric_fog + SSR — +14% GPU freed' },
  { id: 'delta-1', msg: 'CPU Thread Master: Render thread → P-Core-0 (THREAD_PRIORITY_HIGHEST)' },
  { id: 'delta-2', msg: 'iGPU Router: Physics particles rerouted to Intel UHD — dGPU freed 7%' },
  { id: 'delta-3', msg: 'VRAM Steward: Budget 6.8GB enforced — 3 textures evicted (LRU)' },
  { id: 'delta-4', msg: 'Power Governor: High Performance mode active | Timer 0.5ms' },
  { id: 'epsilon-1',msg: 'Mobile Link Guardian: No USB 3.2 device — standby mode' },
  { id: 'epsilon-3',msg: 'Failsafe Commander: Standby — no disconnect events this session' },
  { id: 'zeta-1',  msg: 'Validator Alpha: Approved 4/5 proposals — 1 rejected (implausible gain)' },
  { id: 'zeta-2',  msg: 'Validator Beta: Full agreement with Alpha — consensus achieved' },
  { id: 'zeta-3',  msg: 'Policy Enforcer: Auth level SINGLE_PLAYER — 3 actions permitted' },
  { id: 'zeta-4',  msg: 'Integrity Auditor: Chain valid — 0 violations — 1,247 entries' },
  { id: 'eta-1',   msg: 'Execution Supervisor: 3 actions approved — system OPTIMIZING' },
  { id: 'eta-2',   msg: 'Priority Scheduler: Queue 2 — next: LOD bias adjust (HIGH priority)' },
  { id: 'eta-3',   msg: 'Conflict Resolver: FPS vs Latency conflict → balanced LOD+1.5 solution' },
  { id: 'theta-1', msg: 'Frametime Sentinel: Spike 67ms detected — Quality Guardian alerted' },
  { id: 'theta-2', msg: 'Thermal Watchdog: GPU 78°C | CPU 61°C — within safe thresholds' },
  { id: 'theta-3', msg: 'Anomaly Detector: System health 89/100 — 0 active anomalies' },
  { id: 'iota-1',  msg: 'Config Specialist: Injected r.ShadowQuality=0, r.ScreenPercentage=60' },
  { id: 'iota-2',  msg: 'Engine.ini Optimizer: Profile "CyberpunkHeavy_v3" — 47 keys active' },
  { id: 'iota-3',  msg: 'Compatibility Oracle: 47 keys checked — 0 crash risks detected' },
];

// ─── Boot ───────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {

  // 1. Init UI
  const ui = new UIRenderer();
  window.__ui = ui;
  ui.init();

  // 2. Init chart
  const chart = new NexusChart('frametime-chart');
  chart.init();

  // 3. Init hardware (local simulation)
  const hw = new HardwareTelemetry();
  const localOrchestrator = new AgentOrchestrator();

  // 4. Init WebSocket client
  const client = new NexusBackendClient();
  window.__client = client;

  // ── WebSocket handlers ──────────────────────────────────────
  client.on('hardware', (data) => {
    // Real data from Python backend
    ui.updateMetrics(data);
    ui.updateHardwareTab(data);
    hw._history.frametime.push({ x: Date.now(), y: data.frametime_ms || 16.6 });
    if (hw._history.frametime.length > 150) hw._history.frametime.shift();
    chart.update(hw.getHistory());
  });

  client.on('agents', (data) => {
    if (!Array.isArray(data)) return;
    // Transform flat agent list into status format
    const statusMap = {};
    data.forEach(a => {
      statusMap[a.id] = a;
    });
    // Build mini status from AGENT_TEAMS
    if (window.AGENT_TEAMS) {
      const status = {
        activeAgents: data.filter(a => a.status !== 'offline').length,
        standbyAgents: data.filter(a => a.status === 'standby').length,
        systemHealth: Math.round(data.reduce((s, a) => s + a.confidence, 0) / data.length),
        teams: window.AGENT_TEAMS.map(t => ({
          ...t,
          agents: t.agents.map(a => ({ ...a, ...(statusMap[a.id] || {}), teamColor: t.color })),
          activeCount: t.agents.filter(a => (statusMap[a.id]?.status || 'active') !== 'offline').length,
        })),
      };
      ui.updateAgentsMini(status);
      ui.updateAgentCards(status);
    }
  });

  client.on('cycle', (data) => {
    if (!data) return;
    // Show approved actions as toasts
    const actions = data.approved_actions || [];
    if (actions.length > 0) {
      ui.showToast('success', '⚡', `Cycle #${data.cycle_id}: ${actions.length} actions applied`);
    }
    // Update agents if bundled
    if (data.agents) {
      client._emit('agents', data.agents);
    }
  });

  client.on('processes', (data) => {
    if (Array.isArray(data) && data.length > 0) {
      ui.renderProcesses(data);
    }
  });

  client.on('log', (entry) => {
    ui.addLog({
      source:    entry.source || 'System',
      message:   entry.message || '',
      level:     entry.level || 'info',
      timestamp: entry.timestamp ? new Date(entry.timestamp * 1000).toISOString() : new Date().toISOString(),
    });
  });

  client.on('connected', () => {
    hw.stop();  // Stop local sim — backend takes over
    ui.showToast('success', '🔗', 'Nexus Engine backend connected — live data active');
  });

  // ── Local simulation (when backend is offline) ──────────────
  hw.on('update', (data) => {
    if (!client.online) {
      ui.updateMetrics(data);
      ui.updateHardwareTab(data);
      chart.update(hw.getHistory());
    }
  });
  hw.start();

  // ── Local agent orchestrator (simulation mode) ──────────────
  localOrchestrator.on('cycle', (status) => {
    if (!client.online) {
      ui.updateAgentsMini(status);
      ui.updateAgentCards(status);
    }
  });
  localOrchestrator.start();

  // ── Try connecting to backend ───────────────────────────────
  client.connect();

  // ── Simulated agent actions (always run for realism) ────────
  let simIdx = 0;
  const runSimAction = () => {
    if (!client.online) {
      const act = SIM_ACTIONS[simIdx % SIM_ACTIONS.length];
      simIdx++;
      const agent = window.ALL_AGENTS?.find(a => a.id === act.id);
      if (agent) {
        window.nexusLog(`${agent.icon} ${agent.name}`, act.msg, 'agent');
        localOrchestrator.injectSimulatedAction(act.id, act.msg, true);
      }
    }
    setTimeout(runSimAction, 2000 + Math.random() * 3000);
  };
  setTimeout(runSimAction, 2500);

  // ── Reasoning cycle log messages ────────────────────────────
  const CYCLE_MSGS = [
    ['eta-1',   'Reasoning cycle started — awaiting team reports'],
    ['theta-3', 'Full system scan — health score updated'],
    ['alpha-3', 'Performance Oracle recalibrated from last cycle outcomes'],
    ['zeta-4',  'Audit log hash chain verified — integrity OK'],
    ['eta-3',   'No conflicts in current agent recommendations'],
    ['gamma-1', 'Quality Guardian evaluated frametime — profile held'],
    ['beta-4',  'Bottleneck re-evaluated — classification stable'],
    ['zeta-1',  'Validator Alpha reviewed pending proposals'],
  ];
  let cycleIdx = 0;
  setInterval(() => {
    if (!client.online) {
      const m = CYCLE_MSGS[cycleIdx++ % CYCLE_MSGS.length];
      const agent = window.ALL_AGENTS?.find(a => a.id === m[0]);
      if (agent) window.nexusLog(`🔄 ${agent.name}`, m[1], 'info');
    }
  }, 6000);

  // ── Startup sequence ─────────────────────────────────────────
  setTimeout(() => ui.showToast('info', '🚀', 'Project Nexus v0.9 initializing...'), 400);
  setTimeout(() => ui.showToast('info', '🤖', `${window.TOTAL_AGENTS} agents across ${window.TOTAL_TEAMS} teams loaded`), 1800);
  setTimeout(() => ui.showToast('info', '📡', 'Connecting to Nexus Engine backend...'), 3200);

  // ── Initial logs ─────────────────────────────────────────────
  window.nexusLog('NEXUS CORE', `Project Nexus v0.9 — ${window.TOTAL_AGENTS} agents | ${window.TOTAL_TEAMS} teams`, 'info');
  window.nexusLog('NEXUS CORE', 'Attempting backend connection at ws://localhost:9001', 'info');
  window.nexusLog('Policy Guard', 'Authorization matrix loaded — default: SINGLE_PLAYER', 'info');
  window.nexusLog('Integrity Auditor', 'Audit log initialized — hash chain ready', 'info');
  window.nexusLog('Anomaly Detector', 'All monitors active — baseline phase', 'info');

  // ── Dashboard send helpers ────────────────────────────────────
  document.getElementById('btn-apply-profile')?.addEventListener('click', () => {
    const active = document.querySelector('.profile-item.active');
    if (active) {
      const profileId = active.id.replace('profile-', '');
      client.send({ type: 'set_profile', profile: profileId });
    }
  });

  document.getElementById('btn-confirm-inject')?.addEventListener('click', () => {
    const selected = document.querySelector('.process-item.selected');
    const process  = selected?.querySelector('span:nth-child(2)')?.textContent || 'unknown';
    client.send({ type: 'inject', process });
  });

  document.getElementById('btn-rollback')?.addEventListener('click', () => {
    client.send({ type: 'rollback' });
    ui.showToast('warn', '↺', 'Rollback initiated — restoring original configurations');
    window.nexusLog('Failsafe Commander', 'Manual rollback requested by operator', 'warn');
  });

});

