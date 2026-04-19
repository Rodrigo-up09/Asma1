"""
Legacy scenarios module - imports from scenarios package for backward compatibility.
New code should import directly from the scenarios package.

This file is kept for compatibility with existing code that imports from scenarios.py
"""

# Import everything from the scenarios package
from scenarios import (
    Scenario,
    PriceComparison,
    CSAvailability,
    RandomScenario,
    DynamicScheduling,
    SCENARIOS,
    get_scenario_by_index,
    display_menu,
    generate_scenario_schedule,
    generate_hourly_schedule,
)

__all__ = [
    "Scenario",
    "PriceComparison",
    "CSAvailability",
    "RandomScenario",
    "DynamicScheduling",
    "SCENARIOS",
    "get_scenario_by_index",
    "display_menu",
    "generate_scenario_schedule",
    "generate_hourly_schedule",
]


__all__ = [
    "Scenario",
    "PriceComparison",
    "CSAvailability",
    "RandomScenario",
    "SCENARIOS",
    "get_scenario_by_index",
    "display_menu",
    "generate_scenario_schedule",
    "generate_hourly_schedule",
]
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
                    num_doors=1,  # AVAILABLE - 3 doors, always has space
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
            schedule = _generate_hourly_schedule(home_x, home_y, self.spots)
            
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


# Registry of all available scenarios
SCENARIOS = [
    PriceComparison(),
    CSAvailability(),
]


def get_scenario_by_index(index: int):
    """Get a scenario by index. Returns None if index is out of range."""
    if 0 <= index < len(SCENARIOS):
        return SCENARIOS[index]
    return None


def display_menu():
    """Display scenario selection menu and return user choice."""
    print("\n" + "=" * 70)
    print("ASMA Simulation - Scenario Selection")
    print("=" * 70)
    print("\nAvailable Scenarios:\n")
    
    for i, scenario in enumerate(SCENARIOS):
        print(f"  [{i + 1}] {scenario.name}")
        print(f"      {scenario.description}")
        print()
    
    print(f"  [0] Default Simulation (20 EVs, 3 CS, mixed drivers)")
    print()
    
    while True:
        try:
            choice = input("Select scenario (0-" + str(len(SCENARIOS)) + "): ").strip()
            choice_int = int(choice)
            
            if choice_int == 0:
                return None  # Default scenario
            elif 1 <= choice_int <= len(SCENARIOS):
                return SCENARIOS[choice_int - 1]
            else:
                print(f"Invalid choice. Please enter a number between 0 and {len(SCENARIOS)}.")
        except ValueError:
            print("Invalid input. Please enter a number.")
