#!/usr/bin/env python3
"""Generate the dashboard's HTML pages from one shared shell (sidebar, header, footer).

Run:  python3 build_pages.py      -> writes static/index.html, settings.html,
                                     disclaimer.html, record_panel.html
Bump ASSET_VERSION whenever style.css / app.js / theme.js change, so browsers
fetch the new files instead of an old cached copy.
"""
from pathlib import Path

ASSET_VERSION = "8"
OUT = Path(__file__).resolve().parent / "static"

ICONS = {
    "dashboard": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>',
    "record": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="3.2" fill="currentColor" stroke="none"/></svg>',
    "settings": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/></svg>',
    "disclaimer": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.4 7.5 9.5 4.3-1.1 7.5-4.9 7.5-9.5V6z"/><path d="M12 8.5v4M12 15.5h.01"/></svg>',
    "incidents": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 3.5h7l4 4V20a.5.5 0 0 1-.5.5h-10.5a.5.5 0 0 1-.5-.5V4a.5.5 0 0 1 .5-.5z"/><path d="M14 3.5V8h4M9.5 12.5h5M9.5 16h5"/></svg>',
    "health": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12h4l2.5-6 4 12 2.5-6H21"/></svg>',
    "help": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M9.6 9.5a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.2-2.4 3.6M12 16.8h.01"/></svg>',
    "flame": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3c1 3.5 5 5.5 5 10a5 5 0 0 1-10 0c0-2.2 1-3.7 2.3-4.8.3 1.5 1.2 2.4 2.2 2.8C11 8.5 11 6 12 3z"/></svg>',
}

NAV = [
    ("dashboard", "/", "Dashboard"),
    ("incidents", "/incidents", "Incidents"),
    ("health", "/health", "System health"),
    ("record", "/record", "Data capture"),
    ("settings", "/settings", "Settings"),
    ("disclaimer", "/disclaimer", "Legal disclaimer"),
]


def head(title, extra=""):
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <script src="/static/theme.js?v={ASSET_VERSION}"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&amp;display=swap">
  <link rel="stylesheet" href="/static/style.css?v={ASSET_VERSION}">{extra}
</head>"""


def sidebar(active):
    links = []
    for key, href, label in NAV:
        cur = ' class="is-active" aria-current="page"' if key == active else ""
        links.append(f'      <a href="{href}"{cur}>{ICONS[key]}{label}</a>')
    links.append(f'      <a href="https://appelirhsa.co.za" target="_blank" rel="noopener">{ICONS["help"]}Help &amp; tickets<span class="external">↗</span></a>')
    nav = "\n".join(links)
    return f"""  <aside class="sidebar">
    <a class="brand" href="/">
      <span class="brand-mark">{ICONS["flame"]}</span>
      <span><span class="brand-name">Early Fire Detection</span><span class="brand-sub">Monitoring system</span></span>
    </a>
    <nav class="nav" aria-label="Main">
      <span class="eyebrow nav-label">Menu</span>
{nav}
    </nav>
    <div class="sidebar-note">
      <strong>Academic prototype</strong>
      <span>Not a certified fire alarm panel. Do not rely on it to protect people or property.</span>
    </div>
  </aside>"""


def header(eyebrow, title, sub, actions):
    return f"""    <header class="page-header">
      <div class="page-header-inner">
        <div>
          <span class="eyebrow">{eyebrow}</span>
          <h1 class="page-title">{title}</h1>
          <p class="page-sub">{sub}</p>
        </div>
        <div class="header-actions">
{actions}
        </div>
      </div>
    </header>"""


FOOTER = """    <footer class="site-footer">
      <div class="footer-inner">
        <div class="footer-brand">
          <img src="/static/uj_logo.png" alt="University of Johannesburg" class="footer-logo" width="132" height="36">
          <div class="footer-author">
            <strong>Aphiwe Elihle Mthembu</strong>
            <span>Student number 223087197</span>
            <span>Final Year Project · University of Johannesburg</span>
          </div>
        </div>
        <nav class="footer-links" aria-label="Footer">
          <a href="https://appelirhsa.co.za" target="_blank" rel="noopener">Help · Log a ticket or request maintenance ↗</a>
          <a href="/disclaimer">Legal disclaimer</a>
          <a href="/settings">Settings</a>
        </nav>
        <div class="footer-meta">
          <span>Early Fire Detection and Monitoring System</span>
          <span>Academic prototype · Not a certified fire alarm panel</span>
        </div>
      </div>
    </footer>"""


def page(title, active, hdr, body, tail=""):
    return f"""{head(title)}
<body>
<div class="app">
{sidebar(active)}
  <div class="content">
{hdr}
    <main class="page-body">
{body}
    </main>
{FOOTER}
  </div>
