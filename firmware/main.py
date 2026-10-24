import network
import time
import machine 
import rp2
import onewire
import ds18x20
import config  # Central system configuration
import state_classifier  # Threshold classification system (OBJ03)
from sensors.mlx90640 import MLX90640
from dashboard_client import post_thermal_frame, post_telemetry

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
    time.sleep(3) 

    if wlan.isconnected():
        print(f"Already connected! IP Configuration: {wlan.ifconfig()}")
        return True 

    print(f"Scanning for target network: '{config.WIFI_SSID}'...")
    networks = wlan.scan()
    
    # EXACT indexing match from your working tests.py snippet
    found = any(
        net.decode() == config.WIFI_SSID
        for net in networks
    )

    if not found:
        print(f"Error: '{config.WIFI_SSID}' not found in scan! Check 2.4 GHz availability.")
        return False

    print(f"Connecting to WiFi network: '{config.WIFI_SSID}'...")
    wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD) 

    max_wait = 30
    while max_wait > 0: 
        if wlan.isconnected():
            break 

        status = wlan.status()
        print(f"Waiting... Status code: {status}")
        
        if status in (-1, -2, -3):
            print(f"Link failed early with status: {status}")
            break

        max_wait -= 1
        time.sleep(1) 

    if not wlan.isconnected():
        print(f"\nConnection failed! Final status code: {wlan.status()}")
        return False
    else:
        net_info = wlan.ifconfig()
        print("\nConnection Successful!")
        print("-" * 30)
        print(f"IP Address : {net_info}")
        print(f"Gateway    : {net_info}")
        print("-" * 30)
        return True

def run_thermal_stream():
    """
    Initialises the MLX90640 camera and DS18B20 ambient sensor, streaming readings continuously.
    """
    print(f"Target Dashboard Host: {config.DASHBOARD_HOST}")
    
    # 1. Initialize MLX90640 Thermal Array Sensor
    print("Initializing MLX90640 sensor...")
    try:
        c = MLX90640(config.I2C_ID, config.I2C_SDA_PIN, config.I2C_SCL_PIN, config.I2C_FREQ_HZ, config.MLX90640_I2C_ADDR)
        c.load_calibration()
        print("Camera ready.")
    except Exception as e:
        print("MLX90640 Sensor Initialization Failed:", e)
        return

    # 2. Initialize DS18B20 Ambient Temperature Sensor via OneWire
    print(f"Initializing DS18B20 ambient sensor on Pin {config.ONEWIRE_PIN}...")
    try:
        ds_pin = machine.Pin(config.ONEWIRE_PIN)
        ds_ow = onewire.OneWire(ds_pin)
        ds_sensor = ds18x20.DS18X20(ds_ow)
        roms = ds_sensor.scan()
        print(f"DS18B20 ready. Found {len(roms)} device(s).")
    except Exception as e:
        print("DS18B20 Sensor Initialization Failed:", e)
        roms = []

    wlan = network.WLAN(network.STA_IF)
    count = 0

    print("Starting integrated sensor live stream...")
    while True:
        if not wlan.isconnected():
            print("Wi-Fi lost! Attempting recovery...")
            if not connect_wifi():
                print("Could not reconnect. Retrying in 5 seconds...")
                time.sleep(5)
                continue

        # --- A. Read DS18B20 Ambient Sensor ---
        ambient_temp = None
        if roms:
            try:
                ds_sensor.convert_temp()
                time.sleep_ms(750)  # Wait for conversion time window
                for rom in roms:
                    ambient_temp = round(ds_sensor.read_temp(rom), 1)
            except Exception as ds_err:
                print("Failed reading DS18B20:", ds_err)
                ambient_temp = None

        # --- B. Read MLX90640 Thermal Frame ---
        pages = set()
        frame = []
        
        for i in range(4):
            frame = c.get_frame_celsius()
            pages.add(c._driver.mlx90640_frame)
            if len(pages) == 2: 
                break

        if len(pages) != 2:
            print('Incomplete frame - skipped')
            continue

        valid = [v for v in frame if v > -200]
        if not valid:
            print('No valid pixels - skipped')
            continue

        max_thermal = round(max(valid), 1)

        # --- C. Run Local State Classification (OBJ03) ---
        current_state = state_classifier.classify(max_thermal, ambient_temp)

        # --- D. Transmit Data Payloads (OBJ04) ---
        count += 1
        
        # 1. Post live heatmap grid matrix WITH ambient metrics nested inside
        frame_ok = post_thermal_frame(frame, ambient_c=ambient_temp)
        
        # 2. Post sensor telemetry variables to update separate widget indicators
        telemetry_ok = post_telemetry(
            state=current_state,
            max_thermal_c=max_thermal,
            ambient_c=ambient_temp,
            suppression_active=False
        )
        
        # Clear print diagnostics console output tracking both endpoints
        ambient_str = f"{ambient_temp} C" if ambient_temp is not None else "ERROR"
        print(f"[{count}] State: {current_state} | Thermal Max: {max_thermal} C | Ambient: {ambient_str} | Frame Post: {frame_ok} | Telemetry Post: {telemetry_ok}")
            
        time.sleep(config.SENSOR_POLL_INTERVAL_S)

def main():
    """
    The main boot execution sequence.
    """ 
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
