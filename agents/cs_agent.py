import asyncio
import json

import spade
from spade.agent import Agent
from spade.behaviour import FSMBehaviour, State
from spade.message import Message

# ──────────────────────────────────────────────
#  FSM States
# ──────────────────────────────────────────────
STATE_AVAILABLE = "AVAILABLE"  # can charge immediately
STATE_FULL = "FULL"  # queue if no doors, wait for inform when done


# ──────────────────────────────────────────────
#  FSM Behaviour
# ──────────────────────────────────────────────
class CSChargingFSM(FSMBehaviour):
    async def on_start(self):
        print(f"[FSM] Starting at state: {self.current_state}")

    async def on_end(self):
        print(f"[FSM] Finished at state: {self.current_state}")


# ──────────────────────────────────────────────
#  Helper mixin
# ──────────────────────────────────────────────
class CSStateMixin:
    """Shared logic for CS FSM states."""

    async def _dispatch(self, msg):
        """Calls _on_<performative>(msg) if the method exists on the state."""
        if msg is None:
            return
        handler = getattr(self, f"_on_{msg.get_metadata('performative')}", None)
        if handler:
            await handler(msg)

    def _next_state(self):
        """Each state overrides this to declare its own transition logic."""
        raise NotImplementedError

    # ── Shared message handlers ────────────────

    async def _send_response(self, to_jid, status):
        msg = Message(to=str(to_jid))
        msg.set_metadata("protocol", "ev-charging")
        msg.set_metadata("performative", "response")
        msg.body = json.dumps({"status": status})
        await self.send(msg)
        print(f"[CS] → {to_jid}: {status}")

    def _parse_request(self, msg):
        try:
            data = json.loads(msg.body)
            return {
                "ev_jid": str(msg.sender).split("/")[0],
                "required_energy": float(data.get("required_energy", 0)),
                "max_charging_rate": float(
                    data.get("max_charging_rate", self.agent.max_charging_rate)
                ),
            }
        except (json.JSONDecodeError, ValueError, AttributeError):
            return None

    # ── Request outcome helpers ────────────────

    def _can_accept(self, agent, parsed):
        return (
            agent.used_doors < agent.num_doors
            and parsed["required_energy"] <= agent.capacity
        )

    async def _accept_ev(self, agent, parsed):
        ev_jid = parsed["ev_jid"]
        agent.used_doors += 1
        agent.capacity -= parsed["required_energy"]
        agent.active_charging[ev_jid] = {
            "required_energy": parsed["required_energy"],
            "rate": parsed["max_charging_rate"],
        }
        await self._send_response(ev_jid, "accept")
        print(
            f"[CS] ✓ Accepted {ev_jid}: {parsed['required_energy']:.1f} kWh @ {parsed['max_charging_rate']} kW | Doors: {agent.used_doors}/{agent.num_doors}"
        )

    async def _queue_ev(self, agent, parsed):
        agent.request_queue.append(parsed)
        await self._send_response(parsed["ev_jid"], "wait")
        print(
            f"[CS] ⏳ Queued {parsed['ev_jid']} | Queue size: {len(agent.request_queue)}"
        )

    # ── Performative handlers ──────────────────

    async def _on_request(self, msg):
        parsed = self._parse_request(msg)
        if not parsed:
            return
        agent = self.agent
        if self._can_accept(agent, parsed):
            await self._accept_ev(agent, parsed)
        else:
            await self._queue_ev(agent, parsed)

    async def _on_inform(self, msg):
        agent = self.agent
        ev_jid = str(msg.sender).split("/")[0]
        try:
            status = json.loads(msg.body).get("status")
        except (json.JSONDecodeError, AttributeError):
            return
        if status == "charge-complete" and ev_jid in agent.active_charging:
            session = agent.active_charging.pop(ev_jid)
            agent.used_doors = max(0, agent.used_doors - 1)
            agent.capacity += session["required_energy"]
            print(
                f"[CS] 🔓 {ev_jid} done | Doors free: {agent.num_doors - agent.used_doors}/{agent.num_doors}"
            )

    async def _process_queue(self):
        agent = self.agent
        processed = []
        for i, req in enumerate(agent.request_queue):
            if agent.used_doors >= agent.num_doors:
                break
            if req["required_energy"] <= agent.capacity:
                agent.used_doors += 1
                agent.capacity -= req["required_energy"]
                agent.active_charging[req["ev_jid"]] = {
                    "required_energy": req["required_energy"],
                    "rate": req["max_charging_rate"],
                }
                await self._send_response(req["ev_jid"], "accept")
                print(
                    f"[CS] ✓ Accepted (queue) {req['ev_jid']}: {req['required_energy']:.1f} kWh | Doors: {agent.used_doors}/{agent.num_doors}"
                )
                processed.append(i)
        for idx in reversed(processed):
            agent.request_queue.pop(idx)


# ──────────────────────────────────────────────
#  AVAILABLE State
# ──────────────────────────────────────────────
class AvailableState(CSStateMixin, State):

    def _next_state(self):
        if self.agent.used_doors >= self.agent.num_doors:
            return STATE_FULL
        return STATE_AVAILABLE

    async def run(self):
        await self._dispatch(await self.receive(timeout=5))
        self.set_next_state(self._next_state())


# ──────────────────────────────────────────────
#  FULL State
# ──────────────────────────────────────────────
class FullState(CSStateMixin, State):

    def _next_state(self):
        if self.agent.used_doors < self.agent.num_doors:
            return STATE_AVAILABLE
        return STATE_FULL

    async def run(self):
        await self._dispatch(await self.receive(timeout=1))
        await self._process_queue()
        self.set_next_state(self._next_state())


# ──────────────────────────────────────────────
#  Charging Station Agent
# ──────────────────────────────────────────────
class CSAgent(Agent):
    def __init__(self, jid, password, cs_config=None, *args, **kwargs):
        super().__init__(jid, password, *args, **kwargs)

        config = cs_config or {}

        self.max_charging_rate = config.get("max_charging_rate", 22.0)  # kW
        self.num_doors = config.get("num_doors", 4)
        self.capacity = config.get("capacity", 150.0)  # kWh disponíveis na rede
        self.used_doors = 0
        self.request_queue = []
        self.active_charging = {}

        # Position
        self.x = config.get("x", 0.0)
        self.y = config.get("y", 0.0)

    async def setup(self):
        print(f"[CS Agent] {self.jid} starting...")
        print(
            f"[CS Agent] Doors: {self.num_doors} | "
            f"Max charging rate: {self.max_charging_rate} kW | "
            f"Capacity: {self.capacity} kWh | "
            f"Position: ({self.x}, {self.y})"
        )

        fsm = CSChargingFSM()
        fsm.add_state(name=STATE_AVAILABLE, state=AvailableState(), initial=True)
        fsm.add_state(name=STATE_FULL, state=FullState())
        fsm.add_transition(source=STATE_AVAILABLE, dest=STATE_AVAILABLE)
        fsm.add_transition(source=STATE_AVAILABLE, dest=STATE_FULL)
        fsm.add_transition(source=STATE_FULL, dest=STATE_FULL)
        fsm.add_transition(source=STATE_FULL, dest=STATE_AVAILABLE)

        self.add_behaviour(fsm)


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
