import network
import time
import machine
import rp2
import onewire
import ds18x20
import config  # Central system configuration
import state_classifier  # Threshold classification system (OBJ03)
from sensors.mlx90640 import MLX90640
from dashboard_client import post_thermal_frame, post_telemetry, connection_stats, last_error
from alerts import AlertOutputs
from suppression import FanController

# ---------------------------------------------------------------------------
# Settings used by this file. Each one can be overridden by adding the same
# name to config.py; otherwise these defaults apply.
# ---------------------------------------------------------------------------
# MLX90640 refresh-rate code (driver RefreshRate values): 2 = 2 Hz (factory default),
# 3 = 4 Hz, 4 = 8 Hz. These are sub-page rates; a complete frame takes two sub-pages,
# so code 3 gives about 2 complete frames/s. Higher codes are faster but noisier.
MLX_REFRESH_CODE = getattr(config, "MLX90640_REFRESH_CODE", 3)
# Telemetry is sent when the state changes, or at least this often (ms).
# The dashboard treats telemetry older than 6 s as stale, so keep this under 6000.
TELEMETRY_INTERVAL_MS = getattr(config, "TELEMETRY_INTERVAL_MS", 3000)
# Print a timing summary every N frames.
TIMING_SUMMARY_EVERY = getattr(config, "TIMING_SUMMARY_EVERY", 10)

FIRMWARE_VERSION = "v5 - fan suppression output + alarms + keep-alive uploads (2026-10-31)"


def connect_wifi():
    """
    Handles the connection handshake with the local WiFi network using hardware reset steps.
    """
    try:
        rp2.country("ZA")
    except Exception as e:
        print("Warning: Could not set country code:", e)

    wlan = network.WLAN(network.STA_IF)

    print("Resetting Wi-Fi hardware interface...")
    wlan.active(False)
    time.sleep(2)
    wlan.active(True)
    # Turn off Wi-Fi power saving: the radio otherwise dozes between packets,
    # adding delay to every upload. (0xa11140 = performance mode, no power save.)
    try:
        wlan.config(pm=0xa11140)
        print("Wi-Fi power saving disabled")
    except Exception as e:
        print("Could not disable Wi-Fi power saving:", e)
    time.sleep(3)

    if wlan.isconnected():
        print("Already connected! IP Configuration:", wlan.ifconfig())
        return True

    print("Scanning for target network:", config.WIFI_SSID)
    networks = wlan.scan()

    # EXACT indexing match from your working tests.py snippet (net[0])
    found = any(
        net[0].decode() == config.WIFI_SSID
        for net in networks
    )

    if not found:
        print("Error: Target network not found in scan! Check 2.4 GHz availability.")
        return False

    print("Connecting to WiFi network:", config.WIFI_SSID)
    wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)

    max_wait = 30
    while max_wait > 0:
        if wlan.isconnected():
            break

        status = wlan.status()
        print("Waiting... Status code:", status)

        if status in (-1, -2, -3):
            print("Link failed early with status:", status)
            break

        max_wait -= 1
        time.sleep(1)

    if not wlan.isconnected():
        print("Connection failed! Final status code:", wlan.status())
        return False
    else:
        net_info = wlan.ifconfig()
        print("\nConnection Successful!")
        print("-" * 30)
        print("IP Address :", net_info[0])
        print("Gateway    :", net_info[2])
        print("-" * 30)
        return True


