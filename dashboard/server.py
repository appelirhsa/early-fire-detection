"""Early Fire Detection and Monitoring System - monitoring backend.

Receives measured data and device-reported state. Never commands suppression.
The device is the source of truth for classification; this server does not
infer a fire from thermal display values.
"""
import asyncio
import json
import math
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

import recording  # data-capture page at /record (labelled training data)
import monitoring  # incidents, rate-of-rise alarm, system health

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "alarm_events.sqlite3"
DEVICE_TOKEN = os.environ.get("DEVICE_API_TOKEN", "")

# Temperature history: one stored reading per second at most, kept for 90 days.
READINGS_MIN_INTERVAL_S = 1.0
READINGS_RETENTION_DAYS = int(os.environ.get("READINGS_RETENTION_DAYS", "90"))
_readings_state = {"last": 0.0, "purged": 0.0}

app = FastAPI(
    title="Early Fire Detection and Monitoring System",
    version="2.0"
)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
app.include_router(recording.router)
app.include_router(monitoring.router)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def require_device_token(authorization):
    if DEVICE_TOKEN and authorization != "Bearer " + DEVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Device authentication required")


def initialize_db():
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at TEXT NOT NULL,
            category TEXT NOT NULL,
            message TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS readings (
            ts REAL NOT NULL,
            max_c REAL,
            ambient_c REAL
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS readings_ts ON readings (ts)")


def record_event(category, message):
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "INSERT INTO events (recorded_at, category, message) VALUES (?, ?, ?)",
            (utc_now(), category, message),
        )


def record_reading(max_c, ambient_c):
    """Store the frame's hottest pixel and ambient temperature (throttled to 1 per second)."""
    now = time.time()
    if now - _readings_state["last"] < READINGS_MIN_INTERVAL_S:
        return
    _readings_state["last"] = now
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "INSERT INTO readings (ts, max_c, ambient_c) VALUES (?, ?, ?)",
            (now, max_c, ambient_c),
        )
        if now - _readings_state["purged"] > 3600:
            db.execute(
                "DELETE FROM readings WHERE ts < ?",
                (now - READINGS_RETENTION_DAYS * 86400,),
            )
            _readings_state["purged"] = now


def recent_events():
    with sqlite3.connect(DB_PATH) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT id, recorded_at, category, message FROM events "
            "ORDER BY id DESC LIMIT 100"
        ).fetchall()
    return [dict(row) for row in rows]


class ThermalFrame(BaseModel):
    width: Literal[32] = 32
    height: Literal[24] = 24
    pixels: list[float] = Field(min_length=768, max_length=768)
    ambient_c: float | None = None
    sensor_temperature_c: float | None = None
    source: Literal["simulator", "hardware"] = "hardware"

    @model_validator(mode="before")
    @classmethod
    def support_existing_frame_payload(cls, value):
        if isinstance(value, dict) and "frame" in value:
            value = value.copy()
            if "pixels" in value:
                raise ValueError("Send frame or pixels, not both")
            value["pixels"] = value.pop("frame")
        return value

    @field_validator("pixels")
    @classmethod
    def check_pixels(cls, values):
        if not all(math.isfinite(v) for v in values):
            raise ValueError("All pixels must be finite")
        if not any(v > -200 for v in values):
            raise ValueError("No valid pixels in frame")
        return values

    @field_validator("ambient_c", "sensor_temperature_c")
    @classmethod
    def check_temperature(cls, value):
        if value is not None and not math.isfinite(value):
            raise ValueError("Temperature must be finite")
        return value


class Telemetry(BaseModel):
    state: Literal["NORMAL", "WARNING", "FIRE"]
    max_thermal_c: float | None = None
    ambient_c: float | None = None
    suppression_active: bool = False
    classification_source: str = "firmware"
    # Optional device details for the health page (sent only if the firmware reports them)
    firmware: str | None = None
    uptime_s: float | None = None
    rssi_dbm: float | None = None
    free_memory: int | None = None

    @field_validator("max_thermal_c", "ambient_c")
    @classmethod
    def check_temperature(cls, value):
        if value is not None and not math.isfinite(value):
            raise ValueError("Temperature must be finite")
        return value


class LiveState:
    def __init__(self):
        self.connections = set()
        self.latest_frame = None
        self.latest_telemetry = None
        self.frames = 0
        self.telemetry = 0
        self.lock = asyncio.Lock()

    async def broadcast(self, payload):
        message = json.dumps(payload)
        for socket in tuple(self.connections):
            try:
                await socket.send_text(message)
            except Exception:
                self.connections.discard(socket)


live = LiveState()
initialize_db()
monitoring.initialize()
monitoring.health.viewer_count = lambda: len(live.connections)


@app.get("/")
async def dashboard():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/disclaimer")
async def disclaimer():
    return FileResponse(ROOT / "static" / "disclaimer.html")


@app.get("/settings")
async def settings():
    return FileResponse(ROOT / "static" / "settings.html")


