
import time
from typing import Iterable

from .models import ChargingRequest, IncomingRequest, PendingProposal


DEFAULT_PROPOSAL_TTL_SECONDS = 3.0


def charging_time_minutes(required_energy_kwh, ev_rate_kw, cs_rate_kw):
    effective_rate = min(float(ev_rate_kw), float(cs_rate_kw))
    if effective_rate <= 0:
        return float("inf")
    required_energy = max(0.0, float(required_energy_kwh))
    return (required_energy / effective_rate) * 60.0


def _proposal_is_expired(proposal: PendingProposal, now_monotonic: float) -> bool:
    expires_at = proposal.get("expires_at")
    if expires_at is None:
        return False
    return float(expires_at) <= float(now_monotonic)


def _iter_active_pending_proposals(
    pending_proposals: dict[str, PendingProposal],
    now_monotonic: float,
) -> Iterable[PendingProposal]:
    for proposal in pending_proposals.values():
        if not _proposal_is_expired(proposal, now_monotonic):
            yield proposal


def count_pending_slot_reservations(
    pending_proposals: dict[str, PendingProposal],
    now_monotonic: float | None = None,
) -> int:
    """Count active pending proposals that reserve a charging slot."""
    now_value = time.monotonic() if now_monotonic is None else now_monotonic
    return sum(
        1
        for proposal in _iter_active_pending_proposals(pending_proposals, now_value)
        if proposal.get("reserves_slot", proposal.get("decision") == "accept")
    )


def cleanup_expired_pending_proposals(
    pending_proposals: dict[str, PendingProposal],
    now_monotonic: float | None = None,
) -> list[str]:
    """Remove expired pending proposals and return removed EV JIDs."""
    now_value = time.monotonic() if now_monotonic is None else now_monotonic
    expired_ev_jids: list[str] = []
    for ev_jid, proposal in list(pending_proposals.items()):
        if _proposal_is_expired(proposal, now_value):
            expired_ev_jids.append(ev_jid)
            pending_proposals.pop(ev_jid, None)
    return expired_ev_jids


def store_pending_proposal(
    pending_proposals: dict[str, PendingProposal],
    ev_jid: str,
    request_data: ChargingRequest,
    decision: str,
    ttl_seconds: float = DEFAULT_PROPOSAL_TTL_SECONDS,
    now_monotonic: float | None = None,
) -> None:
    """Store a pending proposal awaiting EV confirmation.
    
    Args:
        pending_proposals: Dictionary keyed by ev_jid
        ev_jid: EV identifier
        request_data: Original request parsed from EV
        decision: "accept" or "wait"
    """
    now_value = time.monotonic() if now_monotonic is None else now_monotonic
    pending_proposals[ev_jid] = {
        "request": request_data,
        "decision": decision,
        "reserves_slot": decision == "accept",
        "created_at": now_value,
        "expires_at": now_value + max(0.0, float(ttl_seconds)),
    }


def retrieve_and_remove_proposal(
    pending_proposals: dict[str, PendingProposal],
    ev_jid: str,
) -> PendingProposal | None:
    """Retrieve and remove a proposal from pending list.
    
    Returns:
        Pending proposal dict or empty dict if not found
    """
    return pending_proposals.pop(ev_jid, None)


def add_incoming_request(
    incoming_requests: dict[str, IncomingRequest],
    ev_jid: str,
    arriving_hours: float,
    required_energy: float,
    max_rate: float,
) -> None:
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


def remove_incoming_request(incoming_requests: dict[str, IncomingRequest], ev_jid: str) -> None:
    """Remove an EV from incoming requests (when it arrives or cancels)."""
    incoming_requests.pop(ev_jid, None)


def _append_request_duration_to_earliest_door(
    door_available_at: list[float],
    request: ChargingRequest,
    cs_max_charging_rate: float,
) -> None:
    duration = charging_time_minutes(
        request.get("required_energy", 0.0),
        request.get("max_charging_rate", cs_max_charging_rate),
        cs_max_charging_rate,
    )
    next_door = min(range(len(door_available_at)), key=lambda idx: door_available_at[idx])
    door_available_at[next_door] += duration


