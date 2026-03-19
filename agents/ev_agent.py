import asyncio
import json
from datetime import datetime

import spade
from spade.agent import Agent
from spade.behaviour import FSMBehaviour, State
from spade.message import Message
from spade.template import Template

# ──────────────────────────────────────────────
#  FSM States
# ──────────────────────────────────────────────
STATE_GOING_TO_CHARGER = "GOING_TO_CHARGER"
STATE_CHARGING = "CHARGING"
STATE_DRIVING = "DRIVING"


# ──────────────────────────────────────────────
#  FSM Behaviour
# ──────────────────────────────────────────────
class EVChargingFSM(FSMBehaviour):
    async def on_start(self):
        name = str(self.agent.jid).split("@")[0]
        print(f"[{name}][FSM] Starting at state: {self.current_state}")

    async def on_end(self):
        name = str(self.agent.jid).split("@")[0]
        print(f"[{name}][FSM] Finished at state: {self.current_state}")


# ──────────────────────────────────────────────
#  GOING_TO_CHARGER State
# ──────────────────────────────────────────────
class GoingToChargerState(State):
    async def run(self):
        agent = self.agent
        cs_jid = agent.cs_jid
        name = str(agent.jid).split("@")[0]

        print(f"[{name}][GOING_TO_CHARGER] 🔌 Requesting charge from {cs_jid}...")

        # Calcula energia necessária
        required_energy = (
            agent.required_soc - agent.current_soc
        ) * agent.battery_capacity_kwh

        # Send a charge request to the CS agent
        msg = Message(to=cs_jid)
        msg.set_metadata("protocol", "ev-charging")
        msg.set_metadata("performative", "request")
        msg.body = json.dumps(
            {
                "required_energy": required_energy,
                "max_charging_rate": agent.max_charge_rate_kw,
            }
        )
        await self.send(msg)

        # Wait for a reply
        reply = await self.receive(timeout=10)

        if reply:
            try:
                response_data = json.loads(reply.body)
                status = response_data.get("status")
                if status == "accept":
                    print(
                        f"[{name}][GOING_TO_CHARGER] ✅ CS accepted! Starting to charge."
                    )
                    self.set_next_state(STATE_CHARGING)
                else:
                    print(
                        f"[{name}][GOING_TO_CHARGER] ❌ CS responded: {status}. Retrying in 3s..."
                    )
                    await asyncio.sleep(3)
                    self.set_next_state(STATE_GOING_TO_CHARGER)
            except json.JSONDecodeError:
                print(
                    f"[{name}][GOING_TO_CHARGER] ❌ Invalid response format. Retrying in 3s..."
                )
                await asyncio.sleep(3)
                self.set_next_state(STATE_GOING_TO_CHARGER)
        else:
            print(
                f"[{name}][GOING_TO_CHARGER] ❌ Timeout waiting for CS response. Retrying in 3s..."
            )
            await asyncio.sleep(3)
            self.set_next_state(STATE_GOING_TO_CHARGER)


# ──────────────────────────────────────────────
#  CHARGING State
# ──────────────────────────────────────────────
class ChargingState(State):
    async def run(self):
        agent = self.agent
        name = str(agent.jid).split("@")[0]

        tick_hours = 0.25
        energy_added = agent.max_charge_rate_kw * tick_hours
        soc_gain = energy_added / agent.battery_capacity_kwh

        agent.current_soc = min(1.0, agent.current_soc + soc_gain)

        print(
            f"[{name}][CHARGING] ⚡ SoC: {agent.current_soc:.0%} "
            f"(+{energy_added:.1f} kWh)"
        )

        await asyncio.sleep(2)

        if agent.current_soc >= agent.required_soc:
            print(f"[{name}][CHARGING] ✅ Fully charged! Resuming driving.")

            # Notify CS that charging is complete
            msg = Message(to=agent.cs_jid)
            msg.set_metadata("protocol", "ev-charging")
            msg.set_metadata("performative", "inform")
            msg.body = json.dumps({"status": "charge-complete"})
            await self.send(msg)

            self.set_next_state(STATE_DRIVING)
        else:
            self.set_next_state(STATE_CHARGING)


