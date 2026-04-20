#!/usr/bin/env python3
"""
Urgency Model System Validation

Demonstrates:
- Urgency level calculation from priority
- Time pressure metrics
- Charging threshold adjustments
- Charging strategy selection
- Destination priority ranking
"""

import math
from agents.ev_agent.urgency_model import UrgencyModel, UrgencyLevel


def print_section(title):
    """Print formatted section header."""
    print(f"\n{'═' * 70}")
    print(f"  {title}")
    print(f"{'═' * 70}\n")


def demo_urgency_levels():
    """Demonstrate urgency level mapping."""
    print_section("1. URGENCY LEVELS: Priority to Urgency Mapping")
    
    priorities = ["LOW", "MEDIUM", "HIGH", "EMERGENCY"]
    
    for priority in priorities:
        urgency = UrgencyModel.get_urgency_level_from_priority(priority)
        print(f"  {priority:10} → {urgency.name:10} (multiplier: {urgency.value:.1f}x)")


def demo_time_pressure():
    """Demonstrate time pressure calculation."""
    print_section("2. TIME PRESSURE: Deadline Urgency Calculation")
    
    test_cases = [
        {
            "current": 9.0,
            "target": 10.0,
            "deadline": 11.0,
            "distance": 20.0,
            "velocity": 2.0,
            "description": "Relaxed - plenty of time",
        },
        {
            "current": 9.5,
            "target": 10.0,
            "deadline": 11.0,
            "distance": 20.0,
            "velocity": 2.0,
            "description": "Normal - moderate time pressure",
        },
        {
            "current": 9.8,
            "target": 10.0,
            "deadline": 11.0,
            "distance": 20.0,
            "velocity": 2.0,
            "description": "Tight - getting urgent",
        },
        {
            "current": 10.2,
            "target": 10.0,
            "deadline": 11.0,
            "distance": 20.0,
            "velocity": 2.0,
            "description": "Critical - already late",
        },
    ]
    
    print(f"{'Time':>6} {'Target':>6} {'Deadline':>8} {'Pressure':>10} {'Status'}")
    print("─" * 60)
    
    for case in test_cases:
        pressure = UrgencyModel.calculate_time_pressure(
            current_time=case["current"],
            target_time=case["target"],
            hard_deadline=case["deadline"],
            distance=case["distance"],
            velocity=case["velocity"],
        )
        print(
            f"{case['current']:6.1f} {case['target']:6.1f} {case['deadline']:8.1f} "
            f"{pressure:10.2f}  {case['description']}"
        )


def demo_charging_threshold_adjustment():
    """Demonstrate charging threshold adjustments by urgency."""
    print_section("3. CHARGING THRESHOLDS: Urgency-Based Adjustment")
    
    base_threshold = 0.30  # 30% baseline
    
    print(f"Base threshold: {base_threshold:.0%}\n")
    print(f"{'Urgency Level':20} {'Multiplier':>10} {'Adjusted':>10} {'Strategy':<15}")
    print("─" * 60)
    
    for urgency_level in UrgencyLevel:
        from agents.ev_agent.urgency_model import UrgencyMetrics, ChargingStrategy
        
        # Create metrics object for this urgency
        if urgency_level == UrgencyLevel.LOW:
            strategy = ChargingStrategy.OPPORTUNISTIC
        elif urgency_level == UrgencyLevel.HIGH or urgency_level == UrgencyLevel.EMERGENCY:
            strategy = ChargingStrategy.AGGRESSIVE
        else:
            strategy = ChargingStrategy.BALANCED
        
        metrics = UrgencyMetrics(
            urgency_level=urgency_level,
            time_pressure=0.5,
            charging_multiplier=0,  # Will be calculated
            speed_adjustment=1.0,
            charging_strategy=strategy,
            priority_score=0,
        )
        
        multiplier = UrgencyModel.calculate_charging_threshold_adjustment(metrics)
        adjusted = UrgencyModel.get_charging_threshold(base_threshold, metrics)
        
        print(
            f"{urgency_level.name:20} {multiplier:10.2f}x {adjusted:10.0%} "
            f"{strategy.value:<15}"
        )


def demo_metrics_calculation():
    """Demonstrate full urgency metrics calculation."""
    print_section("4. URGENCY METRICS: Full Calculation Pipeline")
    
    # Create a destination with HIGH priority
    destination = {
        "name": "Important Meeting",
        "x": 25.0,
        "y": 0.0,
        "hour": 11.0,
        "time_window": {
            "scheduled_hour": 11.0,
            "window_min": 10.5,
            "window_max": 11.5,
            "deadline_hard": 12.0,
            "priority": "HIGH",
        },
    }
    
    # Test at different times
    test_scenarios = [
        {"current_time": 9.0, "soc": 0.70, "distance": 25.0, "velocity": 2.0},
        {"current_time": 10.5, "soc": 0.60, "distance": 25.0, "velocity": 2.0},
        {"current_time": 11.8, "soc": 0.50, "distance": 25.0, "velocity": 2.0},
    ]
    
    print(f"Destination: {destination['name']} at ({destination['x']}, {destination['y']})")
    print(f"Priority: HIGH | Scheduled: {destination['hour']}:00 | Deadline: 12:00\n")
    
    for scenario in test_scenarios:
        metrics = UrgencyModel.calculate_metrics(
            current_time=scenario["current_time"],
            destination=destination,
            current_soc=scenario["soc"],
            distance_to_destination=scenario["distance"],
            velocity=scenario["velocity"],
        )
        
        print(f"At {scenario['current_time']}:00 (SoC {scenario['soc']:.0%}):")
        print(f"  {UrgencyModel.format_urgency_metrics(metrics)}")
        print(f"  Speed Adjustment: {metrics.speed_adjustment}x")
        print()


