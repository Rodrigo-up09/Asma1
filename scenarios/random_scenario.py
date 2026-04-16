"""
Random Scenario:
Randomly generated scenario using the exact logic from main.py
Tests the system with unpredictable configurations.
"""

import random
from agents.cs_agent import CSConfig
from .base import Scenario


# ══════════════════════════════════════════════════════════════════════
#  Configuration (same as main.py)
# ══════════════════════════════════════════════════════════════════════

MAP_MIN, MAP_MAX = -30.0, 30.0

# --- CS ranges ---
CS_NUM_DOORS_RANGE = (1, 4)                  # int
CS_MAX_CHARGING_RATE_RANGE = (7.0, 50.0)     # kW per door
CS_MAX_SOLAR_CAPACITY_RANGE = (50.0, 200.0)  # kWh storage
CS_SOLAR_FILL_RANGE = (0.3, 0.8)             # fraction filled at start
CS_ENERGY_PRICE_RANGE = (0.10, 0.30)         # €/kWh
CS_SOLAR_PRODUCTION_RANGE = (5.0, 25.0)      # kW

# --- EV ranges ---
EV_BATTERY_CAPACITY_RANGE = (30.0, 80.0)     # kWh
EV_INITIAL_SOC_RANGE = (0.40, 1.0)           # fraction
EV_LOW_SOC_THRESHOLD = 0.20                  # fixed
EV_TARGET_SOC = 0.80                         # fixed
EV_MAX_CHARGE_RATE_RANGE = (7.0, 22.0)       # kW
EV_VELOCITY_RANGE = (2.0, 5.0)              # units per tick
EV_ENERGY_PER_KM_RANGE = (1, 4)             # kWh/km  (int)

DAY_BUILDINGS = [
    {"name": "Office A",      "x":  15.0, "y":  20.0},
    {"name": "Office B",      "x": -15.0, "y":  15.0},
    {"name": "School",        "x":   5.0, "y":  18.0},
    {"name": "Gym",           "x":   8.0, "y":  -3.0},
    {"name": "Mall",          "x":  -5.0, "y":   0.0},
    {"name": "Supermarket",   "x":  12.0, "y":  -8.0},
    {"name": "Library",       "x":  -8.0, "y":  10.0},
    {"name": "Park",          "x":   0.0, "y":  12.0},
    {"name": "Hospital",      "x": -20.0, "y":   5.0},
    {"name": "Café",          "x":   3.0, "y":   5.0},
]

NIGHT_BUILDINGS = [
    {"name": "Night Shift",   "x":  15.0, "y":  20.0},
    {"name": "Warehouse",     "x": -18.0, "y": -12.0},
    {"name": "Bar",           "x":   3.0, "y":   2.0},
    {"name": "Airport",       "x":  22.0, "y":  22.0},
    {"name": "Hospital",      "x": -20.0, "y":   5.0},
    {"name": "Factory",       "x": -10.0, "y": -20.0},
    {"name": "Gas Station",   "x":  10.0, "y":  -5.0},
    {"name": "Club",          "x":   0.0, "y":   8.0},
]


# ══════════════════════════════════════════════════════════════════════
#  Helper Functions (same as main.py)
# ══════════════════════════════════════════════════════════════════════

def _rand(lo, hi):
    """Uniform float rounded to 2 dp."""
    return round(random.uniform(lo, hi), 2)


def _rand_pos():
    """Random (x, y) position inside the map area."""
    return _rand(MAP_MIN, MAP_MAX), _rand(MAP_MIN, MAP_MAX)


