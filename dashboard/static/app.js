'use strict';

const $ = id => document.getElementById(id);
const W = 32;
const H = 24;
const STALE_MS = 6000;

const app = {
  socket: null,
  connected: false,
  retryMs: 1000,
  frame: null,
  frameTime: 0,
  ambientTime: 0,
  telemetryTime: 0,
  state: 'UNKNOWN',
  suppression: null,
  silenced: false,
  scaleMin: 20,
  scaleMax: 100,
  events: [],
  audioContext: null,
  oscillator: null,
  gain: null,
  toneTimer: null,
  audioEnabled: false,
  rorAlarm: false
};

const thermalCanvas = $('thermalCanvas');
const thermalCtx = thermalCanvas.getContext('2d', {alpha: false});
const trendCanvas = $('trendCanvas');
const trendCtx = trendCanvas.getContext('2d');

const image = thermalCtx.createImageData(
  thermalCanvas.width,
  thermalCanvas.height
);

function finiteTemperature(v) {
  return typeof v === 'number' && Number.isFinite(v) && v > -200;
}

function degrees(v) {
  return finiteTemperature(v) ? v.toFixed(1) : '—';
}

function localTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleString(undefined, {hour12: false});
}

function timestamp(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 0 : date.getTime();
}

function recent(ms) {
  return ms > 0 &&
    Date.now() - ms <= STALE_MS &&
    Date.now() >= ms - 5000;
}

function setHealth(id, live) {
  const el = $(id);
  el.textContent = live ? 'Online' : 'No recent data';
  el.className = `status ${live ? 'status-on' : 'status-off'}`;
}

/*
 * JET-style colour mapping.
 * Temperatures are interpolated before assigning colours.
 */
function jet(t) {
  const x = Math.max(0, Math.min(1, t));

  const component = shift =>
    Math.round(
      255 * Math.max(
        0,
        Math.min(1, 1.5 - Math.abs(4 * x - shift))
      )
    );

  return [component(3), component(2), component(1)];
}

function interpolatePixel(pixels, x, y) {
  const x0 = Math.floor(x);
  const y0 = Math.floor(y);
  const x1 = Math.min(W - 1, x0 + 1);
  const y1 = Math.min(H - 1, y0 + 1);
  const dx = x - x0;
  const dy = y - y0;

  const samples = [
    [x0, y0, (1 - dx) * (1 - dy)],
    [x1, y0, dx * (1 - dy)],
    [x0, y1, (1 - dx) * dy],
    [x1, y1, dx * dy]
  ];

  let sum = 0;
  let weight = 0;

  for (const [sx, sy, w] of samples) {
    const value = pixels[sy * W + sx];

    if (finiteTemperature(value)) {
      sum += value * w;
      weight += w;
    }
  }

  return weight ? sum / weight : null;
}

function drawThermal() {
  if (!app.frame) return;

  const pixels = app.frame.pixels;
  const outW = thermalCanvas.width;
  const outH = thermalCanvas.height;
  const span = app.scaleMax - app.scaleMin;

  for (let y = 0; y < outH; y++) {
    for (let x = 0; x < outW; x++) {
      const v = interpolatePixel(
        pixels,
        x * (W - 1) / (outW - 1),
        y * (H - 1) / (outH - 1)
      );

      const rgb = v === null
        ? [110, 115, 120]
        : jet((v - app.scaleMin) / span);

      const offset = (y * outW + x) * 4;

      image.data[offset] = rgb[0];
      image.data[offset + 1] = rgb[1];
      image.data[offset + 2] = rgb[2];
      image.data[offset + 3] = 255;
    }
  }

  thermalCtx.putImageData(image, 0, 0);

  let hottest = -Infinity;
  let index = -1;

  pixels.forEach((v, i) => {
    if (finiteTemperature(v) && v > hottest) {
      hottest = v;
      index = i;
    }
  });

  if (index >= 0) {
    const hx = ((index % W) + .5) * outW / W;
    const hy = (Math.floor(index / W) + .5) * outH / H;

    thermalCtx.strokeStyle = '#fff';
    thermalCtx.lineWidth = 1.5;
    thermalCtx.beginPath();
    thermalCtx.moveTo(hx - 10, hy);
    thermalCtx.lineTo(hx + 10, hy);
    thermalCtx.moveTo(hx, hy - 10);
    thermalCtx.lineTo(hx, hy + 10);
    thermalCtx.stroke();

    thermalCtx.strokeStyle = '#17202a';
    thermalCtx.lineWidth = .6;
    thermalCtx.stroke();

    $('hotspot').textContent =
      `X ${index % W}, Y ${Math.floor(index / W)}`;
  }
}

