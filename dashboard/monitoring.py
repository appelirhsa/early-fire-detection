"""Incident log, rate-of-rise alarm and system health for the monitoring backend.

* Rate of rise: the hottest-pixel temperature is tracked over a sliding window.
  Like an EN 54-5 class "R" heat detector, a fast rise raises an early alarm
  even before the fixed 65 C fire threshold is reached.
* Incidents: every FIRE (reported by the device) or rate-of-rise alarm opens an
  incident. The server records when it started, the peak temperature and a
  snapshot of the thermal frame at the peak, when suppression was active, and
  when the condition cleared. Each incident has a printable report and the whole
  log can be exported as CSV.
* Health: device link, frame rate, sensor status, storage and availability.

The rate-of-rise alarm is an advisory computed by this dashboard. The device
remains the source of truth for the FIRE classification and for suppression.
"""
import csv
import io
import json
import os
import sqlite3
import time
from collections import deque
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "alarm_events.sqlite3"

ROR_WINDOW_S = float(os.environ.get("ROR_WINDOW_S", "30"))           # slope measured over this window
ROR_ALARM_C_PER_MIN = float(os.environ.get("ROR_ALARM_C_PER_MIN", "8"))
ROR_MIN_TEMP_C = float(os.environ.get("ROR_MIN_TEMP_C", "40"))       # ignore rises below this (people, sunlight)
ROR_HOLD_S = float(os.environ.get("ROR_HOLD_S", "5"))                # rise must persist this long
INCIDENT_CLEAR_S = float(os.environ.get("INCIDENT_CLEAR_S", "10"))   # quiet time before an incident closes
DEVICE_ONLINE_S = 6.0
SESSION_GAP_S = 30.0

router = APIRouter()
SERVER_STARTED = time.time()


