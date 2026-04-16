"""
Utility functions for scenario generation.
"""

import random


def generate_scenario_schedule(home_x, home_y, spots, num_stops=None):
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
        num_stops = random.choice([5, 6])
    
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


def generate_hourly_schedule(home_x, home_y, spots):
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
