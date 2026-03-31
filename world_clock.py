"""
Shared world clock for the EV charging simulation.
1 simulated hour = REAL_SECONDS_PER_HOUR real seconds (default 3).
The clock cycles through 24 hours continuously.
"""

import threading
import time


class WorldClock:
    """Thread-safe simulation clock that maps real time to a 24-hour cycle."""

    def __init__(self, real_seconds_per_hour: float = 3.0, start_hour: float = 0.0):
        self.real_seconds_per_hour = real_seconds_per_hour
        self._start_real_time = time.monotonic()
        self._start_hour = start_hour

    @property
    def elapsed_real_seconds(self) -> float:
        return time.monotonic() - self._start_real_time

    @property
    def sim_hours(self) -> float:
        """Total simulated hours since start (unbounded)."""
        return self._start_hour + self.elapsed_real_seconds / self.real_seconds_per_hour

    @property
    def time_of_day(self) -> float:
        """Current hour in [0, 24)."""
        return self.sim_hours % 24.0

    @property
    def day(self) -> int:
        """Current day number (0-indexed)."""
        return int(self.sim_hours // 24)

    def formatted_time(self) -> str:
        """Return the current sim time as HH:MM."""
        tod = self.time_of_day
        hours = int(tod)
        minutes = int((tod - hours) * 60)
        return f"{hours:02d}:{minutes:02d}"

    def formatted_day_time(self) -> str:
        """Return 'Day N  HH:MM'."""
        return f"Day {self.day + 1}  {self.formatted_time()}"