/* Read a colour from the active theme (style.css custom properties). */
function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/* ---------------------------------------------------------------------------
 * Temperature history — stored on the server, so it survives page refreshes.
 * The operator picks the time range; "last N" ranges follow live data.
 * ------------------------------------------------------------------------- */
const HIST_TICK_STEPS_S = [10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200,
  10800, 21600, 43200, 86400, 172800, 604800];

const hist = {
  mode: 'relative',   // 'relative' = last `span` seconds (live); 'absolute' = fixed from/to
  span: 3600,         // seconds
  start: 0,           // ms (absolute mode)
  end: 0,             // ms (absolute mode)
  bucketMs: 1000,
  points: [],         // { t (ms), max, amb }
  earliest: null,
  loading: false,
  error: '',
  hoverX: null,
  lastFetch: 0,
  reqId: 0,
  customOpen: false
};

function storeGet(key) {
  try { return localStorage.getItem(key); } catch (e) { return null; }
}

function storeSet(key, value) {
  try { localStorage.setItem(key, value); } catch (e) { /* storage blocked */ }
}

function histWindow() {
  if (hist.mode === 'relative') {
    const end = Date.now();
    return [end - hist.span * 1000, end];
  }
  return [hist.start, hist.end];
}

function histRefreshMs() {
  return Math.min(300000, Math.max(5000, hist.span * 1000 / 100));
}

function fmtTime(ms, withSeconds) {
  return new Date(ms).toLocaleTimeString(undefined, withSeconds
    ? { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }
    : { hour: '2-digit', minute: '2-digit', hour12: false });
}

