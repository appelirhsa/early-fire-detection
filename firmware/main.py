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
        print("IP Address :", net_info)
        print("Gateway    :", net_info)
        print("-" * 30)
        return True

def run_thermal_stream():
    """
    Pipelined non-blocking loop for true real-time streaming performance.
    """
    print("Target Dashboard Host:", config.DASHBOARD_HOST)
    
    # 1. Initialize MLX90640 Thermal Sensor at High Frequency (Fast Mode+)
    print("Initializing MLX90640 sensor...")
    try:
        c = MLX90640(config.I2C_ID, config.I2C_SDA_PIN, config.I2C_SCL_PIN, config.I2C_FREQ_HZ, config.MLX90640_I2C_ADDR)
        c.load_calibration()
        print("Camera ready.")
    except Exception as e:
        print("MLX90640 Sensor Initialization Failed:", e)
        return

    # 2. Initialize DS18B20 Ambient Sensor via OneWire
    print("Initializing DS18B20 ambient sensor on Pin", config.ONEWIRE_PIN)
    try:
        ds_pin = machine.Pin(config.ONEWIRE_PIN)
        ds_ow = onewire.OneWire(ds_pin)
        ds_sensor = ds18x20.DS18X20(ds_ow)
        roms = ds_sensor.scan()
        print("DS18B20 ready. Found", len(roms), "device(s).")
        # Prime the sensor cache instantly by ordering an early conversion
        if roms:
            ds_sensor.convert_temp()
    except Exception as e:
        print("DS18B20 Sensor Initialization Failed:", e)
        roms = []

    wlan = network.WLAN(network.STA_IF)
    count = 0
    ambient_temp = 25.0  # Safe initial baseline parameter default
    last_ambient_poll = 0

    print("Starting optimized low-latency live stream...")
    while True:
        if not wlan.isconnected():
            print("Wi-Fi lost! Attempting recovery...")
            if not connect_wifi():
                print("Could not reconnect. Retrying in 5 seconds...")
                time.sleep(5)
                continue

        current_millis = time.ticks_ms()

        # --- A. Non-Blocking Pipelined Ambient Fetch (Every 2 seconds) ---
        if roms and time.ticks_diff(current_millis, last_ambient_poll) >= 2000:
            try:
                # Read the completed temperature values computed in the previous loop background step
                for rom in roms:
                    temp_read = ds_sensor.read_temp(rom)
                    if temp_read is not None:
                        ambient_temp = round(temp_read, 1)
                
                # Order a fresh background conversion calculation immediately and move on (Zero delay!)
                ds_sensor.convert_temp()
                last_ambient_poll = current_millis
            except Exception as ds_err:
                pass # Fail silently to prioritize continuous frame streaming loops

        # --- B. Streamlined Sub-Page Frame Acquisition ---
        pages = set()
        frame = []
        
        # Pull frames instantly. Only look for 2 sub-pages to build a valid matrix
        for i in range(3):
            frame = c.get_frame_celsius()
            pages.add(c._driver.mlx90640_frame[833])
            if len(pages) == 2: 
                break

        if len(pages) != 2:
            continue

        valid = [v for v in frame if v > -200]
        if not valid:
            continue

        max_thermal = round(max(valid), 1)

        # --- C. Classification & Immediate Network Transmission ---
        current_state = state_classifier.classify(max_thermal, ambient_temp)
        count += 1
        
        # Broadcast payloads simultaneously to your AWS endpoint
        frame_ok = post_thermal_frame(frame, ambient_c=ambient_temp)
        telemetry_ok = post_telemetry(
            state=current_state,
            max_thermal_c=max_thermal,
            ambient_c=ambient_temp,
            suppression_active=False
        )
        
        print("[", count, "] Real-Time Stream -> Max Thermal:", max_thermal, "C | Ambient:", ambient_temp, "C | Frame Sent:", frame_ok)
        
        # Explicitly removed time.sleep() completely to maximize frame rate processing frequencies

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
