"""
dashboard_client.py
OBJ04: sends telemetry and live thermal frames to the Flask dashboard via
HTTP POST with absolute minimal data overhead.
"""

import urequests
import config


def post_telemetry(state, max_thermal_c, ambient_c, suppression_active):
    """
    Posts a JSON telemetry payload to the Flask dashboard.
    Returns True on success (HTTP 2xx), False otherwise. Never raises.
    """
    url = "http://{}:{}{}".format(
        config.DASHBOARD_HOST, config.DASHBOARD_PORT, config.DASHBOARD_ENDPOINT
    )

    payload = {
        "state": str(state),
        "max_thermal_c": float(max_thermal_c) if max_thermal_c is not None else None,
        "ambient_c": float(ambient_c) if ambient_c is not None else None,
        "suppression_active": bool(suppression_active),
        "classification_source": "firmware"
    }

    headers = {"Content-Type": "application/json"}
    if hasattr(config, "DEVICE_API_TOKEN") and config.DEVICE_API_TOKEN:
        headers["Authorization"] = "Bearer " + config.DEVICE_API_TOKEN

    try:
        response = urequests.post(url, json=payload, headers=headers)
        ok = 200 <= response.status_code < 300
        response.close()  # Recycles port links instantly
        return ok
    except Exception:
        return False


def post_thermal_frame(frame, ambient_c=None):
    """
    Posts the current 768-value (32x24) thermal frame and ambient temperature
    to the dashboard for low-latency real-time rendering.
    """
    url = "http://{}:{}{}".format(
        config.DASHBOARD_HOST, config.DASHBOARD_PORT, config.DASHBOARD_FRAME_ENDPOINT
    )

    payload = {
        "width": 32,
        "height": 24,
        "pixels": [float(v) for v in frame],
        "ambient_c": float(ambient_c) if ambient_c is not None else None,
        "sensor_temperature_c": None,
        "source": "hardware"
    }

    headers = {"Content-Type": "application/json"}
    if hasattr(config, "DEVICE_API_TOKEN") and config.DEVICE_API_TOKEN:
        headers["Authorization"] = "Bearer " + config.DEVICE_API_TOKEN

    try:
        response = urequests.post(url, json=payload, headers=headers)
        ok = 200 <= response.status_code < 300
        response.close()  # Recycles port links instantly
        return ok
    except Exception:
        return False
