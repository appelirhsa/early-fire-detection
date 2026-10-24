"""
dashboard_client.py
OBJ04: sends telemetry and live thermal frames to the Flask dashboard via
HTTP POST.

Requires the `urequests` module (included in most MicroPython builds,
including the pimoroni/official RP2350 builds with network support).

Note: MicroPython's urequests.post() does not accept a `timeout` keyword
argument (only url, data/json, headers) - an earlier version of this file
passed one, which would have raised TypeError the first time this ran
against a real connection. Removed here.
"""

import urequests
import config


def post_telemetry(state, max_thermal_c, ambient_c, suppression_active):
    """
    Posts a JSON telemetry payload to the Flask dashboard.
    Returns True on success (HTTP 2xx), False otherwise. Never raises -
    a dashboard outage must not crash or stall the monitoring loop.
    """
    url = "http://{}:{}{}".format(
        config.DASHBOARD_HOST, config.DASHBOARD_PORT, config.DASHBOARD_ENDPOINT
    )

    payload = {
        "state": state,
        "max_thermal_c": max_thermal_c,
        "ambient_c": ambient_c,
        "suppression_active": suppression_active,
    }

    try:
        response = urequests.post(url, json=payload)
        ok = 200 <= response.status_code < 300
        response.close()
        return ok
    except Exception as e:
        print("Dashboard telemetry POST failed:", e)
        return False


def post_thermal_frame(frame, ambient_c=None):
    """
    Posts the current 768-value (32x24) thermal frame and ambient temperature
    to the dashboard for live heatmap display and module status activation.

    Returns True on success (HTTP 2xx), False otherwise. Never raises.
    """
    url = "http://{}:{}{}".format(
        config.DASHBOARD_HOST, config.DASHBOARD_PORT, config.DASHBOARD_FRAME_ENDPOINT
    )

    # Added ambient_c into the payload dictionary for module list parsing
    payload = {
        "frame": list(frame),
        "ambient_c": ambient_c
    }

    try:
        response = urequests.post(url, json=payload)
        ok = 200 <= response.status_code < 300
        response.close()
        return ok
    except Exception as e:
        print("Dashboard frame POST failed:", e)
        return False
