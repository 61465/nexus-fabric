/**
 * Chart module — real-time frametime chart using Chart.js
 */

class NexusChart {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.chart = null;
  }

  init() {
    if (!this.canvas) return;
    const ctx = this.canvas.getContext('2d');

    // Create gradient fill
    const grad = ctx.createLinearGradient(0, 0, 0, 200);
    grad.addColorStop(0, 'rgba(0,212,255,0.3)');
    grad.addColorStop(1, 'rgba(0,212,255,0.0)');

    this.chart = new Chart(ctx, {
      type: 'line',
      data: {
        datasets: [
          {
            label: 'Frame Time (ms)',
            data: [],
            borderColor: '#00d4ff',
            backgroundColor: grad,
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.4,
            fill: true,
            order: 1,
          },
          {
            label: '30 FPS Budget (33.3ms)',
            data: [],
            borderColor: 'rgba(245,158,11,0.6)',
            borderWidth: 1,
            borderDash: [4, 4],
            pointRadius: 0,
            fill: false,
            order: 2,
          },
          {
            label: '60 FPS Budget (16.6ms)',
            data: [],
            borderColor: 'rgba(168,85,247,0.6)',
            borderWidth: 1,
            borderDash: [4, 4],
            pointRadius: 0,
            fill: false,
            order: 3,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        animation: { duration: 0 },
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: 'rgba(13,21,38,0.95)',
            borderColor: 'rgba(0,212,255,0.3)',
            borderWidth: 1,
            titleColor: '#94a3b8',
            bodyColor: '#e2e8f0',
            callbacks: {
              label: (c) => ` ${c.dataset.label}: ${c.parsed.y?.toFixed(1)} ms`,
            },
          },
        },
        scales: {
          x: {
            type: 'time',
            time: { unit: 'second', displayFormats: { second: 'HH:mm:ss' } },
            grid: { color: 'rgba(255,255,255,0.04)' },
            ticks: { color: '#475569', font: { family: 'JetBrains Mono', size: 10 }, maxTicksLimit: 6 },
          },
          y: {
            min: 0,
            suggestedMax: 50,
            grid: { color: 'rgba(255,255,255,0.04)' },
            ticks: {
              color: '#475569', font: { family: 'JetBrains Mono', size: 10 },
              callback: (v) => v + 'ms',
            },
          },
        },
      },
    });
  }

  update(history) {
    if (!this.chart || !history?.frametime) return;
    const now = Date.now();

    this.chart.data.datasets[0].data = history.frametime.map(p => ({ x: p.x, y: p.y }));

    // Reference lines — use same time range
    if (history.frametime.length > 0) {
      const times = history.frametime.map(p => p.x);
      const first = times[0], last = times[times.length - 1];
      this.chart.data.datasets[1].data = [{ x: first, y: 33.3 }, { x: last, y: 33.3 }];
      this.chart.data.datasets[2].data = [{ x: first, y: 16.6 }, { x: last, y: 16.6 }];
    }

    this.chart.update('none');
  }
}

window.NexusChart = NexusChart;
