'use strict';
/* System health page: device link, data flow, sensors, storage, availability. */

function kv(label, value, cls = '') {
  return `<div><span>${esc(label)}</span><strong class="${cls}">${esc(value)}</strong></div>`;
}

/* Typical Wi-Fi signal bands (dBm). */
function signalQuality(dbm) {
  if (dbm >= -60) return 'Excellent';
  if (dbm >= -70) return 'Good';
  if (dbm >= -80) return 'Fair';
  return 'Weak';
}

function setBadge(id, ok, okText, badText, warn = false) {
  const el = $(id);
  el.textContent = ok ? okText : badText;
  el.className = `status ${ok ? 'status-on' : warn ? 'status-warning' : 'status-rec'}`;
}

function render(h) {
  const d = h.device, s = h.sensors, sv = h.server, r = h.rate_of_rise, a = h.availability_24h;
  const fps = d.frame_rate_fps;

  setBadge('overall', d.online && !r.alarm && d.state !== 'FIRE',
    'All systems normal',
    !d.online ? 'Device offline' : d.state === 'FIRE' ? 'Fire reported' : 'Rapid temperature rise',
    d.online && d.state !== 'FIRE');

  setBadge('deviceBadge', d.online, 'Online', d.last_frame_at ? 'Offline' : 'Never connected');
  $('device').innerHTML = [
    kv('Last frame received', d.last_frame_at ? `${fmtClock(d.last_frame_at)} (${fmtDur(d.last_frame_age_s)} ago)` : '—'),
    kv('Last telemetry received', d.last_telemetry_at ? `${fmtClock(d.last_telemetry_at)} (${fmtDur(d.last_telemetry_age_s)} ago)` : '—'),
    kv('Connected since', d.connected_since ? `${fmtClock(d.connected_since)} (${fmtDur(h.now - d.connected_since)})` : '—'),
    kv('Reconnections since server start', String(Math.max(0, d.sessions_since_start - 1))),
    kv('Reported state', d.state || '—', d.state === 'FIRE' ? 'text-fire' : d.state === 'WARNING' ? 'text-warn' : ''),
    kv('Suppression / fan', d.suppression_active == null ? '—' : d.suppression_active ? 'Active' : 'Inactive'),
    kv('Firmware version', d.reported.firmware || 'Not reported by device'),
    kv('Wi-Fi signal', isNum(d.reported.rssi_dbm)
      ? `${d.reported.rssi_dbm} dBm · ${signalQuality(d.reported.rssi_dbm)}` : 'Not reported by device',
      isNum(d.reported.rssi_dbm) && d.reported.rssi_dbm < -80 ? 'text-warn' : ''),
    kv('Device uptime', isNum(d.reported.uptime_s) ? fmtDur(d.reported.uptime_s) : 'Not reported by device'),
    kv('Free memory on device', isNum(d.reported.free_memory) ? fmtBytes(d.reported.free_memory) : 'Not reported by device'),
  ].join('');

  const flowOk = d.online && isNum(fps) && fps >= 0.5;
  setBadge('flowBadge', flowOk, 'Streaming', d.online ? 'Slow' : 'Stopped', d.online);
  $('flow').innerHTML = [
    kv('Frame rate (last 60 s)', isNum(fps) ? `${fps.toFixed(2)} frames/s` : '—'),
    kv('Average frame interval', isNum(d.frame_interval_avg_ms) ? `${d.frame_interval_avg_ms} ms` : '—'),
    kv('Longest gap (last 60 s)', isNum(d.frame_interval_max_ms) ? `${d.frame_interval_max_ms} ms` : '—'),
    kv('Frames received', d.frames_total.toLocaleString()),
    kv('Telemetry messages', d.telemetry_total.toLocaleString()),
    kv('Dashboard viewers', String(sv.viewers)),
  ].join('');

  const invalid = s.thermal_invalid_pixels;
  const thermalOk = d.online && isNum(invalid) && invalid < 20;
  setBadge('sensorBadge', thermalOk, 'Healthy', d.online ? 'Check sensors' : 'No data', d.online);
  $('sensors').innerHTML = [
    kv('Thermal camera (MLX90640)', d.online ? (thermalOk ? 'Reading' : 'Invalid pixels') : 'No data'),
    kv('Invalid pixels in last frame', isNum(invalid) ? `${invalid} / 768` : '—'),
    kv('Thermal range in last frame', isNum(s.thermal_min_c) ? `${s.thermal_min_c.toFixed(1)} – ${s.thermal_max_c.toFixed(1)} °C` : '—'),
    kv('Ambient sensor (DS18B20)', isNum(s.ambient_c) ? deg(s.ambient_c) : 'No reading'),
    kv('Rate of rise', isNum(r.c_per_min) ? `${r.c_per_min.toFixed(1)} °C/min` : 'Collecting data',
      r.alarm ? 'text-warn' : ''),
    kv('Rate-of-rise alarm', `${r.alarm ? 'ACTIVE' : 'Normal'} · limit ${r.threshold_c_per_min} °C/min above ${r.min_temp_c} °C`,
      r.alarm ? 'text-warn' : ''),
  ].join('');

  const availOk = a.percent == null || a.percent >= 95;
  setBadge('availBadge', availOk, a.percent == null ? 'Measuring' : 'Good', 'Gaps in data', true);
  $('avail').innerHTML = [
    kv('Data coverage (last 24 h)', a.percent == null ? 'Not enough data yet' : `${a.percent}%`),
    kv('Measured over', fmtDur(a.window_s)),
    kv('Outages longer than 30 s', String(a.outages)),
    kv('Longest outage', a.outages ? fmtDur(a.longest_outage_s) : '—'),
  ].join('');
  $('availBar').style.width = `${a.percent ?? 0}%`;

  $('server').innerHTML = [
    kv('Server uptime', fmtDur(sv.uptime_s)),
    kv('Database size', fmtBytes(sv.db_size_bytes)),
    kv('Readings stored', sv.readings_stored.toLocaleString()),
    kv('History available since', sv.oldest_reading ? fmtDateTime(sv.oldest_reading) : '—'),
    kv('Incidents (24 h / total)', `${sv.incidents_24h} / ${sv.incidents_total}`),
    kv('Open incident', sv.open_incident ? `#${sv.open_incident}` : 'None'),
  ].join('');
  $('openIncident').hidden = !sv.open_incident;
  if (sv.open_incident) $('openIncident').href = `/incidents/report?id=${sv.open_incident}`;

  $('updated').textContent = `Updated ${fmtClock(h.now)} · refreshes every 2 s`;
  $('healthError').hidden = true;
}

async function load() {
  try {
    const r = await fetch('/api/health', { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    render(await r.json());
  } catch (err) {
    $('healthError').hidden = false;
    $('healthError').textContent = `Could not reach the server (${err.message}).`;
  }
}

load();
setInterval(load, 2000);
