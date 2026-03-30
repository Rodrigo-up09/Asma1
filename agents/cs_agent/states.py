import json

from spade.behaviour import FSMBehaviour, State
from spade.message import Message

from .utils import charging_time_minutes

STATE_AVAILABLE = "AVAILABLE"
STATE_FULL      = "FULL"


# ── Metrics helper ─────────────────────────────
async def _send_stat(state, world_jid: str, payload: dict) -> None:
    """Fire-and-forget a world-stats message to the WorldAgent."""
    if not world_jid:
        return
    msg = Message(to=world_jid)
    msg.set_metadata("protocol", "world-stats")
    msg.set_metadata("performative", "inform")
    msg.body = json.dumps(payload)
    await state.send(msg)


async def _report_load(state) -> None:
    """Send current load kW to the WorldAgent after any door change."""
    agent       = state.agent
    world_jid   = getattr(agent, "world_jid", None)
    current_load = agent.used_doors * agent.max_charging_rate
    await _send_stat(state, world_jid, {
        "event":        "load_update",
        "current_load": current_load,
    })


# ══════════════════════════════════════════════════════════════════════
#  FSM
# ══════════════════════════════════════════════════════════════════════

class CSChargingFSM(FSMBehaviour):
    async def on_start(self):
        print(f"[FSM] Starting at state: {self.current_state}")

    async def on_end(self):
        print(f"[FSM] Finished at state: {self.current_state}")


# ══════════════════════════════════════════════════════════════════════
#  Shared mixin
# ══════════════════════════════════════════════════════════════════════

class CSStateMixin:
    """Shared logic for CS FSM states."""

    def _estimate_wait_minutes(self, agent, incoming_request):
        doors             = max(1, int(agent.num_doors))
        door_available_at = [0.0] * doors

        for session in agent.active_charging.values():
            duration = charging_time_minutes(
                session.get("required_energy", 0.0),
                session.get("rate", agent.max_charging_rate),
                agent.max_charging_rate,
            )
            next_door = min(range(doors), key=lambda idx: door_available_at[idx])
            door_available_at[next_door] += duration

        for request in agent.request_queue.snapshot():
            duration = charging_time_minutes(
                request.get("required_energy", 0.0),
                request.get("max_charging_rate", agent.max_charging_rate),
                agent.max_charging_rate,
            )
            next_door = min(range(doors), key=lambda idx: door_available_at[idx])
            door_available_at[next_door] += duration

        return min(door_available_at)

    async def _dispatch(self, msg):
        if msg is None:
            return
        performative = msg.get_metadata("performative")
        handler      = getattr(self, f"_on_{performative}", None)
        if handler:
            await handler(msg)

    def _next_state(self):
        raise NotImplementedError

    async def _on_request(self, msg):
        agent  = self.agent
        parsed = agent.messaging_service.parse_request(msg, agent.max_charging_rate)

        if not parsed:
            return

        ev_jid = parsed["ev_jid"]

        if agent.request_queue.contains_ev(ev_jid):
            raise ValueError(f"Duplicate queue entry for EV '{ev_jid}'")

        if ev_jid in agent.active_charging:
            await agent.messaging_service.send_response(self, ev_jid, "accept")
            print(f"[CS] Ignored duplicate request from {ev_jid} (already charging)")
            return

        if agent.can_accept_request(parsed):
            await agent.accept_request(parsed, self, from_queue=False)
            # ── metric: door opened ──
            await _report_load(self)
        else:
            estimated_wait_minutes = self._estimate_wait_minutes(agent, parsed)
            agent.request_queue.enqueue(parsed)
            await agent.messaging_service.send_response(
                self,
                ev_jid,
                "wait",
                extra={"estimated_wait_minutes": round(estimated_wait_minutes, 2)},
            )
            print(f"[CS] Queued {ev_jid} | Queue size: {len(agent.request_queue)}")

    async def _on_inform(self, msg):
        agent  = self.agent
        parsed = agent.messaging_service.parse_inform_status(msg)

        if not parsed:
            return

        ev_jid, status = parsed
        if status == "charge-complete":
            finished = agent.complete_session(ev_jid)
            if finished:
                print(
                    f"[CS] {ev_jid} done | Doors free: "
                    f"{agent.num_doors - agent.used_doors}/{agent.num_doors}"
                )
                # ── metric: door freed ──
                await _report_load(self)

    async def _process_queue(self):
        agent        = self.agent
        doors_before = agent.used_doors
        await agent.request_queue.dispatch_eligible(
            has_free_door=lambda: agent.used_doors < agent.num_doors,
            can_accept_request=agent.can_accept_request,
            accept_request=lambda req: agent.accept_request(req, self, from_queue=True),
        )
        # ── metric: report load if any queued EVs were accepted ──
        if agent.used_doors != doors_before:
            await _report_load(self)


# ══════════════════════════════════════════════════════════════════════
#  States
# ══════════════════════════════════════════════════════════════════════

class AvailableState(CSStateMixin, State):
    def _next_state(self):
        if self.agent.used_doors >= self.agent.num_doors:
            return STATE_FULL
        return STATE_AVAILABLE

    async def run(self):
        await self._dispatch(await self.receive(timeout=5))
        self.set_next_state(self._next_state())


class FullState(CSStateMixin, State):
    def _next_state(self):
        if self.agent.used_doors < self.agent.num_doors:
            return STATE_AVAILABLE
        return STATE_FULL

    async def run(self):
        await self._dispatch(await self.receive(timeout=1))
        await self._process_queue()
        self.set_next_state(self._next_state())