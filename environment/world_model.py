"""
environment/world_model.py

Pure environment logic — no SPADE, no agent concepts.
The WorldAgent calls update() and distributes the result; it never lives here.
"""

from dataclasses import dataclass
import math
from typing import Any, Dict


@dataclass
class WorldState:
    electricity_price: float = 0.15
    grid_load: float = 0.4
    solar_production_rate: float = 0.0


class WorldModel:
    """
    Models the physical / economic environment of the EV charging ecosystem.

    All logic is deterministic given an hour value — trivially testable
    without spinning up any agents.
    """

    def __init__(
        self,
        map_min_x: float = -30.0,
        map_max_x: float = 30.0,
        map_min_y: float = -30.0,
        map_max_y: float = 30.0,
    ) -> None:
        self._state = WorldState()
        self.map_min_x = float(map_min_x)
        self.map_max_x = float(map_max_x)
        self.map_min_y = float(map_min_y)
        self.map_max_y = float(map_max_y)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, hour: float) -> Dict[str, Any]:
        """
        Recalculate environment state for the given simulation hour.

        Parameters
        ----------
        hour : float
            Current simulation time in fractional hours [0, 24).

        Returns
        -------
        dict with keys:
            electricity_price   (float, €/kWh)
            grid_load           (float, 0–1 normalised)
            solar_production_rate (float, kW)
        """
        self._state.electricity_price = self._calc_electricity_price(hour)
        self._state.grid_load = self._calc_grid_load(hour)
        self._state.solar_production_rate = self._calc_base_solar_production_rate(hour)

        return {
            "electricity_price": self._state.electricity_price,
            "grid_load": self._state.grid_load,
            "solar_production_rate": self._state.solar_production_rate,
        }

    @property
    def state(self) -> WorldState:
        """Read-only snapshot of the most recent state."""
        return self._state

    # ------------------------------------------------------------------
    # Private helpers — one rule per method for easy future extension
    # ------------------------------------------------------------------

    @staticmethod
    def _calc_electricity_price(hour: float) -> float:
        """
        Night  (00-06) → 0.10 €/kWh   off-peak
        Day    (06-18) → 0.15 €/kWh   standard
        Peak   (18-22) → 0.25 €/kWh   evening peak
        Late   (22-24) → 0.10 €/kWh   off-peak again
        """
        if hour < 6:
            return 0.10
        if hour < 18:
            return 0.15
        if hour < 22:
            return 0.25
        return 0.10

    @staticmethod
    def _calc_grid_load(hour: float) -> float:
        """
        Morning peak  (07-10) → 0.80
        Evening peak  (18-22) → 0.90
        Otherwise             → 0.40
        """
        if 7 <= hour < 10:
            return 0.80
        if 18 <= hour < 22:
            return 0.90
        return 0.40

    @staticmethod
    def _calc_base_solar_production_rate(hour: float) -> float:
        """Simulate the time-of-day solar envelope in kW (no spatial effect)."""
        if hour >= 20 or hour < 5:
            return 0.0
        if 12 <= hour < 15:
            return 18.0
        if 10 <= hour < 12 or 15 <= hour < 17:
            return 12.0
        if 5 <= hour < 10 or 17 <= hour < 20:
            return 4.0
        return 0.0

    @staticmethod
    def _is_daylight(hour: float) -> bool:
        return 5.0 <= hour < 20.0

    def _sun_progress(self, hour: float) -> float:
        """Map daylight time to [0, 1] for horizontal sun movement."""
        day_start = 5.0
        day_end = 20.0
        daylight_span = day_end - day_start
        if daylight_span <= 0.0:
            return 0.0
        progress = (hour - day_start) / daylight_span
        return min(1.0, max(0.0, progress))

    def get_sun_position(self, hour: float) -> Dict[str, float]:
        """Return sun position for the current hour.

        At night, returns {"active": False, "x": 0.0, "y": 0.0}.
        During daylight, sun moves from x=min_x to x=max_x at y=max_y/2.
        """
        if not self._is_daylight(hour):
            return {"active": False, "x": 0.0, "y": 0.0}

        progress = self._sun_progress(hour)
        sun_x = self.map_min_x + progress * (self.map_max_x - self.map_min_x)
        sun_y = self.map_max_y / 2.0
        return {"active": True, "x": sun_x, "y": sun_y}

    def _spatial_light_intensity(self, x: float, y: float, sun_x: float, sun_y: float) -> float:
        """Compute relative solar intensity [0, 1] by distance to sun position."""
        distance = math.hypot(float(x) - sun_x, float(y) - sun_y)
        map_width = max(1.0, self.map_max_x - self.map_min_x)
        sigma = max(1.0, 0.30 * map_width)
        intensity = math.exp(-((distance ** 2) / (2.0 * (sigma ** 2))))
        return min(1.0, max(0.0, intensity))

    def solar_production_at_position(self, hour: float, x: float, y: float) -> float:
        """Return local solar production at a map position (kW)."""
        base_solar = self._calc_base_solar_production_rate(hour)
        if base_solar <= 0.0:
            return 0.0

        sun = self.get_sun_position(hour)
        if not sun["active"]:
            return 0.0

        intensity = self._spatial_light_intensity(x, y, sun["x"], sun["y"])
        return base_solar * intensity