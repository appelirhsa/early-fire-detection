# Fire Detection Firmware Skeleton — Pico 2 W

## Structure
- `config.py` — all pin assignments, thresholds, WiFi/dashboard settings. Edit this first.
- `sensors/mlx90640.py` — MLX90640 thermal camera interface. **Calibration/frame reading is deliberately unimplemented** — see the module docstring. This is the highest-effort remaining piece.
- `sensors/ds18b20.py` — DS18B20 ambient sensor, uses MicroPython's built-in `onewire`/`ds18x20` modules. Should work as-is once wired.
- `state_classifier.py` — OBJ03 placeholder threshold classifier. Swap for TFLite Micro inference later; keep the same `classify(max_thermal_c, ambient_c)` signature.
- `suppression.py` — D4 solenoid control. Requires 3 consecutive FIRE classifications within a 10s window before activating, and auto-cuts-off after 30s regardless.
- `wifi_manager.py` — connects and auto-reconnects the Pico 2 W's WiFi.
- `dashboard_client.py` — posts JSON telemetry to your Flask dashboard (OBJ04).
- `main.py` — ties it all together with a hardware watchdog (OBJ05).

## Before deploying to hardware
1. Fill in real GPIO pin numbers in `config.py` to match your PCB2 schematic (the current values are placeholders).
2. Fill in `WIFI_SSID` / `WIFI_PASSWORD` and `DASHBOARD_HOST` (the IP of the machine running your Flask app).
3. Integrate a proper calibrated MLX90640 driver — see `sensors/mlx90640.py` docstring for why the raw calibration math wasn't hand-rolled here.
4. Copy this whole `firmware/` folder onto the Pico 2 W's filesystem (e.g. via Thonny's file browser) and run `main.py`.

## Current status
Runs end-to-end right now with the MLX90640 stubbed out — DS18B20, classifier, suppression interlock, WiFi, dashboard posting, and alerts are all live logic, not placeholders. `state` will report `"WARNING"` continuously until the thermal driver is finished, by design (see `state_classifier.classify()` comment on fail-safe behaviour).