def demo_destination_ranking():
    """Demonstrate destination ranking by urgency."""
    print_section("5. DESTINATION RANKING: Priority-Based Sorting")
    
    # Create multiple destinations with different urgencies
    destinations = [
        {
            "name": "Shopping",
            "x": -12.0,
            "y": 18.0,
            "hour": 14.0,
            "time_window": {
                "scheduled_hour": 14.0,
                "window_min": 13.0,
                "window_max": 15.0,
                "deadline_hard": 16.0,
                "priority": "LOW",
            },
        },
        {
            "name": "Critical Delivery",
            "x": 20.0,
            "y": -20.0,
            "hour": 10.5,
            "time_window": {
                "scheduled_hour": 10.5,
                "window_min": 10.25,
                "window_max": 10.75,
                "deadline_hard": 11.0,
                "priority": "EMERGENCY",
            },
        },
        {
            "name": "Office Meeting",
            "x": 15.0,
            "y": 15.0,
            "hour": 9.0,
            "time_window": {
                "scheduled_hour": 9.0,
                "window_min": 8.5,
                "window_max": 9.5,
                "deadline_hard": 10.0,
                "priority": "HIGH",
            },
        },
        {
            "name": "Optional Task",
            "x": 5.0,
            "y": 10.0,
            "hour": 13.0,
            "time_window": {
                "scheduled_hour": 13.0,
                "window_min": 12.0,
                "window_max": 14.0,
                "deadline_hard": 15.0,
                "priority": "MEDIUM",
            },
        },
    ]
    
    # Rank destinations
    current_time = 9.5
    ranked = UrgencyModel.rank_destinations(
        destinations=destinations,
        current_time=current_time,
        current_soc=0.60,
        current_x=0.0,
        current_y=0.0,
        velocity=2.0,
    )
    
    print(f"Current time: {current_time}:00 | Current position: (0.0, 0.0) | SoC: 60%\n")
    print(f"{'Rank':>5} {'Destination':20} {'Priority':>10} {'Urgency':>10} {'Score':>8}")
    print("─" * 70)
    
    for rank, (dest, metrics, score) in enumerate(ranked, 1):
        print(
            f"{rank:5} {dest['name']:20} {metrics.urgency_level.name:>10} "
            f"{metrics.time_pressure:>10.2f} {score:>8.0f}"
        )


def demo_should_charge_now():
    """Demonstrate charging decision logic."""
    print_section("6. CHARGING DECISION: Should Charge Now?")
    
    from agents.ev_agent.urgency_model import UrgencyMetrics, ChargingStrategy
    
    test_scenarios = [
        {
            "urgency": "LOW",
            "strategy": ChargingStrategy.OPPORTUNISTIC,
            "current_soc": 0.35,
            "threshold": 0.30,
        },
        {
            "urgency": "MEDIUM",
            "strategy": ChargingStrategy.BALANCED,
            "current_soc": 0.30,
            "threshold": 0.30,
        },
        {
            "urgency": "HIGH",
            "strategy": ChargingStrategy.BALANCED,
            "current_soc": 0.35,
            "threshold": 0.45,
        },
        {
            "urgency": "EMERGENCY",
            "strategy": ChargingStrategy.AGGRESSIVE,
            "current_soc": 0.40,
            "threshold": 0.54,
        },
    ]
    
    print(f"{'Urgency':10} {'Strategy':15} {'SoC':>8} {'Threshold':>10} {'Charge?':>10}")
    print("─" * 60)
    
    for scenario in test_scenarios:
        metrics = UrgencyMetrics(
            urgency_level=UrgencyLevel[scenario["urgency"]],
            time_pressure=0.7,
            charging_multiplier=1.0,
            speed_adjustment=1.0,
            charging_strategy=scenario["strategy"],
            priority_score=0,
        )
        
        should_charge = UrgencyModel.should_charge_now(
            current_soc=scenario["current_soc"],
            adjusted_threshold=scenario["threshold"],
            urgency_metrics=metrics,
        )
        
        print(
            f"{scenario['urgency']:10} {scenario['strategy'].value:15} "
            f"{scenario['current_soc']:8.0%} {scenario['threshold']:10.0%} "
            f"{'YES' if should_charge else 'NO':>10}"
        )


if __name__ == "__main__":
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 15 + "URGENCY MODEL SYSTEM VALIDATION" + " " * 23 + "║")
    print("╚" + "═" * 68 + "╝")
    
    demo_urgency_levels()
    demo_time_pressure()
    demo_charging_threshold_adjustment()
    demo_metrics_calculation()
    demo_destination_ranking()
    demo_should_charge_now()
    
    print_section("✓ VALIDATION COMPLETE")
    print("All urgency model features demonstrated successfully!")
    print()
