import math
from typing import Any, Dict, List, Optional, Tuple

# ──────────────────────────────────────────────────────────────────
#  CS Selection Weights (configurable for testing different strategies)
# ──────────────────────────────────────────────────────────────────
# These weights control how much each factor influences CS selection:
# - WEIGHT_DISTANCE: Preference based on proximity (0=ignore, 1=equal weight)
# - WEIGHT_PRICE: Preference based on low cost (0=ignore, 1=equal weight)  
# - WEIGHT_LOAD: Preference based on availability (0=ignore, 1=equal weight)
#
# The EV scores each CS and picks the one with the lowest score.
# Adjust these to test different scenarios.

CS_SELECTION_WEIGHTS = {
    "distance": 1.0,  # Weight for distance (lower distance = better)
    "price": 1.0,     # Weight for price (lower price = better)
    "load": 1.0,      # Weight for load (less full = better, i.e., lower utilization)
}


def set_cs_selection_weights(distance: float = 1.0, price: float = 1.0, load: float = 1.0):
    """Configure the weights for CS selection strategy.
    
    Args:
        distance: Weight for distance factor (0 to disable, higher = more important)
        price: Weight for price factor (0 to disable, higher = more important)
        load: Weight for load factor (0 to disable, higher = more important)
    """
    CS_SELECTION_WEIGHTS["distance"] = distance
    CS_SELECTION_WEIGHTS["price"] = price
    CS_SELECTION_WEIGHTS["load"] = load


def required_energy_kwh(
    current_soc: float, required_soc: float, battery_capacity_kwh: float
) -> float:
    return max(0.0, (required_soc - current_soc) * battery_capacity_kwh)


def calculate_arrival_time_hours(
    ev_x: float,
    ev_y: float,
    cs_pos: Dict[str, float],
    velocity: float,
    world_clock: Optional[Any] = None,
) -> Optional[float]:
    """Calculate the arrival time (in simulation hours) for an EV to reach a charging station.

    Args:
        ev_x: Current EV x position
        ev_y: Current EV y position
        cs_pos: Charging station position dict with keys 'x' and 'y'
        velocity: EV velocity (units per simulation hour)
        world_clock: World clock object with sim_hours attribute

    Returns:
        Arrival time in simulation hours, or None if world_clock is not available
    """
    if world_clock is None:
        return None

    distance = math.hypot(cs_pos["x"] - ev_x, cs_pos["y"] - ev_y)
    time_to_arrive_hours = distance / velocity if velocity > 0 else 0.0
    return world_clock.sim_hours + time_to_arrive_hours


def apply_energy_drain(
    current_soc: float,
    energy_per_km: float,
    velocity: float,
    sim_hours_elapsed: float,
    battery_capacity_kwh: float,
) -> Tuple[float, float]:
    """Apply energy drain during travel.

    Args:
        current_soc: Current SoC (0.0 to 1.0)
        energy_per_km: kWh per km
        velocity: Units per simulation hour
        sim_hours_elapsed: Simulation hours that passed
        battery_capacity_kwh: Battery capacity in kWh

    Returns:
        Tuple of (new_soc, energy_used_kwh)
    """
    drain_kw = energy_per_km * velocity
    energy_used = drain_kw * sim_hours_elapsed
    soc_drop = energy_used / battery_capacity_kwh
    new_soc = max(0.0, current_soc - soc_drop)
    return new_soc, energy_used


def calculate_energy_consumed(
    energy_per_km: float,
    velocity: float,
    sim_hours_elapsed: float,
) -> float:
    """Calculate energy consumed during travel.

    Args:
        energy_per_km: kWh per km
        velocity: Units per simulation hour
        sim_hours_elapsed: Simulation hours that passed

    Returns:
        Energy consumed in kWh
    """
    drain_kw = energy_per_km * velocity
    return drain_kw * sim_hours_elapsed


