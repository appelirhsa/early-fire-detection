"""
alerts.py
Local alarm outputs on PCB2 (OBJ02): buzzer and status LEDs.

Pin map (traced from the PCB2 netlist; override any of them in config.py):
  BUZZER_PIN     GP7   -> R43 -> Q2 (NPN) -> 12 V buzzer (BUZZER3)
  LED_RED_PIN    GP14  -> R28 -> LED5 (red, FIRE)
  LED_AMBER_PIN  GP10  -> R29 -> LED4 (amber, sensor fault)
  LED_BLUE_PIN   GP6   -> R27 -> LED3 (blue, Wi-Fi link)
  (LED2, green, is wired straight to 3.3 V: it is the power-good LED, not software controlled)

The buzzer runs from the 12 V rail through Q2, so it only sounds when the board
is powered from the 12 V supply, not from USB alone.

Behaviour:
  FIRE     -> buzzer ON continuously, red LED ON
  WARNING  -> red LED OFF, buzzer silent (set WARNING_BEEP = True in config.py
              for a short beep on each WARNING frame)
  NORMAL   -> buzzer OFF, red LED OFF
  Wi-Fi    -> blue LED ON while connected
  Sensor   -> amber LED ON when the thermal camera read fails
"""

import time
from machine import Pin, PWM

import config

BUZZER_PIN = getattr(config, "BUZZER_PIN", 7)
LED_RED_PIN = getattr(config, "LED_RED_PIN", 14)
LED_AMBER_PIN = getattr(config, "LED_AMBER_PIN", 10)
LED_BLUE_PIN = getattr(config, "LED_BLUE_PIN", 6)

# "active" buzzer: makes its own tone when powered (just switch it on/off).
# "passive" buzzer: needs a square wave -> driven with PWM at BUZZER_FREQ_HZ.
BUZZER_TYPE = getattr(config, "BUZZER_TYPE", "active")
BUZZER_FREQ_HZ = getattr(config, "BUZZER_FREQ_HZ", 2700)
WARNING_BEEP = getattr(config, "WARNING_BEEP", False)


class AlertOutputs:
    def __init__(self):
        self.red = Pin(LED_RED_PIN, Pin.OUT, value=0)
        self.amber = Pin(LED_AMBER_PIN, Pin.OUT, value=0)
        self.blue = Pin(LED_BLUE_PIN, Pin.OUT, value=0)
        self._pwm = None
        self._buzzer_pin = Pin(BUZZER_PIN, Pin.OUT, value=0)
        if BUZZER_TYPE == "passive":
            self._pwm = PWM(self._buzzer_pin)
            self._pwm.freq(BUZZER_FREQ_HZ)
            self._pwm.duty_u16(0)
        self._buzzing = False
        self.state = None

    # ---------------------------------------------------------------- buzzer
    def _buzzer(self, on):
        if on == self._buzzing:
            return
        if self._pwm is not None:
            self._pwm.duty_u16(32768 if on else 0)
        else:
            self._buzzer_pin.value(1 if on else 0)
        self._buzzing = on

    def beep(self, ms=120):
        """Short blocking beep (start-up self-test, warning chirp)."""
        self._buzzer(True)
        time.sleep_ms(ms)
        self._buzzer(False)

    # ---------------------------------------------------------------- states
    def set_state(self, state):
        """Call once per classification with "NORMAL", "WARNING" or "FIRE"."""
        fire = state == "FIRE"
        self.red.value(1 if fire else 0)
        self._buzzer(fire)
        if state == "WARNING" and WARNING_BEEP:
            self.beep(60)
        if state != self.state:
            print("ALERT:", self.state, "->", state,
                  "| buzzer", "ON" if fire else "off", "| red LED", "ON" if fire else "off")
        self.state = state

    def set_wifi(self, connected):
        self.blue.value(1 if connected else 0)

    def set_sensor_fault(self, fault):
        self.amber.value(1 if fault else 0)

    # ---------------------------------------------------------------- helpers
    def self_test(self):
        """At boot: flash each LED and give one short beep, so you can see/hear them work."""
        for led in (self.blue, self.red, self.amber):
            led.value(1)
            time.sleep_ms(200)
            led.value(0)
        self.beep(150)

    def all_off(self):
        self._buzzer(False)
        self.red.value(0)
        self.amber.value(0)
        self.blue.value(0)