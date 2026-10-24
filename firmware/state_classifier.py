"""
state_classifier.py
OBJ03: classify environment into NORMAL / WARNING / FIRE.

This is a placeholder threshold-based classifier so the rest of the
firmware (suppression interlock, alerts, dashboard reporting) can be
built and tested end-to-end right now, without hardware or a trained
model. Replace `classify()` with real TensorFlow Lite Micro inference
once your Semester 1 model is ready to integrate - keep the same
function signature so nothing else in the firmware needs to change.
"""

import config


def classify(max_thermal_c, ambient_c):
    """
    Placeholder logic: combines the hottest pixel from the MLX90640
    frame with the DS18B20 ambient reading. Real model should eventually
    take the full 32x24 frame as input rather than just a max value -
    this is a deliberately simple stand-in.

    Returns one of: "NORMAL", "WARNING", "FIRE"
    """
    if max_thermal_c is None:
        # Sensor read failure - treat conservatively as WARNING, not
        # NORMAL, so a failed sensor never masks a real fire, and not
        # FIRE, so a transient I2C glitch can't trigger suppression.
        return "WARNING"

    if max_thermal_c >= config.TEMP_FIRE_C:
        return "FIRE"
    elif max_thermal_c >= config.TEMP_WARNING_C:
        return "WARNING"
    else:
        return "NORMAL"