</div>
<script src="/static/expand.js?v={ASSET_VERSION}"></script>
{tail}</body>
</html>
"""


# ---------------------------------------------------------------- Dashboard
DASH_BODY = """      <div id="fireBanner" class="fire-banner" role="alert" aria-live="assertive" hidden>
        <strong>FIRE DETECTED — OPERATOR ACTION REQUIRED</strong>
        <span>Confirmed fire state reported by the sensing unit. Follow site emergency procedures.</span>
      </div>

      <div id="rorBanner" class="ror-banner" role="alert" hidden>
        <strong>RAPID TEMPERATURE RISE</strong>
        <span id="rorBannerText">The hottest point is heating faster than the rate-of-rise limit.</span>
        <a id="rorIncident" href="/incidents" hidden>View incident →</a>
      </div>

      <div id="faultBanner" class="fault-banner" role="status" hidden>
        Sensor data stale or connection lost — verify device status.
      </div>

      <section class="stat-strip" aria-label="System measurements">
        <div class="stat">
          <span class="eyebrow">System condition</span>
          <strong id="systemState" class="stat-value">UNKNOWN</strong>
          <small id="classificationSource">Awaiting device classification</small>
        </div>
        <div class="stat">
          <span class="eyebrow">Max thermal temperature</span>
          <strong class="stat-value"><span id="maxTemp">—</span><span class="unit"> °C</span></strong>
          <small>MLX90640 · hottest valid pixel</small>
        </div>
        <div class="stat">
          <span class="eyebrow">Ambient temperature</span>
          <strong class="stat-value"><span id="ambientTemp">—</span><span class="unit"> °C</span></strong>
          <small>DS18B20 · 1-Wire sensor</small>
        </div>
        <div class="stat">
          <span class="eyebrow">Rate of rise</span>
          <strong id="rorStat" class="stat-value"><span id="rorValue">—</span><span class="unit"> °C/min</span></strong>
          <small id="rorLimit">Alarm above 8 °C/min</small>
        </div>
        <div class="stat">
          <span class="eyebrow">Suppression system</span>
          <strong id="suppression" class="stat-value stat-value-sm">UNKNOWN</strong>
          <small>Device-reported relay status only</small>
        </div>
      </section>

      <div class="grid-main">
        <section class="card">
          <div class="card-head">
            <div>
              <span class="eyebrow">Primary sensor</span>
              <h2 class="card-title">MLX90640 thermal camera</h2>
            </div>
            <span id="thermalHealth" class="status status-off">No data</span>
          </div>

          <div class="thermal-wrap">
            <canvas id="thermalCanvas" width="320" height="240" aria-label="Live 32 by 24 thermal temperature map"></canvas>
            <div id="thermalPlaceholder" class="thermal-placeholder">Awaiting thermal frame from sensing unit</div>
          </div>

          <div class="scale-row">
            <span id="scaleMinLabel">20 °C</span>
            <div class="thermal-scale"></div>
            <span id="scaleMaxLabel">100 °C</span>
          </div>

          <div class="range-row">
            <label class="field">Display minimum (°C)
              <input id="scaleMin" class="input" type="number" min="-40" max="300" value="20">
            </label>
            <label class="field">Display maximum (°C)
              <input id="scaleMax" class="input" type="number" min="-39" max="350" value="100">
            </label>
            <button id="applyScale" type="button" class="button">Apply range</button>
          </div>

          <div class="kv-grid">
            <div class="kv"><span>Minimum</span><strong id="minTemp">—</strong></div>
            <div class="kv"><span>Average</span><strong id="meanTemp">—</strong></div>
            <div class="kv"><span>Valid pixels</span><strong id="validPixels">— / 768</strong></div>
            <div class="kv"><span>Hotspot location</span><strong id="hotspot">—</strong></div>
            <div class="kv"><span>Frame sequence</span><strong id="frameSeq">—</strong></div>
            <div class="kv"><span>Last thermal update</span><strong id="frameTime">—</strong></div>
          </div>

          <p id="pixelInspect" class="hint">Move the pointer over the image to inspect measured pixel temperatures.</p>
        </section>

        <div class="stack">
          <section class="card">
            <div class="card-head">
              <div>
                <span class="eyebrow">Response</span>
                <h2 class="card-title">Alarm management</h2>
              </div>
            </div>
            <div id="alarmCondition" class="alarm-condition">No fire alarm reported</div>
            <p id="alarmMessage" class="detail-text">Awaiting current system telemetry.</p>
            <div class="alarm-controls">
              <button id="enableAudio" type="button" class="button button-primary button-lg">Enable alarm audio</button>
              <button id="killAlarm" type="button" class="button button-danger button-lg" disabled>Kill alarm — silence</button>
            </div>
            <div class="detail-list">
              <div><span>Operator audio</span><strong id="audioStatus">NOT ENABLED</strong></div>
              <div><span>Alarm acknowledgement</span><strong id="silenceStatus">NOT SILENCED</strong></div>
              <div><span>Last telemetry</span><strong id="telemetryTime">—</strong></div>
              <div><span>Current incident</span><strong><a id="incidentLink" href="/incidents">None</a></strong></div>
            </div>
            <p class="safety-note">Kill alarm silences this browser only. It does not clear the fire condition, stop the device buzzer or control suppression.</p>
          </section>

          <section class="card">
            <div class="card-head">
              <div>
                <span class="eyebrow">Secondary sensor</span>
                <h2 class="card-title">DS18B20 ambient sensor</h2>
              </div>
              <span id="ambientHealth" class="status status-off">No data</span>
            </div>
            <div class="ambient-reading"><span id="ambientLarge">—</span><span>°C</span></div>
            <p class="detail-text">Ambient temperature is a separate reference for judging localised thermal activity.</p>
            <div class="detail-list">
              <div><span>Sensor interface</span><strong>1-Wire</strong></div>
              <div><span>Last ambient update</span><strong id="ambientTime">—</strong></div>
            </div>
          </section>
        </div>
      </div>

      <section class="card section">
        <div class="card-head">
          <div>
            <span class="eyebrow">Measurements</span>
            <h2 class="card-title">Temperature history</h2>
            <p class="card-sub">Stored on the server · choose the time range to view</p>
          </div>
          <div class="chart-key">
            <span class="key-thermal">Thermal max</span>
            <span class="key-ambient">Ambient</span>
          </div>
        </div>
        <div class="history-controls">
          <div class="range-tabs" id="histRanges" role="group" aria-label="Time range">
            <button type="button" data-span="300" aria-pressed="false">5 min</button>
            <button type="button" data-span="900" aria-pressed="false">15 min</button>
            <button type="button" data-span="3600" aria-pressed="false">1 h</button>
            <button type="button" data-span="21600" aria-pressed="false">6 h</button>
            <button type="button" data-span="86400" aria-pressed="false">24 h</button>
            <button type="button" data-span="604800" aria-pressed="false">7 days</button>
            <button type="button" data-span="2592000" aria-pressed="false">30 days</button>
            <button type="button" data-span="custom" aria-pressed="false">Custom</button>
          </div>
          <form class="custom-range" id="histCustom" hidden>
            <label>From <input class="input" type="datetime-local" id="histFrom" required></label>
            <label>To <input class="input" type="datetime-local" id="histTo" required></label>
            <button class="button button-primary" type="submit">Show</button>
          </form>
        </div>
        <canvas id="trendCanvas" aria-label="Thermal and ambient temperature history"></canvas>
        <p class="small-text" id="histStatus" aria-live="polite"></p>
      </section>

      <section class="card section">
        <div class="card-head">
          <div>
            <span class="eyebrow">Audit</span>
            <h2 class="card-title">Alarm and system events</h2>
            <p class="card-sub">Server-recorded state transitions and suppression reports</p>
          </div>
        </div>
        <div class="table-scroll">
          <table class="events-table">
            <thead><tr><th>Time</th><th>Category</th><th>Event</th></tr></thead>
            <tbody id="eventsBody"><tr><td colspan="3">No recorded events.</td></tr></tbody>
          </table>
        </div>
      </section>"""

DASH_ACTIONS = """          <a href="/disclaimer" class="status status-warning status-plain" title="Academic project — read the legal disclaimer">Academic prototype</a>
          <span id="connection" class="status status-off">Connecting</span>
          <span id="clock" class="clock">--</span>"""

# ---------------------------------------------------------------- Incidents
INC_BODY = """      <div id="openBanner" class="fire-banner fire-banner-static" role="status" hidden>
        <strong>INCIDENT IN PROGRESS</strong>
        <span id="openText"></span>
        <a id="openLink" href="/incidents">Open live report →</a>
      </div>

      <section class="stat-strip stat-strip-4" aria-label="Incident summary">
        <div class="stat">
          <span class="eyebrow">Incidents recorded</span>
          <strong id="statTotal" class="stat-value">—</strong>
          <small>Since the log was started</small>
        </div>
        <div class="stat">
          <span class="eyebrow">Last 24 hours</span>
          <strong id="statDay" class="stat-value">—</strong>
          <small>FIRE or rate-of-rise alarms</small>
        </div>
        <div class="stat">
          <span class="eyebrow">Highest peak</span>
          <strong class="stat-value"><span id="statPeak">—</span><span class="unit"> °C</span></strong>
          <small>Hottest pixel during any incident</small>
        </div>
        <div class="stat">
          <span class="eyebrow">Median suppression response</span>
          <strong class="stat-value"><span id="statResponse">—</span><span class="unit"> s</span></strong>
          <small>Incident start to fan on · 0 = already running</small>
        </div>
      </section>

      <section class="card section">
        <div class="card-head">
          <div>
            <span class="eyebrow">Audit</span>
            <h2 class="card-title">Incident log</h2>
            <p class="card-sub">Opened automatically on a device FIRE report or a rate-of-rise alarm; closed 10 s after the condition clears</p>
          </div>
          <a class="button" href="/api/incidents.csv" download>Export CSV</a>
        </div>
        <p id="loadError" class="form-error" hidden></p>
        <div class="table-scroll table-tall">
          <table>
            <thead><tr><th>#</th><th>Started</th><th>Duration</th><th>Trigger</th><th>Peak</th><th>Max rise</th><th>Suppression</th><th></th></tr></thead>
            <tbody id="incidentsBody"><tr><td colspan="8">Loading…</td></tr></tbody>
          </table>
        </div>
      </section>"""

INC_ACTIONS = """          <a class="button" href="/">← Back to dashboard</a>"""

REPORT_BODY = """      <p id="reportError" class="form-error" hidden></p>
      <div id="reportBody" class="report" hidden>
        <section class="card">
          <div class="card-head">
            <div>
              <span class="eyebrow">Incident report</span>
              <h2 id="reportTitle" class="card-title">Incident</h2>
              <p id="reportSub" class="card-sub"></p>
            </div>
            <span id="reportStatus" class="status status-off">—</span>
          </div>
          <div id="summary" class="detail-list detail-list-wide"></div>
        </section>

        <div class="report-grid section">
          <section class="card">
            <div class="card-head">
              <div>
                <span class="eyebrow">Evidence</span>
                <h2 class="card-title">Thermal frame at peak</h2>
              </div>
            </div>
            <div id="snapWrap" hidden>
              <canvas id="snapshot" class="snapshot" width="320" height="240" aria-label="Thermal frame captured at the peak temperature"></canvas>
              <div class="scale-row">
                <span id="snapLo">—</span>
                <div class="thermal-scale"></div>
                <span id="snapHi">—</span>
              </div>
              <p id="snapInfo" class="small-text"></p>
            </div>
            <p id="snapEmpty" class="small-text">No thermal frame was captured for this incident.</p>
          </section>

          <section class="card">
            <div class="card-head">
              <div>
                <span class="eyebrow">Sequence</span>
                <h2 class="card-title">Timeline</h2>
              </div>
            </div>
            <ol id="timeline" class="timeline"></ol>
          </section>
        </div>

        <section class="card section">
          <div class="card-head">
            <div>
              <span class="eyebrow">Measurements</span>
              <h2 class="card-title">Temperature during the incident</h2>
              <p class="card-sub">Shaded area: incident active · from 1 min before to 1 min after</p>
            </div>
            <div class="chart-key">
              <span class="key-thermal">Thermal max</span>
              <span class="key-ambient">Ambient</span>
            </div>
          </div>
          <canvas id="incidentChart" class="incident-chart" aria-label="Temperature during the incident"></canvas>
        </section>

        <p id="generated" class="small-text section"></p>
      </div>"""

REPORT_ACTIONS = """          <a id="prevLink" class="button no-print" href="#" hidden>← Previous</a>
          <a id="nextLink" class="button no-print" href="#" hidden>Next →</a>
          <button id="printReport" type="button" class="button button-primary no-print">Print / save as PDF</button>
          <a class="button no-print" href="/incidents">All incidents</a>"""

HEALTH_BODY = """      <p id="healthError" class="form-error" hidden></p>
      <div class="health-top">
        <span id="overall" class="status status-off">Checking…</span>
        <a id="openIncident" class="button small-button" href="/incidents" hidden>View open incident →</a>
        <span id="updated" class="small-text"></span>
      </div>

      <div class="health-grid">
        <section class="card">
          <div class="card-head">
            <div><span class="eyebrow">Sensing unit</span><h2 class="card-title">Device link</h2></div>
            <span id="deviceBadge" class="status status-off">—</span>
          </div>
          <div id="device" class="detail-list"></div>
        </section>

        <section class="card">
          <div class="card-head">
            <div><span class="eyebrow">Network</span><h2 class="card-title">Data flow</h2></div>
            <span id="flowBadge" class="status status-off">—</span>
          </div>
          <div id="flow" class="detail-list"></div>
        </section>

        <section class="card">
          <div class="card-head">
            <div><span class="eyebrow">Measurement</span><h2 class="card-title">Sensors and alarms</h2></div>
            <span id="sensorBadge" class="status status-off">—</span>
          </div>
          <div id="sensors" class="detail-list"></div>
        </section>

        <section class="card">
          <div class="card-head">
            <div><span class="eyebrow">Reliability</span><h2 class="card-title">Availability</h2></div>
            <span id="availBadge" class="status status-off">—</span>
          </div>
          <div class="avail-track" aria-hidden="true"><div id="availBar" class="avail-bar"></div></div>
          <div id="avail" class="detail-list"></div>
        </section>

        <section class="card health-wide">
          <div class="card-head">
            <div><span class="eyebrow">Backend</span><h2 class="card-title">Server and storage</h2></div>
          </div>
          <div id="server" class="detail-list detail-list-wide"></div>
        </section>
      </div>"""

# ---------------------------------------------------------------- Settings
SETTINGS_BODY = """      <div class="settings stack">
        <section class="card">
          <div class="card-head">
            <div>
              <span class="eyebrow">Appearance</span>
              <h2 class="card-title">Theme</h2>
              <p class="card-sub">Applies to every page in this browser.</p>
            </div>
          </div>
          <div class="setting-row">
            <div class="setting-text">
              <strong>Colour mode</strong>
              <span>System follows your device's light or dark setting.</span>
            </div>
            <div class="segmented" role="radiogroup" aria-label="Colour mode">
              <label><input type="radio" name="theme" value="light"><span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/></svg>Light</span></label>
              <label><input type="radio" name="theme" value="dark"><span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>Dark</span></label>
              <label><input type="radio" name="theme" value="system"><span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg>System</span></label>
            </div>
          </div>
        </section>

        <section class="card">
          <div class="card-head">
            <div>
              <span class="eyebrow">Thermal display</span>
              <h2 class="card-title">Default colour range</h2>
              <p class="card-sub">Starting range for the thermal image on the dashboard. You can still change it there.</p>
            </div>
          </div>
          <div class="setting-row">
            <div class="setting-text">
              <strong>Display range (°C)</strong>
              <span>Values outside this range show as the end colours. Fire threshold is 65 °C.</span>
            </div>
            <form class="range-pair" id="rangeForm">
              <label class="field">Minimum
                <input id="defMin" class="input" type="number" min="-40" max="300" value="20">
              </label>
              <label class="field">Maximum
                <input id="defMax" class="input" type="number" min="-39" max="350" value="100">
              </label>
              <button type="submit" class="button button-primary">Save</button>
              <button type="button" id="rangeReset" class="button">Reset</button>
            </form>
          </div>
          <p class="save-note" id="rangeNote" aria-live="polite"></p>
        </section>

        <section class="card">
          <div class="card-head">
            <div>
              <span class="eyebrow">System</span>
              <h2 class="card-title">Server status</h2>
            </div>
            <span id="srvStatus" class="status status-off">Checking</span>
          </div>
          <div class="detail-list">
            <div><span>Frames received</span><strong id="srvFrames">—</strong></div>
            <div><span>Telemetry received</span><strong id="srvTelemetry">—</strong></div>
            <div><span>Last frame</span><strong id="srvLastFrame">—</strong></div>
            <div><span>Connected viewers</span><strong id="srvViewers">—</strong></div>
          </div>
        </section>
      </div>"""

SETTINGS_SCRIPT = """<script>
'use strict';
(function () {
  const $ = id => document.getElementById(id);
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); return true; } catch (e) { return false; } },
    del(k) { try { localStorage.removeItem(k); } catch (e) {} }
  };

  /* Theme */
  const radios = document.querySelectorAll('input[name=theme]');
  const current = window.getThemeMode ? window.getThemeMode() : 'system';
  radios.forEach(r => {
    r.checked = r.value === current;
    r.addEventListener('change', () => { if (r.checked && window.setThemeMode) window.setThemeMode(r.value); });
  });

  /* Default thermal range */
  const min = store.get('efd-scale-min'), max = store.get('efd-scale-max');
  if (min !== null) $('defMin').value = min;
  if (max !== null) $('defMax').value = max;
  $('rangeForm').addEventListener('submit', e => {
    e.preventDefault();
    const lo = Number($('defMin').value), hi = Number($('defMax').value);
    if (!Number.isFinite(lo) || !Number.isFinite(hi) || lo >= hi || lo < -40 || hi > 350) {
      $('rangeNote').textContent = 'Enter a range between -40 and 350 °C, with minimum below maximum.';
      $('rangeNote').style.color = 'var(--fire)';
      return;
    }
    const ok = store.set('efd-scale-min', lo) && store.set('efd-scale-max', hi);
    $('rangeNote').style.color = '';
    $('rangeNote').textContent = ok ? `Saved: ${lo} – ${hi} °C.` : 'This browser blocked saving settings.';
  });
  $('rangeReset').addEventListener('click', () => {
    store.del('efd-scale-min'); store.del('efd-scale-max');
    $('defMin').value = 20; $('defMax').value = 100;
    $('rangeNote').style.color = '';
    $('rangeNote').textContent = 'Reset to 20 – 100 °C.';
  });

  /* Server status */
  const when = v => { if (!v) return '—'; const d = new Date(v); return isNaN(d) ? '—' : d.toLocaleString(undefined, { hour12: false }); };
  async function refresh() {
    try {
      const s = await (await fetch('/api/status', { cache: 'no-store' })).json();
      $('srvStatus').textContent = 'Online'; $('srvStatus').className = 'status status-on';
      $('srvFrames').textContent = s.frames_received;
      $('srvTelemetry').textContent = s.telemetry_received;
      $('srvLastFrame').textContent = when(s.last_frame_at);
      $('srvViewers').textContent = s.connected_viewers;
    } catch (e) {
      $('srvStatus').textContent = 'Unreachable'; $('srvStatus').className = 'status status-off';
    }
  }
  refresh(); setInterval(refresh, 5000);
})();
</script>
"""

# ---------------------------------------------------------------- Disclaimer
DISC_BODY = """      <div class="doc">
        <div class="doc-alert" role="note">
          <strong>Academic project — not for public or immediate use</strong>
          <span>This system is a student prototype. It is not a certified fire detection, alarm or suppression system and must not be relied on to protect people, property or equipment.</span>
        </div>

        <section class="card">
          <div class="doc-section">
            <span class="eyebrow">01 · Project status</span>
            <h2 class="card-title">An academic project</h2>
            <p>The Early Fire Detection and Monitoring System was designed and built by Aphiwe Elihle Mthembu (student number 223087197) as a Final Year Project in the Department of Electrical and Electronic Engineering Science at the University of Johannesburg (Project Investigation (Electrical) 4B). It exists to demonstrate and evaluate engineering concepts for assessment and research.</p>
            <p>The University of Johannesburg is named only as the institution at which the work was carried out. The system is not a product of the university, and the university has not endorsed, certified or approved it for any use.</p>
          </div>

          <div class="doc-section">
            <span class="eyebrow">02 · Intended use</span>
            <h2 class="card-title">Not intended for public or immediate use</h2>
            <ul>
              <li>The system has not been certified, approved or independently tested as a fire detection, alarm or suppression system, and has not been assessed against SANS 10139 or any other fire-safety standard.</li>
              <li>It must not be used as the sole, primary or replacement means of detecting fire or protecting life, property, data or equipment.</li>
              <li>It must not replace or interfere with any certified fire detection, alarm or suppression system already installed in a building or server room.</li>
              <li>It is intended only for supervised demonstration, testing and evaluation by the author and assessors.</li>
            </ul>
          </div>

          <div class="doc-section">
            <span class="eyebrow">03 · Suppression</span>
            <h2 class="card-title">Experimental suppression output</h2>
            <p>The prototype can switch a relay intended to operate a small suppression device or a stand-in. Water near energised electrical equipment can cause electric shock, short circuits and damage. The suppression output is a proof of concept only and must not be connected to a building's suppression system, a mains water supply or live equipment outside a supervised test.</p>
          </div>

          <div class="doc-section">
            <span class="eyebrow">04 · Accuracy and availability</span>
            <h2 class="card-title">Readings and alerts may be wrong, late or missing</h2>
            <ul>
              <li>Temperatures come from a low-resolution 32 × 24 thermal sensor and an ambient sensor, and may be inaccurate, especially for small or distant heat sources.</li>
              <li>The fire classification combines fixed temperature thresholds with an experimental machine-learning model trained on limited data. It can miss fires and raise false alarms.</li>
              <li>This dashboard depends on Wi-Fi, the internet and a cloud server. Alerts shown here may be delayed or may not arrive at all, and the dashboard can only display what the sensing unit reports.</li>
            </ul>
          </div>

          <div class="doc-section">
            <span class="eyebrow">05 · Data</span>
            <h2 class="card-title">Data collected</h2>
            <p>The system stores low-resolution thermal readings, ambient temperatures and event records on the project server for monitoring, testing and model training. At 32 × 24 pixels, people appear only as warm shapes. Data is used solely for this academic project and is not sold or shared with third parties.</p>
          </div>

          <div class="doc-section">
            <span class="eyebrow">06 · Liability</span>
            <h2 class="card-title">No warranty</h2>
            <p>The system, its hardware designs, software and this dashboard are provided "as is", without warranty of any kind, express or implied, including fitness for a particular purpose. To the fullest extent permitted by law, the author accepts no liability for any loss, damage, injury or cost arising from the use of, or reliance on, the system or the information it displays. Anyone who chooses to use it does so at their own risk.</p>
          </div>

          <div class="doc-section">
            <span class="eyebrow">07 · Emergencies</span>
            <h2 class="card-title">In a real fire</h2>
            <p>Do not wait for this system. Leave the area, raise the alarm and call emergency services: <strong>10177</strong> (fire and ambulance, South Africa) or <strong>112</strong> from a mobile phone. Follow your site's emergency procedures.</p>
          </div>

          <div class="doc-section">
            <span class="eyebrow">08 · Contact</span>
            <h2 class="card-title">Help and maintenance</h2>
            <p>To report a fault, log a ticket or request maintenance, visit <a href="https://appelirhsa.co.za" target="_blank" rel="noopener">appelirhsa.co.za</a>.</p>
          </div>

          <p class="doc-updated">Last updated: 30 October 2026</p>
        </section>
      </div>"""

BACK = '          <a href="/" class="button">← Back to dashboard</a>'

# ---------------------------------------------------------------- Data capture
REC_BODY = """      <div class="capture-grid">
        <section class="card">
          <div class="card-head">
            <div>
              <span class="eyebrow">Live view</span>
              <h2 class="card-title">MLX90640 thermal camera</h2>
            </div>
          </div>
          <div class="thermal-wrap">
            <canvas id="heat" width="320" height="240" aria-label="Live thermal view"></canvas>
            <div id="nofeed" class="thermal-placeholder">Awaiting thermal frame from sensing unit</div>
          </div>
          <div class="scale-row">
            <span id="smin">— °C</span>
            <div class="thermal-scale"></div>
            <span id="smax">— °C</span>
          </div>
          <div class="kv-grid">
            <div class="kv"><span>Hottest pixel</span><strong id="vmax">—</strong></div>
            <div class="kv"><span>Frame average</span><strong id="vmean">—</strong></div>
            <div class="kv"><span>Ambient (DS18B20)</span><strong id="vamb">—</strong></div>
          </div>
          <p class="hint">Colours auto-scale to the current frame so small heat sources stay visible.</p>
        </section>

        <section class="card">
          <div class="card-head">
            <div>
              <span class="eyebrow">New session</span>
              <h2 class="card-title">Record a scene</h2>
            </div>
          </div>
          <div class="capture-form">
            <div class="label-choice" id="labels">
              <button type="button" data-l="normal">Normal<small>No fire, everyday heat</small></button>
              <button type="button" data-l="warning">Warning<small>Hot, not burning</small></button>
              <button type="button" data-l="fire">Fire<small>Open flame</small></button>
            </div>

            <div class="field">
              <label for="scene">Scene</label>
              <input type="text" id="scene" class="input" placeholder="e.g. candle_1m" autocomplete="off">
              <div class="chips" id="chips"></div>
              <p class="name-preview">Saved as <b id="sname">—</b></p>
            </div>

            <label class="field">Note (optional)
              <input type="text" id="note" class="input" placeholder="Distance, angle, room…" autocomplete="off">
            </label>

            <div class="field">
              <span>Duration</span>
              <div class="duration" id="dur">
                <button type="button" data-s="30">30 s</button>
                <button type="button" data-s="60" class="sel">60 s</button>
                <button type="button" data-s="120">2 min</button>
                <button type="button" data-s="0">Until stop</button>
              </div>
            </div>

            <button id="go" type="button" class="button button-primary button-lg button-block" disabled>Start recording</button>
            <div class="record-progress" id="prog" hidden><i id="progbar"></i></div>
            <p class="capture-msg" id="msg">Choose a label and a scene.</p>
            <button class="link-button" id="discard" type="button" hidden>Discard this recording</button>
          </div>
        </section>
      </div>

      <section class="card section">
        <div class="card-head">
          <div>
            <span class="eyebrow">Progress</span>
            <h2 class="card-title">Sessions per class</h2>
            <p class="card-sub" id="tgt"></p>
          </div>
        </div>
        <div class="class-progress" id="classes"></div>
      </section>

      <section class="card section">
        <div class="card-head">
          <div>
            <span class="eyebrow">Dataset</span>
            <h2 class="card-title">Recorded sessions</h2>
            <p class="card-sub">Click a preview to enlarge it · delete and re-record anything that looks wrong</p>
          </div>
          <a class="button" href="/record/download">Download dataset (.zip)</a>
        </div>
        <div class="table-scroll capture-table">
          <table>
            <thead><tr><th>Preview</th><th>Label</th><th>Session</th><th>Frames</th><th>Length</th><th>Max °C</th><th>Ambient</th><th>Note</th><th><span class="sr-only">Actions</span></th></tr></thead>
            <tbody id="rows"><tr><td colspan="9">No sessions yet.</td></tr></tbody>
          </table>
        </div>
      </section>"""

REC_ACTIONS = """          <span id="feedStatus" class="status status-off">No data</span>
          <a href="/" class="button">← Back to dashboard</a>"""

REC_SCRIPT = r"""<dialog id="dlg" class="preview-dialog"><img id="dlgimg" alt="Session preview"></dialog>

