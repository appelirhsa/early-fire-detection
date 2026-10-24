
"""
FireSense - MLX90640 Thermal Camera Simulator

Generates simulated 32 x 24 thermal frames and
sends them to the FireSense dashboard.

This is for testing the dashboard only.
No physical camera is required.
"""

import argparse
import json
import math
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


WIDTH = 32
HEIGHT = 24

DASHBOARD_URL = "http://127.0.0.1:5000/api/frame"


def generate_thermal_frame(t):
    """
    Generate 768 simulated temperature readings.

    A moving hotspot represents a heat source
    inside the camera's field of view.
    """

    frame = []

    # Moving hotspot position
    hotspot_x = 16 + 9 * math.sin(t * 0.37)
    hotspot_y = 12 + 6 * math.cos(t * 0.29)

    for y in range(HEIGHT):
        for x in range(WIDTH):

            # Simulated ambient background
            background = (
                25.5
                + 2.5 * math.sin(x * 0.33 + t * 0.2)
            )

            # Distance from hotspot centre
            dx = (x - hotspot_x) / 5.2
            dy = (y - hotspot_y) / 4.8

            # Gaussian thermal hotspot
            hotspot = (
                65.0
                * math.exp(-(dx * dx + dy * dy) / 2)
            )

            temperature = background + hotspot

            frame.append(round(temperature, 2))

    return frame


def send_frame(frame):
    """
    Send one simulated thermal frame to the dashboard.
    """

    payload = {
        "frame": frame,
        "source": "simulator"
    }

    json_data = json.dumps(payload).encode("utf-8")

    request = Request(
        DASHBOARD_URL,
        data=json_data,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urlopen(request, timeout=5) as response:
            return 200 <= response.status < 300

    except (URLError, HTTPError, TimeoutError) as error:
        print("Frame transmission failed:", error)
        return False


def main():

    parser = argparse.ArgumentParser(
        description="FireSense Thermal Simulator"
    )

    parser.add_argument(
        "--fps",
        type=float,
        default=2.0,
        help="Frames per second"
    )

    args = parser.parse_args()

    if args.fps <= 0 or args.fps > 32:
        parser.error("FPS must be between 0 and 32")

    print("=" * 50)
    print("FIRESENSE THERMAL CAMERA SIMULATOR")
    print("=" * 50)

    print("Resolution: 32 x 24")
    print("Total pixels: 768")
    print("Frame rate:", args.fps, "FPS")
    print("Dashboard:", DASHBOARD_URL)
    print("Source: SIMULATED - NOT REAL CAMERA DATA")

    print("=" * 50)

    frame_count = 0
    start_time = time.monotonic()

    try:
        while True:

            current_time = time.monotonic() - start_time

            frame = generate_thermal_frame(current_time)

            success = send_frame(frame)

            if success:
                frame_count += 1

                print(
                    "Frame:",
                    frame_count,
                    "| Maximum:",
                    round(max(frame), 2),
                    "C"
                )

            time.sleep(1.0 / args.fps)

    except KeyboardInterrupt:
        print("\nSimulator stopped.")


if __name__ == "__main__":
    main()