def _generate_schedule(home_x, home_y, num_destinations=3, night=False):
    """Build a schedule with random selection from established world points.
    
    Each EV gets num_destinations random points from the fixed world locations
    plus returns home at the end.
    
    Args:
        home_x: Home x position
        home_y: Home y position
        num_destinations: Number of destinations to visit (default 3)
        night: If True, use night buildings; otherwise day buildings
    """
    buildings = NIGHT_BUILDINGS if night else DAY_BUILDINGS
    
    # Select random destinations from established world points
    num_to_pick = min(num_destinations, len(buildings))
    chosen = random.sample(buildings, num_to_pick)
    
    # Calculate time windows
    if night:
        start_hour = random.uniform(20.0, 21.5)
        end_hour = random.uniform(5.0, 7.0)
        total_span = (24.0 - start_hour) + end_hour
    else:
        start_hour = random.uniform(7.5, 9.0)
        end_hour = 20.0
        total_span = end_hour - start_hour

    # Distribute stops evenly across the time window
    num_stops = num_to_pick + 1  # destinations + home
    gap = total_span / num_stops
    
    stops = []
    for i, bld in enumerate(chosen):
        hour = start_hour + gap * i
        if hour >= 24.0:
            hour -= 24.0
        stops.append(
            {
                "name": bld["name"],
                "x": bld["x"],
                "y": bld["y"],
                "hour": round(hour, 1),
                "type": "destination",
            }
        )
    
    # Final stop → Home
    stops.append(
        {
            "name": "Home",
            "x": home_x,
            "y": home_y,
            "hour": round(end_hour, 1),
            "type": "destination",
        }
    )
    
    # Sort by hour so the agent's next_target() logic works correctly
    stops.sort(key=lambda s: s["hour"])
    return stops


# ══════════════════════════════════════════════════════════════════════
#  Random Scenario Class
# ══════════════════════════════════════════════════════════════════════

class RandomScenario(Scenario):
    """
    Randomly generated scenario with variable parameters.
    Uses the same random generation logic as main.py with configurable NUM_EVS and NUM_CSS.
    Creates diverse configurations for stress testing.
    """
    
    def __init__(self, num_evs=20, num_css=3, night_driver_ratio=0.4):
        super().__init__(
            name="Random Scenario",
            description=f"Random simulation: {num_evs} EVs, {num_css} CS, {night_driver_ratio:.0%} night drivers.",
        )
        
        self.num_evs = num_evs
        self.num_css = num_css
        self.night_driver_ratio = night_driver_ratio
        self.spots = DAY_BUILDINGS + NIGHT_BUILDINGS
        
        # Generate random CS configurations (same as main.py generate_cs_deployment)
        self.cs_configs = []
        for i in range(1, self.num_css + 1):
            x, y = _rand_pos()
            max_solar = _rand(*CS_MAX_SOLAR_CAPACITY_RANGE)
            
            self.cs_configs.append({
                "jid": f"cs{i}@localhost",
                "password": "password",
                "config": CSConfig(
                    num_doors=random.randint(*CS_NUM_DOORS_RANGE),
                    max_charging_rate=_rand(*CS_MAX_CHARGING_RATE_RANGE),
                    max_solar_capacity=max_solar,
                    actual_solar_capacity=round(
                        max_solar * _rand(*CS_SOLAR_FILL_RANGE), 2
                    ),
                    energy_price=_rand(*CS_ENERGY_PRICE_RANGE),
                    solar_production_rate=_rand(*CS_SOLAR_PRODUCTION_RANGE),
                    x=x,
                    y=y,
                ),
            })
        
        # Generate random EV configurations (same as main.py generate_ev_deployment)
        self.ev_configs = []
        num_night = max(0, round(self.num_evs * self.night_driver_ratio))
        night_indices = set(random.sample(range(self.num_evs), num_night)) if num_night > 0 else set()
        
        for i in range(1, self.num_evs + 1):
            is_night = (i - 1) in night_indices
            home_x, home_y = _rand_pos()
            num_destinations = 3  # Each EV visits 3 established world points
            
            if is_night:
                departure = f"{random.randint(19, 21):02d}:00"  # leave in the evening
            else:
                departure = f"{random.randint(7, 9):02d}:00"
            
            self.ev_configs.append({
                "jid": f"ev{i}@localhost",
                "password": "password",
                "config": {
                    "battery_capacity_kwh": _rand(*EV_BATTERY_CAPACITY_RANGE),
                    "current_soc": _rand(*EV_INITIAL_SOC_RANGE),
                    "target_soc": EV_TARGET_SOC,
                    "max_charge_rate_kw": _rand(*EV_MAX_CHARGE_RATE_RANGE),
                    "velocity": _rand(*EV_VELOCITY_RANGE),
                    "energy_per_km": random.randint(*EV_ENERGY_PER_KM_RANGE),
                    "x": home_x,
                    "y": home_y,
                    "schedule": _generate_schedule(home_x, home_y, num_destinations, night=is_night),
                    "is_night_driver": is_night,
                },
            })