@app.get("/api/status")
async def status():
    return {
        "server": "online",
        "frames_received": live.frames,
        "telemetry_received": live.telemetry,
        "last_frame_at": live.latest_frame.get("received_at") if live.latest_frame else None,
        "last_telemetry_at": live.latest_telemetry.get("received_at") if live.latest_telemetry else None,
        "connected_viewers": len(live.connections),
    }


@app.get("/api/history")
async def history(start: float | None = None, end: float | None = None, points: int = 400):
    """Stored temperature history between start and end (Unix seconds), condensed to
    about `points` buckets. Each bucket keeps the HOTTEST pixel reading (so short
    spikes are never averaged away) and the average ambient temperature."""
    now = time.time()
    end = now if end is None else end
    start = end - 3600 if start is None else start
    if end <= start:
        raise HTTPException(status_code=400, detail="end must be after start")
    if end - start > 366 * 86400:
        raise HTTPException(status_code=400, detail="range longer than one year")
    points = max(10, min(points, 2000))
    bucket = max(1.0, (end - start) / points)
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute(
            "SELECT CAST((ts - ?) / ? AS INTEGER) AS b, AVG(ts), MAX(max_c), AVG(ambient_c) "
            "FROM readings WHERE ts >= ? AND ts <= ? GROUP BY b ORDER BY b",
            (start, bucket, start, end),
        ).fetchall()
        earliest = db.execute("SELECT MIN(ts) FROM readings").fetchone()[0]
    return {
        "start": start,
        "end": end,
        "bucket_s": bucket,
        "earliest": earliest,
        "points": [
            {
                "t": round(r[1], 3),
                "max": None if r[2] is None else round(r[2], 2),
                "amb": None if r[3] is None else round(r[3], 2),
            }
            for r in rows
        ],
    }


@app.get("/api/events")
async def events():
    return {"events": recent_events()}


@app.post("/api/frame", status_code=202)
async def receive_frame(
    frame: ThermalFrame,
    authorization: str | None = Header(default=None)
):
    require_device_token(authorization)

    pixels = [value for value in frame.pixels if value > -200]
    data = frame.model_dump()
    data.update({
        "received_at": utc_now(),
        "max_c": max(pixels),
        "min_c": min(pixels),
        "mean_c": sum(pixels) / len(pixels),
        "invalid_pixel_count": 768 - len(pixels),
    })

    recording.add_frame(data)  # saves the frame if a capture session is running
    record_reading(data["max_c"], frame.ambient_c)  # temperature history for the chart
    monitoring.on_frame(data)  # rate of rise, incidents, health (adds ror_* fields)

    async with live.lock:
        previous_frame = live.latest_frame
        if data["ror_alarm"] and not (previous_frame and previous_frame.get("ror_alarm")):
            record_event("RATE OF RISE",
                         f"Rapid temperature rise: {data['ror_c_per_min']} °C/min "
                         f"(alarm at {data['ror_threshold']:g} °C/min)")
            await live.broadcast({"type": "events", "events": recent_events()})
        elif previous_frame and previous_frame.get("ror_alarm") and not data["ror_alarm"]:
            record_event("RATE OF RISE", "Temperature rise returned to normal")
            await live.broadcast({"type": "events", "events": recent_events()})
        live.frames += 1
        data["sequence"] = live.frames
        live.latest_frame = data
        await live.broadcast({"type": "frame", **data})

    return {"accepted": True, "sequence": live.frames}


@app.post("/api/telemetry", status_code=202)
async def receive_telemetry(
    telemetry: Telemetry,
    authorization: str | None = Header(default=None)
):
    require_device_token(authorization)

    data = telemetry.model_dump()
    data["received_at"] = utc_now()
    monitoring.on_telemetry(data)  # incidents and health

    async with live.lock:
        previous = live.latest_telemetry

        if previous is None or previous["state"] != data["state"]:
            record_event(data["state"], "Device reported " + data["state"])

        if previous is None or previous["suppression_active"] != data["suppression_active"]:
            record_event(
                "SUPPRESSION",
                "Suppression reported ACTIVE"
                if data["suppression_active"]
                else "Suppression reported INACTIVE",
            )

        live.telemetry += 1
        data["sequence"] = live.telemetry
        live.latest_telemetry = data

        await live.broadcast({"type": "telemetry", **data})
        await live.broadcast({"type": "events", "events": recent_events()})

    return {"accepted": True, "sequence": live.telemetry}


@app.websocket("/ws/thermal")
async def thermal_websocket(socket: WebSocket):
    await socket.accept()
    live.connections.add(socket)

    try:
        if live.latest_frame:
            await socket.send_json({"type": "frame", **live.latest_frame})

        if live.latest_telemetry:
            await socket.send_json({"type": "telemetry", **live.latest_telemetry})

        await socket.send_json({"type": "events", "events": recent_events()})

        while True:
            await socket.receive_text()

    except WebSocketDisconnect:
        pass

    finally:
        live.connections.discard(socket)
        