# ──────────────────────────────────────────────
#  DRIVING State
# ──────────────────────────────────────────────
class DrivingState(State):
    async def run(self):
        agent = self.agent
        name = str(agent.jid).split("@")[0]

        tick_hours = 0.25
        drain_kw = 7.5
        energy_used = drain_kw * tick_hours
        soc_drop = energy_used / agent.battery_capacity_kwh

        agent.current_soc = max(0.0, agent.current_soc - soc_drop)

        print(
            f"[{name}][DRIVING] 🚗 SoC: {agent.current_soc:.0%} "
            f"(-{energy_used:.1f} kWh)"
        )

        await asyncio.sleep(2)

        if agent.current_soc <= agent.required_soc:
            print(
                f"[{name}][DRIVING] ⚠ SoC below {agent.required_soc:.0%}, heading to charger..."
            )
            self.set_next_state(STATE_GOING_TO_CHARGER)
        else:
            self.set_next_state(STATE_DRIVING)


# ──────────────────────────────────────────────
#  EV Agent
# ──────────────────────────────────────────────
class EVAgent(Agent):
    def __init__(self, jid, password, ev_config=None, *args, **kwargs):
        super().__init__(jid, password, *args, **kwargs)

        config = ev_config or {}

        # Battery
        self.battery_capacity_kwh = config.get("battery_capacity_kwh", 60.0)
        self.current_soc = config.get("current_soc", 0.20)
        self.required_soc = config.get("required_soc", 0.80)

        # Schedule
        self.departure_time = config.get("departure_time", "08:00")
        self.arrival_time = config.get("arrival_time", "22:00")

        # Charging
        self.max_charge_rate_kw = config.get("max_charge_rate_kw", 22.0)
        self.current_charge_rate_kw = 0.0

        # CS Agent to contact
        self.cs_jid = config.get("cs_jid", "cs1@localhost")

        # Environment (updated via messages from other agents)
        self.electricity_price = config.get("electricity_price", 0.15)
        self.grid_load = config.get("grid_load", 0.5)
        self.renewable_available = config.get("renewable_available", False)

    async def setup(self):
        print(f"[EV Agent] {self.jid} starting...")
        print(
            f"[EV Agent] Battery: {self.battery_capacity_kwh} kWh | "
            f"Current SoC: {self.current_soc:.0%} | "
            f"Max charge rate: {self.max_charge_rate_kw} kW"
        )

        # Build the FSM
        fsm = EVChargingFSM()

        # Register states
        fsm.add_state(name=STATE_DRIVING, state=DrivingState(), initial=True)
        fsm.add_state(name=STATE_GOING_TO_CHARGER, state=GoingToChargerState())
        fsm.add_state(name=STATE_CHARGING, state=ChargingState())

        # Register transitions
        fsm.add_transition(source=STATE_DRIVING, dest=STATE_DRIVING)
        fsm.add_transition(source=STATE_DRIVING, dest=STATE_GOING_TO_CHARGER)
        fsm.add_transition(source=STATE_GOING_TO_CHARGER, dest=STATE_CHARGING)
        fsm.add_transition(source=STATE_GOING_TO_CHARGER, dest=STATE_GOING_TO_CHARGER)
        fsm.add_transition(source=STATE_CHARGING, dest=STATE_CHARGING)
        fsm.add_transition(source=STATE_CHARGING, dest=STATE_DRIVING)

        template = Template()
        template.set_metadata("protocol", "ev-charging")

        self.add_behaviour(fsm, template)


# ──────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────
async def main():
    ev = EVAgent(
        "ev1@localhost",
        "password",
        ev_config={
            "battery_capacity_kwh": 60.0,
            "x": 0,
            "y": 0,
            "current_soc": 1.0,
            "required_soc": 0.80,
            "departure_time": "08:00",
            "max_charge_rate_kw": 22.0,
            "cs_jid": "cs1@localhost",
            "electricity_price": 0.15,
            "grid_load": 0.5,
            "renewable_available": False,
        },
    )
    await ev.start()
    ev.web.start(hostname="127.0.0.1", port=10000)

    print("\nWeb interface: http://127.0.0.1:10000")
    print("Press Ctrl+C to stop.\n")

    while True:
        try:
            await asyncio.sleep(1)
        except KeyboardInterrupt:
            break

    await ev.stop()


if __name__ == "__main__":
    spade.run(main())
