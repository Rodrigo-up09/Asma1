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
    "SCENARIOS",
    "get_scenario_by_index",
    "display_menu",
    "generate_scenario_schedule",
    "generate_hourly_schedule",
]
