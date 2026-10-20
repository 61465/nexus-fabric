/**
 * Hardware telemetry simulation — reads real data via WebSocket
 * when backend is available, falls back to realistic simulation.
 */

class HardwareTelemetry {
  constructor() {
    this.ws = null;
    this.simMode = true;
    this.data = this._defaultData();
    this.listeners = [];
    this._simState = { fpsBase: 47, frametimeBase: 21, trend: 0 };
    this._history = { frametime: [] };
  }

  start() {
    this._tryWebSocket();
    this._simTick = setInterval(() => this._simulate(), 300);
  }

  stop() {
    if (this._simTick) clearInterval(this._simTick);
    if (this.ws) this.ws.close();
  }

  on(event, fn) { this.listeners.push({ event, fn }); }
  emit(event, data) { this.listeners.filter(l => l.event === event).forEach(l => l.fn(data)); }

  getData() { return this.data; }
  getHistory() { return this._history; }

  _tryWebSocket() {
    // Managed centrally by NexusBackendClient in main.js
  }

  _handleServerData(msg) {
    const d = msg.data || msg;
    this.data = { ...this.data, ...d };
    if (d.frametime_ms) this._pushHistory(d.frametime_ms);
    this.emit('update', this.data);
  }

  _simulate() {
    const s = this._simState;

    // Gradual trend changes
    s.trend += (Math.random() - 0.5) * 0.3;
    s.trend = Math.max(-3, Math.min(3, s.trend));
    s.fpsBase = Math.max(18, Math.min(120, s.fpsBase + s.trend * 0.1 + (Math.random() - 0.5) * 2));

    const fps = Math.round(s.fpsBase + (Math.random() - 0.5) * 4);
    const frametime = parseFloat((1000 / fps + (Math.random() - 0.5) * 2).toFixed(1));
    const cpuLoad = Math.min(98, Math.max(20, 45 + s.trend * 5 + (Math.random() - 0.5) * 15));
    const gpuLoad = Math.min(99, Math.max(30, 70 + s.trend * 8 + (Math.random() - 0.5) * 10));
    const vramUsed = Math.min(7.8, Math.max(1.2, 3.4 + s.trend * 0.2 + (Math.random() - 0.5) * 0.3));
    const cpuTemp = Math.min(98, Math.max(35, 58 + cpuLoad * 0.3 + (Math.random() - 0.5) * 3));
    const gpuTemp = Math.min(95, Math.max(40, 65 + gpuLoad * 0.15 + (Math.random() - 0.5) * 2));
    const ramUsed = Math.min(15, Math.max(4, 8.2 + (Math.random() - 0.5) * 0.5));
    const powerDraw = Math.round(gpuLoad * 1.8 + cpuLoad * 0.5 + 20);
    const fps1pct = Math.round(fps * (0.55 + Math.random() * 0.15));
    const avgFt = parseFloat((frametime * (1 + Math.random() * 0.1)).toFixed(1));

    this.data = {
      fps, frametime_ms: frametime, fps_1pct: fps1pct, frametime_avg: avgFt,
      cpu_load: parseFloat(cpuLoad.toFixed(1)),
      gpu_load: parseFloat(gpuLoad.toFixed(1)),
      vram_used_gb: parseFloat(vramUsed.toFixed(2)),
      vram_total_gb: 8,
      cpu_temp_c: parseFloat(cpuTemp.toFixed(1)),
      gpu_temp_c: parseFloat(gpuTemp.toFixed(1)),
      ram_used_gb: parseFloat(ramUsed.toFixed(1)),
      ram_total_gb: 16,
      power_draw_w: powerDraw,
      igpu_load: parseFloat((Math.random() * 40 + 10).toFixed(1)),
      mobile_connected: false,
      mobile_latency_ms: null,
      mobile_load: null,
      nexus_score: this._computeNexusScore({ fps, cpuLoad, gpuLoad, vramUsed }),
      cpu_name: 'Intel Core i5-12400F',
      gpu_name: 'NVIDIA RTX 3060',
      igpu_name: 'Intel UHD 730',
      detected_game: 'Cyberpunk 2077',
      detected_engine: 'REDengine 4',
      bottleneck: gpuLoad > 85 ? 'GPU_COMPUTE' : cpuLoad > 80 ? 'CPU_MAIN' : 'BALANCED',
      active_profile: 'PERFORMANCE',
      sim_mode: true,
    };

    this._pushHistory(frametime);
    this.emit('update', this.data);
  }

  _pushHistory(ft) {
    this._history.frametime.push({ x: Date.now(), y: ft });
    if (this._history.frametime.length > 150) this._history.frametime.shift();
  }

  _computeNexusScore({ fps, cpuLoad, gpuLoad, vramUsed }) {
    const fpsScore = Math.min(10, fps / 12);
    const efficiencyScore = 10 - (cpuLoad + gpuLoad) / 20;
    const memScore = Math.max(0, 10 - vramUsed);
    return parseFloat(((fpsScore * 0.5 + efficiencyScore * 0.3 + memScore * 0.2)).toFixed(1));
  }

  _defaultData() {
    return {
      fps: 0, frametime_ms: 0, fps_1pct: 0, frametime_avg: 0,
      cpu_load: 0, gpu_load: 0, vram_used_gb: 0, vram_total_gb: 8,
      cpu_temp_c: 0, gpu_temp_c: 0, ram_used_gb: 0, ram_total_gb: 16,
      power_draw_w: 0, igpu_load: 0,
      mobile_connected: false,
      cpu_name: 'Detecting...', gpu_name: 'Detecting...', igpu_name: 'Detecting...',
      nexus_score: 0, bottleneck: 'UNKNOWN', active_profile: 'BALANCED',
    };
  }
}

window.HardwareTelemetry = HardwareTelemetry;
