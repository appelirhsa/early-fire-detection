'use strict';
/* Helpers shared by the incidents, report and health pages. */

const $ = id => document.getElementById(id);
const TW = 32;
const TH = 24;

function esc(v) {
  return String(v ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function isNum(v) {
  return typeof v === 'number' && Number.isFinite(v);
}

function deg(v, digits = 1) {
  return isNum(v) ? `${v.toFixed(digits)} °C` : '—';
}

/* Unix seconds -> "31 Oct 2026, 18:42:07" */
function fmtDateTime(sec) {
  if (!isNum(sec)) return '—';
  const d = new Date(sec * 1000);
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) +
    ', ' + d.toLocaleTimeString(undefined, { hour12: false });
}

function fmtClock(sec, withSeconds = true) {
  if (!isNum(sec)) return '—';
  return new Date(sec * 1000).toLocaleTimeString(undefined, withSeconds
    ? { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }
    : { hour: '2-digit', minute: '2-digit', hour12: false });
}

function fmtDur(s) {
  if (!isNum(s)) return '—';
  s = Math.max(0, s);
  if (s < 60) return `${s < 10 ? s.toFixed(1) : Math.round(s)} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min`;
  return `${Math.floor(s / 86400)} d ${Math.round((s % 86400) / 3600)} h`;
}

function fmtBytes(b) {
  if (!isNum(b)) return '—';
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}

function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function jet(t) {
  const x = Math.max(0, Math.min(1, t));
  const c = shift => Math.round(255 * Math.max(0, Math.min(1, 1.5 - Math.abs(4 * x - shift))));
  return [c(3), c(2), c(1)];
}

/* Draw a 32x24 thermal frame (bilinear, JET colours) with a crosshair on the hottest pixel. */
function drawHeatmap(canvas, pixels, lo, hi) {
  const ctx = canvas.getContext('2d', { alpha: false });
  const w = canvas.width;
  const h = canvas.height;
  const img = ctx.createImageData(w, h);
  const span = Math.max(1, hi - lo);
  const val = (x, y) => {
    const v = pixels[y * TW + x];
    return isNum(v) && v > -200 ? v : null;
  };
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const fx = x * (TW - 1) / (w - 1);
      const fy = y * (TH - 1) / (h - 1);
      const x0 = Math.floor(fx), y0 = Math.floor(fy);
      const x1 = Math.min(TW - 1, x0 + 1), y1 = Math.min(TH - 1, y0 + 1);
      const dx = fx - x0, dy = fy - y0;
      let sum = 0, wt = 0;
      for (const [sx, sy, k] of [[x0, y0, (1 - dx) * (1 - dy)], [x1, y0, dx * (1 - dy)],
        [x0, y1, (1 - dx) * dy], [x1, y1, dx * dy]]) {
        const v = val(sx, sy);
        if (v !== null) { sum += v * k; wt += k; }
      }
      const rgb = wt ? jet((sum / wt - lo) / span) : [110, 115, 120];
      const o = (y * w + x) * 4;
      img.data[o] = rgb[0]; img.data[o + 1] = rgb[1]; img.data[o + 2] = rgb[2]; img.data[o + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);

  let best = -Infinity, idx = -1;
  pixels.forEach((v, i) => { if (isNum(v) && v > best) { best = v; idx = i; } });
  if (idx >= 0) {
    const hx = ((idx % TW) + 0.5) * w / TW;
    const hy = (Math.floor(idx / TW) + 0.5) * h / TH;
    ctx.beginPath();
    ctx.arc(hx, hy, 9, 0, Math.PI * 2);
    ctx.moveTo(hx - 14, hy); ctx.lineTo(hx + 14, hy);
    ctx.moveTo(hx, hy - 14); ctx.lineTo(hx, hy + 14);
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.stroke();
    ctx.strokeStyle = '#17202a'; ctx.lineWidth = 0.8; ctx.stroke();
  }
  return idx;
}

/* Describe a hotspot position in plain words (3 x 3 zones of the camera view). */
function zoneName(index) {
  if (index < 0) return '—';
  const x = index % TW, y = Math.floor(index / TW);
  const col = x < TW / 3 ? 'left' : x < 2 * TW / 3 ? 'centre' : 'right';
  const row = y < TH / 3 ? 'upper' : y < 2 * TH / 3 ? 'middle' : 'lower';
  const name = row === 'middle' && col === 'centre' ? 'centre' : `${row} ${col}`;
  return `${name} (pixel ${x}, ${y})`;
}

/*
 * Time-series chart: points [{t (s), max, amb}], optional markers [{t, label, color}]
 * and dashed horizontal thresholds [{v, label, color}].
 */
function drawTimeChart(canvas, { points, start, end, markers = [], thresholds = [], shade = null }) {
  const box = canvas.getBoundingClientRect();
  if (!box.width || !box.height) return;
  const ratio = Math.min(devicePixelRatio || 1, 2);
  canvas.width = Math.round(box.width * ratio);
  canvas.height = Math.round(box.height * ratio);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

  const W = box.width, H = box.height;
  const L = 52, R = W - 14, T = 22, B = H - 28;
  const font = getComputedStyle(document.body).fontFamily;
  const grid = cssVar('--chart-grid', '#ececea');
  const label = cssVar('--chart-label', '#66665f');
  ctx.clearRect(0, 0, W, H);
  ctx.font = `12px ${font}`;

  const vals = points.flatMap(p => [p.max, p.amb]).filter(isNum)
    .concat(thresholds.map(th => th.v));
  let lo = vals.length ? Math.min(...vals) - 2 : 0;
  let hi = vals.length ? Math.max(...vals) + 2 : 100;
  if (hi - lo < 10) { const m = (hi + lo) / 2; lo = m - 5; hi = m + 5; }
  const step = [1, 2, 5, 10, 20, 25, 50, 100, 200].find(s => (hi - lo) / s <= 5) || 500;
  lo = Math.floor(lo / step) * step;
  hi = Math.ceil(hi / step) * step;
  const span = Math.max(1, end - start);
  const x = t => L + (t - start) / span * (R - L);
  const y = v => B - (v - lo) / (hi - lo) * (B - T);

  if (shade) {
    ctx.fillStyle = cssVar('--fire-bg', 'rgba(220,60,40,.08)');
    const x0 = Math.max(L, x(shade.start)), x1 = Math.min(R, x(shade.end));
    if (x1 > x0) ctx.fillRect(x0, T, x1 - x0, B - T);
  }

  ctx.textAlign = 'right';
  for (let v = lo; v <= hi + 1e-9; v += step) {
    const yy = Math.round(y(v)) + 0.5;
    ctx.strokeStyle = grid; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(L, yy); ctx.lineTo(R, yy); ctx.stroke();
    ctx.fillStyle = label; ctx.fillText(`${v} °C`, L - 8, yy + 4);
  }

  const steps = [5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 21600, 43200, 86400];
  const maxTicks = Math.max(2, Math.floor((R - L) / 90));
  const tick = steps.find(s => span / s <= maxTicks) || 86400;
  const tz = -new Date(start * 1000).getTimezoneOffset() * 60;
  ctx.textAlign = 'center';
  for (let t = Math.ceil((start + tz) / tick) * tick - tz; t <= end; t += tick) {
    const xx = Math.round(x(t)) + 0.5;
    ctx.strokeStyle = grid;
    ctx.beginPath(); ctx.moveTo(xx, T); ctx.lineTo(xx, B); ctx.stroke();
    ctx.fillStyle = label; ctx.fillText(fmtClock(t, tick < 60), xx, B + 18);
  }

  ctx.save();
  ctx.setLineDash([5, 4]);
  ctx.textAlign = 'left';
  for (const th of thresholds) {
    if (th.v <= lo || th.v >= hi) continue;
    const yy = Math.round(y(th.v)) + 0.5;
    ctx.strokeStyle = th.color; ctx.globalAlpha = 0.7;
    ctx.beginPath(); ctx.moveTo(L, yy); ctx.lineTo(R, yy); ctx.stroke();
    ctx.globalAlpha = 1; ctx.fillStyle = th.color; ctx.fillText(th.label, L + 6, yy - 5);
  }
  ctx.restore();

  for (const [key, colour] of [['max', cssVar('--chart-thermal', '#d4561a')],
    ['amb', cssVar('--chart-ambient', '#2f6fb2')]]) {
    ctx.strokeStyle = colour; ctx.lineWidth = 2; ctx.lineJoin = 'round';
    ctx.beginPath();
    let prev = null;
    for (const p of points) {
      if (!isNum(p[key])) { prev = null; continue; }
      if (prev === null || p.t - prev > 15) ctx.moveTo(x(p.t), y(p[key]));
      else ctx.lineTo(x(p.t), y(p[key]));
      prev = p.t;
    }
    ctx.stroke();
  }

  ctx.font = `11px ${font}`;
  let lastLabelX = -Infinity, row = 0;
  for (const m of markers.filter(m => isNum(m.t) && m.t >= start && m.t <= end).sort((a, b) => a.t - b.t)) {
    const xx = Math.round(x(m.t)) + 0.5;
    ctx.strokeStyle = m.color; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(xx, T); ctx.lineTo(xx, B); ctx.stroke();
    row = xx - lastLabelX < 90 ? (row + 1) % 2 : 0;
    ctx.fillStyle = m.color;
    ctx.textAlign = xx > R - 60 ? 'right' : 'left';
    ctx.fillText(m.label, xx + (ctx.textAlign === 'right' ? -4 : 4), row ? T + 12 : T - 8);
    lastLabelX = xx;
  }
}