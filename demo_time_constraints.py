#!/usr/bin/env python3
"""
Time Constraints System Validation

Demonstrates:
- Time window enforcement
- Deadline penalties
- Energy vs time trade-off decisions
- Speed recommendations for deadline compliance
"""

import math
from agents.ev_agent.time_constraints import (
    TimeConstraintManager,
    Priority,
    TimeWindow,
    ArrivalStatus,
)


def print_section(title):
    """Print a formatted section header."""
    print(f"\n{'═' * 70}")
    print(f"  {title}")
    print(f"{'═' * 70}\n")


def demo_time_window():
    """Demonstrate TimeWindow arrival status and penalties."""
    print_section("1. TIME WINDOW: Arrival Status & Penalties")
    
    # Create a time window: scheduled at 15:00, ±1 hour soft window, hard deadline at 17:00
    window = TimeWindow(
        scheduled_hour=15.0,
        window_min=14.0,
        window_max=16.0,
        deadline_hard=17.0,
        priority=Priority.HIGH,
    )
    
    test_times = [13.5, 14.5, 15.0, 15.5, 16.5, 17.5, 18.0]
    
    print(f"Window Definition:")
    print(f"  Scheduled:    15:00")
    print(f"  Soft window:  14:00 - 16:00")
    print(f"  Hard deadline: 17:00")
    print(f"  Priority:     HIGH (2.0x multiplier)")
    print()
    
    for arrival_time in test_times:
        status = window.get_arrival_status(arrival_time)
        penalty_score, penalty_reason = window.calculate_time_penalty(arrival_time)
        
        print(f"Arrival at {arrival_time:5.1f}:  Status={status.value:12} | "
              f"Penalty={penalty_score:5.1f} | {penalty_reason}")


def demo_schedule_enhancement():
    """Demonstrate schedule enhancement with time windows."""
    print_section("2. SCHEDULE ENHANCEMENT: Adding Time Windows")
    
    manager = TimeConstraintManager(home_x=0.0, home_y=0.0)
    
    # Create a basic schedule
    basic_schedule = [
        {"name": "Office", "x": 10.0, "y": 10.0, "hour": 8.0},
        {"name": "Meeting", "x": 15.0, "y": 5.0, "hour": 11.5},
        {"name": "Lunch", "x": 0.0, "y": 0.0, "hour": 13.0},
    ]
    
    print("Original Schedule (without time windows):")
    for entry in basic_schedule:
        print(f"  - {entry['name']:15} at {entry['hour']:5.1f}")
    
    # Enhance with time constraints
    enhanced = TimeConstraintManager.enhance_schedule_with_constraints(
        basic_schedule,
        default_window_width=1.0,
        default_priority=Priority.MEDIUM,
    )
    
    print("\nEnhanced Schedule (with time windows):")
    for entry in enhanced:
        tw = entry["time_window"]
        print(
            f"  - {entry['name']:15} at {tw['scheduled_hour']:5.1f} "
            f"({tw['window_min']:5.1f} - {tw['window_max']:5.1f}) "
            f"[Priority: {tw['priority']}]"
        )


def demo_deadline_feasibility():
    """Demonstrate deadline feasibility checking."""
    print_section("3. DEADLINE FEASIBILITY: Can we make the deadline?")
    
    manager = TimeConstraintManager(home_x=0.0, home_y=0.0)
    
    # Create destination with tight deadline
    destination = {
        "name": "Emergency Meeting",
        "x": 20.0,
        "y": 20.0,
        "hour": 10.0,
        "time_window": {
            "scheduled_hour": 10.0,
            "window_min": 9.5,
            "window_max": 10.5,
            "deadline_hard": 11.0,
            "priority": Priority.EMERGENCY.name,
        },
    }
    
    test_scenarios = [
        {"current_time": 9.0, "distance": 28.3, "velocity": 2.0},
        {"current_time": 9.3, "distance": 28.3, "velocity": 2.0},
        {"current_time": 9.0, "distance": 28.3, "velocity": 1.0},
        {"current_time": 9.5, "distance": 28.3, "velocity": 2.0},
    ]
    
    print(f"Destination: {destination['name']} at ({destination['x']}, {destination['y']})")
    print(f"Hard Deadline: {destination['time_window']['deadline_hard']}:00")
    print()
    
    for scenario in test_scenarios:
        can_make, arrival_time, reason = manager.will_make_deadline(
            current_time=scenario["current_time"],
            distance_to_destination=scenario["distance"],
            velocity=scenario["velocity"],
            destination=destination,
        )
        
        feasibility = "✓ FEASIBLE" if can_make else "✗ INFEASIBLE"
        print(
            f"At {scenario['current_time']:4.1f}h, {scenario['distance']:5.1f}km away, "
            f"v={scenario['velocity']}:  {feasibility:12}  "
            f"(arrive at {arrival_time:5.1f}) - {reason}"
        )


