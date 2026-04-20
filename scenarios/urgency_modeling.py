"""
Urgency Modeling Scenario:
Demonstrates urgency-based scheduling with dynamic charging decisions.

Features:
- Mix of LOW, MEDIUM, HIGH, and EMERGENCY priority destinations
- Urgency-influenced charging thresholds and strategies
- Routing prioritization based on deadline proximity
- Time pressure response mechanisms
"""

import random
from agents.cs_agent import CSConfig
from agents.ev_agent.urgency_model import UrgencyLevel
from .base import Scenario


def generate_urgency_schedule(home_x, home_y, spots, num_stops=5):
    """Generate a schedule with varied urgency levels.
    
    Each destination has different urgency levels throughout the day,
    creating mixed priority scenarios for decision making.
    """
    schedule = []
    
    # Daily schedule with varied urgencies
    time_slots = [
        (8.0, UrgencyLevel.MEDIUM, "Morning routine"),
        (10.5, UrgencyLevel.LOW, "Optional meeting"),
        (13.0, UrgencyLevel.HIGH, "Important presentation"),
        (15.5, UrgencyLevel.EMERGENCY, "Critical delivery"),
        (18.0, UrgencyLevel.MEDIUM, "Evening errand"),
    ]
    
    for i, (time_slot, urgency_level, description) in enumerate(time_slots[:num_stops]):
        if i < len(spots):
            spot = spots[i % len(spots)]
        else:
            spot = random.choice(spots)
        
        # Urgency determines window width and deadline tightness
        window_width = {
            UrgencyLevel.LOW: 2.0,        # 2 hour window, relaxed
            UrgencyLevel.MEDIUM: 1.0,    # 1 hour window, normal
            UrgencyLevel.HIGH: 0.75,     # 45 min window, tight
            UrgencyLevel.EMERGENCY: 0.5,  # 30 min window, very tight
        }.get(urgency_level, 1.0)
        
        schedule.append({
            "name": spot["name"],
            "x": spot["x"],
            "y": spot["y"],
            "hour": time_slot,
            "time_window": {
                "scheduled_hour": time_slot,
                "window_min": time_slot - window_width,
                "window_max": time_slot + window_width,
                "deadline_hard": time_slot + (window_width * 2),
                "priority": urgency_level.name,
            },
            "urgency": urgency_level.name,
            "description": description,
            "type": "destination",
        })
    
    # Return home with flexible timing
    schedule.append({
        "name": "Home",
        "x": home_x,
        "y": home_y,
        "hour": 20.0,
        "time_window": {
            "scheduled_hour": 20.0,
            "window_min": 18.0,
            "window_max": 22.0,
            "deadline_hard": 23.0,
            "priority": UrgencyLevel.LOW.name,
        },
        "urgency": UrgencyLevel.LOW.name,
        "description": "Return home",
        "type": "destination",
    })
    
    return schedule


class UrgencyModelingScenario(Scenario):
    """Scenario demonstrating urgency-based scheduling and charging decisions."""
    
    def __init__(self):
        """Initialize urgency modeling scenario with 5 EVs and 4 CSs."""
        super().__init__(
            name="Urgency Modeling",
            description="EV schedules with varied urgency levels and dynamic charging",
        )
        
        self.num_evs = 5
        self.num_css = 4
        self.night_driver_ratio = 0.0  # All day drivers
        
        # Available spots for scheduling
        self.spots = [
            {"name": "Office Complex", "x": 15.0, "y": 15.0},
            {"name": "Shopping Center", "x": -12.0, "y": 18.0},
            {"name": "Industrial Hub", "x": 18.0, "y": -20.0},
            {"name": "Downtown Station", "x": 5.0, "y": 10.0},
            {"name": "Medical Center", "x": -8.0, "y": 5.0},
            {"name": "Airport", "x": 25.0, "y": 0.0},
        ]
        
        # ══════════════════════════════════════════════════════════════════════
        #  Charging Stations
        # ══════════════════════════════════════════════════════════════════════
        self.cs_configs = [
            {
                "jid": "cs1@localhost",
                "password": "password",
                "config": CSConfig(
                    num_doors=2,
                    max_charging_rate=11.0,
                    max_solar_capacity=100.0,
                    actual_solar_capacity=60.0,
                    energy_price=0.18,
                    solar_production_rate=10.0,
                    x=8.0,
                    y=8.0,
                ),
            },
            {
                "jid": "cs2@localhost",
                "password": "password",
                "config": CSConfig(
                    num_doors=3,
                    max_charging_rate=22.0,
                    max_solar_capacity=150.0,
                    actual_solar_capacity=80.0,
                    energy_price=0.15,
                    solar_production_rate=12.0,
                    x=-10.0,
                    y=-10.0,
                ),
            },
            {
                "jid": "cs3@localhost",
                "password": "password",
                "config": CSConfig(
                    num_doors=2,
                    max_charging_rate=7.0,
                    max_solar_capacity=80.0,
                    actual_solar_capacity=50.0,
                    energy_price=0.20,
                    solar_production_rate=8.0,
                    x=15.0,
                    y=-15.0,
                ),
            },
            {
                "jid": "cs4@localhost",
                "password": "password",
                "config": CSConfig(
                    num_doors=2,
                    max_charging_rate=11.0,
                    max_solar_capacity=100.0,
                    actual_solar_capacity=70.0,
                    energy_price=0.16,
                    solar_production_rate=11.0,
                    x=-15.0,
                    y=15.0,
                ),
            },
        ]
        
        # ══════════════════════════════════════════════════════════════════════
        #  Electric Vehicles
        # ══════════════════════════════════════════════════════════════════════
        self.ev_configs = []
        
        base_ev_configs = [
            {"battery": 60.0, "soc": 0.60, "rate": 11.0, "velocity": 2.2, "energy": 2.5},
            {"battery": 65.0, "soc": 0.50, "rate": 22.0, "velocity": 1.8, "energy": 2.3},
            {"battery": 55.0, "soc": 0.55, "rate": 7.0, "velocity": 2.0, "energy": 2.8},
            {"battery": 70.0, "soc": 0.65, "rate": 11.0, "velocity": 2.1, "energy": 2.4},
            {"battery": 62.0, "soc": 0.45, "rate": 11.0, "velocity": 1.9, "energy": 2.6},
        ]
        
        for i in range(1, self.num_evs + 1):
            # Randomize home positions
            home_x = random.uniform(-18, 18)
            home_y = random.uniform(-18, 18)
            
            # Generate schedule with urgency levels
            schedule = generate_urgency_schedule(
                home_x, home_y, self.spots, num_stops=5
            )
            
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
                    "enable_time_constraints": True,
                    "time_constraint_window_width": 1.0,
                    "default_priority": "MEDIUM",
                },
            })