function fmtDate(ms) {
  return new Date(ms).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

function fmtFull(ms) {
  return `${fmtDate(ms)}, ${fmtTime(ms, true)}`;
}

function fmtTick(ms, spanMs) {
  if (spanMs <= 15 * 60e3) return fmtTime(ms, true);
  if (spanMs <= 36 * 3600e3) return fmtTime(ms, false);
  if (spanMs <= 8 * 86400e3) return `${fmtDate(ms)} ${fmtTime(ms, false)}`;
  return fmtDate(ms);
}

function fmtDuration(s) {
  if (s < 90) return `${Math.round(s)} s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  if (s < 172800) return `${+(s / 3600).toFixed(1)} h`;
  return `${+(s / 86400).toFixed(1)} days`;
}

function toLocalInput(ms) {
  const d = new Date(ms - new Date(ms).getTimezoneOffset() * 60000);
  return d.toISOString().slice(0, 16);
}

function updateHistStatus() {
  const [start, end] = histWindow();
  let text;
  if (hist.error) {
    text = hist.error;
  } else if (hist.loading && !hist.points.length) {
    text = 'Loading history…';
  } else {
    text = `${fmtFull(start)} – ${hist.mode === 'relative' ? 'now' : fmtFull(end)}` +
      ` · ${hist.points.length} points, one per ${fmtDuration(hist.bucketMs / 1000)}`;
    if (hist.earliest) text += ` · stored since ${fmtFull(hist.earliest)}`;
  }
  $('histStatus').textContent = text;
}

async function loadHistory() {
  const [start, end] = histWindow();
  const width = trendCanvas.getBoundingClientRect().width || 800;
  const points = Math.max(100, Math.min(1000, Math.round(width)));
  const id = ++hist.reqId;
  hist.loading = true;
  hist.error = '';
  updateHistStatus();
  drawTrend();

  try {
    const r = await fetch(
      `/api/history?start=${start / 1000}&end=${end / 1000}&points=${points}`,
      { cache: 'no-store' }
    );
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    if (id !== hist.reqId) return;          // a newer request replaced this one
    hist.points = d.points.map(p => ({ t: p.t * 1000, max: p.max, amb: p.amb }));
    hist.bucketMs = d.bucket_s * 1000;
    hist.earliest = d.earliest ? d.earliest * 1000 : null;
  } catch (err) {
    if (id !== hist.reqId) return;
    hist.error = `Could not load history (${err.message}).`;
  }

  hist.loading = false;
  hist.lastFetch = Date.now();
  updateHistStatus();
  drawTrend();
}

/* Live frames extend a "last N" range immediately; the server re-condenses it periodically. */
function addLivePoint(t, max, amb) {
  if (hist.mode !== 'relative') return;
  hist.points.push({ t, max, amb });
  const cutoff = Date.now() - hist.span * 1000;
  while (hist.points.length && hist.points[0].t < cutoff) hist.points.shift();
  drawTrend();
}

function tickHistory() {
  if (hist.mode !== 'relative') return;
  drawTrend();
  if (!hist.loading && Date.now() - hist.lastFetch > histRefreshMs()) loadHistory();
}

function setRangeButtons() {
  document.querySelectorAll('#histRanges button').forEach(b => {
    const pressed = b.dataset.span === 'custom'
      ? hist.customOpen || hist.mode === 'absolute'
      : !hist.customOpen && hist.mode === 'relative' && b.dataset.span === String(hist.span);
    b.setAttribute('aria-pressed', String(pressed));
  });
  $('histCustom').hidden = !(hist.customOpen || hist.mode === 'absolute');
}

function initHistory() {
  const saved = Number(storeGet('efd-history-span'));
  if (Number.isFinite(saved) && saved > 0) hist.span = saved;
  setRangeButtons();
  loadHistory();
}

function ingestFrame(data) {
  if (!Array.isArray(data.pixels) ||
      data.pixels.length !== W * H) {
    return;
  }

  const valid = data.pixels.filter(finiteTemperature);
  if (!valid.length) return;

  app.frame = data;
  app.frameTime = timestamp(data.received_at);
  $('thermalPlaceholder').hidden = true;

  const max = Math.max(...valid);
  const min = Math.min(...valid);
  const mean = valid.reduce((a, b) => a + b, 0) / valid.length;

  $('maxTemp').textContent = degrees(max);
  $('minTemp').textContent = `${degrees(min)} °C`;
  $('meanTemp').textContent = `${degrees(mean)} °C`;
  $('validPixels').textContent = `${valid.length} / 768`;
  $('frameSeq').textContent = String(data.sequence ?? '—');
  $('frameTime').textContent = localTime(data.received_at);

  if (data.ambient_c != null) {
    updateAmbient(data.ambient_c, data.received_at);
  }

  updateRateOfRise(data);

  if (recent(app.frameTime)) {
    addLivePoint(
      app.frameTime,
      max,
      finiteTemperature(data.ambient_c) ? data.ambient_c : null
    );
  }

  drawThermal();
  updateHealth();
}

/* Rate-of-rise alarm (computed by the server from the stored readings). */
function updateRateOfRise(data) {
  const rate = data.ror_c_per_min;
  const limit = data.ror_threshold;
  const alarm = Boolean(data.ror_alarm);
  app.rorAlarm = alarm;

  $('rorValue').textContent = Number.isFinite(rate) ? rate.toFixed(1) : '—';
  $('rorStat').className = 'stat-value' + (alarm ? ' is-warning' : '');
  if (Number.isFinite(limit)) {
    $('rorLimit').textContent = `Alarm above ${limit} °C/min`;
  }

  $('rorBanner').hidden = !alarm || app.state === 'FIRE';
  if (alarm) {
    $('rorBannerText').textContent =
      `The hottest point is rising ${Number.isFinite(rate) ? rate.toFixed(1) : '?'} °C/min ` +
      `(limit ${limit} °C/min), before the fixed fire threshold is reached. Investigate now.`;
  }
  setIncident(data.incident_id);
}

function setIncident(id) {
  const link = $('incidentLink');
  if (id) {
    link.textContent = `#${id} in progress →`;
    link.href = `/incidents/report?id=${id}`;
  } else {
    link.textContent = 'None';
    link.href = '/incidents';
  }
  $('rorIncident').hidden = !id;
  if (id) $('rorIncident').href = `/incidents/report?id=${id}`;
}

