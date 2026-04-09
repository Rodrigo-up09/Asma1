import math
from typing import Any, Dict, List, Optional, Tuple


def required_energy_kwh(current_soc: float, required_soc: float, battery_capacity_kwh: float) -> float:
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


async def handle_cs_proposal(
    state: Any,
    agent: Any,
    response_data: Dict[str, Any],
    cs_jid: str,
) -> Optional[Tuple[bool, str]]:
    """Process and confirm CS proposal (accept/wait).
    
    Args:
        state: SPADE state
        agent: EV agent
        response_data: Parsed response from CS
        cs_jid: Charging station JID
        
    Returns:
        Tuple of (confirmed, decision_msg) where:
        - confirmed: True if proposal was accepted
        - decision_msg: Human-readable message about the decision
    """
    status = response_data.get("status", "unknown")
    
    # Decide whether to accept the proposal
    if status in ("accept", "wait"):
        # Always accept for now (in future: could add logic to reject)
        accepted = True
        decision_msg = f"Accepted CS proposal: {status}"
    else:
        accepted = False
        decision_msg = f"Rejected CS proposal: {status}"
    
    # Send confirmation to CS
    await agent.messaging_service.send_proposal_confirm(
        state,
        cs_jid,
        accepted,
    )
    
    return accepted, decision_msg


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


def closest_station(ev_x: float, ev_y: float, cs_stations: Dict[str, Any]) -> Tuple[Optional[str], float]:
    """Find closest charging station.
    
    Args:
        ev_x: EV x position
        ev_y: EV y position
        cs_stations: Dict of charging stations {jid: {x, y, ...}}
        
    Returns:
        Tuple of (closest_jid, distance) or (None, float('inf')) if no stations
    """
    min_dist = float("inf")
    closest_jid = None
    for jid, pos in cs_stations.items():
        dist = math.hypot(pos["x"] - ev_x, pos["y"] - ev_y)
        if dist < min_dist:
            min_dist = dist
            closest_jid = jid
    return closest_jid, min_dist


def get_station_position(cs_stations: Dict[str, Any], jid: str) -> Optional[Dict[str, float]]:
    """Get position of a charging station.
    
    Args:
        cs_stations: Dict of charging stations {jid: {x, y, ...}}
        jid: Charging station JID
        
    Returns:
        Position dict {x, y} or None if not found
    """
    return cs_stations.get(jid)


def move_towards(
    current_x: float,
    current_y: float,
    target_x: float,
    target_y: float,
    velocity: float,
) -> Tuple[float, float, float]:
    """Move towards target position.
    
    Args:
        current_x: Current x position
        current_y: Current y position
        target_x: Target x position
        target_y: Target y position
        velocity: Velocity (units per sim hour)
        
    Returns:
        Tuple of (new_x, new_y, remaining_distance)
    """
    dx = target_x - current_x
    dy = target_y - current_y
    dist = math.hypot(dx, dy)
    
    if dist == 0:
        return current_x, current_y, 0.0
    
    # Move velocity units towards target (assuming 1 frame = 1 unit of time)
    move_distance = velocity
    if move_distance >= dist:
        return target_x, target_y, 0.0
    
    # Partial move
    ratio = move_distance / dist
    new_x = current_x + dx * ratio
    new_y = current_y + dy * ratio
    new_dist = dist - move_distance
    
    return new_x, new_y, new_dist
