
"""
FireSense - Early Fire Detection and Suppression System

Live MLX90640 Thermal Dashboard Server

Hardware:
- Raspberry Pi Pico 2 W
- MLX90640 thermal camera (32 x 24)
- DS18B20 temperature sensor

Features:
- Receive thermal camera frames via HTTP
- Receive temperature and system telemetry
- Broadcast frames to browsers using WebSockets
- Serve the HTML, CSS and JavaScript dashboard

This server only monitors and displays sensor data.
It does not control the fire suppression system.
"""

import asyncio
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import (
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect
)

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator
)


# ==========================================
# CONFIGURATION
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

FRAME_WIDTH = 32
FRAME_HEIGHT = 24
FRAME_PIXELS = FRAME_WIDTH * FRAME_HEIGHT


# ==========================================
# FASTAPI APPLICATION
# ==========================================

app = FastAPI(
    title="FireSense Thermal Dashboard",
    description="Live thermal monitoring for Pico 2 W",
    version="1.0.0"
)

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static"
)


def current_time():
    return datetime.now(timezone.utc).isoformat()


# ==========================================
# THERMAL FRAME DATA MODEL
# ==========================================

class ThermalFrame(BaseModel):

    width: Literal[32] = 32
    height: Literal[24] = 24

    pixels: list[float] = Field(
        description="768 thermal pixel temperatures"
    )

    sensor_temperature_c: float | None = None

    source: Literal[
        "simulator",
        "hardware"
    ] = "hardware"

    @model_validator(mode="before")
    @classmethod
    def accept_frame_format(cls, values):

        if isinstance(values, dict):
            values = values.copy()

            # Compatible with dashboard_client.py
            # and the desktop simulator.

            if "frame" in values:

                if "pixels" in values:
                    raise ValueError(
                        "Use either frame or pixels"
                    )

                values["pixels"] = values.pop("frame")

        return values

    @field_validator("pixels")
    @classmethod
    def validate_pixels(cls, values):

        if len(values) != FRAME_PIXELS:
            raise ValueError(
                "Expected exactly 768 thermal readings"
            )

        if not all(math.isfinite(v) for v in values):
            raise ValueError(
                "Thermal readings must be finite"
            )

        # Invalid pixels are represented by
        # -273.15 in the provided MLX90640 driver.

        if not any(v > -200 for v in values):
            raise ValueError(
                "No valid thermal pixels received"
            )

        return values


# ==========================================
# TELEMETRY MODEL
# ==========================================

class Telemetry(BaseModel):

    state: Literal[
        "NORMAL",
        "WARNING",
        "FIRE"
    ]

    max_thermal_c: float | None = None
    ambient_c: float | None = None

    suppression_active: bool = False

    @field_validator(
        "max_thermal_c",
        "ambient_c"
    )
    @classmethod
    def check_temperature(cls, value):

        if value is not None:
            if not math.isfinite(value):
                raise ValueError(
                    "Invalid temperature value"
                )

        return value


# ==========================================
# LIVE CONNECTION MANAGER
# ==========================================

class ConnectionManager:

    def __init__(self):

        self.connections = set()

        self.latest_frame = None
        self.latest_telemetry = None

        self.frame_count = 0
        self.telemetry_count = 0

        self.lock = asyncio.Lock()

    async def connect(self, websocket):

        await websocket.accept()

        self.connections.add(websocket)

    def disconnect(self, websocket):

        self.connections.discard(websocket)

    async def broadcast(self, message):

        payload = json.dumps(message)

        disconnected = []

        for websocket in tuple(self.connections):

            try:
                await websocket.send_text(payload)

            except Exception:
                disconnected.append(websocket)

        for websocket in disconnected:
            self.disconnect(websocket)

    async def publish_frame(self, frame):

        async with self.lock:

            self.frame_count += 1

            frame["sequence"] = self.frame_count

            self.latest_frame = frame

            await self.broadcast({
                "type": "frame",
                **frame
            })

    async def publish_telemetry(self, telemetry):

        async with self.lock:

            self.telemetry_count += 1

            telemetry["sequence"] = (
                self.telemetry_count
            )

            self.latest_telemetry = telemetry

            await self.broadcast({
                "type": "telemetry",
                **telemetry
            })


manager = ConnectionManager()


# ==========================================
# DASHBOARD HOME PAGE
# ==========================================

@app.get("/")
async def dashboard():

    return FileResponse(
        STATIC_DIR / "index.html"
    )


# ==========================================
# SERVER STATUS
# ==========================================

@app.get("/api/status")
async def get_status():

    return {
        "server": "online",
        "camera": "MLX90640",
        "resolution": "32x24",

        "connected_viewers": len(
            manager.connections
        ),

        "frames_received": manager.frame_count,

        "telemetry_received": (
            manager.telemetry_count
        ),

        "has_frame": (
            manager.latest_frame is not None
        ),

        "last_frame_at": (
            manager.latest_frame["received_at"]
            if manager.latest_frame else None
        )
    }


# ==========================================
# RECEIVE THERMAL CAMERA FRAME
# ==========================================

@app.post("/api/frame", status_code=202)
async def receive_thermal_frame(
    frame: ThermalFrame
):

    # Convert validated frame into dictionary
    data = frame.model_dump()

    pixels = frame.pixels

    # Exclude invalid thermal pixels
    valid_pixels = [
        value for value in pixels
        if value > -200
    ]

    # Calculate actual thermal statistics
    maximum = max(valid_pixels)
    minimum = min(valid_pixels)

    average = (
        sum(valid_pixels) / len(valid_pixels)
    )

    data.update({

        "received_at": current_time(),

        "max_c": maximum,

        "min_c": minimum,

        "mean_c": average,

        "invalid_pixel_count": (
            FRAME_PIXELS - len(valid_pixels)
        )

    })

    # Broadcast to connected dashboard viewers
    await manager.publish_frame(data)

    return {
        "accepted": True,
        "sequence": manager.frame_count,
        "max_temperature": maximum
    }


# ==========================================
# RECEIVE TEMPERATURE TELEMETRY
# ==========================================

@app.post("/api/telemetry", status_code=202)
async def receive_telemetry(
    telemetry: Telemetry
):

    data = telemetry.model_dump()

    data["received_at"] = current_time()

    await manager.publish_telemetry(data)

    return {
        "accepted": True,
        "sequence": manager.telemetry_count
    }


# ==========================================
# LIVE THERMAL VIDEO WEBSOCKET
# ==========================================

@app.websocket("/ws/thermal")
async def thermal_websocket(
    websocket: WebSocket
):

    await manager.connect(websocket)

    try:

        # Send the newest frame to a new viewer
        if manager.latest_frame:

            await websocket.send_json({
                "type": "frame",
                **manager.latest_frame
            })

        # Send latest system telemetry
        if manager.latest_telemetry:

            await websocket.send_json({
                "type": "telemetry",
                **manager.latest_telemetry
            })

        # Keep the connection alive
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        pass

    finally:
        manager.disconnect(websocket)


# ==========================================
# STARTUP MESSAGE
# ==========================================

@app.on_event("startup")
async def startup():

    print("=" * 55)
    print("FIRESENSE THERMAL DASHBOARD")
    print("=" * 55)

    print("Status: ONLINE")
    print("Camera resolution: 32 x 24")
    print("Thermal pixels: 768")

    print("Thermal endpoint: /api/frame")
    print("Telemetry endpoint: /api/telemetry")
    print("WebSocket endpoint: /ws/thermal")

    print("=" * 55)
