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
            description="1 EV, frequent trips + 3 CS with different prices. EV should often pick the lowest-price station.",
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
            home_x, home_y = random.uniform(-12, 12), random.uniform(-12, 12)

            # More frequent appointments across the day to force repeated travel/charging.
            schedule = generate_scenario_schedule(home_x, home_y, self.spots, num_stops=6)
            frequent_time_slots = [8.0, 10.0, 12.0, 14.0, 16.0, 18.0]
            for idx, stop in enumerate(schedule[:-1]):  # keep final home stop at 20:00
                if idx < len(frequent_time_slots):
                    stop["hour"] = frequent_time_slots[idx]
            
            self.ev_configs.append({
                "jid": f"ev{i}@localhost",
                "password": "password",
                "config": {
                    "battery_capacity_kwh": 45.0,
                    "current_soc": 0.18,  # Low SoC + frequent travel forces repeated charging
                    "target_soc": 0.80,
                    "max_charge_rate_kw": 12.0,
                    "velocity": 2.6,
                    "energy_per_km": 3.4,
                    "x": home_x,
                    "y": home_y,
                    "schedule": schedule,
                    "is_night_driver": False,
                },
            })
