"""
Realistic Chaos Scenario:
Fixed, deterministic BUT chaotic scenario designed to stress-test the system.

10 EVs with varied profiles, many starting with critically low battery,
overlapping schedules causing CS contention, and only 3 CS with limited doors.
Real-world speeds and energy consumption.

Map: 40×40 units (−20 to 20). 1 unit ≈ 1 km.
"""

from agents.cs_agent import CSConfig
from .base import Scenario


# ══════════════════════════════════════════════════════════════════════
#  Fixed city locations
# ══════════════════════════════════════════════════════════════════════

LOCATIONS = [
    {"name": "Centro", "x": 0.0, "y": 0.0},
    {"name": "Universidade", "x": -8.0, "y": 12.0},
    {"name": "Hospital", "x": 10.0, "y": 6.0},
    {"name": "Supermercado", "x": 5.0, "y": -4.0},
    {"name": "Parque Industrial", "x": -14.0, "y": -8.0},
    {"name": "Escola", "x": 3.0, "y": 10.0},
    {"name": "Estádio", "x": 16.0, "y": -2.0},
    {"name": "Shopping", "x": -6.0, "y": -12.0},
    {"name": "Aeroporto", "x": 18.0, "y": 14.0},
    {"name": "Câmara Municipal", "x": -2.0, "y": 4.0},
    {"name": "Porto", "x": -18.0, "y": -2.0},
    {"name": "Praia", "x": 19.0, "y": -18.0},
]


# ══════════════════════════════════════════════════════════════════════
#  Real EV profiles
# ══════════════════════════════════════════════════════════════════════

EV_PROFILES = {
    "compact": {  # Renault Zoe / Fiat 500e
        "battery_capacity_kwh": 65.0,
        "energy_per_km": 2.4,
        "max_charge_rate_kw": 20.0,
        "velocity": 3.6,
    },
    "midrange": {  # VW ID.3 / MG4
        "battery_capacity_kwh": 68.0,
        "energy_per_km": 2.8,
        "max_charge_rate_kw": 21.0,
        "velocity": 3.8,
    },
    "large": {  # Tesla Model 3 / Ioniq 5
        "battery_capacity_kwh": 70.0,
        "energy_per_km": 3.2,
        "max_charge_rate_kw": 22.0,
        "velocity": 4.0,
    },
}


