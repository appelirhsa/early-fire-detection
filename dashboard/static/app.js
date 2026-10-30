
'use strict';

const $ = id => document.getElementById(id);
const W = 32;
const H = 24;
const STALE_MS = 6000;
const HISTORY_LIMIT = 180;

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
  history: [],
  events: [],
  audioContext: null,
  oscillator: null,
  gain: null,
  toneTimer: null,
  audioEnabled: false
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
  el.textContent = live ? 'ONLINE' : 'NO RECENT DATA';
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

function addHistory(point) {
  app.history.push(point);

  if (app.history.length > HISTORY_LIMIT) {
    app.history.shift();
  }

  drawTrend();
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

  if (recent(app.frameTime)) {
    addHistory({
      time: app.frameTime,
      thermal: max,
      ambient: finiteTemperature(data.ambient_c)
        ? data.ambient_c
        : null
    });
  }

  drawThermal();
  updateHealth();
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
    ? 'ACTIVE (REPORTED)'
    : 'INACTIVE (REPORTED)';

  if (data.ambient_c != null || !app.ambientTime) {
    updateAmbient(data.ambient_c, data.received_at);
  }

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
  $('systemState').style.color = fire
    ? '#a92d27'
    : app.state === 'WARNING'
      ? '#8d5b08'
      : '#25303b';

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
      ? 'Alarm Audio Enabled'
      : 'Enable Alarm Audio';

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
    ? 'SERVER CONNECTED'
    : 'SERVER DISCONNECTED';

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

/* Plot measured maximum and ambient temperatures. */
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
  const right = width - 18;
  const top = 14;
  const bottom = height - 25;

  trendCtx.clearRect(0, 0, width, height);

  const values = app.history
    .flatMap(p => [p.thermal, p.ambient])
    .filter(finiteTemperature);

  const lo = values.length
    ? Math.floor(Math.min(...values) / 10) * 10 - 5
    : 0;

  const hi = values.length
    ? Math.ceil(Math.max(...values) / 10) * 10 + 5
    : 100;

  const range = Math.max(10, hi - lo);

  const y = v =>
    bottom - (v - lo) / range * (bottom - top);

  trendCtx.font = '11px Segoe UI, Arial';

  for (let i = 0; i <= 4; i++) {
    const val = lo + range * i / 4;
    const yy = y(val);

    trendCtx.strokeStyle = '#e4e8eb';
    trendCtx.beginPath();
    trendCtx.moveTo(left, yy);
    trendCtx.lineTo(right, yy);
    trendCtx.stroke();

    trendCtx.fillStyle = '#7a8792';
    trendCtx.textAlign = 'right';
    trendCtx.fillText(
      `${val.toFixed(0)} °C`,
      left - 8,
      yy + 4
    );
  }

  if (!app.history.length) {
    trendCtx.fillStyle = '#788591';
    trendCtx.textAlign = 'center';
    trendCtx.fillText(
      'Temperature history will appear when live data arrives',
      width / 2,
      height / 2
    );
    return;
  }

  const x = i =>
    left +
    (right - left) * i / Math.max(1, HISTORY_LIMIT - 1);

  const start = HISTORY_LIMIT - app.history.length;

  for (const [key, colour] of [
    ['thermal', '#ad5d29'],
    ['ambient', '#366d96']
  ]) {
    trendCtx.strokeStyle = colour;
    trendCtx.lineWidth = 2;
    trendCtx.beginPath();

    let started = false;

    app.history.forEach((point, i) => {
      if (!finiteTemperature(point[key])) {
        started = false;
        return;
      }

      const xx = x(start + i);
      const yy = y(point[key]);

      if (!started) {
        trendCtx.moveTo(xx, yy);
      } else {
        trendCtx.lineTo(xx, yy);
      }

      started = true;
    });

    trendCtx.stroke();
  }
}

/* Operator controls */
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

setInterval(() => {
  $('clock').textContent = new Date().toLocaleString(
    undefined,
    {hour12: false}
  );

  updateHealth();
}, 1000);

$('clock').textContent = new Date().toLocaleString(
  undefined,
  {hour12: false}
);

updateAlarm();
updateHealth();
drawTrend();
connect();
