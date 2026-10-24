"""
sensors/mlx90640.py
Wrapper around the verified MLX90640 driver (sensors/mlx90640_driver.py,
sourced from https://github.com/michael-sulyak/micropython-mlx90640, MIT
License - a small refactor of Adafruit's CircuitPython MLX90640 driver).

The only change made to the vendored driver was mechanically stripping
Python type-hint syntax (`import typing`, `-> typing.List[int]`, etc.),
which MicroPython does not support out of the box. That transformation
was verified via an AST diff to be logic-for-logic identical to the
original - no calibration math was touched, written, or altered here.

This wrapper keeps the same get_frame_celsius() / max_temperature()
interface the rest of the firmware (main.py) already expects, so no
other file needs to change now that this is a real implementation
instead of a stub.
"""

from machine import I2C, Pin
from sensors.mlx90640_driver import MLX90640 as _MLX90640Driver, RefreshRate, init_float_array


class MLX90640:
    def __init__(self, i2c_id, sda_pin, scl_pin, freq, addr):
        self.i2c = I2C(i2c_id, sda=Pin(sda_pin), scl=Pin(scl_pin), freq=freq)
        self.addr = addr
        self._driver = None
        self._frame = init_float_array(768)

    def is_connected(self):
        """Quick I2C presence check - does not validate calibration data."""
        return self.addr in self.i2c.scan()

    def load_calibration(self):
        """
        Constructs the real driver, which reads and parses the MLX90640's
        EEPROM calibration table internally (per michael-sulyak/
        micropython-mlx90640, itself based on Adafruit's driver and the
        Melexis datasheet calibration procedure). Raises whatever the
        underlying driver raises (e.g. OSError) if the sensor doesn't
        respond correctly - this is NOT caught here, since a silent
        failure at calibration time could let a bad sensor pass as
        working for a fire detection system.
        """
        self._driver = _MLX90640Driver(self.i2c, self.addr)
        # Start conservative - 2Hz is a safe default matching the
        # driver's own README example. Can be raised once bring-up is
        # confirmed stable; higher rates increase I2C bus load and the
        # chance of read timing issues.
        self._driver.refresh_rate = RefreshRate.REFRESH_2_HZ

    def get_frame_celsius(self):
        """
        Returns a list of 768 floats (32x24) in degrees Celsius.
        Requires load_calibration() to have been called first (main.py
        does this once during startup).
        """
        if self._driver is None:
            raise RuntimeError(
                "load_calibration() must be called before get_frame_celsius()"
            )
        self._driver.get_frame(self._frame)
        return self._frame

    def max_temperature(self):
        frame = self.get_frame_celsius()
        return max(frame)