def _wait_for_target_request(
    door_available_at: list[float],
    requests: list[ChargingRequest],
    cs_max_charging_rate: float,
    target_ev_jid: str,
) -> float | None:
    """Return wait time (minutes) until target EV can start charging.

    Requests are processed in FIFO order and assigned to the earliest free door,
    matching queue dispatch behavior.
    """
    for request in requests:
        next_door = min(range(len(door_available_at)), key=lambda idx: door_available_at[idx])
        if request.get("ev_jid") == target_ev_jid:
            return door_available_at[next_door]
        _append_request_duration_to_earliest_door(
            door_available_at,
            request,
            cs_max_charging_rate,
        )
    return None


def _build_pending_reservation_requests(
    pending_proposals: dict[str, PendingProposal] | None,
    now_monotonic: float,
) -> list[ChargingRequest]:
    if not pending_proposals:
        return []

    pending_requests: list[ChargingRequest] = []
    for proposal in _iter_active_pending_proposals(pending_proposals, now_monotonic):
        if not proposal.get("reserves_slot", proposal.get("decision") == "accept"):
            continue

        request = proposal.get("request") or {}
        pending_requests.append(
            {
                "required_energy": request.get("required_energy", 0.0),
                "max_charging_rate": request.get("max_charging_rate", 0.0),
            }
        )
    return pending_requests


def _build_incoming_requests_for_estimate(
    incoming_requests: dict[str, IncomingRequest] | None,
) -> list[ChargingRequest]:
    if not incoming_requests:
        return []
    return [
        {
            "required_energy": item.get("required_energy", 0.0),
            "max_charging_rate": item.get("max_charging_rate", 0.0),
        }
        for item in incoming_requests.values()
    ]


def calculate_wait_time_minutes(
    active_charging: dict[str, dict[str, float]],
    request_queue: list[ChargingRequest],
    num_doors: int,
    cs_max_charging_rate: float,
    pending_proposals: dict[str, PendingProposal] | None = None,
    incoming_requests: dict[str, IncomingRequest] | None = None,
    include_incoming_requests: bool = False,
    target_ev_jid: str | None = None,
    assumed_request: ChargingRequest | None = None,
) -> float:
    """Calculate estimated wait time until the first door is available.
    
    Args:
        active_charging: Dict of currently charging EVs
        request_queue: List of queued requests
        num_doors: Number of charging doors
        cs_max_charging_rate: Station's max charging rate (kW)
        pending_proposals: Pending CS proposals; only active "accept" entries reserve slots
        incoming_requests: Incoming, not-yet-confirmed requests (optional)
        include_incoming_requests: Whether incoming requests should affect estimate
        target_ev_jid: EV JID to estimate wait for, considering queue position
        assumed_request: Request to append virtually (e.g., proposal not confirmed yet)
        
    Returns:
        Wait time in minutes until a door is free
    """
    doors = max(1, int(num_doors))
    now_value = time.monotonic()
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

    queue_for_estimate = list(request_queue)
    if assumed_request is not None:
        queue_for_estimate.append(assumed_request)

    if target_ev_jid:
        wait_for_target = _wait_for_target_request(
            door_available_at,
            queue_for_estimate,
            cs_max_charging_rate,
            target_ev_jid,
        )
        if wait_for_target is not None:
            return wait_for_target

    # Account for queued requests
    for request in queue_for_estimate:
        _append_request_duration_to_earliest_door(
            door_available_at,
            request,
            cs_max_charging_rate,
        )

    # Account for pending ACCEPT proposals as temporary reservations.
    for request in _build_pending_reservation_requests(pending_proposals, now_value):
        _append_request_duration_to_earliest_door(
            door_available_at,
            request,
            cs_max_charging_rate,
        )

    # Optional: account for incoming requests, disabled by default to avoid overestimation.
    if include_incoming_requests:
        for request in _build_incoming_requests_for_estimate(incoming_requests):
            _append_request_duration_to_earliest_door(
                door_available_at,
                request,
                cs_max_charging_rate,
            )

    return min(door_available_at)