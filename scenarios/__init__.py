"""
Scenario management module.
Provides scenario selection, registration, and display functionality.
"""

from .base import Scenario
from .price_comparison import PriceComparison
from .cs_availability import CSAvailability
from .random_scenario import RandomScenario, EV_LOW_SOC_THRESHOLD, EV_TARGET_SOC
from .dynamic_scheduling import DynamicScheduling
from .time_constraints import TimeConstraintScenario
from .utils import generate_scenario_schedule, generate_hourly_schedule

# Registry of all available scenarios
SCENARIOS = [
    PriceComparison(),
    CSAvailability(),
    RandomScenario(),
    DynamicScheduling(),
    TimeConstraintScenario(),
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


__all__ = [
    "Scenario",
    "PriceComparison",
    "CSAvailability",
    "RandomScenario",
    "DynamicScheduling",
    "TimeConstraintScenario",
    "SCENARIOS",
    "get_scenario_by_index",
    "display_menu",
    "generate_scenario_schedule",
    "generate_hourly_schedule",
]
