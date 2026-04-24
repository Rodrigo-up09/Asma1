import json
from typing import Any

from spade.behaviour import FSMBehaviour, State
from spade.message import Message

from .models import ChargingRequest
from .utils import (
    add_incoming_request,
    calculate_wait_time_minutes,
    cleanup_expired_pending_proposals,
    count_pending_slot_reservations,
    remove_incoming_request,
    retrieve_and_remove_proposal,
    store_pending_proposal,
)

STATE_AVAILABLE = "AVAILABLE"
STATE_FULL = "FULL"


async def _send_stat(state: State, world_jid: str, payload: dict[str, Any]) -> None:
    if not world_jid:
        return
    msg = Message(to=world_jid)
    msg.set_metadata("protocol", "world-stats")
    msg.set_metadata("performative", "inform")
    msg.body = json.dumps(payload)
    await state.send(msg)


async def _report_load(state: State) -> None:
    agent = state.agent
    world_jid = getattr(agent, "world_jid", None)
    queued_evs = {
        item.get("ev_jid")
        for item in agent.request_queue.snapshot()
        if item.get("ev_jid")
    }
    current_load = len(set(agent.active_charging.keys()) | queued_evs)
    await _send_stat(
        state,
        world_jid,
        {
            "event": "load_update",
            "current_load": current_load,
        },
    )


class CSChargingFSM(FSMBehaviour):
    async def on_start(self) -> None:
        print(f"[FSM] Starting at state: {self.current_state}")

    async def on_end(self) -> None:
        print(f"[FSM] Finished at state: {self.current_state}")

    async def on_receive(self, msg: Message) -> None:
        if self.current_state:
            state = self._states[self.current_state]
            if hasattr(state, "_dispatch"):
                await state._dispatch(msg)


