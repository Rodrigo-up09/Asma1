"""
Shared constants, state name strings, and helper functions
used across all EV agent states.
"""

import json

from spade.message import Message

# ── State name constants ───────────────────────
STATE_GOING_TO_CHARGER = "GOING_TO_CHARGER"
STATE_WAITING_QUEUE = "WAITING_QUEUE"
STATE_CHARGING = "CHARGING"
STATE_DRIVING = "DRIVING"
STATE_STOPPED = "STOPPED"

# ── Tick timing ────────────────────────────────
TICK_SLEEP_SECONDS = 0.1  # real-time delay between ticks

DRIVE_DRAIN_KW = 7.5  # energy consumption while moving
DRIVE_ENERGY_MULTIPLIER = 1.3  # global multiplier for travel energy use


# ── Metrics helper ─────────────────────────────
async def send_stat(state, world_jid: str, payload: dict) -> None:
    """Fire-and-forget a world-stats message to the WorldAgent."""
    if not world_jid:
        return
    msg = Message(to=world_jid)
    msg.set_metadata("protocol", "world-stats")
    msg.set_metadata("performative", "inform")
    msg.body = json.dumps(payload)
    await state.send(msg)
