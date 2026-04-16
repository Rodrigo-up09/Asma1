"""
Price Comparison Scenario:
Single EV choosing between multiple CS stations with different prices.
The EV should prefer the lowest-price station.
"""

import random
from agents.cs_agent import CSConfig
from .base import Scenario
from .utils import generate_scenario_schedule


class PriceComparison(Scenario):
    """
    Single EV choosing between multiple CS stations with different prices.
    The EV should prefer the lowest-price station.
    """
    
    def __init__(self):
        super().__init__(
            name="Price Comparison",
            description="1 EV, 3 CS with different prices. EV chooses lowest price.",
        )
        self.num_evs = 1
        self.num_css = 3
        self.night_driver_ratio = 0.0
        
        # Available spots for this scenario
        self.spots = [
            {"name": "Work", "x": 18.0, "y": 12.0},
            {"name": "Office", "x": -10.0, "y": 15.0},
            {"name": "Store", "x": -15.0, "y": 10.0},
            {"name": "Gym", "x": 12.0, "y": -8.0},
            {"name": "Park", "x": -10.0, "y": 5.0},
        ]
        
        # Three CS with different prices
        self.cs_configs = [
            {
                "jid": "cs1@localhost",
                "password": "password",
                "config": CSConfig(
                    num_doors=2,
                    max_charging_rate=20.0,
                    max_solar_capacity=100.0,
                    actual_solar_capacity=50.0,
                    energy_price=0.25,  # HIGH price
                    solar_production_rate=10.0,
                    x=10.0,
                    y=0.0,
                ),
            },
            {
                "jid": "cs2@localhost",
                "password": "password",
                "config": CSConfig(
                    num_doors=2,
                    max_charging_rate=20.0,
                    max_solar_capacity=100.0,
                    actual_solar_capacity=50.0,
                    energy_price=0.12,  # LOW price - should be chosen
                    solar_production_rate=10.0,
                    x=5.0,
                    y=-15.0,
                ),
            },
            {
                "jid": "cs3@localhost",
                "password": "password",
                "config": CSConfig(
                    num_doors=2,
                    max_charging_rate=20.0,
                    max_solar_capacity=100.0,
                    actual_solar_capacity=50.0,
                    energy_price=0.18,  # MEDIUM price
                    solar_production_rate=10.0,
                    x=12.0,
                    y=7.0,
                ),
            },
        ]
        
        # Generate dynamic schedules for each EV
        self.ev_configs = []
        for i in range(1, self.num_evs + 1):
            home_x, home_y = random.uniform(-5, 5), random.uniform(-5, 5)
            schedule = generate_scenario_schedule(home_x, home_y, self.spots, num_stops=3)
            
            self.ev_configs.append({
                "jid": f"ev{i}@localhost",
                "password": "password",
                "config": {
                    "battery_capacity_kwh": 60.0,
                    "current_soc": 0.25,  # Low SoC to force charging
                    "target_soc": 0.80,
                    "max_charge_rate_kw": 15.0,
                    "velocity": 3.0,
                    "energy_per_km": 2.0,
                    "x": home_x,
                    "y": home_y,
                    "schedule": schedule,
                    "is_night_driver": False,
                },
            })