<script>
'use strict';
const NEEDS_KEY = __NEEDS_KEY__;
const SCENES = {
  normal:  ['pc_load', 'router_tv', 'person', 'window_sun', 'room_empty', 'fridge_back', 'heater_far', 'lab_rack'],
  warning: ['mug', 'kettle', 'hairdryer', 'iron', 'pan_warm', 'heater_near', 'soldering'],
  fire:    ['candle_05m', 'candle_1m', 'candle_2m', 'candle_3m', 'candles_multi', 'lighter', 'gas_stove', 'paper_tray', 'braai'],
};
let label = null, seconds = 60, sessions = [], recording = false, key = '';
try { key = localStorage.getItem('recordKey') || ''; } catch (e) {}
const $ = id => document.getElementById(id);

async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (NEEDS_KEY) headers['X-Record-Key'] = key;
  const r = await fetch(path, { ...opts, headers });
  if (r.status === 401) {
    key = prompt('Recording key:') || '';
    try { localStorage.setItem('recordKey', key); } catch (e) {}
    return api(path, opts);
  }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || r.statusText);
  return j;
}

/* JET colour map, same as the dashboard */
function jet(t) {
  const x = Math.max(0, Math.min(1, t));
  const c = s => Math.round(255 * Math.max(0, Math.min(1, 1.5 - Math.abs(4 * x - s))));
  return [c(3), c(2), c(1)];
}
const off = document.createElement('canvas'); off.width = 32; off.height = 24;
const octx = off.getContext('2d'), img = octx.createImageData(32, 24);
const ctx = $('heat').getContext('2d');
function draw(frame) {
  let mn = Infinity, mx = -Infinity, sum = 0, n = 0, mi = 0;
  frame.forEach((v, i) => { if (v > -200) { if (v < mn) mn = v; if (v > mx) { mx = v; mi = i; } sum += v; n++; } });
  const span = Math.max(mx - mn, 2);
  frame.forEach((v, i) => img.data.set([...jet((v - mn) / span), 255], i * 4));
  octx.putImageData(img, 0, 0);
  ctx.imageSmoothingEnabled = true; ctx.drawImage(off, 0, 0, 320, 240);
  const x = (mi % 32 + .5) * 10, y = (Math.floor(mi / 32) + .5) * 10;
  ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.beginPath();
  ctx.moveTo(x - 10, y); ctx.lineTo(x + 10, y); ctx.moveTo(x, y - 10); ctx.lineTo(x, y + 10); ctx.stroke();
  $('smin').textContent = mn.toFixed(1) + ' °C'; $('smax').textContent = mx.toFixed(1) + ' °C';
  $('vmax').textContent = mx.toFixed(1) + ' °C'; $('vmean').textContent = (sum / n).toFixed(1) + ' °C';
}