function updateAmbient(value, receivedAt) {
  app.ambientTime = timestamp(receivedAt);

  $('ambientTemp').textContent = degrees(value);
  $('ambientLarge').textContent = degrees(value);
  $('ambientTime').textContent = localTime(receivedAt);

  updateHealth();
}

function ingestTelemetry(data) {
  const previous = app.state;

  app.state = data.state || 'UNKNOWN';
  app.telemetryTime = timestamp(data.received_at);
  app.suppression = Boolean(data.suppression_active);

  $('telemetryTime').textContent = localTime(data.received_at);

  $('classificationSource').textContent =
    `Reported by ${data.classification_source || 'firmware'} · ` +
    'not independently verified by dashboard';

  $('suppression').textContent = app.suppression
    ? 'ACTIVE'
    : 'INACTIVE';

  if (data.ambient_c != null || !app.ambientTime) {
    updateAmbient(data.ambient_c, data.received_at);
  }

  if ('incident_id' in data) setIncident(data.incident_id);
  $('rorBanner').hidden = !app.rorAlarm || app.state === 'FIRE';

  if (previous !== 'FIRE' && app.state === 'FIRE') {
    app.silenced = false;
  }

  if (previous === 'FIRE' && app.state !== 'FIRE') {
    app.silenced = false;
  }

  updateAlarm();
  updateHealth();
}

/* Alarm state is based on telemetry reported by the device. */
function updateAlarm() {
  const fire = app.state === 'FIRE';

  document.body.classList.toggle('fire-active', fire);
  $('fireBanner').hidden = !fire;

  $('systemState').textContent = app.state;
  $('systemState').className = 'stat-value' + (
    fire ? ' is-fire' : app.state === 'WARNING' ? ' is-warning' : ''
  );

  const condition = $('alarmCondition');

  condition.className =
    `alarm-condition ${
      fire ? 'fire' : app.state === 'WARNING' ? 'warning' : ''
    }`;

  condition.textContent = fire
    ? 'FIRE ALARM ACTIVE'
    : app.state === 'WARNING'
      ? 'WARNING CONDITION'
      : app.state === 'NORMAL'
        ? 'Normal monitoring'
        : 'Condition unknown';

  $('alarmMessage').textContent = fire
    ? 'The sensing unit has reported FIRE. Audible alarm remains active ' +
      'until silenced in this browser or the condition clears.'
    : app.state === 'WARNING'
      ? 'The sensing unit has reported an abnormal thermal condition.'
      : app.state === 'NORMAL'
        ? 'No active fire condition reported by the sensing unit.'
        : 'Awaiting valid device telemetry.';

  $('killAlarm').disabled = !fire || app.silenced;

  $('silenceStatus').textContent = fire && app.silenced
    ? 'SILENCED LOCALLY'
    : fire
      ? 'NOT SILENCED'
      : 'NOT APPLICABLE';

  if (fire && !app.silenced && app.audioEnabled) {
    startAlarmTone();
  } else {
    stopAlarmTone();
  }
}

/* Web Audio requires an operator gesture before playback. */
async function enableAudio() {
  try {
    if (!app.audioContext) {
      app.audioContext = new (
        window.AudioContext || window.webkitAudioContext
      )();

      app.oscillator = app.audioContext.createOscillator();
      app.gain = app.audioContext.createGain();

      app.oscillator.type = 'sine';
      app.oscillator.frequency.value = 880;
      app.gain.gain.value = 0;

      app.oscillator
        .connect(app.gain)
        .connect(app.audioContext.destination);

      app.oscillator.start();
    }

    await app.audioContext.resume();

    app.audioEnabled =
      app.audioContext.state === 'running';

    $('audioStatus').textContent = app.audioEnabled
      ? 'ENABLED'
      : 'BROWSER BLOCKED';

    $('enableAudio').textContent = app.audioEnabled
      ? 'Alarm audio enabled'
      : 'Enable alarm audio';

    updateAlarm();
  } catch (err) {
    $('audioStatus').textContent = 'UNAVAILABLE';
    console.error('Could not enable audio', err);
  }
}

