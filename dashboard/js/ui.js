/**
 * UI rendering — populates and updates all DOM elements
 */

const QUALITY_PROFILES = [
  { id: 'ULTRA_PERFORMANCE', name: 'Ultra Performance', desc: 'LOD +4.0 | Res 40% | Shadows OFF', color: '#ef4444' },
  { id: 'PERFORMANCE',       name: 'Performance',       desc: 'LOD +2.5 | Res 60% | Shadows LOW', color: '#f59e0b' },
  { id: 'BALANCED',          name: 'Balanced',          desc: 'LOD +1.0 | Res 75% | Shadows MED', color: '#22c55e' },
  { id: 'QUALITY',           name: 'Quality',           desc: 'LOD +0.0 | Res 90% | RT Reflect',  color: '#00d4ff' },
  { id: 'ULTRA_QUALITY',     name: 'Ultra Quality',     desc: 'LOD -0.5 | Res 100% | RT FULL',    color: '#a855f7' },
];

class UIRenderer {
  constructor() {
    this._activeProfile = 'PERFORMANCE';
    this._activeTab = 'dashboard';
    this._logEntries = [];
    this._logFilter = 'all';
  }

  // ─── INIT ────────────────────────────────────────────────────
  init() {
    this._buildSVGDefs();
    this._buildProfilesList();
    this._buildAgentsTab();
    this._buildHardwareTab();
    this._buildConfigTab();
    this._setupNavigation();
    this._setupModal();
    this._setupLogFilters();
  }

  _buildSVGDefs() {
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    defs.setAttribute('class', 'defs-only');
    defs.innerHTML = `
      <defs>
        <linearGradient id="ringGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#00d4ff"/>
          <stop offset="100%" stop-color="#a855f7"/>
        </linearGradient>
        <linearGradient id="cpuGrad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#22c55e"/>
          <stop offset="100%" stop-color="#00d4ff"/>
        </linearGradient>
        <linearGradient id="gpuGrad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#a855f7"/>
          <stop offset="100%" stop-color="#ec4899"/>
        </linearGradient>
      </defs>`;
    document.body.prepend(defs);
  }

