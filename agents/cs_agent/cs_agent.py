import asyncio
import json
from typing import Any, Mapping, Optional

import spade
from spade.agent import Agent

from environment.world_clock import WorldClock

from spade.behaviour import CyclicBehaviour
from spade.template import Template

from .messaging import CSMessagingService
from .queue_manager import CSRequestQueue
from .states import AvailableState, CSChargingFSM, FullState, STATE_AVAILABLE, STATE_FULL
from .models import CSConfig


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
    def __init__(
        self,
        jid,
        password,
        cs_config: CSConfig | Mapping[str, Any] | None = None,
        *args,
        **kwargs,
    ):
        super().__init__(jid, password, *args, **kwargs)

        if isinstance(cs_config, CSConfig):
            config = cs_config
            world_jid = ""
        else:
            config_dict = cs_config or {}
            config = CSConfig.from_mapping(config_dict)
            world_jid = config_dict.get("world_jid", "")

        self.max_charging_rate = config.max_charging_rate
        self.num_doors = config.num_doors

        self.max_solar_capacity = config.max_solar_capacity
        self.actual_solar_capacity = config.actual_solar_capacity
        self.energy_price = config.energy_price
        self.solar_production_rate = config.solar_production_rate
        self.x = config.x
        self.y = config.y

        self.used_doors = 0
        self.request_queue = CSRequestQueue()
        self.active_charging = {}
        self.messaging_service = CSMessagingService()
        self.world_clock = None
        self._last_solar_update_sim_hours = None
        
        # World-state — updated by WorldUpdateBehaviour on each broadcast
        self.electricity_price: float = 0.15
        self.grid_load: float = 0.5
        self.renewable_available: bool = False

        # WorldAgent JID — set by main.py after construction
        self.world_jid: str = world_jid
    def solar_discount(self):
        if self.actual_solar_capacity <= 0.0:
            return 0.0
        max_discount = 0.3
        return min(max_discount, (self.actual_solar_capacity / self.max_solar_capacity) * max_discount)
    
    def update_solar_energy(self) -> float:
        """Accumulate solar energy using simulated time delta.

        Assumptions:
        - `solar_production_rate` is in kW.
        - `actual_solar_capacity` and `max_solar_capacity` are in kWh.
        """
        if self.world_clock is None:
            return 0.0

        now_sim_hours = float(self.world_clock.sim_hours)
        if self._last_solar_update_sim_hours is None:
            self._last_solar_update_sim_hours = now_sim_hours
            return 0.0

        delta_hours = max(0.0, now_sim_hours - self._last_solar_update_sim_hours)
        self._last_solar_update_sim_hours = now_sim_hours

        if delta_hours <= 0.0 or self.solar_production_rate <= 0.0:
            return 0.0

        generated_kwh = float(self.solar_production_rate) * delta_hours
        previous = float(self.actual_solar_capacity)
        self.actual_solar_capacity = min(
            float(self.max_solar_capacity),
            previous + generated_kwh,
        )
        return self.actual_solar_capacity - previous

    def can_accept_request(self, request):
        ev_jid = request.get("ev_jid")
        return (
            ev_jid not in self.active_charging
            and self.used_doors < self.num_doors
            
        )

    async def accept_request(self, request, state, from_queue=False):
        ev_jid = request["ev_jid"]
        self.used_doors += 1
        if self.actual_solar_capacity >= request["required_energy"]:
            self.actual_solar_capacity -= request["required_energy"]
        
        # Calculate price with current solar discount
        discount = self.solar_discount()
        final_price = request["required_energy"] * self.energy_price * (1 - discount)
        
        self.active_charging[ev_jid] = {
            "required_energy": request["required_energy"],
            "rate": request["max_charging_rate"],
            "price": final_price,
        }

        await self.messaging_service.send_response(
            state, 
            ev_jid, 
            "accept",
            extra={
                "price": final_price,
                "solar_discount": discount,
                "energy_price": self.energy_price,
            }
        )

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

        self.active_charging.pop(ev_jid)
        self.used_doors = max(0, self.used_doors - 1)
        return True

    async def setup(self):
        print(f"[CS Agent] {self.jid} starting...")
        print(
            f"[CS Agent] Doors: {self.num_doors} | "
            f"Max charging rate: {self.max_charging_rate} kW | "
            f"Max solar capacity: {self.max_solar_capacity} kWh"
        )

        fsm = CSChargingFSM()
        fsm.add_state(name=STATE_AVAILABLE, state=AvailableState(), initial=True)
        fsm.add_state(name=STATE_FULL, state=FullState())
        fsm.add_transition(source=STATE_AVAILABLE, dest=STATE_AVAILABLE)
        fsm.add_transition(source=STATE_AVAILABLE, dest=STATE_FULL)
        fsm.add_transition(source=STATE_FULL, dest=STATE_FULL)
        fsm.add_transition(source=STATE_FULL, dest=STATE_AVAILABLE)

        # Register FSM without specific template to receive all messages.
        # The FSM._dispatch will route messages to _on_request or _on_inform
        # based on performative; the handlers filter by protocol internally.
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
        cs_config=CSConfig(
  

        ),
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