def update_soc_after_travel(
    current_soc: float,
    energy_consumed_kwh: float,
    battery_capacity_kwh: float,
) -> float:
    """Update State of Charge after energy consumption.

    Args:
        current_soc: Current SoC (0.0 to 1.0)
        energy_consumed_kwh: Energy consumed in kWh
        battery_capacity_kwh: Battery capacity in kWh

    Returns:
        New SoC (0.0 to 1.0)
    """
    soc_drop = energy_consumed_kwh / battery_capacity_kwh
    return max(0.0, current_soc - soc_drop)


def score_charging_station(
    ev_x: float,
    ev_y: float,
    station: Dict[str, Any],
) -> float:
    """Score a charging station based on distance, price, and load.
    
    Lower scores are better. Returns a composite score combining all factors.
    
    Args:
        ev_x: EV x position
        ev_y: EV y position
        station: Station dict with keys: jid, x, y, electricity_price, used_doors, expected_evs, num_doors
        
    Returns:
        Composite score (lower is better)
    """
    # Distance component (normalized)
    distance = math.hypot(station["x"] - ev_x, station["y"] - ev_y)
    distance_score = distance  # Keep in original units (larger values = farther)
    
    # Price component adjusted by available solar energy at the station.
    # Mirrors CS-side discount model: up to 30% off when solar storage is full.
    base_price = station.get("electricity_price", 0.15)
    actual_solar = max(0.0, float(station.get("actual_solar_capacity", 0.0)))
    max_solar = max(1e-6, float(station.get("max_solar_capacity", 1.0)))
    solar_discount = min(0.3, (actual_solar / max_solar) * 0.3)
    price_score = base_price * (1.0 - solar_discount)
    
    # Load component (0.0 to 1.0, where 1.0 = completely full)
    used_doors = station.get("used_doors", 0)
    expected_evs = station.get("expected_evs", 0)
    num_doors = station.get("num_doors", 1)
    load_factor = (used_doors + (0.5 * expected_evs)) / num_doors if num_doors > 0 else 1.0
    
    # Composite score with configurable weights
    composite_score = (
        CS_SELECTION_WEIGHTS["distance"] * distance_score
        + CS_SELECTION_WEIGHTS["price"] * price_score * 100  # Scale price to be comparable
        + CS_SELECTION_WEIGHTS["load"] * load_factor * 100  # Scale load to be comparable
    )
    
    return composite_score


def best_charging_station(
    x: float, y: float, stations: List[Dict[str, Any]]
) -> Tuple[Optional[str], float]:
    """Select the best charging station based on distance, price, and load.
    
    Uses weighted scoring to balance proximity, cost, and availability.
    
    Returns:
        Tuple of (station_jid, best_score)
    """
    if not stations:
        return None, float("inf")
    
    best_jid = None
    best_score = float("inf")
    
    for station in stations:
        score = score_charging_station(x, y, station)
        if score < best_score:
            best_score = score
            best_jid = station.get("jid")
    
    return best_jid, best_score


def closest_station(
    x: float, y: float, stations: List[Dict[str, float]]
) -> Tuple[Optional[str], float]:
    """Get closest station by distance only (legacy function, kept for compatibility).
    
    For new code, use best_charging_station() instead which considers price and load.
    """
    best_jid = None
    best_dist = float("inf")

    for station in stations:
        distance = math.hypot(station["x"] - x, station["y"] - y)
        if distance < best_dist:
            best_dist = distance
            best_jid = station["jid"]

    return best_jid, best_dist


def get_station_position(
    stations: List[Dict[str, float]], station_jid: Optional[str]
) -> Dict[str, float]:
    for station in stations:
        if station["jid"] == station_jid:
            return station
    return {"x": 0.0, "y": 0.0}


def move_towards(
    x: float, y: float, target_x: float, target_y: float, max_step: float
) -> Tuple[float, float, float]:
    distance = math.hypot(target_x - x, target_y - y)
    if distance == 0.0:
        return x, y, 0.0

    step = min(max_step, distance)
    new_x = x + ((target_x - x) / distance) * step
    new_y = y + ((target_y - y) / distance) * step
    remaining_distance = math.hypot(target_x - new_x, target_y - new_y)
    return new_x, new_y, remaining_distance