class LoopTimer:
    """Collects per-stage timings (ms) and prints an average every N frames."""

    STAGES = ("ambient", "read", "classify", "post_frame", "post_telem", "total")

    def __init__(self):
        self.sums = {s: 0 for s in self.STAGES}
        self.max = {s: 0 for s in self.STAGES}
        self.n = 0
        self.window_start = time.ticks_ms()

    def add(self, t):
        for s in self.STAGES:
            v = t.get(s, 0)
            self.sums[s] += v
            if v > self.max[s]:
                self.max[s] = v
        self.n += 1

    def report_if_due(self, every, connections=None):
        if self.n < every:
            return
        elapsed_s = time.ticks_diff(time.ticks_ms(), self.window_start) / 1000
        fps = self.n / elapsed_s if elapsed_s > 0 else 0
        print("-" * 72)
        print("TIMING over {} frames  |  {:.2f} frames/s  ({:.2f} s per frame)".format(
            self.n, fps, (elapsed_s / self.n) if self.n else 0))
        for s in self.STAGES:
            print("  {:<11} avg {:>6} ms   max {:>6} ms".format(
                s, self.sums[s] // self.n, self.max[s]))
        if connections is not None:
            print("  connections opened so far: {} (1 = connection is being reused)".format(connections))
        print("-" * 72)
        self.__init__()


def read_full_frame(c, fixed_driver):
    """
    Returns one complete 768-pixel frame, or None.

    Fixed driver (reads both sub-pages inside get_frame): one call is a full frame.
    Original driver (one sub-page per call): call until both sub-pages have been seen.
    """
    if fixed_driver:
        return c.get_frame_celsius()

    pages = set()
    frame = None
    for _ in range(3):
        frame = c.get_frame_celsius()
        pages.add(c._driver.mlx90640_frame[833])
        if len(pages) == 2:
            return frame
    return None


def run_thermal_stream():
    """
    Pipelined loop for real-time streaming, with per-stage timing printouts.
    """
    print("Target Dashboard Host:", config.DASHBOARD_HOST)

    # 0. Local alarm outputs (buzzer + LEDs) with a short self-test
    alerts = AlertOutputs()
    alerts.self_test()
    alerts.set_wifi(True)

    # Suppression / extraction fan (relay on GP11, or MOSFET in PWM mode)
    fan = FanController()
    fan_percent = 0

    # 1. Initialize MLX90640 Thermal Sensor
    print("Initializing MLX90640 sensor...")
    try:
        c = MLX90640(config.I2C_ID, config.I2C_SDA_PIN, config.I2C_SCL_PIN, config.I2C_FREQ_HZ, config.MLX90640_I2C_ADDR)
        c.load_calibration()
        print("Camera ready.")
    except Exception as e:
        print("MLX90640 Sensor Initialization Failed:", e)
        alerts.set_sensor_fault(True)
        fan.stop()
        return

    # The fixed driver (with _fix_bad_pixels) already merges both sub-pages per call.
    driver = getattr(c, "_driver", None)
    fixed_driver = driver is not None and hasattr(driver, "_fix_bad_pixels")
    print("MLX90640 driver:", "fixed (full frame per call)" if fixed_driver else "original (one sub-page per call)")

    # Set the camera refresh rate (default from the factory is 2 Hz).
    try:
        if driver is not None:
            driver.refresh_rate = MLX_REFRESH_CODE
            print("MLX90640 refresh-rate code set to", driver.refresh_rate)
    except Exception as e:
        print("Could not set refresh rate (continuing):", e)

    # 2. Initialize DS18B20 Ambient Sensor via OneWire
    print("Initializing DS18B20 ambient sensor on Pin", config.ONEWIRE_PIN)
    try:
        ds_pin = machine.Pin(config.ONEWIRE_PIN)
        ds_ow = onewire.OneWire(ds_pin)
        ds_sensor = ds18x20.DS18X20(ds_ow)
        roms = ds_sensor.scan()
        print("DS18B20 ready. Found", len(roms), "device(s).")
        if roms:
            ds_sensor.convert_temp()
    except Exception as e:
        print("DS18B20 Sensor Initialization Failed:", e)
        roms = []

    wlan = network.WLAN(network.STA_IF)
    count = 0
    ambient_temp = 25.0  # Safe initial baseline parameter default
    last_ambient_poll = 0
    last_state = None
    last_telemetry_ms = 0
    last_fan_on = False
    timer = LoopTimer()

    print("Starting live stream with timing...")
    while True:
        if not wlan.isconnected():
            alerts.set_wifi(False)
            print("Wi-Fi lost! Attempting recovery...")
            if not connect_wifi():
                print("Could not reconnect. Retrying in 5 seconds...")
                time.sleep(5)
                continue
            alerts.set_wifi(True)

        t = {}
        loop_start = time.ticks_ms()

        # --- A. Ambient (DS18B20), every 2 s, non-blocking conversion ---
        t0 = time.ticks_ms()
        if roms and time.ticks_diff(t0, last_ambient_poll) >= 2000:
            try:
                for rom in roms:
                    temp_read = ds_sensor.read_temp(rom)
                    if temp_read is not None:
                        ambient_temp = round(temp_read, 1)
                ds_sensor.convert_temp()
                last_ambient_poll = t0
            except Exception:
                pass  # keep streaming frames
        t["ambient"] = time.ticks_diff(time.ticks_ms(), t0)

        # --- B. Thermal frame (I2C read + temperature maths) ---
        t0 = time.ticks_ms()
        try:
            frame = read_full_frame(c, fixed_driver)
        except Exception as e:
            print("Frame read error:", e)
            frame = None
        t["read"] = time.ticks_diff(time.ticks_ms(), t0)
        alerts.set_sensor_fault(frame is None)

        if frame is None:
            print("Incomplete frame - skipped (read {} ms)".format(t["read"]))
            continue

        valid = [v for v in frame if v > -200]
        if not valid:
            continue

        # --- C. Classification ---
        t0 = time.ticks_ms()
        max_thermal = round(max(valid), 1)
        current_state = state_classifier.classify(max_thermal, ambient_temp)
        # Local alarm first: buzzer + red LED react before any network upload.
        alerts.set_state(current_state)
        # Suppression fan: off / slow / fast, scaled with fire intensity.
        fan_percent = fan.update(current_state, max_thermal)
        t["classify"] = time.ticks_diff(time.ticks_ms(), t0)
        count += 1

        # --- D. Upload frame ---
        t0 = time.ticks_ms()
        frame_ok = post_thermal_frame(frame, ambient_c=ambient_temp)
        t["post_frame"] = time.ticks_diff(time.ticks_ms(), t0)

        # --- E. Upload telemetry: on state change, or every TELEMETRY_INTERVAL_MS ---
        t0 = time.ticks_ms()
        telemetry_ok = None
        if (current_state != last_state
                or (fan_percent > 0) != last_fan_on
                or time.ticks_diff(t0, last_telemetry_ms) >= TELEMETRY_INTERVAL_MS):
            telemetry_ok = post_telemetry(
                state=current_state,
                max_thermal_c=max_thermal,
                ambient_c=ambient_temp,
                suppression_active=fan_percent > 0
            )
            last_state = current_state
            last_fan_on = fan_percent > 0
            last_telemetry_ms = t0
        t["post_telem"] = time.ticks_diff(time.ticks_ms(), t0)

        t["total"] = time.ticks_diff(time.ticks_ms(), loop_start)
        timer.add(t)

        print("[{}] {} | max {} C | amb {} C | fan {} % | read {} ms | frame {} ms ({}) | telem {} ms ({}) | loop {} ms".format(
            count, current_state, max_thermal, ambient_temp, fan_percent,
            t["read"],
            t["post_frame"], "ok" if frame_ok else "FAIL",
            t["post_telem"], "-" if telemetry_ok is None else ("ok" if telemetry_ok else "FAIL"),
            t["total"]))

        if not frame_ok or telemetry_ok is False:
            print("   upload problem:", last_error())

        timer.report_if_due(TIMING_SUMMARY_EVERY, connection_stats())


STARTUP_DELAY_S = getattr(config, "STARTUP_DELAY_S", 3)


def startup_window():
    """
    Gives VS Code / MicroPico a few seconds to break in (Ctrl+C) before the
    stream loop starts. Holding the BOOTSEL button during this countdown also
    skips main.py, so the board can always be reached for uploads.
    Returns False if start-up should be skipped.
    """
    print("Starting in {} s - press Ctrl+C (or hold BOOTSEL) to stop and upload files".format(STARTUP_DELAY_S))
    for _ in range(STARTUP_DELAY_S * 10):
        try:
            if rp2.bootsel_button():
                print("BOOTSEL held - main.py stopped. Board is free for uploads.")
                return False
        except AttributeError:
            pass                      # older firmware without bootsel_button()
        time.sleep_ms(100)
    return True


def main():
    """
    The main boot execution sequence.
    """
    print("=" * 60)
    print("main.py", FIRMWARE_VERSION)
    print("=" * 60)
    if not startup_window():
        return
    try:
        led = machine.Pin("LED", machine.Pin.OUT)
        led.on()
    except Exception:
        pass

    while True:
        if connect_wifi():
            print("System ready for network operations. Starting stream loop...")
            run_thermal_stream()
        else:
            print("Network unavailable. Retrying stack configuration in 10 seconds...")
            time.sleep(10)


if __name__ == "__main__":
    main()
    