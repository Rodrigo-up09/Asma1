import asyncio

from spade.behaviour import State

from .constants import (
    STATE_CHARGING,
    STATE_STOPPED,
    STATE_WAITING_QUEUE,
    send_stat,
)


class WaitingQueueState(State):
    async def run(self):
        agent = self.agent
        name = str(agent.jid).split("@")[0]
        
        # Get clock for deadline checking
        clock = getattr(agent, "world_clock", None)
        t = (
            clock.formatted_time()
            if clock
            else "??:??"
        )

        reply = await self.receive(timeout=30)

        if not reply:
            print(f"[{t}][{name}][WAITING_QUEUE] Still waiting for CS availability...")
            self.set_next_state(STATE_WAITING_QUEUE)
            return

        response_data = agent.messaging_service.parse_response(reply)
        if response_data is None:
            self.set_next_state(STATE_WAITING_QUEUE)
            return

        status = response_data.get("status")
        # Ignore cs_update messages while in queue - already committed, just wait for slot
        if status == "cs_update":
            print(f"[{t}][{name}][WAITING_QUEUE] Ignoring CS update while waiting in queue.")
            self.set_next_state(STATE_WAITING_QUEUE)
            return

        if status == "accept":
            print(f"[{t}][{name}][WAITING_QUEUE] Slot available. Starting charge.")

            # ── metric: waiting time ──
            entry_time = getattr(
                agent, "_queue_entry_time", asyncio.get_event_loop().time()
            )
            waited_mins = (asyncio.get_event_loop().time() - entry_time) / 60.0
            await send_stat(
                self,
                getattr(agent, "world_jid", None),
                {
                    "event": "waiting_time",
                    "minutes": round(waited_mins, 2),
                },
            )

            self.set_next_state(STATE_CHARGING)
            return

        print(f"[{t}][{name}][WAITING_QUEUE] Received '{status}'. Remaining in queue.")
        self.set_next_state(STATE_WAITING_QUEUE)
