from spade.behaviour import FSMBehaviour, State

STATE_AVAILABLE = "AVAILABLE"
STATE_FULL = "FULL"

class CSChargingFSM(FSMBehaviour):
    async def on_start(self):
        print(f"[FSM] Starting at state: {self.current_state}")

    async def on_end(self):
        print(f"[FSM] Finished at state: {self.current_state}")


class CSStateMixin:
    """Shared logic for CS FSM states."""

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

        # If this EV is already charging, acknowledge and ignore stale retries.
        if ev_jid in agent.active_charging:
            await agent.messaging_service.send_response(self, ev_jid, "accept")
            print(f"[CS] Ignored duplicate request from {ev_jid} (already charging)")
            return

        if agent.can_accept_request(parsed):
            agent.request_queue.remove_by_ev(ev_jid)
            await agent.accept_request(parsed, self, from_queue=False)
        else:
            inserted = agent.request_queue.enqueue_or_update(parsed)
            await agent.messaging_service.send_response(self, ev_jid, "wait")
            if inserted:
                print(f"[CS] Queued {ev_jid} | Queue size: {len(agent.request_queue)}")
            else:
                print(f"[CS] Updated queued request for {ev_jid} | Queue size: {len(agent.request_queue)}")

    async def _on_inform(self, msg):
        agent = self.agent
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
