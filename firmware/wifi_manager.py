"""
wifi_manager.py
WiFi connection handling for the Pico 2 W (CYW43 chip via network module).
Provides connect-with-timeout and a reconnect helper for OBJ05 (continuous,
uninterrupted operation) so a dropped link doesn't require a manual reset.
"""

import time
import network
import config


class WiFiManager:
    def __init__(self):
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)

    def is_connected(self):
        return self.wlan.isconnected()

    def connect(self):
        """
        Attempts to connect using credentials from config.py.
        Returns True on success, False on timeout.
        """
        if self.is_connected():
            return True

        print("WiFi: connecting to {}...".format(config.WIFI_SSID))
        self.wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)

        start = time.ticks_ms()
        timeout_ms = config.WIFI_CONNECT_TIMEOUT_S * 1000

        while not self.wlan.isconnected():
            if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
                print("WiFi: connection attempt timed out")
                return False
            time.sleep_ms(200)

        print("WiFi: connected, IP =", self.wlan.ifconfig()[0])
        return True

    def ensure_connected(self):
        """
        Call periodically from the main loop. Reconnects with a fixed
        backoff if the link has dropped. Non-blocking beyond the backoff
        delay itself - keep this cheap since it runs every cycle.
        """
        if self.is_connected():
            return True

        print("WiFi: link down, retrying in {}s".format(
            config.WIFI_RECONNECT_BACKOFF_S))
        time.sleep(config.WIFI_RECONNECT_BACKOFF_S)
        return self.connect()
