"""
config.py
Central configuration for Early Fire Detection and Suppression System
Hardware: Raspberry Pi Pico 2 W (RP2350)
"""
ENABLE_WIFI = True   # set True once WiFi's USB-disconnect issue is resolved
# ---------------------------------------------------------------------------
# I2C bus - MLX90640ESF thermal camera (32x24, I2C, per D5 Semester 2 deviation)
# ---------------------------------------------------------------------------
I2C_ID = 1
I2C_SDA_PIN = 26
I2C_SCL_PIN = 19
I2C_FREQ_HZ = 900000          # MLX90640 supports up to 1MHz; 400kHz is a safe start
MLX90640_I2C_ADDR = 0x33       # Default MLX90640 address

# ---------------------------------------------------------------------------
# 1-Wire - DS18B20 ambient temperature sensor
# ---------------------------------------------------------------------------
ONEWIRE_PIN = 15

# ---------------------------------------------------------------------------
# Suppression subsystem - relay -> 12V solenoid valve (D4 in D2 test plan)
# ---------------------------------------------------------------------------
SUPPRESSION_RELAY_PIN = 11
SUPPRESSION_MIN_CONFIRM_READINGS = 3     # consecutive FIRE classifications required
SUPPRESSION_CONFIRM_WINDOW_S = 10        # all 3 must occur within this window
SUPPRESSION_MAX_ACTIVE_S = 30            # solenoid auto-cutoff safety timer

# ---------------------------------------------------------------------------
# Alerts - buzzer + status LEDs
# ---------------------------------------------------------------------------
BUZZER_PIN = 7
LED_WIFI_LINK_PIN = 6     # blue
LED_FIRE_ALARM_PIN = 14    # red
LED_FAULT_PIN = 10         # amber

# ---------------------------------------------------------------------------
# Timing - OBJ02: alert within 90 seconds of confirmed detection
# ---------------------------------------------------------------------------
ALERT_MAX_LATENCY_S = 90
SENSOR_POLL_INTERVAL_S = 2       # thermal + ambient sampling rate
WATCHDOG_TIMEOUT_MS = 8000       # OBJ05: continuous monitoring, auto-recover on hang

# ---------------------------------------------------------------------------
# WiFi / dashboard connectivity (OBJ04: real-time web dashboard)
# ---------------------------------------------------------------------------
WIFI_SSID = "NGOZA"
WIFI_PASSWORD = "87654321"
WIFI_CONNECT_TIMEOUT_S = 15
WIFI_RECONNECT_BACKOFF_S = 5

DASHBOARD_HOST = "223087197fyp.duckdns.org"   # IP of the machine running the Flask server
DASHBOARD_FRAME_ENDPOINT = "/api/frame"
DASHBOARD_PORT = 80
DEVICE_API_TOKEN = "" 
DASHBOARD_ENDPOINT = "/api/telemetry"
DASHBOARD_POST_INTERVAL_S = 2
DASHBOARD_HTTP_TIMEOUT_S = 5

# ---------------------------------------------------------------------------
# Classification thresholds (placeholder until TFLite Micro model is wired in)
# Environment states: NORMAL / WARNING / FIRE  (OBJ03)
# ---------------------------------------------------------------------------
TEMP_WARNING_C = 45.0
TEMP_FIRE_C = 65.0
