import asyncio
import math

from spade.behaviour import State

from ..utils import (
    calculate_arrival_time_hours,
    closest_station,
    get_station_position,
    handle_cs_proposal,
    move_towards,
    required_energy_kwh,
)
from .constants import (
    STATE_CHARGING,
    STATE_GOING_TO_CHARGER,
    STATE_WAITING_QUEUE,
    TICK_SLEEP_SECONDS,
    send_stat,
)


class GoingToChargerState(State):
    async def run(self):
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

        if not agent.current_cs_jid:
            closest_jid, dist = closest_station(agent.x, agent.y, agent.cs_stations)
            if not closest_jid:
                print(
                    f"[{t}][{name}][GOING_TO_CHARGER] No charging stations configured. "
                    "Retrying in 3s..."
                )
                await asyncio.sleep(3)
                self.set_next_state(STATE_GOING_TO_CHARGER)
                return
            agent.current_cs_jid = closest_jid
            print(
                f"[{t}][{name}][GOING_TO_CHARGER] Chose {closest_jid} (dist={dist:.1f})"
            )

        cs_pos = get_station_position(agent.cs_stations, agent.current_cs_jid)
        dist = math.hypot(cs_pos["x"] - agent.x, cs_pos["y"] - agent.y)

        # ── still travelling ──
        if dist > 1.0:
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

            drain_kw = agent.energy_per_km * agent.velocity
            energy_used = drain_kw * tick_sim_hours
            soc_drop = energy_used / agent.battery_capacity_kwh
            agent.current_soc = max(0.0, agent.current_soc - soc_drop)

            print(
                f"[{t}][{name}][GOING_TO_CHARGER] Moving to {agent.current_cs_jid} | "
                f"SoC: {agent.current_soc:.0%} (-{energy_used:.1f} kWh) | "
                f"pos=({agent.x:.1f}, {agent.y:.1f}) | dist={new_dist:.1f}"
            )

            # ── metric: energy consumed while travelling ──
            await send_stat(
                self,
                getattr(agent, "world_jid", None),
                {
                    "event": "energy_used",
                    "kwh": energy_used,
                },
            )

            self.set_next_state(STATE_GOING_TO_CHARGER)
            return

        # ── arrived — send charge request ──
        print(
            f"[{t}][{name}][GOING_TO_CHARGER] Arrived at {agent.current_cs_jid}. "
            "Requesting charge..."
        )
        
        # Use trip-specific target SoC if set, otherwise use default target_soc
        target_soc_for_charge = getattr(agent, "_trip_target_soc", agent.target_soc)
        
        # Calculate arrival time
        cs_pos = get_station_position(agent.cs_stations, agent.current_cs_jid)
        arriving_hours = calculate_arrival_time_hours(
            agent.x,
            agent.y,
            cs_pos,
            agent.velocity,
            agent.world_clock,
        )
        
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

        reply = await self.receive(timeout=10)

        if not reply:
            print(
                f"[{t}][{name}][GOING_TO_CHARGER] Timeout waiting CS response. "
                "Retrying in 3s..."
            )
            await asyncio.sleep(3)
            self.set_next_state(STATE_GOING_TO_CHARGER)
            return

        response_data = agent.messaging_service.parse_response(reply)
        if response_data is None:
            print(
                f"[{t}][{name}][GOING_TO_CHARGER] Invalid response format. "
                "Retrying in 3s..."
            )
            await asyncio.sleep(3)
            self.set_next_state(STATE_GOING_TO_CHARGER)
            return

        # Confirm proposal with CS
        confirmed, decision_msg = await handle_cs_proposal(
            self,
            agent,
            response_data,
            agent.current_cs_jid,
        )
        
        if not confirmed:
            print(f"[{t}][{name}][GOING_TO_CHARGER] {decision_msg}. Retrying in 3s...")
            await asyncio.sleep(3)
            self.set_next_state(STATE_GOING_TO_CHARGER)
            return
        
        print(f"[{t}][{name}][GOING_TO_CHARGER] {decision_msg}")

        status = response_data.get("status")
        waiting_time = response_data.get("estimated_wait_minutes")

        if status == "accept":
            print(f"[{t}][{name}][GOING_TO_CHARGER] Entering charge session.")
            # Mark queue-entry time = now (not queued, but reuse the same field
            # so ChargingState can record a zero wait if needed)
            agent._queue_entry_time = asyncio.get_event_loop().time()
            agent._session_kwh = 0.0
            self.set_next_state(STATE_CHARGING)
            return

        if status == "wait":
            print(
                f"[{t}][{name}][GOING_TO_CHARGER] Waiting in queue. "
                f"Estimated wait time: {waiting_time} minutes."
            )
            agent._queue_entry_time = asyncio.get_event_loop().time()
            agent._session_kwh = 0.0
            self.set_next_state(STATE_WAITING_QUEUE)
            return

        print(
            f"[{t}][{name}][GOING_TO_CHARGER] Unexpected response '{status}'. "
            "Retrying in 3s..."
        )
        await asyncio.sleep(3)
        self.set_next_state(STATE_GOING_TO_CHARGER)