/* Alternating 880 Hz and 660 Hz, as specified in the test plan. */
function startAlarmTone() {
  if (!app.audioEnabled || !app.gain || app.toneTimer) {
    return;
  }

  let high = false;

  const pulse = () => {
    high = !high;

    app.oscillator.frequency.setValueAtTime(
      high ? 880 : 660,
      app.audioContext.currentTime
    );

    app.gain.gain.setValueAtTime(
      0.13,
      app.audioContext.currentTime
    );
  };

  pulse();
  app.toneTimer = setInterval(pulse, 350);
}

function stopAlarmTone() {
  if (app.toneTimer) {
    clearInterval(app.toneTimer);
  }

  app.toneTimer = null;

  if (app.gain && app.audioContext) {
    app.gain.gain.setValueAtTime(
      0,
      app.audioContext.currentTime
    );
  }
}

function killAlarm() {
  if (app.state !== 'FIRE') return;

  app.silenced = true;
  stopAlarmTone();
  updateAlarm();
}

/* Render server-recorded alarm events without inserting raw HTML. */
function renderEvents() {
  const body = $('eventsBody');
  body.replaceChildren();

  if (!app.events.length) {
    const row = body.insertRow();
    const cell = row.insertCell();

    cell.colSpan = 3;
    cell.textContent = 'No recorded events.';
    return;
  }

  for (const event of app.events) {
    const row = body.insertRow();

    for (const value of [
      localTime(event.recorded_at),
      event.category,
      event.message
    ]) {
      row.insertCell().textContent = value;
    }
  }
}

function updateHealth() {
  setHealth('thermalHealth', recent(app.frameTime));

  setHealth(
    'ambientHealth',
    recent(app.ambientTime) &&
    $('ambientTemp').textContent !== '—'
  );

  $('connection').textContent = app.connected
    ? 'Server connected'
    : 'Server disconnected';

  $('connection').className =
    `status ${app.connected ? 'status-on' : 'status-off'}`;

  $('faultBanner').hidden =
    app.connected &&
    recent(app.frameTime) &&
    recent(app.telemetryTime) &&
    recent(app.ambientTime);
}

/* Reconnect automatically if the network connection drops. */
function connect() {
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const socket = new WebSocket(
    `${scheme}//${location.host}/ws/thermal`
  );

  app.socket = socket;

  socket.onopen = () => {
    app.connected = true;
    app.retryMs = 1000;
    updateHealth();
  };

  socket.onmessage = event => {
    try {
      const data = JSON.parse(event.data);

      if (data.type === 'frame') {
        ingestFrame(data);
      } else if (data.type === 'telemetry') {
        ingestTelemetry(data);
      } else if (
        data.type === 'events' &&
        Array.isArray(data.events)
      ) {
        app.events = data.events;
        renderEvents();
      }
    } catch (err) {
      console.error('Invalid live message', err);
    }
  };

  socket.onclose = () => {
    if (app.socket !== socket) return;

    app.connected = false;
    updateHealth();

    const delay = app.retryMs;
    app.retryMs = Math.min(
      10000,
      Math.round(app.retryMs * 1.5)
    );

    setTimeout(connect, delay);
  };

  socket.onerror = () => socket.close();
}

