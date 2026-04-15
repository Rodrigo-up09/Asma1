"""
Scenario configurations for different simulation test cases.
Each scenario defines a specific setup to test particular behaviors.
"""

import random
from agents.cs_agent import CSConfig


def _generate_scenario_schedule(home_x, home_y, spots, num_stops=None):
    """Generate a dynamic schedule from available spots.
    
    Args:
        home_x: Home x position
        home_y: Home y position
        spots: List of available spots with name, x, y
        num_stops: Number of stops (3 or 4). If None, randomly choose.
    
    Returns:
        List of schedule destinations
    """
    if num_stops is None:
        num_stops = random.choice([5,6])
    
    # Pick random spots
    num_to_pick = min(num_stops - 1, len(spots))  # -1 for home return
    chosen_spots = random.sample(spots, num_to_pick)
    
    # Generate time windows
    start_hour = random.uniform(7.5, 9.0)
    end_hour = 20.0
    total_span = end_hour - start_hour
    gap = total_span / num_to_pick
    
    schedule = []
    for i, spot in enumerate(chosen_spots):
        hour = start_hour + gap * i
        schedule.append({
            "name": spot["name"],
            "x": spot["x"],
            "y": spot["y"],
            "hour": round(hour, 1),
            "type": "destination",
        })
    
    # Return home
    schedule.append({
        "name": "Home",
        "x": home_x,
        "y": home_y,
        "hour": round(end_hour, 1),
        "type": "destination",
    })
    
    # Sort by hour
    schedule.sort(key=lambda s: s["hour"])
    return schedule


def _generate_hourly_schedule(home_x, home_y, spots):
    """Generate an hourly chaotic schedule - one destination per hour.
    
    Cycles through available spots hour by hour, creating maximum movement.
    """
    schedule = []
    for hour in range(7, 21):  # 7am to 8pm (13 hours)
        # Pick a random spot for this hour
        spot = random.choice(spots)
        schedule.append({
            "name": spot["name"],
            "x": spot["x"],
            "y": spot["y"],
            "hour": float(hour),
            "type": "destination",
        })
    
    # Return home at 20:30
    schedule.append({
        "name": "Home",
        "x": home_x,
        "y": home_y,
        "hour": 20.5,
        "type": "destination",
    })
    
    return schedule


class Scenario:
    """Base scenario configuration."""
    
    def __init__(self, name, description):
        self.name = name
        self.description = description
        self.num_evs = 1
        self.num_css = 1
        self.night_driver_ratio = 0.0
        self.cs_configs = []
        self.ev_configs = []
        self.spots = []  # Available spots for this scenario
    
    def __repr__(self):
        return f"{self.name}: {self.description}"


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
            schedule = _generate_scenario_schedule(home_x, home_y, self.spots, num_stops=3)
            
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