class RealisticTestScenario(Scenario):
    """Fixed chaotic scenario — 20 EVs fighting over 3 CS with limited doors."""

    def __init__(self):
        super().__init__(
            name="Realistic Chaos (20 EV, 3 CS)",
            description=(
                "20 EVs (many with low battery!) fight over 3 CS with only 4 total doors. "
                "Realistic speeds & consumption. Maximum contention guaranteed."
            ),
        )
        self.start_hour = 7.0
        self.log_name = "RealisticChaos"

        self.num_evs = 10
        self.num_css = 3
        self.night_driver_ratio = 0.3
        self.spots = LOCATIONS

        # ── Charging Stations (only 4 doors total for 10 EVs!) ────────
        self.cs_configs = [
            {  # CS1: Centro — 2 doors, moderate
                "jid": "cs1@localhost",
                "password": "password",
                "config": CSConfig(
                    num_doors=2,
                    max_charging_rate=22.0,
                    max_solar_capacity=100.0,
                    actual_solar_capacity=60.0,
                    energy_price=0.18,
                    solar_production_rate=12.0,
                    x=2.0,
                    y=2.0,
                ),
            },
            {  # CS2: Norte — 1 door, cheap but slow
                "jid": "cs2@localhost",
                "password": "password",
                "config": CSConfig(
                    num_doors=1,
                    max_charging_rate=7.4,
                    max_solar_capacity=200.0,
                    actual_solar_capacity=150.0,
                    energy_price=0.10,
                    solar_production_rate=20.0,
                    x=-10.0,
                    y=10.0,
                ),
            },
            {  # CS3: Sul — 1 door, fast but expensive
                "jid": "cs3@localhost",
                "password": "password",
                "config": CSConfig(
                    num_doors=1,
                    max_charging_rate=50.0,
                    max_solar_capacity=80.0,
                    actual_solar_capacity=30.0,
                    energy_price=0.30,
                    solar_production_rate=6.0,
                    x=14.0,
                    y=-6.0,
                ),
            },
        ]

        # ── 10 EVs — designed for MAXIMUM CHAOS ──────────────────────
        # Many start with critically low battery → immediate charger rush
        # Overlapping schedules force CS contention
        # Mix of profiles means different charge rates & consumption
        self.ev_configs = [
            # ── WAVE 1: 4 EVs all start CRITICAL (≤20%) → race to chargers ──
            self._ev(
                1,
                "compact",
                soc=0.88,
                home=(-3.0, 1.0),
                schedule=[
                    {
                        "name": "Centro",
                        "x": 0.0,
                        "y": 0.0,
                        "hour": 8.0,
                        "type": "destination",
                    },
                    {
                        "name": "Hospital",
                        "x": 10.0,
                        "y": 6.0,
                        "hour": 11.5,
                        "type": "destination",
                    },
                    {
                        "name": "Praia",
                        "x": 19.0,
                        "y": -18.0,
                        "hour": 15.0,
                        "type": "destination",
                    },
                    {
                        "name": "Shopping",
                        "x": -6.0,
                        "y": -12.0,
                        "hour": 18.5,
                        "type": "destination",
                    },
                ],
            ),
            self._ev(
                2,
                "midrange",
                soc=0.86,
                home=(8.0, 3.0),
                night_driver=True,
                schedule=[
                    {
                        "name": "Night Shift",
                        "x": 15.0,
                        "y": 18.0,
                        "hour": 19.0,
                        "type": "destination",
                    },
                    {
                        "name": "Warehouse",
                        "x": -18.0,
                        "y": -12.0,
                        "hour": 22.5,
                        "type": "destination",
                    },
                    {
                        "name": "Bar",
                        "x": 3.0,
                        "y": 2.0,
                        "hour": 1.0,
                        "type": "destination",
                    },
                    {
                        "name": "Airport",
                        "x": 18.0,
                        "y": 18.0,
                        "hour": 4.5,
                        "type": "destination",
                    },
                ],
            ),
            self._ev(
                3,
                "large",
                soc=0.84,
                home=(1.0, -5.0),
                schedule=[
                    {
                        "name": "Parque Industrial",
                        "x": -14.0,
                        "y": -8.0,
                        "hour": 8.0,
                        "type": "destination",
                    },
                    {
                        "name": "Universidade",
                        "x": -8.0,
                        "y": 12.0,
                        "hour": 11.5,
                        "type": "destination",
                    },
                    {
                        "name": "Aeroporto",
                        "x": 18.0,
                        "y": 14.0,
                        "hour": 15.0,
                        "type": "destination",
                    },
                    {
                        "name": "Praia",
                        "x": 19.0,
                        "y": -18.0,
                        "hour": 18.5,
                        "type": "destination",
                    },
                ],
            ),
            self._ev(
                4,
                "compact",
                soc=0.90,
                home=(-7.0, -3.0),
                schedule=[
                    {
                        "name": "Escola",
                        "x": 3.0,
                        "y": 10.0,
                        "hour": 8.0,
                        "type": "destination",
                    },
                    {
                        "name": "Supermercado",
                        "x": 5.0,
                        "y": -4.0,
                        "hour": 11.5,
                        "type": "destination",
                    },
                    {
                        "name": "Câmara Municipal",
                        "x": -2.0,
                        "y": 4.0,
                        "hour": 15.0,
                        "type": "destination",
                    },
                    {
                        "name": "Porto",
                        "x": -18.0,
                        "y": -2.0,
                        "hour": 18.5,
                        "type": "destination",
                    },
                ],
            ),
            # ── WAVE 2: 3 EVs start mid-low (25-40%) → will need charging mid-day ──
            self._ev(
                5,
                "midrange",
                soc=0.82,
                home=(15.0, 12.0),
                night_driver=True,
                schedule=[
                    {
                        "name": "Warehouse",
                        "x": -18.0,
                        "y": -12.0,
                        "hour": 19.0,
                        "type": "destination",
                    },
                    {
                        "name": "Night Shift",
                        "x": 15.0,
                        "y": 18.0,
                        "hour": 22.5,
                        "type": "destination",
                    },
                    {
                        "name": "Gas Station",
                        "x": 10.0,
                        "y": -5.0,
                        "hour": 1.0,
                        "type": "destination",
                    },
                    {
                        "name": "Club",
                        "x": 0.0,
                        "y": 8.0,
                        "hour": 4.5,
                        "type": "destination",
                    },
                ],
            ),
            self._ev(
                6,
                "large",
                soc=0.85,
                home=(-12.0, -6.0),
                schedule=[
                    {
                        "name": "Parque Industrial",
                        "x": -14.0,
                        "y": -8.0,
                        "hour": 8.0,
                        "type": "destination",
                    },
                    {
                        "name": "Estádio",
                        "x": 16.0,
                        "y": -2.0,
                        "hour": 11.5,
                        "type": "destination",
                    },
                    {
                        "name": "Universidade",
                        "x": -8.0,
                        "y": 12.0,
                        "hour": 15.0,
                        "type": "destination",
                    },
                    {
                        "name": "Shopping",
                        "x": -6.0,
                        "y": -12.0,
                        "hour": 18.5,
                        "type": "destination",
                    },
                ],
            ),
            self._ev(
                7,
                "compact",
                soc=0.87,
                home=(6.0, 8.0),
                schedule=[
                    {
                        "name": "Escola",
                        "x": 3.0,
                        "y": 10.0,
                        "hour": 8.0,
                        "type": "destination",
                    },
                    {
                        "name": "Shopping",
                        "x": -6.0,
                        "y": -12.0,
                        "hour": 11.5,
                        "type": "destination",
                    },
                    {
                        "name": "Estádio",
                        "x": 16.0,
                        "y": -2.0,
                        "hour": 15.0,
                        "type": "destination",
                    },
                    {
                        "name": "Centro",
                        "x": 0.0,
                        "y": 0.0,
                        "hour": 18.5,
                        "type": "destination",
                    },
                ],
            ),
            # ── WAVE 3: 3 EVs with enough battery but LONG cross-city trips ──
            self._ev(
                8,
                "midrange",
                soc=0.83,
                home=(-16.0, 8.0),
                night_driver=True,
                schedule=[
                    {
                        "name": "Club",
                        "x": 0.0,
                        "y": 8.0,
                        "hour": 19.0,
                        "type": "destination",
                    },
                    {
                        "name": "Hospital",
                        "x": -18.0,
                        "y": 5.0,
                        "hour": 22.5,
                        "type": "destination",
                    },
                    {
                        "name": "Bar",
                        "x": 3.0,
                        "y": 2.0,
                        "hour": 1.0,
                        "type": "destination",
                    },
                    {
                        "name": "Factory",
                        "x": -10.0,
                        "y": -18.0,
                        "hour": 4.5,
                        "type": "destination",
                    },
                ],
            ),
            self._ev(
                9,
                "large",
                soc=0.89,
                home=(18.0, -15.0),
                schedule=[
                    {
                        "name": "Praia",
                        "x": 19.0,
                        "y": -18.0,
                        "hour": 8.0,
                        "type": "destination",
                    },
                    {
                        "name": "Universidade",
                        "x": -8.0,
                        "y": 12.0,
                        "hour": 11.5,
                        "type": "destination",
                    },
                    {
                        "name": "Porto",
                        "x": -18.0,
                        "y": -2.0,
                        "hour": 15.0,
                        "type": "destination",
                    },
                    {
                        "name": "Aeroporto",
                        "x": 18.0,
                        "y": 14.0,
                        "hour": 18.5,
                        "type": "destination",
                    },
                ],
            ),
            self._ev(
                10,
                "compact",
                soc=0.85,
                home=(-1.0, -10.0),
                schedule=[
                    {
                        "name": "Shopping",
                        "x": -6.0,
                        "y": -12.0,
                        "hour": 8.0,
                        "type": "destination",
                    },
                    {
                        "name": "Aeroporto",
                        "x": 18.0,
                        "y": 14.0,
                        "hour": 11.5,
                        "type": "destination",
                    },
                    {
                        "name": "Parque Industrial",
                        "x": -14.0,
                        "y": -8.0,
                        "hour": 15.0,
                        "type": "destination",
                    },
                    {
                        "name": "Estádio",
                        "x": 16.0,
                        "y": -2.0,
                        "hour": 18.5,
                        "type": "destination",
                    },
                ],
            ),
        ]

        day_route_templates = [
            [
                {"name": "Centro", "x": 0.0, "y": 0.0, "hour": 8.0, "type": "destination"},
                {"name": "Hospital", "x": 10.0, "y": 6.0, "hour": 11.5, "type": "destination"},
                {"name": "Supermercado", "x": 5.0, "y": -4.0, "hour": 15.0, "type": "destination"},
                {"name": "Escola", "x": 3.0, "y": 10.0, "hour": 18.5, "type": "destination"},
            ],
            [
                {"name": "Estádio", "x": 16.0, "y": -2.0, "hour": 8.0, "type": "destination"},
                {"name": "Aeroporto", "x": 18.0, "y": 14.0, "hour": 11.5, "type": "destination"},
                {"name": "Porto", "x": -18.0, "y": -2.0, "hour": 15.0, "type": "destination"},
                {"name": "Centro", "x": 0.0, "y": 0.0, "hour": 18.5, "type": "destination"},
            ],
            [
                {"name": "Parque Industrial", "x": -14.0, "y": -8.0, "hour": 8.0, "type": "destination"},
                {"name": "Universidade", "x": -8.0, "y": 12.0, "hour": 11.5, "type": "destination"},
                {"name": "Aeroporto", "x": 18.0, "y": 14.0, "hour": 15.0, "type": "destination"},
                {"name": "Praia", "x": 19.0, "y": -18.0, "hour": 18.5, "type": "destination"},
            ],
            [
                {"name": "Escola", "x": 3.0, "y": 10.0, "hour": 8.0, "type": "destination"},
                {"name": "Supermercado", "x": 5.0, "y": -4.0, "hour": 11.5, "type": "destination"},
                {"name": "Câmara Municipal", "x": -2.0, "y": 4.0, "hour": 15.0, "type": "destination"},
                {"name": "Porto", "x": -18.0, "y": -2.0, "hour": 18.5, "type": "destination"},
            ],
            [
                {"name": "Hospital", "x": 10.0, "y": 6.0, "hour": 8.0, "type": "destination"},
                {"name": "Centro", "x": 0.0, "y": 0.0, "hour": 11.5, "type": "destination"},
                {"name": "Câmara Municipal", "x": -2.0, "y": 4.0, "hour": 15.0, "type": "destination"},
                {"name": "Shopping", "x": -6.0, "y": -12.0, "hour": 18.5, "type": "destination"},
            ],
        ]

        night_route_templates = [
            [
                {"name": "Night Shift", "x": 15.0, "y": 18.0, "hour": 19.0, "type": "destination"},
                {"name": "Warehouse", "x": -18.0, "y": -12.0, "hour": 22.5, "type": "destination"},
                {"name": "Bar", "x": 3.0, "y": 2.0, "hour": 1.0, "type": "destination"},
                {"name": "Airport", "x": 18.0, "y": 18.0, "hour": 4.5, "type": "destination"},
            ],
            [
                {"name": "Warehouse", "x": -18.0, "y": -12.0, "hour": 19.0, "type": "destination"},
                {"name": "Night Shift", "x": 15.0, "y": 18.0, "hour": 22.5, "type": "destination"},
                {"name": "Gas Station", "x": 10.0, "y": -5.0, "hour": 1.0, "type": "destination"},
                {"name": "Club", "x": 0.0, "y": 8.0, "hour": 4.5, "type": "destination"},
            ],
            [
                {"name": "Club", "x": 0.0, "y": 8.0, "hour": 19.0, "type": "destination"},
                {"name": "Hospital", "x": -18.0, "y": 5.0, "hour": 22.5, "type": "destination"},
                {"name": "Bar", "x": 3.0, "y": 2.0, "hour": 1.0, "type": "destination"},
                {"name": "Factory", "x": -10.0, "y": -18.0, "hour": 4.5, "type": "destination"},
            ],
        ]

        extra_ev_specs = [
            (11, "compact", 0.81, (-4.0, 6.0), False, 0, 0),
            (12, "midrange", 0.84, (9.0, 8.0), False, 1, 1),
            (13, "large", 0.86, (-11.0, -4.0), False, 2, 2),
            (14, "compact", 0.79, (13.0, -9.0), False, 3, 3),
            (15, "midrange", 0.83, (1.0, 14.0), False, 4, 4),
            (16, "large", 0.88, (7.0, -14.0), False, 0, 5),
            (17, "compact", 0.80, (-15.0, 2.0), False, 1, 6),
            (18, "midrange", 0.82, (4.0, -9.0), False, 2, 7),
            (19, "large", 0.87, (12.0, 1.0), False, 3, 8),
            (20, "compact", 0.78, (-2.0, 13.0), False, 4, 9),
        ]

        for ev_index, profile, soc, home, night_driver, route_template_index, _ in extra_ev_specs:
            route_templates = day_route_templates
            route = route_templates[route_template_index % len(route_templates)]
            self.ev_configs.append(
                self._ev(
                    ev_index,
                    profile,
                    soc=soc,
                    home=home,
                    schedule=route,
                    night_driver=night_driver,
                )
            )

        self.num_evs = len(self.ev_configs)
        self.description = (
            "20 EVs (mixed day/night) fight over 3 CS with only 4 total doors. "
            "Realistic speeds & consumption. Maximum contention guaranteed."
        )

    @staticmethod
    def _ev(index, profile, soc, home, schedule, night_driver=False):
        """Build an EV config dict from a named profile."""
        p = EV_PROFILES[profile]
        full_schedule = schedule + [
            {
                "name": "Home",
                "x": home[0],
                "y": home[1],
                "hour": 6.0 if night_driver else 20.0,
                "type": "destination",
            },
        ]
        return {
            "jid": f"ev{index}@localhost",
            "password": "password",
            "config": {
                "battery_capacity_kwh": p["battery_capacity_kwh"],
                "current_soc": soc,
                "target_soc": 0.80,
                "max_charge_rate_kw": p["max_charge_rate_kw"],
                "velocity": p["velocity"],
                "energy_per_km": p["energy_per_km"],
                "x": home[0],
                "y": home[1],
                "schedule": full_schedule,
                "is_night_driver": night_driver,
            },
        }