/* Plot the stored history on a real time axis (gaps where the device was offline). */
function drawTrend() {
  const bounds = trendCanvas.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return;

  const ratio = Math.min(devicePixelRatio || 1, 2);
  trendCanvas.width = Math.round(bounds.width * ratio);
  trendCanvas.height = Math.round(bounds.height * ratio);
  trendCtx.setTransform(ratio, 0, 0, ratio, 0, 0);

  const width = bounds.width;
  const height = bounds.height;
  const left = 52;
  const right = width - 16;
  const top = 14;
  const bottom = height - 30;
  const [start, end] = histWindow();
  const spanMs = Math.max(1, end - start);
  const font = getComputedStyle(document.body).fontFamily;
  const grid = cssVar('--chart-grid', '#ececea');
  const label = cssVar('--chart-label', '#66665f');
  const thermalColour = cssVar('--chart-thermal', '#d4561a');
  const ambientColour = cssVar('--chart-ambient', '#2f6fb2');

  trendCtx.clearRect(0, 0, width, height);
  trendCtx.font = `12px ${font}`;
  trendCtx.lineWidth = 1;

  const visible = hist.points.filter(p => p.t >= start && p.t <= end);
  const values = visible.flatMap(p => [p.max, p.amb]).filter(finiteTemperature);
  let lo = values.length ? Math.min(...values) - 2 : 0;
  let hi = values.length ? Math.max(...values) + 2 : 100;
  if (hi - lo < 10) {
    const mid = (hi + lo) / 2;
    lo = mid - 5;
    hi = mid + 5;
  }
  /* Round the axis to a tidy step (1, 2, 5, 10, 20 … °C) so labels are whole numbers */
  const yStep = [1, 2, 5, 10, 20, 25, 50, 100, 200].find(st => (hi - lo) / st <= 5) || 500;
  lo = Math.floor(lo / yStep) * yStep;
  hi = Math.ceil(hi / yStep) * yStep;
  const yRange = hi - lo;
  const y = v => bottom - (v - lo) / yRange * (bottom - top);
  const x = t => left + (t - start) / spanMs * (right - left);

  /* Temperature grid */
  trendCtx.textAlign = 'right';
  for (let val = lo; val <= hi + 1e-9; val += yStep) {
    const yy = Math.round(y(val)) + 0.5;
    trendCtx.strokeStyle = grid;
    trendCtx.beginPath();
    trendCtx.moveTo(left, yy);
    trendCtx.lineTo(right, yy);
    trendCtx.stroke();
    trendCtx.fillStyle = label;
    trendCtx.fillText(`${val.toFixed(0)} °C`, left - 8, yy + 4);
  }

  /* Time axis */
  const maxTicks = Math.max(2, Math.floor((right - left) / 110));
  let step = HIST_TICK_STEPS_S[HIST_TICK_STEPS_S.length - 1] * 1000;
  for (const s of HIST_TICK_STEPS_S) {
    if (spanMs / (s * 1000) <= maxTicks) { step = s * 1000; break; }
  }
  const tz = -new Date(start).getTimezoneOffset() * 60000;
  trendCtx.textAlign = 'center';
  for (let t = Math.ceil((start + tz) / step) * step - tz; t <= end; t += step) {
    const xx = Math.round(x(t)) + 0.5;
    trendCtx.strokeStyle = grid;
    trendCtx.beginPath();
    trendCtx.moveTo(xx, top);
    trendCtx.lineTo(xx, bottom);
    trendCtx.stroke();
    trendCtx.fillStyle = label;
    trendCtx.fillText(fmtTick(t, spanMs), xx, bottom + 19);
  }

  /* Warning / fire thresholds */
  trendCtx.save();
  trendCtx.setLineDash([5, 4]);
  trendCtx.textAlign = 'right';
  for (const [v, text] of [[65, 'Fire 65 °C'], [45, 'Warning 45 °C']]) {
    if (v <= lo || v >= hi) continue;
    const yy = Math.round(y(v)) + 0.5;
    trendCtx.strokeStyle = v === 65 ? cssVar('--fire', '#b42318') : cssVar('--warn', '#8a5300');
    trendCtx.globalAlpha = 0.7;
    trendCtx.beginPath();
    trendCtx.moveTo(left, yy);
    trendCtx.lineTo(right, yy);
    trendCtx.stroke();
    trendCtx.globalAlpha = 1;
    trendCtx.fillStyle = trendCtx.strokeStyle;
    trendCtx.fillText(text, right - 4, yy - 5);
  }
  trendCtx.restore();

  if (!visible.length) {
    trendCtx.fillStyle = label;
    trendCtx.textAlign = 'center';
    trendCtx.fillText(
      hist.loading ? 'Loading history…' : hist.error || 'No readings in this time range',
      (left + right) / 2,
      (top + bottom) / 2
    );
    return;
  }

  /* Series: break the line where the device was offline */
  const gapMs = Math.max(3 * hist.bucketMs, 15000);
  for (const [key, colour] of [['max', thermalColour], ['amb', ambientColour]]) {
    trendCtx.strokeStyle = colour;
    trendCtx.fillStyle = colour;
    trendCtx.lineWidth = 2;
    trendCtx.lineJoin = 'round';
    trendCtx.beginPath();
    let prev = null;
    for (const p of visible) {
      const v = p[key];
      if (!finiteTemperature(v)) { prev = null; continue; }
      const xx = x(p.t);
      const yy = y(v);
      if (prev === null || p.t - prev > gapMs) trendCtx.moveTo(xx, yy);
      else trendCtx.lineTo(xx, yy);
      prev = p.t;
    }
    trendCtx.stroke();
    if (visible.length < 3) {
      for (const p of visible) {
        if (!finiteTemperature(p[key])) continue;
        trendCtx.beginPath();
        trendCtx.arc(x(p.t), y(p[key]), 3, 0, Math.PI * 2);
        trendCtx.fill();
      }
    }
  }

  /* Hover read-out */
  if (hist.hoverX === null || hist.hoverX < left || hist.hoverX > right) return;
  const t = start + (hist.hoverX - left) / (right - left) * spanMs;
  let best = null;
  let bestD = Infinity;
  for (const p of visible) {
    const d = Math.abs(p.t - t);
    if (d < bestD) { bestD = d; best = p; }
  }
  if (!best || bestD > Math.max(gapMs, spanMs / 40)) return;

  const bx = Math.round(x(best.t)) + 0.5;
  trendCtx.strokeStyle = label;
  trendCtx.lineWidth = 1;
  trendCtx.beginPath();
  trendCtx.moveTo(bx, top);
  trendCtx.lineTo(bx, bottom);
  trendCtx.stroke();
  for (const [key, colour] of [['max', thermalColour], ['amb', ambientColour]]) {
    if (!finiteTemperature(best[key])) continue;
    trendCtx.fillStyle = colour;
    trendCtx.beginPath();
    trendCtx.arc(bx, y(best[key]), 4, 0, Math.PI * 2);
    trendCtx.fill();
  }

  const lines = [
    fmtFull(best.t),
    `Thermal max  ${degrees(best.max)} °C`,
    `Ambient      ${degrees(best.amb)} °C`
  ];
  trendCtx.font = `12px ${font}`;
  const boxW = Math.max(...lines.map(l => trendCtx.measureText(l).width)) + 20;
  const boxH = lines.length * 18 + 12;
  let boxX = bx + 12;
  if (boxX + boxW > right) boxX = bx - 12 - boxW;
  const boxY = top + 6;
  trendCtx.fillStyle = cssVar('--surface', '#ffffff');
  trendCtx.strokeStyle = cssVar('--border-strong', '#d0d0cb');
  trendCtx.beginPath();
  trendCtx.rect(boxX + 0.5, boxY + 0.5, boxW, boxH);
  trendCtx.fill();
  trendCtx.stroke();
  trendCtx.textAlign = 'left';
  lines.forEach((l, i) => {
    trendCtx.fillStyle = i === 0 ? cssVar('--text-3', '#66665f') : cssVar('--text', '#1a1a19');
    trendCtx.fillText(l, boxX + 10, boxY + 20 + i * 18);
  });
}

