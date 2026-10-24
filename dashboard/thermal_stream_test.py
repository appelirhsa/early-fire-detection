"""MICROPYTHON ONLY — first real MLX90640 → LAN dashboard test.

Copy this file into the EXISTING firmware/ folder on the Pico 2 W.
Run from Thonny: import thermal_stream_test; thermal_stream_test.run()

This test deliberately DOES NOT import suppression.py, operate a relay,
or make any automatic fire decisions. Its only role is to read and display
real thermal frames. Keep suppression hardware electrically isolated
while bringing up the camera.
"""

import time
import config
from sensors.mlx90640 import MLX90640
from wifi_manager import WiFiManager
from dashboard_client import post_thermal_frame

# 2 Hz is selected by the user's existing sensor wrapper, but the MLX90640
# reports two subpages. Expect roughly <=1 complete frame per second during
# initial bring-up, possibly less due to Python calculation and HTTP time.
MIN_POST_SPACING_MS = 1000


def complete_frame(camera):
    """Wait until the two subpages have been seen, filling camera's shared array.

    The vendored driver calculates the pixels belonging to only the current
    subpage during each get_frame() call. A single call on startup therefore
    does not supply a completely populated 32x24 temperature image.
    """
    seen = set()
    start = time.ticks_ms()
    while len(seen) < 2:
        camera.get_frame_celsius()
        subpage = camera._driver.mlx90640_frame[833]
        if subpage in (0, 1):
            seen.add(subpage)
        if time.ticks_diff(time.ticks_ms(), start) > 6000:
            raise RuntimeError("Timed out acquiring both MLX90640 subpages")
    return camera._frame


def run():
    print("Thermal-only viewer test: suppression code will NOT be loaded")
    camera = MLX90640(
        i2c_id=config.I2C_ID,
        sda_pin=config.I2C_SDA_PIN,
        scl_pin=config.I2C_SCL_PIN,
        freq=config.I2C_FREQ_HZ,
        addr=config.MLX90640_I2C_ADDR,
    )
    print("I2C scan:", [hex(a) for a in camera.i2c.scan()])
    if not camera.is_connected():
        raise RuntimeError("MLX90640 absent at the configured I2C address")

    print("Loading MLX90640 calibration...")
    camera.load_calibration()
    print("Camera calibrated. Refresh-rate setting:", camera._driver.refresh_rate)

    wifi = WiFiManager()
    if not wifi.connect():
        print("Wi-Fi connection failed; check credentials and 2.4 GHz network")
        return
    print("Posting to http://{}:{}{}".format(
        config.DASHBOARD_HOST, config.DASHBOARD_PORT, config.DASHBOARD_FRAME_ENDPOINT
    ))

    frame_number = 0
    previous_post = time.ticks_ms() - MIN_POST_SPACING_MS
    while True:
        try:
            data = complete_frame(camera)
            # Exclude invalid-pixel sentinel inserted by the vendored driver.
            valid = [v for v in data if v > -200]
            if not valid:
                print("Camera provided no valid temperatures; skipped")
                continue
            now = time.ticks_ms()
            remaining = MIN_POST_SPACING_MS - time.ticks_diff(now, previous_post)
            if remaining > 0:
                time.sleep_ms(remaining)
            if not wifi.is_connected():
                if not wifi.ensure_connected():
                    print("No Wi-Fi; frame not posted")
                    continue
            success = post_thermal_frame(data)
            previous_post = time.ticks_ms()
            frame_number += 1
            print("Frame {}: range {:.1f}–{:.1f} C; POST {}".format(
                frame_number, min(valid), max(valid), "OK" if success else "FAILED"
            ))
        except KeyboardInterrupt:
            print("Thermal test stopped")
            return
        except (OSError, RuntimeError, ValueError) as exc:
            print("Camera/transport error:", exc)
            time.sleep_ms(400)