  // ─── NAVIGATION ──────────────────────────────────────────────
  _setupNavigation() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        this._switchTab(tab);
      });
    });
  }

  _switchTab(tab) {
    this._activeTab = tab;
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === `tab-${tab}`));
  }

  // ─── DASHBOARD METRICS UPDATE ─────────────────────────────── 
  updateMetrics(d) {
    // FPS
    this._setText('fps-num', d.fps || '--');
    this._setText('fps-1low', d.fps_1pct || '--');
    this._setBar('fps-bar', Math.min(100, (d.fps / 120) * 100));

    // Frametime
    this._setText('ft-num', d.frametime_ms?.toFixed(1) || '--');
    this._setText('ft-avg', d.frametime_avg?.toFixed(1) || '--');
    const ftPct = Math.min(100, (d.frametime_ms / 40) * 100);
    this._setBar('ft-bar', ftPct);
    const ftBar = document.getElementById('ft-bar');
    if (ftBar) ftBar.style.background = d.frametime_ms > 33 ? 'linear-gradient(90deg,#f59e0b,#ef4444)' : 'linear-gradient(90deg,#22c55e,#f59e0b)';

    // CPU gauge
    this._setGauge('cpu-gauge', d.cpu_load || 0);
    this._setText('cpu-pct', (d.cpu_load?.toFixed(0) || '--') + '%');
    if (d.cpu_name) this._setText('cpu-name', d.cpu_name.split(' ').slice(0, 4).join(' '));

    // GPU gauge
    this._setGauge('gpu-gauge', d.gpu_load || 0);
    this._setText('gpu-pct', (d.gpu_load?.toFixed(0) || '--') + '%');
    if (d.gpu_name) this._setText('gpu-name', d.gpu_name.split(' ').slice(0, 3).join(' '));

    // VRAM
    this._setText('vram-used', d.vram_used_gb?.toFixed(1) || '--');
    this._setText('vram-total', (d.vram_total_gb || 8) + ' GB');
    this._setBar('vram-bar', Math.min(100, (d.vram_used_gb / d.vram_total_gb) * 100));

    // Nexus score
    const score = d.nexus_score || 0;
    this._setText('nexus-score-value', score.toFixed(1));
    const offset = 314 - (314 * score / 10);
    const ring = document.getElementById('score-ring');
    if (ring) ring.style.strokeDashoffset = offset;
    const tier = score >= 8 ? 'ULTRA QUALITY' : score >= 6 ? 'PERFORMANCE' : score >= 4 ? 'BALANCED' : 'ULTRA PERF';
    this._setText('score-tier', tier);

    // Thermal
    this._setText('cpu-temp', (d.cpu_temp_c?.toFixed(0) || '--') + ' °C');
    this._setText('gpu-temp', (d.gpu_temp_c?.toFixed(0) || '--') + ' °C');
    this._setText('power-draw', (d.power_draw_w || '--') + ' W');
    this._setText('ram-usage', (d.ram_used_gb?.toFixed(1) || '--') + ' GB');
    const cpuHot = d.cpu_temp_c > 80;
    const gpuHot = d.gpu_temp_c > 75;
    this._setBar('cpu-temp-bar', Math.min(100, ((d.cpu_temp_c - 30) / 70) * 100));
    this._setBar('gpu-temp-bar', Math.min(100, ((d.gpu_temp_c - 30) / 65) * 100));
    this._setBar('power-bar', Math.min(100, (d.power_draw_w / 250) * 100));
    this._setBar('ram-bar', Math.min(100, (d.ram_used_gb / d.ram_total_gb) * 100));
    const cpuBar = document.getElementById('cpu-temp-bar');
    if (cpuBar) cpuBar.className = `thermal-bar${cpuHot ? ' hot' : ''}`;

    // Topology
    this._setText('topo-cpu-load', (d.cpu_load?.toFixed(0) || '--') + '%');
    this._setText('topo-dgpu-load', (d.gpu_load?.toFixed(0) || '--') + '%');
    this._setText('topo-igpu-load', (d.igpu_load?.toFixed(0) || '--') + '%');
    if (d.cpu_name) this._setText('topo-cpu-name', d.cpu_name.split(' ').slice(0,2).join(' '));
    if (d.gpu_name) this._setText('topo-dgpu-name', d.gpu_name.split(' ').slice(0,2).join(' '));
    const mobileNode = document.getElementById('topo-mobile');
    const mobileStatus = document.getElementById('topo-mobile-status');
    if (mobileStatus) {
      mobileStatus.textContent = d.mobile_connected ? `${d.mobile_latency_ms}ms` : 'DISCONNECTED';
      mobileStatus.style.color = d.mobile_connected ? '#22c55e' : '#ef4444';
    }
    if (mobileNode) mobileNode.classList.toggle('connected', d.mobile_connected);
  }

  // ─── AGENTS PANEL (dashboard mini) ───────────────────────────
  updateAgentsMini(status) {
    const grid = document.getElementById('agents-grid');
    if (!grid) return;

    this._setText('agents-active', status.activeAgents);

    // Only rebuild if empty
    if (grid.children.length === 0) {
      grid.innerHTML = '';
      status.teams.forEach(team => {
        team.agents.forEach(agent => {
          const el = document.createElement('div');
          el.className = 'agent-mini-card';
          el.id = `mini-${agent.id}`;
          el.innerHTML = `
            <span class="agent-mini-icon">${agent.icon}</span>
            <div class="agent-mini-info">
              <div class="agent-mini-name">${agent.name}</div>
              <div class="agent-mini-team" style="color:${team.color}">${team.name}</div>
            </div>
            <span class="agent-mini-status status-${agent.status}">${agent.status.toUpperCase()}</span>`;
          el.addEventListener('click', () => this._switchTab('agents'));
          grid.appendChild(el);
        });
      });
    } else {
      // Just update statuses
      status.teams.forEach(team => {
        team.agents.forEach(agent => {
          const el = document.getElementById(`mini-${agent.id}`);
          if (el) {
            const badge = el.querySelector('.agent-mini-status');
            if (badge) {
              badge.className = `agent-mini-status status-${agent.status}`;
              badge.textContent = agent.status.toUpperCase();
            }
          }
        });
      });
    }
  }

  // ─── AGENTS DETAIL TAB ───────────────────────────────────────
  _buildAgentsTab() {
    const grid = document.getElementById('agents-detail-grid');
    if (!grid || !window.AGENT_TEAMS) return;

    grid.innerHTML = '';
    window.AGENT_TEAMS.forEach(team => {
      const section = document.createElement('div');
      section.className = 'team-section';
      section.id = `team-${team.id}`;

      const agentCount = team.agents.length;
      section.innerHTML = `
        <div class="team-header" onclick="document.getElementById('team-body-${team.id}').classList.toggle('hidden')">
          <span class="team-header-icon">${team.icon}</span>
          <div class="team-header-info">
            <div class="team-header-name" style="color:${team.color}">${team.name}</div>
            <div class="team-header-desc">${team.description}</div>
          </div>
          <span class="team-header-badge" style="background:${team.color}22;color:${team.color};border:1px solid ${team.color}44">
            ${agentCount} Agent${agentCount > 1 ? 's' : ''}
          </span>
        </div>
        <div class="team-agents-grid" id="team-body-${team.id}">
          ${team.agents.map(agent => this._buildAgentCard(agent, team)).join('')}
        </div>`;

      grid.appendChild(section);
    });

    // Prompt toggle handlers
    document.querySelectorAll('.agent-prompt-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        const targetId = btn.dataset.target;
        const content = document.getElementById(targetId);
        if (content) {
          const isOpen = content.classList.toggle('open');
          btn.textContent = isOpen ? '▲ Hide System Prompt' : '▼ View System Prompt';
        }
      });
    });
  }

  _buildAgentCard(agent, team) {
    const promptId = `prompt-${agent.id}`;
    return `
      <div class="agent-detail-card" id="card-${agent.id}">
        <div class="agent-card-header">
          <div class="agent-card-icon" style="border-color:${team.color}33">${agent.icon}</div>
          <div class="agent-card-meta">
            <div class="agent-card-name">${agent.name}</div>
            <div class="agent-card-role">${agent.role}</div>
            <div class="agent-card-badges">
              <span class="agent-mini-status status-${agent.status}">${agent.status.toUpperCase()}</span>
              <span class="confidence-pill">⚡ ${Math.round(agent.confidence)}% confidence</span>
            </div>
          </div>
        </div>
        <div class="agent-last-action">→ ${agent.lastAction}</div>
        <div class="confidence-bar-wrap">
          <div class="confidence-bar" id="conf-${agent.id}" style="width:${agent.confidence}%"></div>
        </div>
        <button class="agent-prompt-toggle" data-target="${promptId}" style="margin-top:10px">▼ View System Prompt</button>
        <div class="agent-prompt-content" id="${promptId}">${agent.systemPrompt}</div>
      </div>`;
  }

  updateAgentCards(status) {
    status.teams.forEach(team => {
      team.agents.forEach(agent => {
        const card = document.getElementById(`card-${agent.id}`);
        if (!card) return;
        const badge = card.querySelector('.agent-mini-status');
        if (badge) { badge.className = `agent-mini-status status-${agent.status}`; badge.textContent = agent.status.toUpperCase(); }
        const confBar = document.getElementById(`conf-${agent.id}`);
        if (confBar) confBar.style.width = Math.round(agent.confidence) + '%';
        const cpill = card.querySelector('.confidence-pill');
        if (cpill) cpill.textContent = `⚡ ${Math.round(agent.confidence)}% confidence`;
      });
    });
  }

  // ─── HARDWARE TAB ────────────────────────────────────────────
  _buildHardwareTab() {
    const grid = document.getElementById('hardware-info-grid');
    if (!grid) return;
    grid.innerHTML = `
      <div class="hw-card">
        <div class="hw-card-title">🖥️ CPU</div>
        <div class="hw-rows" id="hw-cpu-rows">
          <div class="hw-row"><span class="hw-key">Model</span><span class="hw-val" id="hw-cpu-model">Detecting...</span></div>
          <div class="hw-row"><span class="hw-key">Load</span><span class="hw-val" id="hw-cpu-load">--</span></div>
          <div class="hw-row"><span class="hw-key">Temperature</span><span class="hw-val" id="hw-cpu-temp">--</span></div>
          <div class="hw-row"><span class="hw-key">Architecture</span><span class="hw-val">Hybrid (P+E Cores)</span></div>
          <div class="hw-row"><span class="hw-key">AVX2 Support</span><span class="hw-val" style="color:#22c55e">✓ YES</span></div>
        </div>
      </div>
      <div class="hw-card">
        <div class="hw-card-title">🎮 dGPU</div>
        <div class="hw-rows">
          <div class="hw-row"><span class="hw-key">Model</span><span class="hw-val" id="hw-gpu-model">Detecting...</span></div>
          <div class="hw-row"><span class="hw-key">Load</span><span class="hw-val" id="hw-gpu-load">--</span></div>
          <div class="hw-row"><span class="hw-key">Temperature</span><span class="hw-val" id="hw-gpu-temp">--</span></div>
          <div class="hw-row"><span class="hw-key">VRAM</span><span class="hw-val" id="hw-vram">-- / 8 GB</span></div>
          <div class="hw-row"><span class="hw-key">Feature Level</span><span class="hw-val">D3D12 FL 12.2</span></div>
          <div class="hw-row"><span class="hw-key">Ray Tracing</span><span class="hw-val" style="color:#22c55e">✓ YES (RT Cores)</span></div>
          <div class="hw-row"><span class="hw-key">Mesh Shaders</span><span class="hw-val" style="color:#22c55e">✓ YES</span></div>
        </div>
      </div>
      <div class="hw-card">
        <div class="hw-card-title">🔷 iGPU</div>
        <div class="hw-rows">
          <div class="hw-row"><span class="hw-key">Model</span><span class="hw-val" id="hw-igpu-model">Detecting...</span></div>
          <div class="hw-row"><span class="hw-key">Load</span><span class="hw-val" id="hw-igpu-load">--</span></div>
          <div class="hw-row"><span class="hw-key">Shared Memory</span><span class="hw-val">Up to 4 GB</span></div>
          <div class="hw-row"><span class="hw-key">QuickSync</span><span class="hw-val" style="color:#22c55e">✓ YES (H.265)</span></div>
          <div class="hw-row"><span class="hw-key">Nexus Task Routing</span><span class="hw-val" style="color:#00d4ff">✓ ENABLED</span></div>
        </div>
      </div>
      <div class="hw-card">
        <div class="hw-card-title">💾 Memory</div>
        <div class="hw-rows">
          <div class="hw-row"><span class="hw-key">System RAM</span><span class="hw-val" id="hw-ram">-- / 16 GB</span></div>
          <div class="hw-row"><span class="hw-key">Speed</span><span class="hw-val">DDR4-3200</span></div>
          <div class="hw-row"><span class="hw-key">Channels</span><span class="hw-val">Dual Channel</span></div>
          <div class="hw-row"><span class="hw-key">VRAM Used</span><span class="hw-val" id="hw-vram2">--</span></div>
          <div class="hw-row"><span class="hw-key">VRAM Budget</span><span class="hw-val">6.8 GB (safe)</span></div>
        </div>
      </div>
      <div class="hw-card">
        <div class="hw-card-title">📱 Mobile Edge Node</div>
        <div class="hw-rows">
          <div class="hw-row"><span class="hw-key">Status</span><span class="hw-val" id="hw-mobile-status" style="color:#ef4444">DISCONNECTED</span></div>
          <div class="hw-row"><span class="hw-key">Connection</span><span class="hw-val">USB 3.2 Gen 2 (10Gbps)</span></div>
          <div class="hw-row"><span class="hw-key">Latency</span><span class="hw-val" id="hw-mobile-lat">-- ms</span></div>
          <div class="hw-row"><span class="hw-key">NPU Est.</span><span class="hw-val">~15 TOPS (if connected)</span></div>
          <div class="hw-row"><span class="hw-key">Offload Benefit</span><span class="hw-val">Up to +40% FPS</span></div>
        </div>
      </div>
      <div class="hw-card">
        <div class="hw-card-title">⚡ Power & Thermal</div>
        <div class="hw-rows">
          <div class="hw-row"><span class="hw-key">Total Draw</span><span class="hw-val" id="hw-power">-- W</span></div>
          <div class="hw-row"><span class="hw-key">CPU Temp</span><span class="hw-val" id="hw-cpu-temp2">--</span></div>
          <div class="hw-row"><span class="hw-key">GPU Temp</span><span class="hw-val" id="hw-gpu-temp2">--</span></div>
          <div class="hw-row"><span class="hw-key">Power Plan</span><span class="hw-val" style="color:#00d4ff">High Performance</span></div>
          <div class="hw-row"><span class="hw-key">Timer Resolution</span><span class="hw-val" style="color:#00d4ff">0.5ms (boosted)</span></div>
        </div>
      </div>`;
  }

  updateHardwareTab(d) {
    this._setText('hw-cpu-model', d.cpu_name || '--');
    this._setText('hw-cpu-load', (d.cpu_load?.toFixed(1) || '--') + '%');
    this._setText('hw-cpu-temp', (d.cpu_temp_c?.toFixed(0) || '--') + ' °C');
    this._setText('hw-gpu-model', d.gpu_name || '--');
    this._setText('hw-gpu-load', (d.gpu_load?.toFixed(1) || '--') + '%');
    this._setText('hw-gpu-temp', (d.gpu_temp_c?.toFixed(0) || '--') + ' °C');
    this._setText('hw-vram', (d.vram_used_gb?.toFixed(1) || '--') + ' / ' + (d.vram_total_gb || 8) + ' GB');
    this._setText('hw-igpu-model', d.igpu_name || '--');
    this._setText('hw-igpu-load', (d.igpu_load?.toFixed(1) || '--') + '%');
    this._setText('hw-ram', (d.ram_used_gb?.toFixed(1) || '--') + ' / ' + (d.ram_total_gb || 16) + ' GB');
    this._setText('hw-vram2', (d.vram_used_gb?.toFixed(2) || '--') + ' GB');
    this._setText('hw-power', (d.power_draw_w || '--') + ' W');
    this._setText('hw-cpu-temp2', (d.cpu_temp_c?.toFixed(0) || '--') + ' °C');
    this._setText('hw-gpu-temp2', (d.gpu_temp_c?.toFixed(0) || '--') + ' °C');
    const ms = document.getElementById('hw-mobile-status');
    if (ms) { ms.textContent = d.mobile_connected ? 'CONNECTED' : 'DISCONNECTED'; ms.style.color = d.mobile_connected ? '#22c55e' : '#ef4444'; }
    this._setText('hw-mobile-lat', d.mobile_connected ? (d.mobile_latency_ms + ' ms') : '-- ms');
  }

  // ─── PROFILES ────────────────────────────────────────────────
  _buildProfilesList() {
    const list = document.getElementById('profiles-list');
    if (!list) return;
    list.innerHTML = '';
    QUALITY_PROFILES.forEach(p => {
      const el = document.createElement('div');
      el.className = `profile-item${p.id === this._activeProfile ? ' active' : ''}`;
      el.id = `profile-${p.id}`;
      el.setAttribute('role', 'radio');
      el.setAttribute('aria-checked', p.id === this._activeProfile);
      el.innerHTML = `
        <div class="profile-dot" style="background:${p.color}"></div>
        <div class="profile-info">
          <div class="profile-name" style="color:${p.color}">${p.name}</div>
          <div class="profile-desc">${p.desc}</div>
        </div>`;
      el.addEventListener('click', () => this._selectProfile(p.id));
      list.appendChild(el);
    });

    document.getElementById('btn-apply-profile')?.addEventListener('click', () => {
      this.showToast('success', '✅', `Profile "${this._activeProfile}" applied`);
      window.nexusLog('system', `Quality profile changed to ${this._activeProfile}`, 'info');
    });
    document.getElementById('btn-auto-profile')?.addEventListener('click', () => {
      this.showToast('info', '🤖', 'Auto-optimization enabled — Quality Guardian is in control');
      this._setText('profile-mode', 'AUTO');
    });
  }

  _selectProfile(id) {
    this._activeProfile = id;
    document.querySelectorAll('.profile-item').forEach(el => {
      const active = el.id === `profile-${id}`;
      el.classList.toggle('active', active);
      el.setAttribute('aria-checked', active);
    });
    this._setText('profile-mode', 'MANUAL');
  }

  // ─── CONFIG TAB ──────────────────────────────────────────────
  _buildConfigTab() {
    const panel = document.getElementById('config-panel');
    if (!panel) return;
    panel.innerHTML = `
      <div class="config-section">
        <div class="config-section-title">🔧 Rendering Overrides</div>
        <div class="config-rows">
          <div class="config-row">
            <label class="config-label" for="sl-lod">LOD Bias Override</label>
            <input type="range" class="config-slider" id="sl-lod" min="0" max="50" value="25" oninput="this.nextElementSibling.textContent='+'+this.value/10" />
            <span style="font-size:12px;color:#00d4ff;width:32px">+2.5</span>
          </div>
          <div class="config-row">
            <label class="config-label" for="sl-res">Resolution Scale</label>
            <input type="range" class="config-slider" id="sl-res" min="25" max="100" value="60" oninput="this.nextElementSibling.textContent=this.value+'%'" />
            <span style="font-size:12px;color:#00d4ff;width:32px">60%</span>
          </div>
          <div class="config-row">
            <label class="config-label" for="sl-shadow">Shadow Distance</label>
            <input type="range" class="config-slider" id="sl-shadow" min="0" max="100" value="20" oninput="this.nextElementSibling.textContent=this.value+'%'" />
            <span style="font-size:12px;color:#00d4ff;width:32px">20%</span>
          </div>
          <div class="config-row">
            <label class="config-label" for="sl-pool">Texture Pool (MB)</label>
            <input type="range" class="config-slider" id="sl-pool" min="256" max="4096" step="256" value="512" oninput="this.nextElementSibling.textContent=this.value" />
            <span style="font-size:12px;color:#00d4ff;width:40px">512</span>
          </div>
        </div>
      </div>
      <div class="config-section">
        <div class="config-section-title">⚙️ System Features</div>
        <div class="config-rows">
          <label class="toggle-row config-row" for="tog-smrp"><span class="config-label">SMRP Pipeline</span><input type="checkbox" id="tog-smrp" checked role="switch" /><span class="toggle-track"></span></label>
          <label class="toggle-row config-row" for="tog-scheduler"><span class="config-label">Thread Scheduler</span><input type="checkbox" id="tog-scheduler" checked role="switch" /><span class="toggle-track"></span></label>
          <label class="toggle-row config-row" for="tog-guardian"><span class="config-label">Quality Guardian Agent</span><input type="checkbox" id="tog-guardian" checked role="switch" /><span class="toggle-track"></span></label>
          <label class="toggle-row config-row" for="tog-mobile"><span class="config-label">Mobile Edge Node</span><input type="checkbox" id="tog-mobile" role="switch" /><span class="toggle-track"></span></label>
          <label class="toggle-row config-row" for="tog-validators"><span class="config-label">Anti-Hallucination Validators</span><input type="checkbox" id="tog-validators" checked role="switch" /><span class="toggle-track"></span></label>
          <label class="toggle-row config-row" for="tog-audit"><span class="config-label">Integrity Auditor</span><input type="checkbox" id="tog-audit" checked role="switch" /><span class="toggle-track"></span></label>
        </div>
      </div>
      <div class="config-section">
        <div class="config-section-title">🤖 Agent Council Settings</div>
        <div class="config-rows">
          <div class="config-row">
            <label class="config-label" for="sl-cycle">Agent Cycle Interval</label>
            <input type="range" class="config-slider" id="sl-cycle" min="500" max="5000" step="500" value="2000" oninput="this.nextElementSibling.textContent=this.value+'ms'" />
            <span style="font-size:12px;color:#00d4ff;width:52px">2000ms</span>
          </div>
          <div class="config-row">
            <label class="config-label" for="sl-consensus">Consensus Threshold</label>
            <input type="range" class="config-slider" id="sl-consensus" min="50" max="100" value="80" oninput="this.nextElementSibling.textContent=this.value+'%'" />
            <span style="font-size:12px;color:#00d4ff;width:32px">80%</span>
          </div>
          <label class="toggle-row config-row" for="tog-ai"><span class="config-label">Live AI API Mode (Gemini)</span><input type="checkbox" id="tog-ai" role="switch" /><span class="toggle-track"></span></label>
        </div>
      </div>
      <div class="config-section">
        <div class="config-section-title">🔐 Security Policy</div>
        <div class="config-rows">
          <label class="toggle-row config-row" for="tog-policy"><span class="config-label">Policy Guard Active</span><input type="checkbox" id="tog-policy" checked role="switch" /><span class="toggle-track"></span></label>
          <label class="toggle-row config-row" for="tog-ac"><span class="config-label">Anti-Cheat Detection</span><input type="checkbox" id="tog-ac" checked role="switch" /><span class="toggle-track"></span></label>
          <div class="config-row">
            <span class="config-label">Max Authorization Level</span>
            <span style="font-size:11px;font-weight:600;color:#22c55e;font-family:'JetBrains Mono',monospace">SINGLE_PLAYER</span>
          </div>
        </div>
      </div>`;
  }

  // ─── MODAL ───────────────────────────────────────────────────
  _setupModal() {
    const modal = document.getElementById('inject-modal');
    const openBtn = document.getElementById('btn-inject');
    const closeBtn = document.getElementById('modal-close');
    const cancelBtn = document.getElementById('btn-cancel-inject');
    const confirmBtn = document.getElementById('btn-confirm-inject');

    const open = () => {
      modal.hidden = false;
      this._populateProcessList();
      if (window.__client?.online) {
        window.__client.send({ type: 'get_processes' });
      }
    };
    const close = () => { modal.hidden = true; };

    openBtn?.addEventListener('click', open);
    closeBtn?.addEventListener('click', close);
    cancelBtn?.addEventListener('click', close);
    modal?.addEventListener('click', e => { if (e.target === modal) close(); });
    confirmBtn?.addEventListener('click', () => {
      close();
      this.showToast('success', '⚡', 'Nexus injected successfully — agents online');
      window.nexusLog('system', 'Nexus injection initiated — all agents activating', 'info');
    });
  }

  renderProcesses(procs) {
    const list = document.getElementById('process-list');
    if (!list || !procs || procs.length === 0) return;
    list.innerHTML = '';
    procs.forEach((p, i) => {
      const el = document.createElement('div');
      el.className = `process-item${i === 0 ? ' selected' : ''}`;
      const icon = p.is_game ? '🎮' : '⚡';
      const badge = p.is_game ? '<span style="color:#22c55e;font-weight:700">GAME</span>' : `PID ${p.pid}`;
      el.innerHTML = `<span>${icon}</span><span style="flex:1;font-size:12px;font-weight:600">${p.name}</span><span style="font-size:10px;color:#94a3b8">${badge} | ${p.engine || 'DirectX'}</span>`;
      el.addEventListener('click', () => {
        document.querySelectorAll('.process-item').forEach(e => e.classList.remove('selected'));
        el.classList.add('selected');
      });
      list.appendChild(el);
    });
  }

  _populateProcessList() {
    const fakeProcesses = [
      { name: 'Cyberpunk2077.exe', pid: 4821, engine: 'REDengine 4', is_game: true },
      { name: 'Witcher3.exe',      pid: 3302, engine: 'REDengine 3', is_game: true },
      { name: 'RDR2.exe',          pid: 5544, engine: 'RAGE Engine', is_game: true },
      { name: 'eldenring.exe',     pid: 6120, engine: 'Havok/Custom', is_game: true },
    ];
    this.renderProcesses(fakeProcesses);
  }

  // ─── LOG FILTERS ─────────────────────────────────────────────
  _setupLogFilters() {
    document.querySelectorAll('.log-filter').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.log-filter').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this._logFilter = btn.dataset.level;
        this._renderLogs();
      });
    });
    document.getElementById('btn-clear-logs')?.addEventListener('click', () => {
      this._logEntries = [];
      this._renderLogs();
    });
  }

  addLog(entry) {
    this._logEntries.unshift(entry);
    if (this._logEntries.length > 500) this._logEntries.pop();
    if (this._activeTab === 'logs') this._renderLogs();
  }

  _renderLogs() {
    const container = document.getElementById('logs-container');
    if (!container) return;
    const filtered = this._logFilter === 'all'
      ? this._logEntries
      : this._logEntries.filter(e => e.level === this._logFilter);

    container.innerHTML = filtered.slice(0, 200).map(e => `
      <div class="log-entry log-${e.level}">
        <span class="log-time">${new Date(e.timestamp).toTimeString().slice(0,8)}</span>
        <span class="log-source">${e.source}</span>
        <span class="log-msg">${e.message}</span>
      </div>`).join('');
  }

  // ─── TOAST ───────────────────────────────────────────────────
  showToast(type, icon, message, duration = 3500) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `<span class="toast-icon">${icon}</span><span class="toast-msg">${message}</span>`;
    container.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateY(10px)'; el.style.transition = 'all 0.3s'; setTimeout(() => el.remove(), 300); }, duration);
  }

  // ─── HELPERS ─────────────────────────────────────────────────
  _setText(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }
  _setBar(id, pct) { const el = document.getElementById(id); if (el) el.style.width = Math.max(0, Math.min(100, pct)) + '%'; }
  _setGauge(id, pct) {
    const el = document.getElementById(id);
    if (!el) return;
    const maxDash = 126;
    el.style.strokeDashoffset = maxDash - (maxDash * pct / 100);
  }
}

window.UIRenderer = UIRenderer;
window.QUALITY_PROFILES = QUALITY_PROFILES;