/* Form */
function slug(s) { return s.trim().toLowerCase().replace(/[^a-z0-9_\-]+/g, '_').replace(/^_+|_+$/g, ''); }
function nextName() {
  const scene = slug($('scene').value);
  if (!label || !scene) return null;
  const used = new Set(sessions.filter(s => s.label === label).map(s => s.session));
  for (let n = 1; n < 100; n++) { const nm = `${scene}_${String(n).padStart(2, '0')}`; if (!used.has(nm)) return nm; }
  return null;
}
function say(t, cls = '') { $('msg').textContent = t; $('msg').className = 'capture-msg ' + cls; }
function refreshForm() {
  const nm = nextName();
  $('sname').textContent = nm ? `${label}/${nm}` : '—';
  $('go').disabled = !recording && !nm;
  const m = $('msg');
  if (!recording && !m.classList.contains('err') && !m.classList.contains('ok'))
    m.textContent = nm ? 'Set up the scene, then press Start.' : 'Choose a label and a scene.';
}
$('labels').onclick = e => {
  const b = e.target.closest('button'); if (!b || recording) return;
  label = b.dataset.l;
  document.querySelectorAll('#labels button').forEach(x => x.classList.toggle('sel', x === b));
  $('chips').replaceChildren(...SCENES[label].map(s => {
    const c = document.createElement('button'); c.type = 'button'; c.className = 'chip'; c.dataset.s = s; c.textContent = s; return c;
  }));
  say(''); refreshForm();
};
$('chips').onclick = e => { const c = e.target.closest('.chip'); if (c) { $('scene').value = c.dataset.s; say(''); refreshForm(); } };
$('scene').oninput = () => { say(''); refreshForm(); };
$('dur').onclick = e => {
  const b = e.target.closest('button'); if (!b || recording) return;
  seconds = +b.dataset.s;
  document.querySelectorAll('#dur button').forEach(x => x.classList.toggle('sel', x === b));
};
$('go').onclick = async () => {
  try {
    if (!recording) {
      const nm = nextName(); if (!nm) return;
      await api('/record/start', { method: 'POST', body: JSON.stringify({ label, session: nm, seconds, note: $('note').value }) });
      say('');
    } else {
      await api('/record/stop', { method: 'POST' });
    }
    poll(); loadSessions();
  } catch (err) { say(err.message, 'err'); }
};
$('discard').onclick = async () => {
  if (!confirm('Discard this recording? Nothing will be saved.')) return;
  await api('/record/discard', { method: 'POST' }); say('Recording discarded.'); poll();
};

