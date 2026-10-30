"""
dashboard_client.py
OBJ04: sends telemetry and live thermal frames to the FastAPI dashboard via
HTTP POST with minimal data overhead.
"""

import urequests
import config


def _headers():
    headers = {"Content-Type": "application/json"}
    if hasattr(config, "DEVICE_API_TOKEN") and config.DEVICE_API_TOKEN:
        headers["Authorization"] = "Bearer " + config.DEVICE_API_TOKEN
    return headers


def _url(endpoint):
    return "http://{}:{}{}".format(config.DASHBOARD_HOST, config.DASHBOARD_PORT, endpoint)


def _post(url, payload):
    """POST JSON; True on HTTP 2xx, False otherwise. Never raises."""
    response = None
    try:
        response = urequests.post(url, json=payload, headers=_headers())
        return 200 <= response.status_code < 300
    except Exception:
        return False
    finally:
        if response is not None:
            try:
                response.close()  # always free the socket, even on errors
            except Exception:
                pass


def post_telemetry(state, max_thermal_c, ambient_c, suppression_active):
    """Posts the device state to the dashboard."""
    payload = {
        "state": str(state),
        "max_thermal_c": float(max_thermal_c) if max_thermal_c is not None else None,
        "ambient_c": float(ambient_c) if ambient_c is not None else None,
        "suppression_active": bool(suppression_active),
        "classification_source": "firmware"
    }
    return _post(_url(config.DASHBOARD_ENDPOINT), payload)


def post_thermal_frame(frame, ambient_c=None):
    """
    Posts the 768-value (32x24) thermal frame. Values are rounded to 0.1 C,
    which matches the sensor's real precision and roughly halves the upload size.
    """
    payload = {
        "width": 32,
        "height": 24,
        "pixels": [round(v, 1) for v in frame],
        "ambient_c": float(ambient_c) if ambient_c is not None else None,
        "sensor_temperature_c": None,
        "source": "hardware"
    }
    return _post(_url(config.DASHBOARD_FRAME_ENDPOINT), payload)