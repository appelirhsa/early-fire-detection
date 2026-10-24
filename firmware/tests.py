
import network
import time
import rp2
import config

# Set regulatory country
rp2.country("ZA")

# Reset Wi-Fi
wlan = network.WLAN(network.STA_IF)
wlan.active(False)
time.sleep(2)
wlan.active(True)
time.sleep(3)

# Check network visibility
networks = wlan.scan()

found = any(
    net[0].decode() == config.WIFI_SSID
    for net in networks
)

print("Target network:", config.WIFI_SSID)
print("Network visible:", found)

if found:
    print("Connecting...")

    wlan.connect(
        config.WIFI_SSID,
        config.WIFI_PASSWORD
    )

    for attempt in range(30):
        if wlan.isconnected():
            break

        status = wlan.status()
        print("Status:", status)

        if status in (-1, -2, -3):
            break

        time.sleep(1)

    if wlan.isconnected():
        print("SUCCESS: Wi-Fi connected!")
        print("IP:", wlan.ifconfig()[0])
        print("Gateway:", wlan.ifconfig()[2])
    else:
        print("FAILED:", wlan.status())
else:
    print("NGOZA not found. Check 2.4 GHz Wi-Fi.")
