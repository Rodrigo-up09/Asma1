


def charging_time_minutes(required_energy_kwh, ev_rate_kw, cs_rate_kw):
    effective_rate = min(float(ev_rate_kw), float(cs_rate_kw))
    if effective_rate <= 0:
        return float("inf")
    required_energy = max(0.0, float(required_energy_kwh))
    return (required_energy / effective_rate) * 60.0


def store_pending_proposal(pending_proposals: dict, ev_jid: str, request_data: dict, decision: str) -> None:
    """Store a pending proposal awaiting EV confirmation.
    
    Args:
        pending_proposals: Dictionary keyed by ev_jid
        ev_jid: EV identifier
        request_data: Original request parsed from EV
        decision: "accept" or "wait"
    """
    pending_proposals[ev_jid] = {
        "request": request_data,
        "decision": decision,
    }


def retrieve_and_remove_proposal(pending_proposals: dict, ev_jid: str) -> dict:
    """Retrieve and remove a proposal from pending list.
    
    Returns:
        Pending proposal dict or empty dict if not found
    """
    return pending_proposals.pop(ev_jid, {})


def apply_confirmed_proposal(
    ev_jid: str,
    proposal: dict,
    agent: object,  # CSAgent
    state: object,  # SPADE State for sending
) -> None:
    """Apply a confirmed proposal (register EV in charging or queue).
    
    Args:
        ev_jid: EV identifier
        proposal: Proposal dict with 'request' and 'decision'
        agent: CSAgent instance
        state: SPADE state for sending metrics etc.
    """
    decision = proposal.get("decision")
    request_data = proposal.get("request", {})
    
    if decision == "accept":
        # Register directly for immediate charging
        agent.active_charging[ev_jid] = {
            "required_energy": request_data.get("required_energy", 0.0),
            "rate": request_data.get("max_charging_rate", agent.max_charging_rate),
            "price": request_data.get("price", 0.0),
        }
        agent.used_doors += 1
    elif decision == "wait":
        # Register in queue
        agent.request_queue.enqueue(request_data)


def add_incoming_request(incoming_requests: dict, ev_jid: str, arriving_hours: float, required_energy: float, max_rate: float) -> None:
    """Add an EV to the incoming requests list.
    
    Args:
        incoming_requests: Dictionary keyed by ev_jid with arrival info
        ev_jid: EV identifier
        arriving_hours: Simulation hours when EV arrives
        required_energy: Energy needed (kWh)
        max_rate: EV's max charging rate (kW)
    """
    incoming_requests[ev_jid] = {
        "arriving_hours": arriving_hours,
        "required_energy": required_energy,
        "max_charging_rate": max_rate,
    }


def remove_incoming_request(incoming_requests: dict, ev_jid: str) -> None:
    """Remove an EV from incoming requests (when it arrives or cancels)."""
    incoming_requests.pop(ev_jid, None)


def calculate_wait_time_minutes(
    active_charging: dict,
    request_queue: list,
    num_doors: int,
    cs_max_charging_rate: float,
) -> float:
    """Calculate estimated wait time based on active charging, queue, and incoming.
    
    Args:
        active_charging: Dict of currently charging EVs
        request_queue: List of queued requests
        num_doors: Number of charging doors
        cs_max_charging_rate: Station's max charging rate (kW)
        
    Returns:
        Wait time in minutes until a door is free
    """
    doors = max(1, int(num_doors))
    door_available_at = [0.0] * doors

    # Account for active charging sessions
    for session in active_charging.values():
        duration = charging_time_minutes(
            session.get("required_energy", 0.0),
            session.get("rate", cs_max_charging_rate),
            cs_max_charging_rate,
        )
        next_door = min(range(doors), key=lambda idx: door_available_at[idx])
        door_available_at[next_door] += duration

    # Account for queued requests
    for request in request_queue:
        duration = charging_time_minutes(
            request.get("required_energy", 0.0),
            request.get("max_charging_rate", cs_max_charging_rate),
            cs_max_charging_rate,
        )
        next_door = min(range(doors), key=lambda idx: door_available_at[idx])
        door_available_at[next_door] += duration

    return min(door_available_at)