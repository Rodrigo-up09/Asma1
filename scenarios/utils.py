"""
Utility functions for scenario generation.
"""

import random


def generate_scenario_schedule(home_x, home_y, spots, num_stops=None):
    """Generate a recurring daily schedule with fixed time slots and random destinations.
    
    Each EV has 4 fixed appointment times per day. For each time slot,
    a random destination is selected from available spots. The schedule
    repeats every day; hours are within [0, 24).
    
    Args:
        home_x: Home x position
        home_y: Home y position
        spots: List of available spots with name, x, y
        num_stops: Number of stops per day (default 4)
    
    Returns:
        List of schedule destinations for one day.
    """
    if num_stops is None:
        num_stops = 4
    
    # Fixed daily time slots for appointments (spread throughout the day)
    base_times = []
    for i in range(num_stops):
        hour = 8.0 + (i * 3.5)  # 8:00, 11:30, 15:00, 18:30
        base_times.append(hour)
    
    schedule = []
    
    # Generate schedule for ONE day; it will repeat daily via next_target logic
    for time_slot in base_times:
        spot = random.choice(spots)
        schedule.append({
            "name": spot["name"],
            "x": spot["x"],
            "y": spot["y"],
            "hour": time_slot,
            "type": "destination",
        })
    
    # Return home at end of day (20:00)
    schedule.append({
        "name": "Home",
        "x": home_x,
        "y": home_y,
        "hour": 20.0,
        "type": "destination",
    })
    
    return schedule


def generate_hourly_schedule(home_x, home_y, spots):
    """Generate a schedule with 4 fixed daily deadlines and random destinations.
    
    Similar to generate_scenario_schedule but used for specific scenarios.
    Each day has 4 appointment times, each with a random destination pick.
    Repeats for 7 days for continuous movement.
    """
    schedule = []
    
    # Fixed appointment times each day
    daily_times = [8.0, 11.5, 15.0, 18.5]
    
    for day in range(7):
        for time_slot in daily_times:
            spot = random.choice(spots)
            schedule.append({
                "name": spot["name"],
                "x": spot["x"],
                "y": spot["y"],
                "hour": time_slot + (day * 24),
                "type": "destination",
            })
        
        # Return home at 20:00 each day
        schedule.append({
            "name": "Home",
            "x": home_x,
            "y": home_y,
            "hour": 20.0 + (day * 24),
            "type": "destination",
        })
    
    return schedule
