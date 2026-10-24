"""
suppression.py
Controls the relay-driven 12V solenoid valve (D4 subsystem in D2 test plan).

Safety design principle: the solenoid must NEVER be triggered off a single
noisy reading. It requires SUPPRESSION_MIN_CONFIRM_READINGS consecutive
FIRE classifications within SUPPRESSION_CONFIRM_WINDOW_S before activating,
and always has a hard auto-cutoff (SUPPRESSION_MAX_ACTIVE_S) regardless of
sensor state afterwards, in case of a stuck relay or logic fault.
"""

import time
from machine import Pin

import config


class SuppressionController:
    def __init__(self):
        self._relay = Pin(config.SUPPRESSION_RELAY_PIN, Pin.OUT)
        self._relay.value(0)
        self._fire_timestamps = []
        self._active_since_ms = None

    def record_classification(self, state):
        """
        Call this once per classification cycle with the latest state
        string: "NORMAL", "WARNING", or "FIRE".
        Returns True if this call caused suppression to activate.
        """
        now = time.ticks_ms()

        if state == "FIRE":
            self._fire_timestamps.append(now)
        else:
            # Any non-FIRE reading resets the confirmation window -
            # we require *consecutive* confirmed detections, not just
            # "3 out of the last N".
            self._fire_timestamps = []

        # Drop timestamps outside the confirmation window
        window_ms = config.SUPPRESSION_CONFIRM_WINDOW_S * 1000
        self._fire_timestamps = [
            t for t in self._fire_timestamps
            if time.ticks_diff(now, t) <= window_ms
        ]

        if (
            not self.is_active()
            and len(self._fire_timestamps) >= config.SUPPRESSION_MIN_CONFIRM_READINGS
        ):
            self._activate()
            return True

        self._check_auto_cutoff()
        return False

    def is_active(self):
        return self._active_since_ms is not None

    def _activate(self):
        self._relay.value(1)
        self._active_since_ms = time.ticks_ms()

    def _check_auto_cutoff(self):
        if self._active_since_ms is None:
            return
        elapsed_s = time.ticks_diff(time.ticks_ms(), self._active_since_ms) / 1000
        if elapsed_s >= config.SUPPRESSION_MAX_ACTIVE_S:
            self.deactivate()

    def deactivate(self):
        """Manual or automatic shutoff of the solenoid."""
        self._relay.value(0)
        self._active_since_ms = None
        self._fire_timestamps = []
