import asyncio
import math

from spade.behaviour import State

from ..utils import (
    apply_energy_drain,
    calculate_arrival_time_hours,
    get_station_position,
    move_towards,
    required_energy_kwh,
)
from .constants import (
    STATE_CHARGING,
    STATE_GOING_TO_CHARGER,
    STATE_STOPPED,
    STATE_WAITING_QUEUE,
    TICK_SLEEP_SECONDS,
    send_stat,
)


class GoingToChargerState(State):
    """State where EV is traveling towards a charging station."""

    async def _move_step(self, cs_pos, agent, clock, time_before, t):
        """Execute one movement step towards CS.
        
        Updates agent position, SoC, and logs metrics.
        """
        # Move one step
        agent.x, agent.y, new_dist = move_towards(
            agent.x,
            agent.y,
            cs_pos["x"],
            cs_pos["y"],
            agent.velocity,
        )

        # Wait for real time to pass, then calculate actual sim time elapsed
        await asyncio.sleep(TICK_SLEEP_SECONDS)
        time_after = clock.sim_hours
        tick_sim_hours = time_after - time_before

        # Apply energy drain
        agent.current_soc, energy_used = apply_energy_drain(
            agent.current_soc,
            agent.energy_per_km,
            agent.velocity,
            tick_sim_hours,
            agent.battery_capacity_kwh,
        )

        name = str(agent.jid).split("@")[0]
        print(
            f"[{t}][{name}][GOING_TO_CHARGER] Moving to {agent.current_cs_jid} | "
            f"SoC: {agent.current_soc:.0%} (-{energy_used:.1f} kWh) | "
            f"pos=({agent.x:.1f}, {agent.y:.1f}) | dist={new_dist:.1f}"
        )

        # Metric: energy consumed while travelling
        await send_stat(
            self,
            getattr(agent, "world_jid", None),
            {
                "event": "energy_used",
                "kwh": energy_used,
            },
        )

    async def _handle_charge_request_phase(self, agent, cs_pos, t, target_soc_for_charge):
        """Send charge request and wait for response.
        
        Returns:
            response_data: Dict with response from CS, or None if error
        """
        name = str(agent.jid).split("@")[0]
        print(
            f"[{t}][{name}][GOING_TO_CHARGER] Arrived at {agent.current_cs_jid}. "
            "Requesting charge..."
        )
        
        # Calculate arrival time
        arriving_hours = calculate_arrival_time_hours(
            agent.x,
            agent.y,
            cs_pos,
            agent.velocity,
            agent.world_clock,
        )
        
        # Send charge request
        await agent.messaging_service.send_charge_request(
            self,
            to_jid=agent.current_cs_jid,
            required_energy=required_energy_kwh(
                agent.current_soc,
                target_soc_for_charge,
                agent.battery_capacity_kwh,
            ),
            max_charging_rate=agent.max_charge_rate_kw,
            arriving_hours=arriving_hours,
        )

        # Wait for response
        reply = await self.receive(timeout=10)
        if not reply:
            print(
                f"[{t}][{name}][GOING_TO_CHARGER] Timeout waiting CS response. "
                "Retrying in 3s..."
            )
            await asyncio.sleep(3)
            return None

        # Parse response
        response_data = agent.messaging_service.parse_response(reply)
        if response_data is None:
            print(
                f"[{t}][{name}][GOING_TO_CHARGER] Invalid response format. "
                "Retrying in 3s..."
            )
            await asyncio.sleep(3)
            return None
        
        return response_data

    async def _handle_response_and_transition(self, agent, response_data, t):
        """Process CS response, confirm proposal, and return next state.
        
        Returns:
            next_state: STATE_CHARGING or STATE_WAITING_QUEUE, or STATE_GOING_TO_CHARGER if error
        """
        name = str(agent.jid).split("@")[0]
        clock = getattr(agent, "world_clock", None)
        sim_hours_now = getattr(clock, "sim_hours", 0.0)

        status = response_data.get("status")
        if status == "cs_update":
            await agent.reevaluate_cs_after_update(self, response_data.get("reason", "cs_update"))
            print(f"[{t}][{name}][GOING_TO_CHARGER] CS update received; reselecting before continuing.")
            return STATE_GOING_TO_CHARGER
        
        # Confirm proposal with CS
        confirmed, decision_msg = await agent.confirm_cs_proposal(
            self,
            agent.current_cs_jid,
            response_data,
        )
        
        if not confirmed:
            print(f"[{t}][{name}][GOING_TO_CHARGER] {decision_msg}. Retrying in 3s...")
            await asyncio.sleep(3)
            return STATE_GOING_TO_CHARGER
        
        print(f"[{t}][{name}][GOING_TO_CHARGER] {decision_msg}")

        status = response_data.get("status")
        waiting_time = response_data.get("estimated_wait_minutes")

        if status == "accept":
            print(f"[{t}][{name}][GOING_TO_CHARGER] Entering charge session.")
            # Mark queue-entry time = now
            agent._queue_entry_time = sim_hours_now
            agent._session_kwh = 0.0
            return STATE_CHARGING

        if status == "wait":
            print(
                f"[{t}][{name}][GOING_TO_CHARGER] Waiting in queue. "
                f"Estimated wait time: {waiting_time} minutes."
            )
            agent._queue_entry_time = sim_hours_now
            agent._session_kwh = 0.0
            return STATE_WAITING_QUEUE

        print(
            f"[{t}][{name}][GOING_TO_CHARGER] Unexpected response '{status}'. "
            "Retrying in 3s..."
        )
        await asyncio.sleep(3)
        return STATE_GOING_TO_CHARGER

    async def run(self):
        """Main state machine loop: move to CS, charge negotiation, then transition."""
        agent = self.agent
        name = str(agent.jid).split("@")[0]

        clock = getattr(agent, "world_clock", None)
        if not clock:
            print(f"[{name}][GOING_TO_CHARGER] ERROR: No world clock available!")
            await asyncio.sleep(TICK_SLEEP_SECONDS)
            self.set_next_state(STATE_GOING_TO_CHARGER)
            return

        time_before = clock.sim_hours
        t = clock.formatted_time()

        # ── Phase 0: Pick target CS if not selected ──
        if not agent.current_cs_jid:
            chosen = await agent.select_and_commit_cs(self)
            if not chosen:
                print(
                    f"[{t}][{name}][GOING_TO_CHARGER] Could not secure CS, retrying in 3s..."
                )
                await asyncio.sleep(3)
                self.set_next_state(STATE_GOING_TO_CHARGER)
                return
            # chosen CS stored in agent.current_cs_jid by select_and_commit_cs
            print(
                f"[{t}][{name}][GOING_TO_CHARGER] Committed to {agent.current_cs_jid}"
            )

        cs_pos = get_station_position(agent.cs_stations, agent.current_cs_jid)
        dist = math.hypot(cs_pos["x"] - agent.x, cs_pos["y"] - agent.y)

        # ── Phase 1: Move towards CS (still travelling) ──
        if dist > 1.0:
            await self._move_step(cs_pos, agent, clock, time_before, t)
            self.set_next_state(STATE_GOING_TO_CHARGER)
            return

        # ── Phase 2: Arrived — send charge request ──
        # Use trip-specific target SoC if set, otherwise use default target_soc
        target_soc_for_charge = getattr(agent, "_trip_target_soc", agent.target_soc)
        
        response_data = await self._handle_charge_request_phase(
            agent,
            cs_pos,
            t,
            target_soc_for_charge,
        )
        
        if response_data is None:
            # If deadline was missed while waiting, destination and cs_jid were cleared
            # and we should transition to STOPPED. Otherwise, retry GOING_TO_CHARGER.
            if agent.current_destination is None and agent.current_cs_jid is None:
                self.set_next_state(STATE_STOPPED)
            else:
                self.set_next_state(STATE_GOING_TO_CHARGER)
            return
        
        # ── Phase 3: Process response and confirm proposal ──
        next_state = await self._handle_response_and_transition(
            agent,
            response_data,
            t,
        )
        
        self.set_next_state(next_state)
