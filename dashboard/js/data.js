/**
 * data.js — shared constants and utility functions
 */

// Formatting helpers
window.fmt = {
  fps: (v) => v ? Math.round(v) + ' FPS' : '--',
  ms:  (v) => v ? v.toFixed(1) + ' ms' : '--',
  pct: (v) => v ? v.toFixed(1) + '%' : '--',
  gb:  (v) => v ? v.toFixed(2) + ' GB' : '--',
  temp:(v) => v ? v.toFixed(0) + ' °C' : '--',
  w:   (v) => v ? Math.round(v) + ' W' : '--',
};

// Color mapping for values
window.colorScale = {
  fps: (v) => v > 60 ? '#22c55e' : v > 30 ? '#f59e0b' : '#ef4444',
  temp: (v) => v > 85 ? '#ef4444' : v > 70 ? '#f59e0b' : '#22c55e',
  load: (v) => v > 90 ? '#ef4444' : v > 70 ? '#f59e0b' : '#22c55e',
  vram: (v, total) => (v/total) > 0.9 ? '#ef4444' : (v/total) > 0.7 ? '#f59e0b' : '#22c55e',
};