/* Polling */
let lastSaved = null;
async function poll() {
  let s; try { s = await (await fetch('/record/status', { cache: 'no-store' })).json(); } catch (e) { return; }
  const live = s.live_age !== null && s.live_age < 15;
  $('nofeed').hidden = live;
  if (s.frame) draw(s.frame);
  $('vamb').textContent = s.ambient == null ? '—' : s.ambient.toFixed(1) + ' °C';

  recording = s.active;
  const fs = $('feedStatus');
  fs.textContent = recording ? 'Recording' : live ? 'Sensor online' : 'No recent data';
  fs.className = 'status ' + (recording ? 'status-rec' : live ? 'status-on' : 'status-off');
  $('go').textContent = recording ? 'Stop & save' : 'Start recording';
  $('go').className = 'button button-lg button-block ' + (recording ? 'button-danger' : 'button-primary');
  $('prog').hidden = !recording; $('discard').hidden = !recording;
  if (recording) {
    $('go').disabled = false;
    $('progbar').style.width = (s.duration ? Math.min(100, s.elapsed / s.duration * 100) : 100) + '%';
    say(`Recording ${s.label}/${s.session} — ${s.frames} frames, ${s.elapsed.toFixed(0)}` + (s.duration ? ` / ${s.duration} s` : ' s'));
  } else {
    if (s.error) say(s.error, 'err');
    const sv = s.last_saved && JSON.stringify(s.last_saved);
    if (sv && sv !== lastSaved) {
      if (lastSaved !== null) say(`Saved ${s.last_saved.label}/${s.last_saved.session} (${s.last_saved.frames} frames). Check its preview below.`, 'ok');
      lastSaved = sv; loadSessions();
    }
    refreshForm();
  }
}