def demo_energy_time_tradeoff():
    """Demonstrate energy vs time trade-off analysis."""
    print_section("4. ENERGY-TIME TRADE-OFF: Speed Decision Analysis")
    
    manager = TimeConstraintManager(home_x=0.0, home_y=0.0)
    
    destination = {
        "name": "Urgent Appointment",
        "x": 25.0,
        "y": 0.0,
        "hour": 11.0,
        "time_window": {
            "scheduled_hour": 11.0,
            "window_min": 10.0,
            "window_max": 12.0,
            "deadline_hard": 13.0,
            "priority": Priority.HIGH.name,
        },
    }
    
    analysis = manager.calculate_energy_time_tradeoff(
        current_time=10.0,
        current_soc=0.70,
        distance_to_destination=25.0,
        battery_capacity=60.0,
        energy_per_km=2.5,
        base_velocity=2.0,
        destination=destination,
    )
    
    print(f"Decision Point: 10:00")
    print(f"Current SoC: 70% | Battery: 60 kWh | Distance: 25 km")
    print(f"Destination deadline: 13:00")
    print()
    print("Speed Scenarios:")
    print()
    
    for scenario_name in ["normal", "slow_efficient", "fast_deadline_safe"]:
        scenario = analysis[scenario_name]
        print(
            f"  {scenario_name.upper():20} (x{scenario['velocity_multiplier']})"
        )
        print(f"    Travel time: {scenario['travel_time_hours']:5.2f}h")
        print(f"    Arrival time: {scenario['arrival_time']:5.1f}:00")
        print(f"    Energy needed: {scenario['energy_needed_kwh']:5.1f} kWh")
        print(f"    SoC needed: {scenario['soc_needed']:6.1%}")
        print(f"    Feasible: {'✓ YES' if scenario['feasible'] else '✗ NO'}")
        print(
            f"    Time penalty: {scenario['time_penalty']:5.1f} "
            f"({scenario.get('penalty_reason', 'On time')})"
        )
        print()
    
    # Get recommendation
    recommended_multiplier, reason = manager.recommend_speed(analysis, prefer_on_time=True)
    print(f"RECOMMENDATION: Speed multiplier = {recommended_multiplier}")
    print(f"Reason: {reason}")


def demo_cache_performance():
    """Demonstrate time window caching."""
    print_section("5. CACHE PERFORMANCE: Time Window Caching")
    
    manager = TimeConstraintManager(home_x=0.0, home_y=0.0)
    
    destination = {
        "name": "Cached Destination",
        "x": 10.0,
        "y": 10.0,
        "hour": 14.0,
        "time_window": {
            "scheduled_hour": 14.0,
            "window_min": 13.5,
            "window_max": 14.5,
            "deadline_hard": 15.0,
            "priority": Priority.MEDIUM.name,
        },
    }
    
    print(f"Destination: {destination['name']}")
    print()
    
    # First access - cache miss
    print("First access (cache miss):")
    tw1 = manager.get_time_window(destination)
    print(f"  Cached window: {tw1.scheduled_hour}:00 [{tw1.priority.name}]")
    print(f"  Cache size: {len(manager._time_window_cache)}")
    
    # Second access - cache hit
    print("\nSecond access (cache hit):")
    tw2 = manager.get_time_window(destination)
    print(f"  Cached window: {tw2.scheduled_hour}:00 [{tw2.priority.name}]")
    print(f"  Cache size: {len(manager._time_window_cache)}")
    print(f"  Same object? {tw1 is tw2}")


if __name__ == "__main__":
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 15 + "TIME CONSTRAINTS SYSTEM VALIDATION" + " " * 19 + "║")
    print("╚" + "═" * 68 + "╝")
    
    demo_time_window()
    demo_schedule_enhancement()
    demo_deadline_feasibility()
    demo_energy_time_tradeoff()
    demo_cache_performance()
    
    print_section("✓ VALIDATION COMPLETE")
    print("All time constraint features demonstrated successfully!")
    print()
