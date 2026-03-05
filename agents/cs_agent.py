import asyncio

import spade
from spade.agent import Agent
from spade.behaviour import FSMBehaviour, State

# ──────────────────────────────────────────────
#  FSM States
# ──────────────────────────────────────────────
STATE_EMPTY = "EMPTY"
STATE_WORKING = "WORKING"


# ──────────────────────────────────────────────
#  FSM Behaviour (lifecycle hooks)
# ──────────────────────────────────────────────
class CSChargingFSM(FSMBehaviour):
    async def on_start(self):
        print(f"[FSM] Starting at state: {self.current_state}")

    async def on_end(self):
        print(f"[FSM] Finished at state: {self.current_state}")


# ──────────────────────────────────────────────
#  EMPTY State
# ──────────────────────────────────────────────
class EmptyState(State):
    async def run(self):
        pass


# ──────────────────────────────────────────────
#  WORKING State
# ──────────────────────────────────────────────
class WorkingState(State):
    async def run(self):
        pass


# ──────────────────────────────────────────────
#  Charging Station Agent
# ──────────────────────────────────────────────
class CSAgent(Agent):
    def __init__(self, jid, password, cs_config=None, *args, **kwargs):
        super().__init__(jid, password, *args, **kwargs)

        config = cs_config or {}

        # Station capacity
        self.num_charging_points = config.get("num_charging_points", 4)
        self.max_power_kw = config.get("max_power_kw", 150.0)

        # Current usage
        self.active_sessions = 0
        self.current_load_kw = 0.0

    async def setup(self):
        print(f"[CS Agent] {self.jid} starting...")
        print(
            f"[CS Agent] Charging points: {self.num_charging_points} | "
            f"Max power: {self.max_power_kw} kW"
        )

        # Build the FSM
        fsm = CSChargingFSM()

        # Register states
        fsm.add_state(name=STATE_EMPTY, state=EmptyState(), initial=True)
        fsm.add_state(name=STATE_WORKING, state=WorkingState())

        # Register transitions
        fsm.add_transition(source=STATE_EMPTY, dest=STATE_EMPTY)
        fsm.add_transition(source=STATE_EMPTY, dest=STATE_WORKING)
        fsm.add_transition(source=STATE_WORKING, dest=STATE_WORKING)
        fsm.add_transition(source=STATE_WORKING, dest=STATE_EMPTY)

        self.add_behaviour(fsm)


# ──────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────
async def main():
    cs = CSAgent(
        "cs1@localhost",
        "password",
        cs_config={
            "num_charging_points": 4,
            "max_power_kw": 150.0,
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
