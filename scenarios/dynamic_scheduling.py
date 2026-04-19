"""
Dynamic Scheduling Scenario:
Demonstrates EV scheduling with daily regenerated midpoint destinations.

Features:
- Each EV has fixed appointment times (8:00, 11:30, 15:00, 18:30, 20:00-home)
- Midpoint destinations change randomly every 24-hour cycle
- Variability ensures different routing patterns across simulation days
- Useful for testing EV routing and charging station load balancing
"""

import random
from agents.cs_agent import CSConfig
from .base import Scenario
from .utils import generate_scenario_schedule


class DynamicScheduling(Scenario):
    """Scenario with dynamic schedule regeneration - midpoints change daily."""
    
    def __init__(self):
        """Initialize dynamic scheduling scenario with 5 EVs and 2 CSs."""
        super().__init__(
            name="Dynamic Scheduling",
            description="EV schedules with daily regenerated midpoints",
        )
        
        self.num_evs = 5
        self.num_css = 2
        self.night_driver_ratio = 0.2  # 1 out of 5 is night driver
        
        # Available spots for random selection during daily regen
        self.spots = [
            {"name": "Downtown Plaza", "x": 15.0, "y": 15.0},
            {"name": "University", "x": -12.0, "y": 18.0},
            {"name": "Industrial Zone", "x": 18.0, "y": -20.0},
            {"name": "Harbor", "x": -20.0, "y": -15.0},
            {"name": "Shopping Center", "x": 5.0, "y": 10.0},
            {"name": "Hospital", "x": -8.0, "y": 5.0},
            {"name": "Airport", "x": 22.0, "y": 22.0},
            {"name": "Business Park", "x": 10.0, "y": -10.0},
            {"name": "Sports Complex", "x": -15.0, "y": -5.0},
            {"name": "Tech Park", "x": 8.0, "y": 12.0},
        ]
        
        # ══════════════════════════════════════════════════════════════════════
        #  Charging Stations
        # ══════════════════════════════════════════════════════════════════════
        self.cs_configs = [
            {
                "jid": "cs1@localhost",
                "password": "password",
                "config": CSConfig(
                    num_doors=3,
                    max_charging_rate=22.0,
                    max_solar_capacity=150.0,
                    actual_solar_capacity=90.0,
                    energy_price=0.18,
                    solar_production_rate=12.0,
                    x=10.0,
                    y=5.0,
                ),
            },
            {
                "jid": "cs2@localhost",
                "password": "password",
                "config": CSConfig(
                    num_doors=2,
                    max_charging_rate=11.0,
                    max_solar_capacity=100.0,
                    actual_solar_capacity=60.0,
                    energy_price=0.22,
                    solar_production_rate=8.0,
                    x=-12.0,
                    y=-8.0,
                ),
            },
        ]
        
        # ══════════════════════════════════════════════════════════════════════
        #  Electric Vehicles
        # ══════════════════════════════════════════════════════════════════════
        self.ev_configs = []
        
        base_ev_configs = [
            {"battery": 60.0, "soc": 0.40, "rate": 11.0, "velocity": 2.0, "energy": 2.5},
            {"battery": 65.0, "soc": 0.50, "rate": 22.0, "velocity": 1.8, "energy": 2.3},
            {"battery": 58.0, "soc": 0.35, "rate": 7.0, "velocity": 2.2, "energy": 2.8},
            {"battery": 70.0, "soc": 0.55, "rate": 11.0, "velocity": 2.1, "energy": 2.4},
            {"battery": 55.0, "soc": 0.45, "rate": 7.0, "velocity": 1.9, "energy": 2.6},
        ]
        
        for i in range(1, self.num_evs + 1):
            # Randomize home locations across the map
            home_x = random.uniform(-20, 20)
            home_y = random.uniform(-20, 20)
            
            # Is this a night driver?
            is_night = random.random() < self.night_driver_ratio
            
            # Generate initial schedule (will be regenerated daily)
            schedule = generate_scenario_schedule(home_x, home_y, self.spots, num_stops=4)
            
            base = base_ev_configs[i - 1]
            self.ev_configs.append({
                "jid": f"ev{i}@localhost",
                "password": "password",
                "config": {
                    "battery_capacity_kwh": base["battery"],
                    "current_soc": base["soc"],
                    "target_soc": 0.80,
                    "max_charge_rate_kw": base["rate"],
                    "velocity": base["velocity"],
                    "energy_per_km": base["energy"],
                    "x": home_x,
                    "y": home_y,
                    "schedule": schedule,
                    "is_night_driver": is_night,
                    "num_schedule_stops": 4,  # Controls how many midpoints per day
                },
            })
