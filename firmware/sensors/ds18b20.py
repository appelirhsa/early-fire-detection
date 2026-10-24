"""
sensors/ds18b20.py
Wrapper around MicroPython's built-in onewire + ds18x20 modules for the
DS18B20 ambient temperature sensor.

These two modules ship with standard MicroPython builds for rp2, so no
external library install is required on the Pico 2 W.
"""

import onewire
import ds18x20
from machine import Pin


class DS18B20Sensor:
    def __init__(self, pin_num):
        self._ow = onewire.OneWire(Pin(pin_num))
        self._ds = ds18x20.DS18X20(self._ow)
        self._roms = self._ds.scan()
        if not self._roms:
            raise RuntimeError(
                "No DS18B20 device found on 1-Wire bus (pin {}). "
                "Check wiring and pull-up resistor.".format(pin_num)
            )

    def read_celsius(self):
        """
        Triggers a conversion on all devices found, waits the required
        conversion time, then returns the temperature of the first sensor
        found in degrees Celsius.

        Returns None if the read fails (e.g. sensor disconnected mid-read).
        """
        try:
            self._ds.convert_temp()
        except onewire.OneWireError:
            return None

        # DS18B20 needs up to 750ms for a 12-bit conversion
        import time
        time.sleep_ms(750)

        try:
            return self._ds.read_temp(self._roms[0])
        except onewire.OneWireError:
            return None

    def device_count(self):
        return len(self._roms)
