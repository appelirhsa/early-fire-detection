'use strict';
/* Incident log page: every FIRE or rate-of-rise alarm, newest first. */

function triggerTags(trigger) {
  return String(trigger || '').split(' + ').map(t => {
    const cls = t === 'Fixed temperature' ? 'tag-fire' : 'tag-warning';
    return `<span class="tag ${cls}">${esc(t)}</span>`;
  }).join(' ');
}

function median(values) {
  const v = values.filter(isNum).sort((a, b) => a - b);
  if (!v.length) return null;
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
}

function render(data) {
  const list = data.incidents;
  const now = Date.now() / 1000;
  const day = list.filter(i => i.started_at >= now - 86400);
  const peaks = list.map(i => i.peak_c).filter(isNum);

  $('statTotal').textContent = String(list.length);
  $('statDay').textContent = String(day.length);
  $('statPeak').textContent = peaks.length ? Math.max(...peaks).toFixed(1) : '—';
  const resp = median(list.map(i => i.fan_response_s));
  $('statResponse').textContent = isNum(resp) ? resp.toFixed(1) : '—';

  const open = list.find(i => i.open);
  $('openBanner').hidden = !open;
  if (open) {
    $('openText').textContent =
      `Incident #${open.id} in progress since ${fmtClock(open.started_at)} · ` +
      `peak ${deg(open.peak_c)} · ${open.trigger}`;
    $('openLink').href = `/incidents/report?id=${open.id}`;
  }

  const body = $('incidentsBody');
  if (!list.length) {
    body.innerHTML = '<tr><td colspan="8">No incidents recorded yet. An incident opens automatically ' +
      'when the device reports FIRE or the temperature rises faster than the rate-of-rise limit.</td></tr>';
    return;
  }
  body.innerHTML = list.map(i => `
    <tr>
      <td><a href="/incidents/report?id=${i.id}">#${i.id}</a></td>
      <td>${esc(fmtDateTime(i.started_at))}</td>
      <td>${i.open ? '<span class="tag tag-fire">Open</span>' : esc(fmtDur(i.duration_s))}</td>
      <td>${triggerTags(i.trigger)}</td>
      <td class="num">${esc(deg(i.peak_c))}</td>
      <td class="num">${isNum(i.max_ror) ? i.max_ror.toFixed(1) + ' °C/min' : '—'}${isNum(i.ror_lead_s) ? `<br><small class="small-text">${fmtDur(i.ror_lead_s)} early</small>` : ''}</td>
      <td class="num">${isNum(i.fan_response_s)
        ? (i.fan_response_s <= 0 ? 'Already running' : fmtDur(i.fan_response_s)) : 'Not activated'}</td>
      <td><a class="button small-button" href="/incidents/report?id=${i.id}">Report</a></td>
    </tr>`).join('');
}

async function load() {
  try {
    const r = await fetch('/api/incidents', { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    render(await r.json());
    $('loadError').hidden = true;
  } catch (err) {
    $('loadError').hidden = false;
    $('loadError').textContent = `Could not load incidents (${err.message}).`;
  }
}

load();
setInterval(load, 5000);