/* Operator controls */
$('histRanges').addEventListener('click', event => {
  const button = event.target.closest('button');
  if (!button) return;
  if (button.dataset.span === 'custom') {
    hist.customOpen = true;
    const [start, end] = histWindow();
    $('histFrom').value = toLocalInput(start);
    $('histTo').value = toLocalInput(end);
  } else {
    hist.mode = 'relative';
    hist.customOpen = false;
    hist.span = Number(button.dataset.span);
    storeSet('efd-history-span', hist.span);
    hist.points = [];
    loadHistory();
  }
  setRangeButtons();
});

$('histCustom').addEventListener('submit', event => {
  event.preventDefault();
  const start = new Date($('histFrom').value).getTime();
  const end = new Date($('histTo').value).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end) {
    hist.error = 'Choose a start time that is before the end time.';
    updateHistStatus();
    return;
  }
  hist.mode = 'absolute';
  hist.customOpen = false;
  hist.start = start;
  hist.end = Math.min(end, Date.now());
  hist.points = [];
  loadHistory();
  setRangeButtons();
});

trendCanvas.addEventListener('pointermove', event => {
  hist.hoverX = event.clientX - trendCanvas.getBoundingClientRect().left;
  drawTrend();
});

trendCanvas.addEventListener('pointerleave', () => {
  hist.hoverX = null;
  drawTrend();
});

