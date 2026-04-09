"""
environment/world_model.py

Pure environment logic — no SPADE, no agent concepts.
The WorldAgent calls update() and distributes the result; it never lives here.
"""

from dataclasses import dataclass
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

    def __init__(self) -> None:
        self._state = WorldState()

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
        self._state.solar_production_rate = self._calc_solar_production_rate(hour)

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
    def _calc_solar_production_rate(hour: float) -> float:
        """Simulate a simple solar production curve in kW.

        - Zero production between 20:00 and 05:00.
        - High production between 12:00 and 15:00.
        - Shoulder periods around sunrise/sunset.
        """
        if hour >= 20 or hour < 5:
            return 0.0
        if 12 <= hour < 15:
            return 18.0
        if 10 <= hour < 12 or 15 <= hour < 17:
            return 12.0
        if 5 <= hour < 10 or 17 <= hour < 20:
            return 4.0
        return 0.0