"""
CS Availability Scenario:
Multiple EVs with 2 CS - one close but with limited doors, one farther but more available.
Tests if EVs will choose the farther free CS when the closer one is full.
"""

import random
from agents.cs_agent import CSConfig
from .base import Scenario
from .utils import generate_scenario_schedule


class CSAvailability(Scenario):
    """
    Multiple EVs with 2 CS - one close but with limited doors, one farther but more available.
    Tests if EVs will choose the farther free CS when the closer one is full.
    """
    
    def __init__(self):
        super().__init__(
            name="CS Availability",
            description="5 EVs, 2 CS (close+limited vs distant+free). Tests station selection when full.",
        )
        self.num_evs = 5
        self.num_css = 2
        self.night_driver_ratio = 0.0
        
        # Available spots for this scenario
        self.spots = [
            {"name": "Office", "x": -10.0, "y": 15.0},
            {"name": "Store", "x": 15.0, "y": -10.0},
            {"name": "Factory", "x": 22.0, "y": 18.0},
            {"name": "Mall", "x": 16.0, "y": -8.0},
            {"name": "Park", "x": -18.0, "y": 5.0},
        ]
        
        # CS1: Close but limited (only 1 door)
        # CS2: Farther but more available (3 doors)
        self.cs_configs = [
            {
                "jid": "cs1@localhost",
                "password": "password",
                "config": CSConfig(
                    num_doors=1,  # LIMITED - only 1 door, will fill up quickly
                    max_charging_rate=10.0,
                    max_solar_capacity=100.0,
                    actual_solar_capacity=80.0,
                    energy_price=0.15,
                    solar_production_rate=10.0,
                    x=8.0,  # CLOSE to starting area
                    y=0.0,
                ),
            },
            {
                "jid": "cs2@localhost",
                "password": "password",
                "config": CSConfig(
                    num_doors=1, 
                    max_charging_rate=12.0,
                    max_solar_capacity=150.0,
                    actual_solar_capacity=120.0,
                    energy_price=0.15,
                    solar_production_rate=12.0,
                    x=-4.0,  
                    y=0.0,
                ),
            },
        ]
        
        # Generate dynamic schedules for each EV - all starting from same area
        self.ev_configs = []
        base_configs = [
            {"battery": 50.0, "soc": 0.15, "rate": 8.0, "velocity": 1.5, "energy": 3.8},
            {"battery": 55.0, "soc": 0.18, "rate": 9.0, "velocity": 1.6, "energy": 3.6},
            {"battery": 48.0, "soc": 0.20, "rate": 8.5, "velocity": 1.7, "energy": 3.9},
            {"battery": 60.0, "soc": 0.16, "rate": 9.5, "velocity": 1.55, "energy": 3.7},
            {"battery": 52.0, "soc": 0.19, "rate": 8.8, "velocity": 1.65, "energy": 3.85},
        ]
        
        for i in range(1, self.num_evs + 1):
            # Spread EVs out across the map with random home positions
            home_x = random.uniform(-20, 20)
            home_y = random.uniform(-20, 20)
            
            # Generate hourly schedule for maximum chaos
            schedule = generate_scenario_schedule(home_x, home_y, self.spots)
            
            config = base_configs[i - 1]
            self.ev_configs.append({
                "jid": f"ev{i}@localhost",
                "password": "password",
                "config": {
                    "battery_capacity_kwh": config["battery"],
                    "current_soc": config["soc"],  # LOW SoC - needs charge immediately
                    "target_soc": 0.80,
                    "max_charge_rate_kw": config["rate"],
                    "velocity": config["velocity"],
                    "energy_per_km": config["energy"],
                    "x": home_x,
                    "y": home_y,
                    "schedule": schedule,
                    "is_night_driver": False,
                },
            })