function cell(row, text) { const c = row.insertCell(); c.textContent = text; return c; }
async function loadSessions() {
  const j = await (await fetch('/record/sessions', { cache: 'no-store' })).json();
  sessions = j.sessions;
  $('tgt').textContent = `Target: ${j.target} sessions per class`;
  const box = $('classes'); box.replaceChildren();
  for (const l of ['normal', 'warning', 'fire']) {
    const d = document.createElement('div');
    const top = document.createElement('div'); top.className = 'class-top';
    const name = document.createElement('span'); name.textContent = l[0].toUpperCase() + l.slice(1);
    const count = document.createElement('strong'); count.textContent = `${j.counts[l]} / ${j.target}`;
    top.append(name, count);
    const bar = document.createElement('div'); bar.className = 'bar';
    const fill = document.createElement('i'); fill.className = 'bar-' + l;
    fill.style.width = Math.min(100, j.counts[l] / j.target * 100) + '%'; bar.append(fill);
    const sm = document.createElement('small'); sm.textContent = `${j.frames[l]} frames`;
    d.append(top, bar, sm); box.append(d);
  }
  const body = $('rows'); body.replaceChildren();
  if (!sessions.length) { const r = body.insertRow(); const c = r.insertCell(); c.colSpan = 9; c.textContent = 'No sessions yet.'; refreshForm(); return; }
  for (const s of sessions.slice().reverse()) {
    const r = body.insertRow();
    const im = document.createElement('img'); im.className = 'thumb'; im.loading = 'lazy'; im.alt = `Preview of ${s.session}`;
    im.src = `/record/preview/${s.label}/${s.session}.png?${s.frames}`; r.insertCell().append(im);
    const tag = document.createElement('span'); tag.className = `tag tag-${s.label}`; tag.textContent = s.label.toUpperCase(); r.insertCell().append(tag);
    cell(r, s.session); cell(r, s.frames); cell(r, s.seconds + ' s'); cell(r, s.max_c);
    cell(r, s.ambient_c ?? '—'); cell(r, s.note || '');
    const del = document.createElement('button'); del.type = 'button'; del.className = 'button small-button';
    del.textContent = 'Delete'; del.dataset.l = s.label; del.dataset.s = s.session; r.insertCell().append(del);
  }
  refreshForm();
}
$('rows').onclick = async e => {
  const im = e.target.closest('img.thumb');
  if (im) { $('dlgimg').src = im.src; $('dlg').showModal(); return; }
  const d = e.target.closest('button[data-s]');
  if (d && confirm(`Delete ${d.dataset.l}/${d.dataset.s}?`)) {
    try { await api(`/record/sessions/${d.dataset.l}/${d.dataset.s}`, { method: 'DELETE' }); loadSessions(); }
    catch (err) { say(err.message, 'err'); }
  }
};
$('dlg').onclick = () => $('dlg').close();

