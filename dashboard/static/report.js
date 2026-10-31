'use strict';
/* Printable incident report: timeline, peak thermal snapshot and temperature chart. */

const params = new URLSearchParams(location.search);
const incidentId = Number(params.get('id'));
let incident = null;

function row(label, value) {
  return `<div><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
}

function rel(t) {
  if (!isNum(t) || !incident) return '';
  const d = t - incident.started_at;
  return d === 0 ? ' (T+0)' : ` (T${d > 0 ? '+' : '−'}${fmtDur(Math.abs(d))})`;
}

function timeline(i) {
  const ev = [
    [i.warning_at, 'Device reported WARNING', 'warning'],
    [i.started_at, `Incident opened · ${i.trigger.split(' + ')[0]}`, 'fire'],
    [i.ror_at, 'Rate-of-rise alarm', 'warning'],
    [i.fire_at, 'Device reported FIRE (fixed temperature)', 'fire'],
    [i.fan_on_at, 'Suppression / fan activated', 'ok'],
    [i.peak_at, `Peak temperature ${deg(i.peak_c)}`, 'fire'],
    [i.fan_off_at, 'Suppression / fan stopped', 'ok'],
    [i.ended_at, 'Condition cleared · incident closed', 'ok'],
  ].filter(e => isNum(e[0]));
  ev.sort((a, b) => a[0] - b[0]);
  return ev.map(([t, text, kind]) => `
    <li class="tl-${kind}"><time>${esc(fmtClock(t))}${esc(rel(t))}</time><span>${esc(text)}</span></li>`).join('');
}

function drawChart() {
  if (!incident) return;
  drawTimeChart($('incidentChart'), {
    points: incident.readings,
    start: incident.window.start,
    end: incident.window.end,
    shade: { start: incident.started_at, end: incident.ended_at || Date.now() / 1000 },
    thresholds: [
      { v: 65, label: 'Fire 65 °C', color: cssVar('--fire', '#b42318') },
      { v: 45, label: 'Warning 45 °C', color: cssVar('--warn', '#8a5300') },
    ],
    markers: [
      { t: incident.fire_at, label: 'FIRE', color: cssVar('--fire', '#b42318') },
      { t: incident.ror_at, label: 'Rate of rise', color: cssVar('--warn', '#8a5300') },
      { t: incident.fan_on_at, label: 'Fan on', color: cssVar('--ok', '#1f7a3f') },
    ],
  });
}

function render(i) {
  incident = i;
  document.title = `Incident #${i.id} report · Early Fire Detection`;
  $('reportTitle').textContent = `Incident #${i.id}`;
  $('reportSub').textContent = `${fmtDateTime(i.started_at)} · ${i.open ? 'in progress' : 'closed'}`;
  $('reportStatus').className = `status ${i.open ? 'status-rec' : 'status-on'}`;
  $('reportStatus').textContent = i.open ? 'Open' : 'Closed';

  $('summary').innerHTML = [
    row('Trigger', i.trigger),
    row('Started', fmtDateTime(i.started_at)),
    row('Ended', i.open ? 'Still active' : fmtDateTime(i.ended_at)),
    row('Duration', fmtDur(i.duration_s)),
    row('Peak hottest-pixel temperature', `${deg(i.peak_c)} at ${fmtClock(i.peak_at)}`),
    row('Ambient at start', deg(i.ambient_c)),
    row('Maximum rate of rise', isNum(i.max_ror) ? `${i.max_ror.toFixed(1)} °C/min (alarm at ${i.ror_threshold} °C/min)` : '—'),
    row('Rate-of-rise early warning', isNum(i.ror_lead_s)
      ? `${fmtDur(i.ror_lead_s)} before the fixed 65 °C threshold` : '—'),
    row('Warning lead time', isNum(i.warning_lead_s) ? `${fmtDur(i.warning_lead_s)} before the incident` : 'No WARNING beforehand'),
    row('Suppression response', isNum(i.fan_response_s)
      ? (i.fan_response_s <= 0 ? 'Already running when the incident opened' : `${fmtDur(i.fan_response_s)} after the incident opened`)
      : 'Not activated'),
    row('Note', i.note || '—'),
  ].join('');

  $('timeline').innerHTML = timeline(i);

  if (i.snapshot && i.snapshot.length === TW * TH) {
    const valid = i.snapshot.filter(v => isNum(v) && v > -200);
    const lo = Math.floor(Math.min(...valid));
    const hi = Math.ceil(Math.max(...valid));
    const idx = drawHeatmap($('snapshot'), i.snapshot, lo, hi);
    $('snapLo').textContent = `${lo} °C`;
    $('snapHi').textContent = `${hi} °C`;
    $('snapInfo').textContent =
      `Frame captured at the peak (${fmtClock(i.peak_at)}). Hotspot: ${zoneName(idx)}.`;
    $('snapWrap').hidden = false;
    $('snapEmpty').hidden = true;
  }

  $('prevLink').hidden = !i.prev_id;
  $('nextLink').hidden = !i.next_id;
  if (i.prev_id) $('prevLink').href = `/incidents/report?id=${i.prev_id}`;
  if (i.next_id) $('nextLink').href = `/incidents/report?id=${i.next_id}`;
  $('generated').textContent = `Report generated ${fmtDateTime(Date.now() / 1000)} · ` +
    'Early Fire Detection and Monitoring System · Academic prototype, not a certified fire alarm panel';
  $('reportBody').hidden = false;
  drawChart();
}

async function load() {
  if (!Number.isInteger(incidentId) || incidentId < 1) {
    $('reportError').hidden = false;
    $('reportError').textContent = 'No incident selected. Open a report from the incident log.';
    return;
  }
  try {
    const r = await fetch(`/api/incidents/${incidentId}`, { cache: 'no-store' });
    if (r.status === 404) throw new Error('incident not found');
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    render(data);
    if (data.open) setTimeout(load, 5000);   // follow an incident that is still in progress
  } catch (err) {
    $('reportError').hidden = false;
    $('reportError').textContent = `Could not load the report (${err.message}).`;
  }
}

$('printReport').addEventListener('click', () => window.print());
window.addEventListener('resize', drawChart);
window.addEventListener('themechange', drawChart);
window.addEventListener('beforeprint', drawChart);
load();
