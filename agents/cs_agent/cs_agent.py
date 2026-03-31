import asyncio
import json

import spade
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.template import Template

from .messaging import CSMessagingService
from .queue_manager import CSRequestQueue
from .states import AvailableState, CSChargingFSM, FullState, STATE_AVAILABLE, STATE_FULL


class WorldUpdateBehaviour(CyclicBehaviour):
    """Receive world-update broadcasts from the WorldAgent and update local state."""

    async def run(self) -> None:
        msg = await self.receive(timeout=5)
        if msg is None:
            return
        try:
            data = json.loads(msg.body)
        except (json.JSONDecodeError, TypeError):
            return

        self.agent.electricity_price = data.get("electricity_price", self.agent.electricity_price)
        self.agent.grid_load = data.get("grid_load", self.agent.grid_load)
        self.agent.renewable_available = data.get("renewable_available", self.agent.renewable_available)


# ──────────────────────────────────────────────
#  Charging Station Agent
# ──────────────────────────────────────────────
class CSAgent(Agent):
    def __init__(self, jid, password, cs_config=None, *args, **kwargs):
        super().__init__(jid, password, *args, **kwargs)

        config = cs_config or {}

        self.max_charging_rate = config.get("max_charging_rate", config.get("max_power_kw", 22.0))
        self.num_doors = config.get("num_doors", 4)
        self.capacity = config.get("capacity", 150.0)
        self.x = config.get("x", 0.0)
        self.y = config.get("y", 0.0)
        self.used_doors = 0
        self.request_queue = CSRequestQueue()
        self.active_charging = {}
        self.messaging_service = CSMessagingService()

        # World-state — updated by WorldUpdateBehaviour on each broadcast
        self.electricity_price: float = 0.15
        self.grid_load: float = 0.5
        self.renewable_available: bool = False

        # WorldAgent JID — set by main.py after construction
        self.world_jid: str = config.get("world_jid", "")

    def can_accept_request(self, request):
        ev_jid = request.get("ev_jid")
        return (
            ev_jid not in self.active_charging
            and self.used_doors < self.num_doors
            and request["required_energy"] <= self.capacity
        )

    async def accept_request(self, request, state, from_queue=False):
        ev_jid = request["ev_jid"]
        self.used_doors += 1
        self.capacity -= request["required_energy"]
        self.active_charging[ev_jid] = {
            "required_energy": request["required_energy"],
            "rate": request["max_charging_rate"],
        }

        await self.messaging_service.send_response(state, ev_jid, "accept")

        if from_queue:
            print(
                f"[CS] Accepted (queue) {ev_jid}: "
                f"{request['required_energy']:.1f} kWh | "
                f"Doors: {self.used_doors}/{self.num_doors}"
            )
            return

        print(
            f"[CS] Accepted {ev_jid}: "
            f"{request['required_energy']:.1f} kWh @ {request['max_charging_rate']} kW | "
            f"Doors: {self.used_doors}/{self.num_doors}"
        )

    def complete_session(self, ev_jid):
        if ev_jid not in self.active_charging:
            return False

        session = self.active_charging.pop(ev_jid)
        self.used_doors = max(0, self.used_doors - 1)
        self.capacity += session["required_energy"]
        return True

    async def setup(self):
        print(f"[CS Agent] {self.jid} starting...")
        print(
            f"[CS Agent] Doors: {self.num_doors} | "
            f"Max charging rate: {self.max_charging_rate} kW | "
            f"Capacity: {self.capacity} kWh"
        )

        fsm = CSChargingFSM()
        fsm.add_state(name=STATE_AVAILABLE, state=AvailableState(), initial=True)
        fsm.add_state(name=STATE_FULL, state=FullState())
        fsm.add_transition(source=STATE_AVAILABLE, dest=STATE_AVAILABLE)
        fsm.add_transition(source=STATE_AVAILABLE, dest=STATE_FULL)
        fsm.add_transition(source=STATE_FULL, dest=STATE_FULL)
        fsm.add_transition(source=STATE_FULL, dest=STATE_AVAILABLE)

        self.add_behaviour(fsm)

        world_update_template = Template()
        world_update_template.set_metadata("protocol", "world-update")
        self.add_behaviour(WorldUpdateBehaviour(), world_update_template)


# ──────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────
async def main():
    cs = CSAgent(
        "cs1@localhost",
        "password",
        cs_config={
            "max_charging_rate": 22.0,
            "num_doors": 4,
            "capacity": 150.0,
        },
    )
    await cs.start()
    cs.web.start(hostname="127.0.0.1", port=10001)

    print("\nWeb interface: http://127.0.0.1:10001")
    print("Press Ctrl+C to stop.\n")

    while True:
        try:
            await asyncio.sleep(1)
        except KeyboardInterrupt:
            break

    await cs.stop()


if __name__ == "__main__":
    spade.run(main())