loadSessions(); poll(); setInterval(poll, 1000);
</script>
"""


def main():
    pages = {
        "index.html": page(
            "Early Fire Detection and Monitoring System", "dashboard",
            header("Operations · Environmental safety", "Early Fire Detection and Monitoring System",
                   "Real-time thermal surveillance and alarm management", DASH_ACTIONS),
            DASH_BODY,
            f'<script src="/static/app.js?v={ASSET_VERSION}"></script>\n'),
        "incidents.html": page(
            "Incidents · Early Fire Detection", "incidents",
            header("Audit · Response", "Incidents",
                   "Every fire or rapid-rise event, with a report you can print or export", INC_ACTIONS),
            INC_BODY,
            f'<script src="/static/shared.js?v={ASSET_VERSION}"></script>\n'
            f'<script src="/static/incidents.js?v={ASSET_VERSION}"></script>\n'),
        "report.html": page(
            "Incident report · Early Fire Detection", "incidents",
            header("Audit · Incident report", "Incident report",
                   "Timeline, peak thermal frame and temperature record", REPORT_ACTIONS),
            REPORT_BODY,
            f'<script src="/static/shared.js?v={ASSET_VERSION}"></script>\n'
            f'<script src="/static/report.js?v={ASSET_VERSION}"></script>\n'),
        "health.html": page(
            "System health · Early Fire Detection", "health",
            header("Operations · Diagnostics", "System health",
                   "Device link, data flow, sensors, availability and storage", BACK),
            HEALTH_BODY,
            f'<script src="/static/shared.js?v={ASSET_VERSION}"></script>\n'
            f'<script src="/static/health.js?v={ASSET_VERSION}"></script>\n'),
        "settings.html": page(
            "Settings · Early Fire Detection", "settings",
            header("Preferences", "Settings", "Appearance and display options for this browser", BACK),
            SETTINGS_BODY, SETTINGS_SCRIPT),
        "disclaimer.html": page(
            "Legal Disclaimer · Early Fire Detection", "disclaimer",
            header("Legal · Academic use", "Legal disclaimer", "Please read before using or relying on this system", BACK),
            DISC_BODY),
        "record_panel.html": page(
            "Data Capture · Early Fire Detection", "record",
            header("Data · Model training", "Data capture",
                   "Record labelled thermal sessions for training the fire classification model", REC_ACTIONS),
            REC_BODY, REC_SCRIPT),
    }
    for name, html in pages.items():
        (OUT / name).write_text(html, encoding="utf-8", newline="\n")
        print("wrote", name, len(html))


if __name__ == "__main__":
    main()
    
