import math
from typing import Dict, List, Optional, Tuple


def required_energy_kwh(current_soc: float, required_soc: float, battery_capacity_kwh: float) -> float:
    return max(0.0, (required_soc - current_soc) * battery_capacity_kwh)


def closest_station(x: float, y: float, stations: List[Dict[str, float]]) -> Tuple[Optional[str], float]:
    best_jid = None
    best_dist = float("inf")

    for station in stations:
        distance = math.hypot(station["x"] - x, station["y"] - y)
        if distance < best_dist:
            best_dist = distance
            best_jid = station["jid"]

    return best_jid, best_dist


def get_station_position(stations: List[Dict[str, float]], station_jid: Optional[str]) -> Dict[str, float]:
    for station in stations:
        if station["jid"] == station_jid:
            return station
    return {"x": 0.0, "y": 0.0}


def move_towards(x: float, y: float, target_x: float, target_y: float, max_step: float) -> Tuple[float, float, float]:
    distance = math.hypot(target_x - x, target_y - y)
    if distance == 0.0:
        return x, y, 0.0

    step = min(max_step, distance)
    new_x = x + ((target_x - x) / distance) * step
    new_y = y + ((target_y - y) / distance) * step
    remaining_distance = math.hypot(target_x - new_x, target_y - new_y)
    return new_x, new_y, remaining_distance
