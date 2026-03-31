from spade.behaviour import FSMBehaviour, State

from .utils import charging_time_minutes

STATE_AVAILABLE = "AVAILABLE"
STATE_FULL = "FULL"

class CSChargingFSM(FSMBehaviour):
    async def on_start(self):
        print(f"[FSM] Starting at state: {self.current_state}")

    async def on_end(self):
        print(f"[FSM] Finished at state: {self.current_state}")


class CSStateMixin:
    """Shared logic for CS FSM states."""

   

    def _estimate_wait_minutes(self, agent, incoming_request):
        doors = max(1, int(agent.num_doors))
        door_available_at = [0.0] * doors

        # Seed the schedule with currently active charging sessions.
        for session in agent.active_charging.values():
            duration = charging_time_minutes(
                session.get("required_energy", 0.0),
                session.get("rate", agent.max_charging_rate),
                agent.max_charging_rate,
            )
            next_door = min(range(doors), key=lambda idx: door_available_at[idx])
            door_available_at[next_door] += duration

        # Schedule all queued requests in FIFO order.
        for request in agent.request_queue.snapshot():
            duration = charging_time_minutes(
                request.get("required_energy", 0.0),
                request.get("max_charging_rate", agent.max_charging_rate),
                agent.max_charging_rate,
            )
            next_door = min(range(doors), key=lambda idx: door_available_at[idx])
            door_available_at[next_door] += duration

        # Predicted wait is when this request can start on the first free door.
        return min(door_available_at)

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

        # If this EV is already charging, acknowledge and ignore stale retries.
        if ev_jid in agent.active_charging:
            await agent.messaging_service.send_response(self, ev_jid, "accept")
            print(f"[CS] Ignored duplicate request from {ev_jid} (already charging)")
            return

        if agent.can_accept_request(parsed):
            await agent.accept_request(parsed, self, from_queue=False)
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
                agent.solar_production_rate = max(0.0, world_update["solar_production_rate"])
                print(
                    "[CS] World update: "
                    f"solar_production_rate={agent.solar_production_rate:.2f} kW"
                )
            return

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

    async def _process_queue(self):
        agent = self.agent
        await agent.request_queue.dispatch_eligible(
            has_free_door=lambda: agent.used_doors < agent.num_doors,
            can_accept_request=agent.can_accept_request,
            accept_request=lambda req: agent.accept_request(req, self, from_queue=True),
        )


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
