import json

from spade.behaviour import FSMBehaviour, State
from spade.message import Message

from .utils import (
    add_incoming_request,
    apply_confirmed_proposal,
    calculate_wait_time_minutes,
    charging_time_minutes,
    remove_incoming_request,
    retrieve_and_remove_proposal,
    store_pending_proposal,
)

STATE_AVAILABLE = "AVAILABLE"
STATE_FULL = "FULL"


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
    agent = state.agent
    world_jid = getattr(agent, "world_jid", None)
    current_load = agent.used_doors * agent.max_charging_rate
    await _send_stat(
        state,
        world_jid,
        {
            "event": "load_update",
            "current_load": current_load,
        },
    )


# ══════════════════════════════════════════════════════════════════════
#  FSM
# ══════════════════════════════════════════════════════════════════════


class CSChargingFSM(FSMBehaviour):
    async def on_start(self):
        print(f"[FSM] Starting at state: {self.current_state}")

    async def on_end(self):
        print(f"[FSM] Finished at state: {self.current_state}")

    async def on_receive(self, msg):
        """Process incoming messages by dispatching to current state."""
        if self.current_state:
            state = self._states[self.current_state]
            if hasattr(state, "_dispatch"):
                await state._dispatch(msg)


class CSStateMixin:
    """Shared logic for CS FSM states."""

    def _estimate_wait_minutes(self, agent, incoming_request):
        return calculate_wait_time_minutes(
            active_charging=agent.active_charging,
            request_queue=agent.request_queue.snapshot(),
            num_doors=agent.num_doors,
            cs_max_charging_rate=agent.max_charging_rate,
        )

    async def _dispatch(self, msg):
        if msg is None:
            return
        performative = msg.get_metadata("performative")
        handler = getattr(self, f"_on_{performative}", None)
        if handler:
            await handler(msg)

    def _next_state(self):
        raise NotImplementedError

    async def _on_request(self, msg):
        agent = self.agent
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

        # Special handling: EV previously committed to this CS (pre-reserved spot)
        if ev_jid in agent.expected_evs:
            agent.expected_evs.remove(ev_jid)
            agent.reserved_doors = max(0, agent.reserved_doors - 1)
            # Accept immediately; door already counted, just increment used_doors
            agent.used_doors += 1
            required = parsed.get("required_energy", 0.0)
            if agent.actual_solar_capacity >= required:
                agent.actual_solar_capacity -= required
            # Calculate price with solar discount
            discount = agent.solar_discount()
            final_price = required * agent.energy_price * (1 - discount)
            agent.active_charging[ev_jid] = {
                "required_energy": required,
                "rate": parsed.get("max_charging_rate", agent.max_charging_rate),
                "price": final_price,
            }
            await agent.messaging_service.send_response(
                self,
                ev_jid,
                "accept",
                extra={
                    "price": final_price,
                    "solar_discount": discount,
                    "energy_price": agent.energy_price,
                }
            )
            print(
                f"[CS] {ev_jid} CONFIRMED (pre-reserved) | Doors: {agent.used_doors}/{agent.num_doors}"
            )
            await _report_load(self)
            return

        # Normal flow: determine accept or wait
        if agent.can_accept_request(parsed):
            decision = "accept"
        else:
            decision = "wait"
            # Add to incoming requests for tracking
            arriving_hours = parsed.get("arriving_hours")
            if arriving_hours is not None:
                add_incoming_request(
                    agent.incoming_requests,
                    ev_jid,
                    arriving_hours,
                    parsed.get("required_energy", 0.0),
                    parsed.get("max_charging_rate", agent.max_charging_rate),
                )

        # Store proposal as pending (waiting for EV confirmation)
        store_pending_proposal(agent.pending_proposals, ev_jid, parsed, decision)

        # Send proposal (with extra info)
        extra = {"price": agent.energy_price}
        if decision == "wait":
            estimated_wait_minutes = calculate_wait_time_minutes(
                agent.active_charging,
                agent.request_queue.snapshot(),
                agent.num_doors,
                agent.max_charging_rate,
            )
            extra["estimated_wait_minutes"] = round(estimated_wait_minutes, 2)

        await agent.messaging_service.send_response(
            self,
            ev_jid,
            decision,
            extra=extra,
        )
        print(
            f"[CS] Proposed {decision.upper()} to {ev_jid} | Pending: {len(agent.pending_proposals)}"
        )

    async def _on_query(self, msg):
        """Handle CS info request from EV.
        EV asks for current station status (used_doors, num_doors, electricity_price, x, y).
        """
        agent = self.agent
        try:
            data = json.loads(msg.body) if msg.body else {}
        except (json.JSONDecodeError, TypeError):
            return

        if data.get("type") != "cs_info_request":
            return

        ev_jid = str(msg.sender).split("/")[0] if msg.sender else "unknown"

        response = {
            "type": "cs_info_response",
            "jid": str(agent.jid).split("/")[0],
            "used_doors": agent.used_doors,
            "num_doors": agent.num_doors,
            "electricity_price": agent.electricity_price,
            "x": agent.x,
            "y": agent.y,
        }

        reply = Message(to=str(msg.sender))
        reply.set_metadata("protocol", agent.messaging_service.EV_PROTOCOL)
        reply.set_metadata("performative", "inform")
        reply.body = json.dumps(response)
        await self.send(reply)
        print(f"[CS] Sent info to {ev_jid}: {agent.used_doors}/{agent.num_doors} doors, {agent.electricity_price:.3f} €/kWh")

    async def _on_commit(self, msg):
        """Handle EV commitment to visit this CS.
        The EV reserves a spot before traveling; we track it in expected_evs.
        Sends a response indicating acceptance or rejection.
        """
        agent = self.agent
        try:
            data = json.loads(msg.body) if msg.body else {}
        except (json.JSONDecodeError, TypeError):
            return

        if data.get("type") != "ev_commit":
            return

        ev_jid = data.get("ev_jid")
        if not ev_jid:
            return

        # Already expected? ignore (idempotent) and re-confirm
        if ev_jid in agent.expected_evs:
            print(f"[CS] {ev_jid} already committed")
            await agent.messaging_service.send_response(self, ev_jid, "commit_accepted")
            return

        # Reserve a door (count against capacity)
        if (agent.used_doors + agent.reserved_doors) < agent.num_doors:
            agent.expected_evs.add(ev_jid)
            agent.reserved_doors += 1
            print(f"[CS] {ev_jid} committed (reserved {agent.reserved_doors}/{agent.num_doors} doors)")
            await agent.messaging_service.send_response(self, ev_jid, "commit_accepted")
        else:
            # Station is fully reserved; cannot accept commitment
            print(f"[CS] {ev_jid} commit REJECTED — no available doors")
            await agent.messaging_service.send_response(self, ev_jid, "commit_rejected", extra={"reason": "no_available_doors"})

    async def _on_cancel(self, msg):
        """Handle EV cancellation of a prior commitment."""
        agent = self.agent
        try:
            data = json.loads(msg.body) if msg.body else {}
        except (json.JSONDecodeError, TypeError):
            return

        if data.get("type") != "ev_cancel":
            return

        ev_jid = data.get("ev_jid")
        if not ev_jid:
            return

        if ev_jid in agent.expected_evs:
            agent.expected_evs.remove(ev_jid)
            agent.reserved_doors = max(0, agent.reserved_doors - 1)
            print(f"[CS] {ev_jid} canceled commitment (reserved now {agent.reserved_doors}/{agent.num_doors} doors)")
        else:
            print(f"[CS] {ev_jid} cancel but no commitment found")

    async def _on_inform(self, msg):
        agent = self.agent
        protocol = (msg.get_metadata("protocol") or "").strip()

        # Ignore unrelated protocols explicitly.
        if protocol and protocol not in {
            agent.messaging_service.WORLD_PROTOCOL,
            agent.messaging_service.EV_PROTOCOL,
        }:
            return

        # Prefer explicit world protocol for world-originated updates.
        if protocol == agent.messaging_service.WORLD_PROTOCOL:
            world_update = agent.messaging_service.parse_world_update(msg)
            if not world_update:
                return

            if "energy_price" in world_update:
                agent.energy_price = max(0.0, world_update["energy_price"])
                print(f"[CS] World update: energy_price={agent.energy_price:.4f} €/kWh")

            if "solar_production_rate" in world_update:
                agent.solar_production_rate = max(
                    0.0, world_update["solar_production_rate"]
                )
                print(
                    "[CS] World update: "
                    f"solar_production_rate={agent.solar_production_rate:.2f} kW"
                )
            return

        # Check for proposal confirmation from EV
        proposal_confirm = agent.messaging_service.parse_proposal_confirm(msg)
        if proposal_confirm:
            ev_jid, accepted = proposal_confirm
            if accepted:
                await self._handle_proposal_confirmed(ev_jid)
            else:
                await self._handle_proposal_rejected(ev_jid)
            return

        # Otherwise, handle charge-complete inform
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
                # ── immediately try to serve queued EVs ──
                await self._process_queue()

    async def _handle_proposal_confirmed(self, ev_jid: str):
        """Handle EV confirmation of proposal."""
        agent = self.agent

        proposal = retrieve_and_remove_proposal(agent.pending_proposals, ev_jid)
        if not proposal:
            print(f"[CS] Proposal confirm from {ev_jid} but no pending proposal found")
            return

        decision = proposal.get("decision")
        request_data = proposal.get("request", {})

        if decision == "accept":
            # Register for immediate charging
            agent.used_doors += 1
            agent.active_charging[ev_jid] = {
                "required_energy": request_data.get("required_energy", 0.0),
                "rate": request_data.get("max_charging_rate", agent.max_charging_rate),
                "price": agent.energy_price,
            }
            remove_incoming_request(agent.incoming_requests, ev_jid)
            print(
                f"[CS] {ev_jid} CONFIRMED ACCEPT | Active: {len(agent.active_charging)} | Doors used: {agent.used_doors}/{agent.num_doors}"
            )
            await _report_load(self)

        elif decision == "wait":
            # Register in queue
            agent.request_queue.enqueue(request_data)
            print(
                f"[CS] {ev_jid} CONFIRMED WAIT | Queue size: {len(agent.request_queue)} | Incoming: {len(agent.incoming_requests)}"
            )

    async def _handle_proposal_rejected(self, ev_jid: str):
        """Handle EV rejection of proposal."""
        agent = self.agent

        proposal = retrieve_and_remove_proposal(agent.pending_proposals, ev_jid)
        if not proposal:
            print(f"[CS] Proposal reject from {ev_jid} but no pending proposal found")
            return

        remove_incoming_request(agent.incoming_requests, ev_jid)
        print(f"[CS] {ev_jid} REJECTED proposal")

    async def _process_queue(self):
        agent = self.agent
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
        self.agent.update_solar_energy()
        await self._dispatch(await self.receive(timeout=5))
        await self._process_queue()
        self.set_next_state(self._next_state())


class FullState(CSStateMixin, State):
    def _next_state(self):
        if self.agent.used_doors < self.agent.num_doors:
            return STATE_AVAILABLE
        return STATE_FULL

    async def run(self):
        self.agent.update_solar_energy()
        await self._dispatch(await self.receive(timeout=1))
        await self._process_queue()
        self.set_next_state(self._next_state())