$('enableAudio').addEventListener('click', enableAudio);
$('killAlarm').addEventListener('click', killAlarm);

$('applyScale').addEventListener('click', () => {
  const low = Number($('scaleMin').value);
  const high = Number($('scaleMax').value);

  if (
    !Number.isFinite(low) ||
    !Number.isFinite(high) ||
    low >= high ||
    low < -40 ||
    high > 350
  ) {
    window.alert(
      'Enter a valid display range between -40 °C and 350 °C, ' +
      'with minimum below maximum.'
    );
    return;
  }

  app.scaleMin = low;
  app.scaleMax = high;

  $('scaleMinLabel').textContent = `${low} °C`;
  $('scaleMaxLabel').textContent = `${high} °C`;

  drawThermal();
});

thermalCanvas.addEventListener('mousemove', event => {
  if (!app.frame) return;

  const rect = thermalCanvas.getBoundingClientRect();

  const x = Math.min(
    W - 1,
    Math.max(
      0,
      Math.floor(
        (event.clientX - rect.left) / rect.width * W
      )
    )
  );

  const y = Math.min(
    H - 1,
    Math.max(
      0,
      Math.floor(
        (event.clientY - rect.top) / rect.height * H
      )
    )
  );

  const value = app.frame.pixels[y * W + x];

  $('pixelInspect').textContent =
    `Sensor pixel X ${x}, Y ${y}: ` +
    (
      finiteTemperature(value)
        ? degrees(value) + ' °C'
        : 'invalid reading'
    );
});

thermalCanvas.addEventListener('mouseleave', () => {
  $('pixelInspect').textContent =
    'Move the pointer over the image to inspect ' +
    'measured pixel temperatures.';
});

window.addEventListener('resize', drawTrend);
document.addEventListener('themechange', drawTrend);

setInterval(() => {
  $('clock').textContent = new Date().toLocaleString(
    undefined,
    {hour12: false}
  );

  updateHealth();
  tickHistory();
}, 1000);

$('clock').textContent = new Date().toLocaleString(
  undefined,
  {hour12: false}
);

/* Default display range saved on the Settings page (per browser). */
(function loadSavedRange() {
  let low = null;
  let high = null;
  try {
    low = localStorage.getItem('efd-scale-min');
    high = localStorage.getItem('efd-scale-max');
  } catch (e) { /* storage blocked: keep built-in defaults */ }
  if (low === null || high === null) return;
  low = Number(low);
  high = Number(high);
  if (!Number.isFinite(low) || !Number.isFinite(high) || low >= high) return;
  app.scaleMin = low;
  app.scaleMax = high;
  $('scaleMin').value = low;
  $('scaleMax').value = high;
  $('scaleMinLabel').textContent = `${low} °C`;
  $('scaleMaxLabel').textContent = `${high} °C`;
})();

updateAlarm();
updateHealth();
initHistory();
connect();