def _db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def initialize():
    with _db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at REAL NOT NULL,
            ended_at REAL,
            trigger TEXT NOT NULL,
            warning_at REAL,
            ror_at REAL,
            fire_at REAL,
            fan_on_at REAL,
            fan_off_at REAL,
            peak_c REAL,
            peak_at REAL,
            ambient_c REAL,
            max_ror REAL,
            snapshot TEXT,
            updated_at REAL,
            note TEXT
        )""")
        # An incident still open from before a restart is closed at its last update.
        db.execute(
            "UPDATE incidents SET ended_at = COALESCE(updated_at, started_at), "
            "note = 'Closed automatically after a server restart' WHERE ended_at IS NULL"
        )


# ----------------------------------------------------------------------------- rate of rise
class RateOfRise:
    """Least-squares slope of the hottest pixel over the last ROR_WINDOW_S seconds."""

    def __init__(self):
        self.samples = deque()
        self.rate = None          # C per minute, None until enough data
        self.alarm = False
        self.alarm_since = None
        self._above_since = None
        self._below_since = None

    def add(self, t, max_c):
        self.samples.append((t, max_c))
        while self.samples and t - self.samples[0][0] > ROR_WINDOW_S:
            self.samples.popleft()

        if len(self.samples) < 5 or t - self.samples[0][0] < ROR_WINDOW_S / 3:
            self.rate = None
        else:
            n = len(self.samples)
            mt = sum(s[0] for s in self.samples) / n
            mv = sum(s[1] for s in self.samples) / n
            num = sum((s[0] - mt) * (s[1] - mv) for s in self.samples)
            den = sum((s[0] - mt) ** 2 for s in self.samples)
            self.rate = num / den * 60 if den > 0 else None

        rising = (self.rate is not None and self.rate >= ROR_ALARM_C_PER_MIN
                  and max_c >= ROR_MIN_TEMP_C)
        calm = self.rate is None or self.rate < ROR_ALARM_C_PER_MIN / 2

        if rising:
            self._below_since = None
            self._above_since = self._above_since or t
            if not self.alarm and t - self._above_since >= ROR_HOLD_S:
                self.alarm = True
                self.alarm_since = t
        else:
            self._above_since = None
            if self.alarm and calm:
                self._below_since = self._below_since or t
                if t - self._below_since >= ROR_HOLD_S:
                    self.alarm = False
                    self.alarm_since = None
            else:
                self._below_since = None
        return self.rate, self.alarm


# ----------------------------------------------------------------------------- incidents
class IncidentTracker:
    def __init__(self):
        self.state = None
        self.state_since = None
        self.warning_since = None
        self.fan_on = False
        self.fan_on_since = None
        self.ror_alarm = False
        self.open = None            # dict for the open incident
        self.clear_since = None
        self._last_write = 0.0

    # -- inputs
    def on_telemetry(self, t, state, fan_on):
        if state != self.state:
            self.state_since = t
            if state == "WARNING":
                self.warning_since = t
            elif state == "NORMAL":
                self.warning_since = None
            self.state = state
        if fan_on and not self.fan_on:
            self.fan_on_since = t
        if not fan_on:
            self.fan_on_since = None
        if self.open is not None:
            if fan_on:
                if self.open["fan_on_at"] is None:
                    self.open["fan_on_at"] = self.fan_on_since or t
                self.open["fan_off_at"] = None
            if not fan_on and self.fan_on and self.open["fan_on_at"] is not None:
                self.open["fan_off_at"] = t
        self.fan_on = fan_on
        self._evaluate(t)

    def on_frame(self, t, max_c, ambient_c, pixels, ror_rate, ror_alarm):
        self.ror_alarm = ror_alarm
        if self.open is not None:
            inc = self.open
            if inc["peak_c"] is None or max_c > inc["peak_c"]:
                inc["peak_c"] = max_c
                inc["peak_at"] = t
                inc["snapshot"] = [round(v, 1) for v in pixels]
            if ror_rate is not None and (inc["max_ror"] is None or ror_rate > inc["max_ror"]):
                inc["max_ror"] = ror_rate
            if ror_alarm and inc["ror_at"] is None:
                inc["ror_at"] = t
                self._add_trigger("Rate of rise")
        self._evaluate(t, max_c, ambient_c, pixels, ror_rate)

    # -- logic
    def _active(self):
        return self.state == "FIRE" or self.ror_alarm

    def _add_trigger(self, name):
        parts = self.open["trigger"].split(" + ")
        if name not in parts:
            self.open["trigger"] = " + ".join(parts + [name])

    def _evaluate(self, t, max_c=None, ambient_c=None, pixels=None, ror_rate=None):
        if self._active():
            self.clear_since = None
            if self.open is None:
                self._open(t, max_c, ambient_c, pixels, ror_rate)
            if self.state == "FIRE" and self.open["fire_at"] is None:
                self.open["fire_at"] = t
                self._add_trigger("Fixed temperature")
        elif self.open is not None:
            self.clear_since = self.clear_since or t
            if t - self.clear_since >= INCIDENT_CLEAR_S:
                self._close(self.clear_since)
                return
        if self.open is not None and t - self._last_write >= 2:
            self._write()

    def _open(self, t, max_c, ambient_c, pixels, ror_rate):
        trigger = "Fixed temperature" if self.state == "FIRE" else "Rate of rise"
        self.open = {
            "id": None,
            "started_at": t,
            "ended_at": None,
            "trigger": trigger,
            "warning_at": self.warning_since,
            "ror_at": t if self.ror_alarm else None,
            "fire_at": t if self.state == "FIRE" else None,
            "fan_on_at": self.fan_on_since if self.fan_on else None,
            "fan_off_at": None,
            "peak_c": max_c,
            "peak_at": t if max_c is not None else None,
            "ambient_c": ambient_c,
            "max_ror": ror_rate,
            "snapshot": [round(v, 1) for v in pixels] if pixels else None,
            "note": None,
        }
        with _db() as db:
            cur = db.execute(
                "INSERT INTO incidents (started_at, trigger, updated_at) VALUES (?, ?, ?)",
                (t, trigger, t))
            self.open["id"] = cur.lastrowid
        self._write()

    def _write(self):
        inc = self.open
        now = time.time()
        with _db() as db:
            db.execute(
                """UPDATE incidents SET ended_at=?, trigger=?, warning_at=?, ror_at=?, fire_at=?,
                   fan_on_at=?, fan_off_at=?, peak_c=?, peak_at=?, ambient_c=?, max_ror=?,
                   snapshot=?, updated_at=? WHERE id=?""",
                (inc["ended_at"], inc["trigger"], inc["warning_at"], inc["ror_at"], inc["fire_at"],
                 inc["fan_on_at"], inc["fan_off_at"], inc["peak_c"], inc["peak_at"], inc["ambient_c"],
                 inc["max_ror"], json.dumps(inc["snapshot"]) if inc["snapshot"] else None, now,
                 inc["id"]))
        self._last_write = now

    def _close(self, t):
        self.open["ended_at"] = t
        if self.fan_on and self.open["fan_on_at"] is not None and self.open["fan_off_at"] is None:
            self.open["note"] = "Suppression still active when the incident cleared"
        self._write()
        if self.open.get("note"):
            with _db() as db:
                db.execute("UPDATE incidents SET note=? WHERE id=?", (self.open["note"], self.open["id"]))
        self.open = None
        self.clear_since = None

    @property
    def open_id(self):
        return self.open["id"] if self.open else None


# ----------------------------------------------------------------------------- health
class Health:
    def __init__(self):
        self.frame_times = deque()
        self.frames_total = 0
        self.telemetry_total = 0
        self.last_frame_at = None
        self.last_telemetry_at = None
        self.session_started = None
        self.sessions = 0
        self.latest = {}
        self.device_info = {}
        self.viewer_count = lambda: 0
        self._avail_cache = (0.0, None)

    def on_frame(self, t, frame_stats):
        if self.last_frame_at is None or t - self.last_frame_at > SESSION_GAP_S:
            self.session_started = t
            self.sessions += 1
        self.last_frame_at = t
        self.frames_total += 1
        self.frame_times.append(t)
        while self.frame_times and t - self.frame_times[0] > 60:
            self.frame_times.popleft()
        self.latest.update(frame_stats)

    def on_telemetry(self, t, data):
        self.last_telemetry_at = t
        self.telemetry_total += 1
        self.latest["state"] = data.get("state")
        self.latest["suppression_active"] = data.get("suppression_active")
        for key in ("firmware", "uptime_s", "rssi_dbm", "free_memory"):
            if data.get(key) is not None:
                self.device_info[key] = data[key]

    def _availability(self, now):
        cached_at, value = self._avail_cache
        if value is not None and now - cached_at < 30:
            return value
        since = now - 86400
        with _db() as db:
            earliest = db.execute("SELECT MIN(ts) FROM readings").fetchone()[0]
            count = db.execute("SELECT COUNT(*) FROM readings WHERE ts >= ?", (since,)).fetchone()[0]
            gaps = db.execute(
                "SELECT COUNT(*), MAX(gap) FROM (SELECT ts - LAG(ts) OVER (ORDER BY ts) AS gap "
                "FROM readings WHERE ts >= ?) WHERE gap > ?", (since, SESSION_GAP_S)).fetchone()
        window = now - max(since, earliest) if earliest else 0
        value = {
            "window_s": round(window),
            "percent": round(min(100.0, 100.0 * count / window), 1) if window > 60 else None,
            "outages": gaps[0] or 0,
            "longest_outage_s": round(gaps[1]) if gaps[1] else 0,
        }
        self._avail_cache = (now, value)
        return value

    def snapshot(self, ror, incidents):
        now = time.time()
        times = list(self.frame_times)
        intervals = [b - a for a, b in zip(times, times[1:])]
        fps = (len(times) - 1) / (times[-1] - times[0]) if len(times) > 2 and times[-1] > times[0] else None
        online = self.last_frame_at is not None and now - self.last_frame_at < DEVICE_ONLINE_S
        with _db() as db:
            readings = db.execute("SELECT COUNT(*), MIN(ts) FROM readings").fetchone()
            inc_total = db.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
            inc_24h = db.execute("SELECT COUNT(*) FROM incidents WHERE started_at >= ?",
                                 (now - 86400,)).fetchone()[0]
        try:
            db_size = DB_PATH.stat().st_size
        except OSError:
            db_size = None
        return {
            "now": now,
            "server": {
                "started_at": SERVER_STARTED,
                "uptime_s": round(now - SERVER_STARTED),
                "viewers": self.viewer_count(),
                "db_size_bytes": db_size,
                "readings_stored": readings[0],
                "oldest_reading": readings[1],
                "incidents_total": inc_total,
                "incidents_24h": inc_24h,
                "open_incident": incidents.open_id,
            },
            "device": {
                "online": online,
                "last_frame_at": self.last_frame_at,
                "last_frame_age_s": None if self.last_frame_at is None else round(now - self.last_frame_at, 1),
                "last_telemetry_at": self.last_telemetry_at,
                "last_telemetry_age_s": None if self.last_telemetry_at is None else round(now - self.last_telemetry_at, 1),
                "connected_since": self.session_started if online else None,
                "sessions_since_start": self.sessions,
                "frame_rate_fps": None if fps is None else round(fps, 2),
                "frame_interval_avg_ms": round(1000 * sum(intervals) / len(intervals)) if intervals else None,
                "frame_interval_max_ms": round(1000 * max(intervals)) if intervals else None,
                "frames_total": self.frames_total,
                "telemetry_total": self.telemetry_total,
                "state": self.latest.get("state"),
                "suppression_active": self.latest.get("suppression_active"),
                "reported": self.device_info,
            },
            "sensors": {
                "thermal_max_c": self.latest.get("max_c"),
                "thermal_min_c": self.latest.get("min_c"),
                "thermal_invalid_pixels": self.latest.get("invalid_pixel_count"),
                "ambient_c": self.latest.get("ambient_c"),
            },
            "rate_of_rise": {
                "c_per_min": None if ror.rate is None else round(ror.rate, 1),
                "alarm": ror.alarm,
                "threshold_c_per_min": ROR_ALARM_C_PER_MIN,
                "window_s": ROR_WINDOW_S,
                "min_temp_c": ROR_MIN_TEMP_C,
            },
            "availability_24h": self._availability(now),
        }


ror = RateOfRise()
incidents = IncidentTracker()
health = Health()


def on_frame(data):
    """Called by the server for every accepted frame. Adds rate-of-rise fields to `data`."""
    t = time.time()
    pixels = data["pixels"]
    rate, alarm = ror.add(t, data["max_c"])
    health.on_frame(t, {
        "max_c": data["max_c"], "min_c": data["min_c"],
        "invalid_pixel_count": data["invalid_pixel_count"], "ambient_c": data.get("ambient_c"),
    })
    incidents.on_frame(t, data["max_c"], data.get("ambient_c"), pixels, rate, alarm)
    data["ror_c_per_min"] = None if rate is None else round(rate, 1)
    data["ror_alarm"] = alarm
    data["ror_threshold"] = ROR_ALARM_C_PER_MIN
    data["incident_id"] = incidents.open_id


def on_telemetry(data):
    t = time.time()
    health.on_telemetry(t, data)
    incidents.on_telemetry(t, data["state"], bool(data.get("suppression_active")))
    data["incident_id"] = incidents.open_id


# ----------------------------------------------------------------------------- API
INCIDENT_FIELDS = ("id", "started_at", "ended_at", "trigger", "warning_at", "ror_at", "fire_at",
                   "fan_on_at", "fan_off_at", "peak_c", "peak_at", "ambient_c", "max_ror", "note")


def _row(r, with_snapshot=False):
    d = {k: r[k] for k in INCIDENT_FIELDS}
    end = d["ended_at"] or time.time()
    d["open"] = d["ended_at"] is None
    d["duration_s"] = round(end - d["started_at"], 1)
    # 0 = suppression was already running (e.g. started at WARNING) when the incident opened
    d["fan_response_s"] = (max(0.0, round(d["fan_on_at"] - d["started_at"], 1))
                           if d["fan_on_at"] is not None else None)
    d["warning_lead_s"] = (round(d["started_at"] - d["warning_at"], 1)
                           if d["warning_at"] is not None else None)
    d["ror_lead_s"] = (round(d["fire_at"] - d["ror_at"], 1)
                       if d["ror_at"] is not None and d["fire_at"] is not None
                       and d["ror_at"] < d["fire_at"] else None)
    if with_snapshot:
        d["snapshot"] = json.loads(r["snapshot"]) if r["snapshot"] else None
    return d


@router.get("/incidents")
async def incidents_page():
    return FileResponse(ROOT / "static" / "incidents.html")


@router.get("/incidents/report")
async def incident_report_page():
    return FileResponse(ROOT / "static" / "report.html")


@router.get("/health")
async def health_page():
    return FileResponse(ROOT / "static" / "health.html")


@router.get("/api/incidents")
async def list_incidents(limit: int = 200):
    limit = max(1, min(limit, 1000))
    with _db() as db:
        rows = db.execute(f"SELECT {', '.join(INCIDENT_FIELDS)} FROM incidents "
                          "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return {"open_incident": incidents.open_id, "incidents": [_row(r) for r in rows]}


@router.get("/api/incidents.csv")
async def incidents_csv():
    with _db() as db:
        rows = db.execute(f"SELECT {', '.join(INCIDENT_FIELDS)} FROM incidents ORDER BY id").fetchall()

    def iso(v):
        return "" if v is None else time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(v))

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Incident", "Started", "Ended", "Duration (s)", "Trigger", "Peak max (C)",
                "Peak at", "Ambient at start (C)", "Max rate of rise (C/min)",
                "Warning lead time (s)", "Rate-of-rise lead over 65 C threshold (s)",
                "Fan/suppression response (s)", "Note"])
    for r in rows:
        d = _row(r)
        w.writerow([d["id"], iso(d["started_at"]), iso(d["ended_at"]), d["duration_s"], d["trigger"],
                    "" if d["peak_c"] is None else round(d["peak_c"], 1), iso(d["peak_at"]),
                    "" if d["ambient_c"] is None else round(d["ambient_c"], 1),
                    "" if d["max_ror"] is None else round(d["max_ror"], 1),
                    "" if d["warning_lead_s"] is None else d["warning_lead_s"],
                    "" if d["ror_lead_s"] is None else d["ror_lead_s"],
                    "" if d["fan_response_s"] is None else d["fan_response_s"],
                    d["note"] or ""])
    name = "incidents_" + time.strftime("%Y%m%d") + ".csv"
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/api/incidents/{incident_id}")
async def incident_detail(incident_id: int):
    with _db() as db:
        r = db.execute(f"SELECT {', '.join(INCIDENT_FIELDS)}, snapshot FROM incidents WHERE id=?",
                       (incident_id,)).fetchone()
        if r is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        d = _row(r, with_snapshot=True)
        start = (d["warning_at"] or d["started_at"]) - 60
        end = (d["ended_at"] or time.time()) + 60
        bucket = max(1.0, (end - start) / 600)
        pts = db.execute(
            "SELECT AVG(ts), MAX(max_c), AVG(ambient_c) FROM readings WHERE ts BETWEEN ? AND ? "
            "GROUP BY CAST((ts - ?) / ? AS INTEGER) ORDER BY 1",
            (start, end, start, bucket)).fetchall()
        prev_id = db.execute("SELECT MAX(id) FROM incidents WHERE id < ?", (incident_id,)).fetchone()[0]
        next_id = db.execute("SELECT MIN(id) FROM incidents WHERE id > ?", (incident_id,)).fetchone()[0]
    d["readings"] = [{"t": p[0], "max": p[1], "amb": p[2]} for p in pts]
    d["window"] = {"start": start, "end": end}
    d["prev_id"], d["next_id"] = prev_id, next_id
    d["ror_threshold"] = ROR_ALARM_C_PER_MIN
    return d


@router.get("/api/health")
async def health_api():
    return health.snapshot(ror, incidents)
    