"""
Schedule Check Scenario:
2 EVs and 3 CS with fixed timed destinations to validate schedule-following behavior.
"""

from agents.cs_agent import CSConfig
from .base import Scenario


class ScheduleCheckScenario(Scenario):
    """Deterministic 2-EV scenario for verifying schedule arrivals."""

    def __init__(self):
        super().__init__(
            name="Schedule Check (2 EV, 3 CS)",
            description="2 EVs with fixed timed stops and 3 CS to verify on-time schedule behavior.",
        )
        self.start_hour = 6.5

        self.num_evs = 2
        self.num_css = 3
        self.night_driver_ratio = 0.0

        # Spot names include owner EV and expected arrival time for easy visual/log verification.
        self.spots = [
            {"name": "EV1 Office [09:00]", "x": 12.0, "y": 14.0},
            {"name": "EV1 Store [12:00]", "x": -15.0, "y": 8.0},
            {"name": "EV1 Factory [15:00]", "x": 20.0, "y": 16.0},
            {"name": "EV1 Park [18:00]", "x": -18.0, "y": 4.0},
            {"name": "EV1 Home [20:00]", "x": -10.0, "y": -6.0},
            {"name": "EV2 Harbor [09:00]", "x": 24.0, "y": -2.0},
            {"name": "EV2 Library [12:00]", "x": 6.0, "y": 20.0},
            {"name": "EV2 Stadium [15:00]", "x": -22.0, "y": -12.0},
            {"name": "EV2 Market [18:00]", "x": 26.0, "y": 10.0},
            {"name": "EV2 Home [20:00]", "x": 14.0, "y": -8.0},
        ]

        self.cs_configs = [
            {
                "jid": "cs1@localhost",
                "password": "password",
                "config": CSConfig(
                    num_doors=2,
                    max_charging_rate=28.0,
                    max_solar_capacity=90.0,
                    actual_solar_capacity=45.0,
                    energy_price=0.20,
                    solar_production_rate=7.0,
                    x=8.0,
                    y=0.0,
                ),
            },
            {
                "jid": "cs2@localhost",
                "password": "password",
                "config": CSConfig(
                    num_doors=2,
                    max_charging_rate=28.0,
                    max_solar_capacity=120.0,
                    actual_solar_capacity=70.0,
                    energy_price=0.14,
                    solar_production_rate=10.0,
                    x=-6.0,
                    y=0.0,
                ),
            },
            {
                "jid": "cs3@localhost",
                "password": "password",
                "config": CSConfig(
                    num_doors=2,
                    max_charging_rate=28.0,
                    max_solar_capacity=80.0,
                    actual_solar_capacity=30.0,
                    energy_price=0.24,
                    solar_production_rate=6.0,
                    x=2.0,
                    y=-10.0,
                ),
            },
        ]

        self.ev_configs = [
            {
                "jid": "ev1@localhost",
                "password": "password",
                "config": {
                    "battery_capacity_kwh": 62.0,
                    "current_soc": 0.95,
                    "target_soc": 0.75,
                    "max_charge_rate_kw": 18.0,
                    "velocity": 3.4,
                    "energy_per_km": 2.0,
                    "x": -10.0,
                    "y": -6.0,
                    "schedule": [
                        {"name": "EV1 Office [09:00]", "x": 12.0, "y": 14.0, "hour": 9.0, "type": "destination"},
                        {"name": "EV1 Store [12:00]", "x": -15.0, "y": 8.0, "hour": 12.0, "type": "destination"},
                        {"name": "EV1 Factory [15:00]", "x": 20.0, "y": 16.0, "hour": 15.0, "type": "destination"},
                        {"name": "EV1 Park [18:00]", "x": -18.0, "y": 4.0, "hour": 18.0, "type": "destination"},
                        {"name": "EV1 Home [20:00]", "x": -10.0, "y": -6.0, "hour": 20.0, "type": "destination"},
                    ],
                    "is_night_driver": False,
                },
            },
            {
                "jid": "ev2@localhost",
                "password": "password",
                "config": {
                    "battery_capacity_kwh": 64.0,
                    "current_soc": 0.95,
                    "target_soc": 0.75,
                    "max_charge_rate_kw": 18.0,
                    "velocity": 3.3,
                    "energy_per_km": 1.9,
                    "x": 14.0,
                    "y": -8.0,
                    "schedule": [
                        {"name": "EV2 Harbor [09:00]", "x": 24.0, "y": -2.0, "hour": 9.0, "type": "destination"},
                        {"name": "EV2 Library [12:00]", "x": 6.0, "y": 20.0, "hour": 12.0, "type": "destination"},
                        {"name": "EV2 Stadium [15:00]", "x": -22.0, "y": -12.0, "hour": 15.0, "type": "destination"},
                        {"name": "EV2 Market [18:00]", "x": 26.0, "y": 10.0, "hour": 18.0, "type": "destination"},
                        {"name": "EV2 Home [20:00]", "x": 14.0, "y": -8.0, "hour": 20.0, "type": "destination"},
                    ],
                    "is_night_driver": False,
                },
            },
        ]
