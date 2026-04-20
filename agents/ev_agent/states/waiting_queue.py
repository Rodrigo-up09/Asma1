import asyncio
import math

from spade.behaviour import State

from .constants import (
    STATE_CHARGING,
    STATE_GOING_TO_CHARGER,
    STATE_STOPPED,
    STATE_WAITING_QUEUE,
    send_stat,
)


class WaitingQueueState(State):
    def _travel_time_minutes(self, agent, station_info: dict) -> float:
        if agent.velocity <= 0:
            return float("inf")
        dist = math.hypot(station_info["x"] - agent.x, station_info["y"] - agent.y)
        return (dist / agent.velocity) * 60.0

    async def _should_switch_to_other_cs(self) -> tuple[bool, dict | None, float, float]:
        """Evaluate whether queue waiting time justifies switching to another CS."""
        agent = self.agent
        current_jid = agent.current_cs_jid
        if not current_jid:
            return False, None, 0.0, 0.0

        infos = await agent.collect_station_infos(self, timeout_seconds=0.3)
        if not infos:
            return False, None, 0.0, 0.0

        current_info = next((s for s in infos if s["jid"] == current_jid), None)
        if not current_info:
            return False, None, 0.0, 0.0

        predicted_wait = float(current_info.get("estimated_wait_minutes", 0.0))
        if predicted_wait <= 0:
            return False, None, predicted_wait, 0.0

        alternatives = [s for s in infos if s["jid"] != current_jid]
        if not alternatives:
            return False, None, predicted_wait, 0.0

        # Requirement: check the closest other CS.
        alternatives.sort(key=lambda s: math.hypot(s["x"] - agent.x, s["y"] - agent.y))
        candidate = alternatives[0]

        num_doors = int(candidate.get("num_doors", 1))
        used_doors = int(candidate.get("used_doors", 0))
        expected_evs = int(candidate.get("expected_evs", 0))
        free_ports = max(0, num_doors - used_doors)

        # Switch allowed when:
        # 1) at least 1 free port and nobody expected, OR
        # 2) at least 2 free ports (even if someone is expected)
        capacity_ok = (free_ports >= 1 and expected_evs == 0) or (free_ports >= 2)
        travel_minutes = self._travel_time_minutes(agent, candidate)
        should_switch = capacity_ok and predicted_wait > travel_minutes
        return should_switch, candidate, predicted_wait, travel_minutes

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

        reply = await self.receive(timeout=15)

        if not reply:
            should_switch, candidate, predicted_wait, travel_minutes = await self._should_switch_to_other_cs()
            if should_switch and candidate:
                target_jid = candidate["jid"]
                previous_jid = agent.current_cs_jid
                accepted = await agent.commit_to_station(self, candidate)
                if accepted:
                    await agent.messaging_service.send_cancel(
                        self,
                        previous_jid,
                        str(agent.jid).split("/")[0],
                    )
                    agent.current_cs_jid = target_jid
                    print(
                        f"[{t}][{name}][WAITING_QUEUE] Switching CS {previous_jid} -> {target_jid} "
                        f"(wait {predicted_wait:.1f}m > travel {travel_minutes:.1f}m)."
                    )
                    self.set_next_state(STATE_GOING_TO_CHARGER)
                    return

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
            self.set_next_state(STATE_WAITING_QUEUE)
            return

        if status == "accept":
            print(f"[{t}][{name}][WAITING_QUEUE] Slot available. Starting charge.")

            # ── metric: waiting time ──
            clock = getattr(agent, "world_clock", None)
            entry_time = getattr(
                agent, "_queue_entry_time", getattr(clock, "sim_hours", 0.0)
            )
            current_time = getattr(clock, "sim_hours", entry_time)
            waited_hours = current_time - entry_time
            if waited_hours < 0:
                waited_hours += 24.0
            waited_mins = waited_hours * 60.0
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
