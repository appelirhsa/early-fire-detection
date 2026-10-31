"""
suppression.py
Suppression / extraction fan output, driven by the fire state and intensity.

    NORMAL   -> fan OFF
    WARNING  -> fan slow  (FAN_WARNING_SPEED %, default 30 %)
    FIRE     -> fan fast: FAN_FIRE_MIN_SPEED % (default 60 %) at the fire threshold,
                rising linearly to 100 % at FAN_FULL_SPEED_C (default 120 C)

This mirrors how an off-the-shelf suppression system scales its response with
fire intensity. (Blowing air at a real fire is NOT a valid suppression method;
the fan stands in for the suppression actuator in this demonstration.)

Two ways to drive the fan (set FAN_DRIVE in config.py):

  "relay" (default) - PCB relay on GP11 (Q1 -> RELAY1, COM/NO -> fan).
      A relay can only switch fully on or off, so speed is set by
      time-proportioning: in every FAN_RELAY_PERIOD_MS window (default 2 s)
      the fan is ON for <percent> of the window. 100 % = relay held closed.
      Runs from a timer, so it keeps working while uploads are in progress.

  "pwm" - a logic-level N-MOSFET driving the fan (gate on FAN_PIN), switched
      at 20 kHz for genuinely smooth speed control.

The fan is controlled locally on the Pico, so it keeps working even if
Wi-Fi or the dashboard is down.
"""

from machine import Pin, PWM, Timer

import config

FAN_PIN = getattr(config, "FAN_PIN", getattr(config, "RELAY_PIN", 11))
FAN_DRIVE = getattr(config, "FAN_DRIVE", "relay")          # "relay" or "pwm"

FIRE_THRESHOLD_C = getattr(config, "FIRE_THRESHOLD_C", 65.0)
FAN_WARNING_SPEED = getattr(config, "FAN_WARNING_SPEED", 30)     # %
FAN_FIRE_MIN_SPEED = getattr(config, "FAN_FIRE_MIN_SPEED", 60)   # % at the fire threshold
FAN_FULL_SPEED_C = getattr(config, "FAN_FULL_SPEED_C", 120.0)    # temperature for 100 %

FAN_RELAY_PERIOD_MS = getattr(config, "FAN_RELAY_PERIOD_MS", 2000)
RELAY_MIN_SWITCH_MS = 250      # never switch the relay faster than this (contact wear)
TICK_MS = 50                   # timer resolution in relay mode
PWM_FREQ_HZ = 20000            # above hearing, so the motor does not whine


def speed_for(state, max_thermal_c):
    """Fan speed (0-100 %) for a classified state and the hottest pixel."""
    if state == "WARNING":
        return FAN_WARNING_SPEED
    if state == "FIRE":
        if max_thermal_c is None:
            return 100
        span = FAN_FULL_SPEED_C - FIRE_THRESHOLD_C
        frac = (max_thermal_c - FIRE_THRESHOLD_C) / span if span > 0 else 1
        frac = min(1.0, max(0.0, frac))
        return int(round(FAN_FIRE_MIN_SPEED + (100 - FAN_FIRE_MIN_SPEED) * frac))
    return 0                    # NORMAL, unknown or sensor fault -> off


class FanController:
    def __init__(self):
        self.percent = 0
        self._on_ms = 0
        self._phase = 0
        self._pwm = None
        self._timer = None
        if FAN_DRIVE == "pwm":
            self._pwm = PWM(Pin(FAN_PIN))
            self._pwm.freq(PWM_FREQ_HZ)
            self._pwm.duty_u16(0)
            self._pin = None
        else:
            self._pin = Pin(FAN_PIN, Pin.OUT, value=0)
            self._timer = Timer(period=TICK_MS, mode=Timer.PERIODIC, callback=self._tick)
        print("FAN: {} mode on GP{} (warning {} %, fire {}-100 % up to {} C)".format(
            FAN_DRIVE, FAN_PIN, FAN_WARNING_SPEED, FAN_FIRE_MIN_SPEED, FAN_FULL_SPEED_C))

    # -------------------------------------------------------------- relay timing
    def _tick(self, _t):
        """Timer callback (relay mode): ON for the first _on_ms of each period."""
        self._phase += TICK_MS
        if self._phase >= FAN_RELAY_PERIOD_MS:
            self._phase = 0
        self._pin.value(1 if self._phase < self._on_ms else 0)

    def _relay_on_ms(self, percent):
        if percent <= 0:
            return 0
        if percent >= 100:
            return FAN_RELAY_PERIOD_MS          # held closed: no switching at all
        on = FAN_RELAY_PERIOD_MS * percent // 100
        if on < RELAY_MIN_SWITCH_MS:
            on = RELAY_MIN_SWITCH_MS
        if FAN_RELAY_PERIOD_MS - on < RELAY_MIN_SWITCH_MS:
            on = FAN_RELAY_PERIOD_MS            # off-time too short to be useful
        return on

    # -------------------------------------------------------------- public API
    def set_percent(self, percent):
        percent = int(min(100, max(0, percent)))
        if percent == self.percent:
            return
        if self._pwm is not None:
            self._pwm.duty_u16(65535 * percent // 100)
        else:
            self._on_ms = self._relay_on_ms(percent)
        print("FAN:", self.percent, "% ->", percent, "%")
        self.percent = percent

    def update(self, state, max_thermal_c):
        """Call once per frame. Returns the fan speed in %."""
        self.set_percent(speed_for(state, max_thermal_c))
        return self.percent

    def stop(self):
        self.set_percent(0)
        if self._pin is not None:
            self._pin.value(0)
            