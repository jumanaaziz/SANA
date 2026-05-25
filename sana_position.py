#!/usr/bin/env python3
"""
sana_position.py – SANA Indoor Position Tracker
=================================================
Hardware:
    VL53L1X ToF    I2C 0x29  → obstacle proximity vibration

ToF vibration:
    - Buzzes ONCE when distance crosses a threshold
    - Does NOT repeat until user moves away and comes back closer
    - < 150cm → single buzz (far warning)
    - < 100cm → double buzz (medium warning)
    - < 50cm  → triple buzz (danger warning)
    - Callbacks set from sana_main.py
"""

import time
import threading

# ── CONFIG ────────────────────────────────────────────────────────────────────
POSITION_LOG_SEC  = 5.0

TOF_DANGER_CM     = 50
TOF_MEDIUM_CM     = 100
TOF_WARN_CM       = 150
TOF_CHECK_SEC     = 0.1

# How far the user must move back before buzzing again for the same level
TOF_RESET_MARGIN_CM = 20

MAP_DIRECTIONS = ["north", "east", "south", "west"]


class PositionTracker:

    def __init__(self, start_node_id: str, map_data: dict):
        self.current_node        = start_node_id
        self.map_data            = map_data
        self._running            = False
        self._lock               = threading.Lock()

        self._distance_walked    = 0.0
        self._expected_next_node = None
        self._expected_distance  = 0.0

        self._current_map_heading = "north"

        self._vibrate_far_cb      = None
        self._vibrate_medium_cb   = None
        self._vibrate_fast_cb     = None
        self._tof_started         = False

        # Track which level has already been buzzed
        # Only resets when distance rises back above threshold + margin
        self._buzzed_danger  = False
        self._buzzed_medium  = False
        self._buzzed_far     = False

        self._vl53 = None
        self._init_sensors()

    # ── SENSOR INIT ───────────────────────────────────────────────────────────

    def _init_sensors(self):
        try:
            import board, busio
            i2c = busio.I2C(board.SCL, board.SDA)
            try:
                import adafruit_vl53l1x
                self._vl53 = adafruit_vl53l1x.VL53L1X(i2c)
                self._vl53.distance_mode = 2
                self._vl53.timing_budget = 50
                self._vl53.start_ranging()
            except Exception as e:
                print(f"[POS] VL53L1X failed: {e}", flush=True)
        except Exception as e:
            print(f"[POS] I2C failed: {e} – simulation mode", flush=True)

    # ── TOF ───────────────────────────────────────────────────────────────────

    def get_tof_distance_cm(self) -> float:
        if self._vl53 is None:
            return 999.0
        try:
            dist = self._vl53.distance
            return dist if dist is not None else 999.0
        except Exception:
            return 999.0

    # ── TOF PROXIMITY LOOP ────────────────────────────────────────────────────

    def _tof_loop(self):
        while self._running:
            dist = self.get_tof_distance_cm()

            # ── DANGER < 50cm ─────────────────────────────────────────────────
            if dist < TOF_DANGER_CM:
                if not self._buzzed_danger:
                    self._buzzed_danger = True
                    if self._vibrate_fast_cb:
                        self._vibrate_fast_cb()
            else:
                # Reset danger once user moves back beyond threshold + margin
                if dist > TOF_DANGER_CM + TOF_RESET_MARGIN_CM:
                    self._buzzed_danger = False

            # ── MEDIUM < 100cm ────────────────────────────────────────────────
            if TOF_DANGER_CM <= dist < TOF_MEDIUM_CM:
                if not self._buzzed_medium:
                    self._buzzed_medium = True
                    if self._vibrate_medium_cb:
                        self._vibrate_medium_cb()
            else:
                if dist > TOF_MEDIUM_CM + TOF_RESET_MARGIN_CM:
                    self._buzzed_medium = False

            # ── FAR < 150cm ───────────────────────────────────────────────────
            if TOF_MEDIUM_CM <= dist < TOF_WARN_CM:
                if not self._buzzed_far:
                    self._buzzed_far = True
                    if self._vibrate_far_cb:
                        self._vibrate_far_cb()
            else:
                if dist > TOF_WARN_CM + TOF_RESET_MARGIN_CM:
                    self._buzzed_far = False

            time.sleep(TOF_CHECK_SEC)

    # ── NODE MANAGEMENT ───────────────────────────────────────────────────────

    def set_expected_next(self, node_id: str, distance_m: float):
        with self._lock:
            self._expected_next_node = node_id
            self._expected_distance  = distance_m
            self._distance_walked    = 0.0

    def set_current_node(self, node_id: str):
        with self._lock:
            self.current_node     = node_id
            self._distance_walked = 0.0

    def update_heading(self, heading: str):
        self._current_map_heading = heading

    # ── LOG LOOP ──────────────────────────────────────────────────────────────

    def _log_loop(self):
        while self._running:
            time.sleep(POSITION_LOG_SEC)

    # ── PUBLIC ────────────────────────────────────────────────────────────────

    def set_vibrate_callbacks(self, vibrate_far_cb, vibrate_medium_cb=None, vibrate_fast_cb=None):
        self._vibrate_far_cb    = vibrate_far_cb
        self._vibrate_medium_cb = vibrate_medium_cb or vibrate_far_cb
        self._vibrate_fast_cb   = vibrate_fast_cb or vibrate_medium_cb or vibrate_far_cb

    def start_tof(self):
        if self._tof_started:
            return
        if self._vibrate_far_cb or self._vibrate_medium_cb or self._vibrate_fast_cb:
            self._tof_started = True
            threading.Thread(target=self._tof_loop, daemon=True).start()

    def start(self):
        self._running = True
        print("[POS] Tracker started at N1, facing north", flush=True)

    def stop(self):
        self._running = False

    def get_heading_name(self) -> str:
        return self._current_map_heading

    @property
    def distance_walked(self) -> float:
        with self._lock:
            return self._distance_walked