class CSStateMixin:
    def _cleanup_expired_pending(self, agent) -> int:
        expired_ev_jids = cleanup_expired_pending_proposals(
            agent.pending_proposals)
        for ev_jid in expired_ev_jids:
            remove_incoming_request(agent.incoming_requests, ev_jid)
        return len(expired_ev_jids)

    def _can_offer_accept(self, agent, request: ChargingRequest) -> bool:
        if request.get("ev_jid") in agent.active_charging:
            return False
        reserved_slots = count_pending_slot_reservations(
            agent.pending_proposals)
        return (agent.used_doors + reserved_slots) < agent.num_doors

    def _estimate_wait_minutes(
        self,
        agent,
        target_ev_jid: str | None = None,
        assumed_request: ChargingRequest | None = None,
    ) -> float:
        return calculate_wait_time_minutes(
            active_charging=agent.active_charging,
            request_queue=agent.request_queue.snapshot(),
            num_doors=agent.num_doors,
            cs_max_charging_rate=agent.max_charging_rate,
            pending_proposals=agent.pending_proposals,
            target_ev_jid=target_ev_jid,
            assumed_request=assumed_request,
        )

    def _parse_json_body(self, msg: Message) -> dict[str, Any] | None:
        try:
            return json.loads(msg.body) if msg.body else {}
        except (json.JSONDecodeError, TypeError):
            return None

    async def _dispatch(self, msg: Message | None) -> None:
        if msg is None:
            return
        performative = msg.get_metadata("performative")
        handler = getattr(self, f"_on_{performative}", None)
        if handler:
            await handler(msg)

    def _next_state(self) -> str:
        raise NotImplementedError

    async def _on_request(self, msg: Message) -> None:
        agent = self.agent
        self._cleanup_expired_pending(agent)

        parsed = agent.messaging_service.parse_request(
            msg, agent.max_charging_rate)
        if not parsed:
            return

        ev_jid = parsed["ev_jid"]

        if agent.request_queue.contains_ev(ev_jid):
            raise ValueError(f"Duplicate queue entry for EV '{ev_jid}'")

        if ev_jid in agent.active_charging:
            await agent.messaging_service.send_response(self, ev_jid, "accept")
            print(
                f"[CS] Ignored duplicate request from {ev_jid} (already charging)")
            return

        if agent.consume_expected_arrival(ev_jid):
            print(
                f"[CS] {ev_jid} arrived after commitment (expected now {len(agent.expected_evs)})")

        decision = "accept" if self._can_offer_accept(
            agent, parsed) else "wait"
        self._register_incoming_request_if_needed(agent, parsed, decision)
        self._store_pending(agent, ev_jid, parsed, decision)

        await self._send_proposal(agent, ev_jid, decision)
        await agent.notify_interested_evs(self, f"proposal_{decision}", exclude_ev_jid=ev_jid)

    def _register_incoming_request_if_needed(self, agent, parsed: ChargingRequest, decision: str) -> None:
        if decision != "wait":
            return
        arriving_hours = parsed.get("arriving_hours")
        if arriving_hours is None:
            return
        add_incoming_request(
            agent.incoming_requests,
            parsed["ev_jid"],
            arriving_hours,
            parsed.get("required_energy", 0.0),
            parsed.get("max_charging_rate", agent.max_charging_rate),
        )

    def _store_pending(self, agent, ev_jid: str, parsed: ChargingRequest, decision: str) -> None:
        store_pending_proposal(agent.pending_proposals,
                               ev_jid, parsed, decision)

    async def _send_proposal(self, agent, ev_jid: str, decision: str) -> None:
        extra: dict[str, Any] = {"price": agent.energy_price}
        if decision == "wait":
            pending = agent.pending_proposals.get(ev_jid) or {}
            assumed_request = pending.get("request") if pending else None
            extra["estimated_wait_minutes"] = round(
                self._estimate_wait_minutes(
                    agent,
                    target_ev_jid=ev_jid,
                    assumed_request=assumed_request,
                ),
                2,
            )

        await agent.messaging_service.send_response(self, ev_jid, decision, extra=extra)
        print(
            f"[CS] Proposed {decision.upper()} to {ev_jid} | Pending: {len(agent.pending_proposals)}")

    async def _on_query(self, msg: Message) -> None:
        agent = self.agent
        data = self._parse_json_body(msg)
        if data is None or data.get("type") != "cs_info_request":
            return

        ev_jid = str(msg.sender).split("/")[0] if msg.sender else "unknown"
        agent.interested_evs.add(ev_jid)

        response = agent.build_station_snapshot()
        response["type"] = "cs_info_response"
        estimate_for_ev = ev_jid if agent.request_queue.contains_ev(ev_jid) else None
        response["estimated_wait_minutes"] = round(
            self._estimate_wait_minutes(agent, target_ev_jid=estimate_for_ev), 2)

        await agent.messaging_service.send_info_response(self, str(msg.sender), response)
        print(
            f"[CS] Sent info to {ev_jid}: "
            f"{agent.used_doors}/{agent.num_doors} doors, {agent.electricity_price:.3f} EUR/kWh"
        )

    async def _on_commit(self, msg: Message) -> None:
        agent = self.agent
        data = self._parse_json_body(msg)
        if data is None or data.get("type") != "ev_commit":
            return

        ev_jid = data.get("ev_jid")
        if not ev_jid:
            return

        if not agent.register_expected_arrival(ev_jid):
            print(f"[CS] {ev_jid} already committed")
            await agent.messaging_service.send_response(self, ev_jid, "commit_accepted")
            return

        print(
            f"[CS] {ev_jid} committed (expected now {len(agent.expected_evs)})")
        await agent.messaging_service.send_response(self, ev_jid, "commit_accepted")
        await agent.notify_interested_evs(self, "commit_accepted", exclude_ev_jid=ev_jid)

    async def _on_cancel(self, msg: Message) -> None:
        agent = self.agent
        data = self._parse_json_body(msg)
        if data is None or data.get("type") != "ev_cancel":
            return

        ev_jid = data.get("ev_jid")
        if not ev_jid:
            return

        removed = agent.clear_tracking_for_ev(ev_jid)
        if any(removed.values()):
            print(
                f"[CS] {ev_jid} cancel cleared "
                f"expected={removed['expected']}, pending={removed['pending']}, "
                f"incoming={removed['incoming']}, queue={removed['queue']}"
            )
            await agent.notify_interested_evs(self, "cancel", exclude_ev_jid=ev_jid)
        else:
            print(f"[CS] {ev_jid} cancel but no tracked data found")

    async def _on_inform(self, msg: Message) -> None:
        agent = self.agent
        protocol = (msg.get_metadata("protocol") or "").strip()

        if protocol and protocol not in {
            agent.messaging_service.WORLD_PROTOCOL,
            agent.messaging_service.EV_PROTOCOL,
        }:
            return

        if protocol == agent.messaging_service.WORLD_PROTOCOL:
            await self._apply_world_update(msg)
            return

        proposal_confirm = agent.messaging_service.parse_proposal_confirm(msg)
        if proposal_confirm:
            ev_jid, accepted = proposal_confirm
            if accepted:
                await self._handle_proposal_confirmed(ev_jid)
            else:
                await self._handle_proposal_rejected(ev_jid)
            return

        await self._handle_charge_complete(msg)

    async def _apply_world_update(self, msg: Message) -> None:
        agent = self.agent
        world_update = agent.messaging_service.parse_world_update(msg)
        if not world_update:
            return

        if "energy_price" in world_update:
            agent.energy_price = max(0.0, world_update["energy_price"])
            print(
                f"[CS] World update: energy_price={agent.energy_price:.4f} EUR/kWh")

        if "solar_production_rate" in world_update:
            agent.solar_production_rate = max(
                0.0, world_update["solar_production_rate"])
            print(
                "[CS] World update: "
                f"solar_production_rate={agent.solar_production_rate:.2f} kW"
            )

    async def _handle_charge_complete(self, msg: Message) -> None:
        agent = self.agent
        parsed = agent.messaging_service.parse_inform_status(msg)
        if not parsed:
            return

        ev_jid, status = parsed
        if status != "charge-complete":
            return

        finished = agent.complete_session(ev_jid)
        if not finished:
            return

        print(
            f"[CS] {ev_jid} done | Doors free: "
            f"{agent.num_doors - agent.used_doors}/{agent.num_doors}"
        )
        await _report_load(self)
        await self._process_queue()
        await agent.notify_interested_evs(self, "charge_complete", exclude_ev_jid=ev_jid)

    async def _handle_proposal_confirmed(self, ev_jid: str) -> None:
        agent = self.agent
        proposal = retrieve_and_remove_proposal(
            agent.pending_proposals, ev_jid)
        if not proposal:
            print(
                f"[CS] Proposal confirm from {ev_jid} but no pending proposal found")
            return

        decision = proposal.get("decision")
        request_data = proposal.get("request", {})

        if decision == "accept":
            agent.register_active_session(ev_jid, request_data)
            print(
                f"[CS] {ev_jid} CONFIRMED ACCEPT | Active: {len(agent.active_charging)} | "
                f"Doors used: {agent.used_doors}/{agent.num_doors}"
            )
            await _report_load(self)
            await agent.notify_interested_evs(self, "proposal_confirmed_accept", exclude_ev_jid=ev_jid)
            return

        if decision == "wait":
            agent.queue_confirmed_request(request_data)
            print(
                f"[CS] {ev_jid} CONFIRMED WAIT | Queue size: {len(agent.request_queue)} | "
                f"Incoming: {len(agent.incoming_requests)}"
            )
            await agent.notify_interested_evs(self, "proposal_confirmed_wait", exclude_ev_jid=ev_jid)

    async def _handle_proposal_rejected(self, ev_jid: str) -> None:
        agent = self.agent
        proposal = retrieve_and_remove_proposal(
            agent.pending_proposals, ev_jid)
        if not proposal:
            print(
                f"[CS] Proposal reject from {ev_jid} but no pending proposal found")
            return

        remove_incoming_request(agent.incoming_requests, ev_jid)
        print(f"[CS] {ev_jid} REJECTED proposal")

    async def _process_queue(self) -> None:
        agent = self.agent
        self._cleanup_expired_pending(agent)

        doors_before = agent.used_doors
        await agent.request_queue.dispatch_eligible(
            has_free_door=lambda: (
                agent.used_doors +
                count_pending_slot_reservations(agent.pending_proposals)
            )
            < agent.num_doors,
            can_accept_request=agent.can_accept_request,
            accept_request=lambda req: agent.accept_request(
                req, self, from_queue=True),
        )
        if agent.used_doors != doors_before:
            await _report_load(self)


class AvailableState(CSStateMixin, State):
    def _next_state(self) -> str:
        if self.agent.used_doors >= self.agent.num_doors:
            return STATE_FULL
        return STATE_AVAILABLE

    async def run(self) -> None:
        self.agent.update_solar_energy()
        await self._dispatch(await self.receive(timeout=5))
        await self._process_queue()
        self.set_next_state(self._next_state())


class FullState(CSStateMixin, State):
    def _next_state(self) -> str:
        if self.agent.used_doors < self.agent.num_doors:
            return STATE_AVAILABLE
        return STATE_FULL

    async def run(self) -> None:
        self.agent.update_solar_energy()
        await self._dispatch(await self.receive(timeout=1))
        await self._process_queue()
        self.set_next_state(self._next_state())
