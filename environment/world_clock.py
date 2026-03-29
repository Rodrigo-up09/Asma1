"""
environment/world_clock.py

Simulated wall-clock for the EV charging ecosystem.
Moved from project root — constructor signature preserved exactly.
"""

import time


class WorldClock:
    """
    Tracks simulated time independently of real wall-clock time.

    Parameters
    ----------
    real_seconds_per_hour : float
        How many real seconds correspond to one simulated hour.
        e.g. 3.0  →  1 sim-hour passes every 3 real seconds.
    start_hour : float
        Simulation start time in fractional hours (e.g. 7.0 = 07:00).
    """

    def __init__(self, real_seconds_per_hour: float = 3.0, start_hour: float = 0.0) -> None:
        self._real_seconds_per_hour: float = real_seconds_per_hour
        self._start_sim_hour: float = start_hour
        self._start_real: float = time.monotonic()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def current_hour(self) -> float:
        """Return current simulation time as fractional hours [0, 24)."""
        elapsed_real = time.monotonic() - self._start_real
        sim_hours_elapsed = elapsed_real / self._real_seconds_per_hour
        return (self._start_sim_hour + sim_hours_elapsed) % 24.0

    def formatted_time(self) -> str:
        """Return current sim time as 'HH:MM' string."""
        hour_f = self.current_hour()
        hh = int(hour_f)
        mm = int((hour_f - hh) * 60)
        return f"{hh:02d}:{mm:02d}"