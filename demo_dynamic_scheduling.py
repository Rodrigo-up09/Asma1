#!/usr/bin/env python3
"""
Demo script: Dynamic Schedule Regeneration Test

Run this to see how the ScheduleManager generates different schedules
for each simulation day.

Usage:
    python3 demo_dynamic_scheduling.py

Shows:
- Day 0: Initial random destinations
- Day 1: Different destinations (regenerated)
- Day 2: Different again
- Day 3: Different again
"""

from agents.ev_agent.schedule_manager import ScheduleManager

# Available locations across the virtual city
SPOT_LIST = [
    {"name": "Downtown Plaza", "x": 15.0, "y": 15.0},
    {"name": "University Campus", "x": -12.0, "y": 18.0},
    {"name": "Industrial Zone", "x": 18.0, "y": -20.0},
    {"name": "Harbor Terminal", "x": -20.0, "y": -15.0},
    {"name": "Shopping Center", "x": 5.0, "y": 10.0},
    {"name": "City Hospital", "x": -8.0, "y": 5.0},
    {"name": "International Airport", "x": 22.0, "y": 22.0},
    {"name": "Business Park", "x": 10.0, "y": -10.0},
    {"name": "Sports Complex", "x": -15.0, "y": -5.0},
    {"name": "Tech Innovation Hub", "x": 8.0, "y": 12.0},
]

# EV home location
HOME_X, HOME_Y = 5.0, 5.0


def print_schedule(schedule, day_num):
    """Pretty print a schedule."""
    print(f"\n{'='*70}")
    print(f"  DAY {day_num} REGENERATED SCHEDULE")
    print(f"{'='*70}")
    
    for i, stop in enumerate(schedule, 1):
        hour = stop["hour"]
        hour_of_day = int(hour) % 24
        min_of_hour = int((hour % 1) * 60)
        time_str = f"{hour_of_day:02d}:{min_of_hour:02d}"
        
        distance_from_home = (
            f"({stop['x']:6.1f}, {stop['y']:6.1f})"
            if stop["name"] != "Home"
            else f"({HOME_X:6.1f}, {HOME_Y:6.1f})"
        )
        
        print(f"  {i}. {time_str}  →  {stop['name']:25s}  {distance_from_home}")
    
    # Calculate total distance (rough)
    total_distance = 0.0
    for i in range(len(schedule) - 1):
        curr = schedule[i]
        nxt = schedule[i + 1]
        dx = nxt["x"] - curr["x"]
        dy = nxt["y"] - curr["y"]
        total_distance += (dx**2 + dy**2)**0.5
    
    # Add return to home
    if schedule and schedule[-1]["name"] != "Home":
        last = schedule[-1]
        dx = HOME_X - last["x"]
        dy = HOME_Y - last["y"]
        total_distance += (dx**2 + dy**2)**0.5
    
    print(f"\n  Total travel distance: ~{total_distance:.1f} units")


def main():
    print("\n" + "=" * 70)
    print("  Dynamic Schedule Regeneration Demo")
    print("=" * 70)
    print(f"\nHome Location: ({HOME_X}, {HOME_Y})")
    print(f"Available Destinations: {len(SPOT_LIST)} spots")
    print(f"Stops per Day: 4 appointments + 1 return home")
    print(f"Fixed Times: 08:00, 11:30, 15:00, 18:30, 20:00 (home)")
    
    # Create the schedule manager
    manager = ScheduleManager(
        home_x=HOME_X,
        home_y=HOME_Y,
        available_spots=SPOT_LIST,
        num_stops=4,
    )
    
    # Generate and show 4 days
    print("\nGenerating 4 days of schedules...\n")
    
    for day in range(4):
        schedule = manager.get_schedule_for_day(day)
        print_schedule(schedule, day)
    
    # Show that asking for the same day returns same schedule (cached)
    print(f"\n{'='*70}")
    print(f"  CACHE TEST: Asking for Day 1 again")
    print(f"{'='*70}")
    schedule_again = manager.get_schedule_for_day(1)
    
    print("\nSchedules are identical (cached):")
    for i, (s1, s2) in enumerate(zip(schedule, schedule_again)):
        match = "✓" if s1 == s2 else "✗"
        print(f"  {match} Stop {i+1}: {s1['name']} == {s2['name']}")
    
    print("\n" + "=" * 70)
    print("  DEMO COMPLETE")
    print("=" * 70)
    print("\nKey observations:")
    print("  1. Fixed times each day: 08:00, 11:30, 15:00, 18:30, 20:00")
    print("  2. Different destinations each day (random selection)")
    print("  3. Same day returns cached schedule (efficient)")
    print("  4. This simulates real-world variability!")
    print()


if __name__ == "__main__":
    main()
