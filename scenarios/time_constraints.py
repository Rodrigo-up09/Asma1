"""
Time Constraints Scenario:
Demonstrates time-constrained scheduling with deadlines and penalties.

Features:
- Each destination has soft deadlines (preferred arrival windows)
- Hard deadlines (penalty if missed)
- Emergency destinations with stricter constraints
- Energy vs time trade-off decisions
"""

import random
from agents.cs_agent import CSConfig
from agents.ev_agent.time_constraints import Priority
from .base import Scenario


def generate_time_constrained_schedule(home_x, home_y, spots, num_stops=4):
    """Generate a schedule with time windows and deadline constraints.
    
    Each destination has:
    - scheduled_hour: target arrival time
    - window_min/window_max: soft deadline window
    - deadline_hard: hard deadline with penalties
    - priority: urgency level
    """
    schedule = []
    
    # Fixed daily time slots
    base_times = [8.0, 11.5, 15.0, 18.5]
    
    for i, time_slot in enumerate(base_times[:num_stops]):
        if i < len(spots):
            spot = spots[i % len(spots)]
        else:
            spot = random.choice(spots)
        
        # Determine priority based on position in day
        if i == 0:
            priority = Priority.HIGH  # Morning appointment
        elif i == 3:
            priority = Priority.EMERGENCY  # Evening deadline
        else:
            priority = Priority.MEDIUM
        
        # Create time window
        window_width = 0.5 if priority == Priority.EMERGENCY else 1.0
        
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
                "priority": priority.name,
            },
            "type": "destination",
        })
    
    # Return home (flexible window)
    schedule.append({
        "name": "Home",
        "x": home_x,
        "y": home_y,
        "hour": 20.0,
        "time_window": {
            "scheduled_hour": 20.0,
            "window_min": 19.0,
            "window_max": 21.0,
            "deadline_hard": 22.0,
            "priority": Priority.LOW.name,
        },
        "type": "destination",
    })
    
    return schedule


class TimeConstraintScenario(Scenario):
    """Scenario demonstrating time constraints and deadline management."""
    
    def __init__(self):
        """Initialize time constraint scenario with 4 EVs and 3 CSs."""
        super().__init__(
            name="Time Constraints",
            description="EV schedules with time windows and deadline penalties",
        )
        
        self.num_evs = 4
        self.num_css = 3
        self.night_driver_ratio = 0.0  # All day drivers for simplicity
        
        # Available spots for scheduling
        self.spots = [
            {"name": "Office Complex", "x": 15.0, "y": 15.0},
            {"name": "Shopping Center", "x": -12.0, "y": 18.0},
            {"name": "Industrial Hub", "x": 18.0, "y": -20.0},
            {"name": "Downtown Station", "x": 5.0, "y": 10.0},
            {"name": "Medical Center", "x": -8.0, "y": 5.0},
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
        ]
        
        for i in range(1, self.num_evs + 1):
            # Randomize home positions
            home_x = random.uniform(-18, 18)
            home_y = random.uniform(-18, 18)
            
            # Generate schedule with time constraints
            schedule = generate_time_constrained_schedule(
                home_x, home_y, self.spots, num_stops=4
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
