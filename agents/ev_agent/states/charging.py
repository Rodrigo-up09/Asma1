import asyncio
import math

from spade.behaviour import State

from .constants import (
    STATE_CHARGING,
    STATE_DRIVING,
    STATE_STOPPED,
    TICK_SLEEP_SECONDS,
    send_stat,
)


class ChargingState(State):
    async def run(self):
        agent = self.agent
        name = str(agent.jid).split("@")[0]

        clock = getattr(agent, "world_clock", None)
        if not clock:
            print(f"[{name}][CHARGING] ERROR: No world clock available!")
            await asyncio.sleep(TICK_SLEEP_SECONDS)
            self.set_next_state(STATE_CHARGING)
            return

        time_before = clock.sim_hours
        t = clock.formatted_time()

        msg = await self.receive(timeout=0)
        if msg:
            response_data = agent.messaging_service.parse_response(msg)
            if response_data and response_data.get("status") == "cs_update":
                print(
                    f"[{t}][{name}][CHARGING] CS update '{response_data.get('reason', 'cs_update')}' ignored while charging."
                )

        # Wait for real time to pass, then calculate actual sim time elapsed
        await asyncio.sleep(TICK_SLEEP_SECONDS)
        time_after = clock.sim_hours
        tick_sim_hours = time_after - time_before

        energy_added = agent.max_charge_rate_kw * tick_sim_hours
        soc_gain = energy_added / agent.battery_capacity_kwh
        agent.current_soc = min(1.0, agent.current_soc + soc_gain)

        # Accumulate kWh for this session
        agent._session_kwh = getattr(agent, "_session_kwh", 0.0) + energy_added

        # Use trip-specific target SoC if set, otherwise aim for 100%
        target_soc_for_charge = getattr(agent, "_trip_target_soc", 1.0)

        # ── Check if we must leave early due to upcoming deadline ─────
        must_leave_early = False
        if (
            agent.current_destination
            and agent.current_soc >= agent.low_soc_threshold + 0.05
        ):
            dest = agent.current_destination
            dest_hour = dest.get("hour", None)

            if dest_hour is not None:
                dist_to_dest = math.hypot(dest["x"] - agent.x, dest["y"] - agent.y)

                # Estimate travel time properly: (dist / velocity) gives num_ticks,
                # multiply by tick_sim_hours to get sim-hours.
                if agent.velocity > 0 and tick_sim_hours > 0:
                    travel_hours = (dist_to_dest / agent.velocity) * tick_sim_hours
                else:
                    travel_hours = 0.0

                # dest_hour is already day-offset-adjusted (set by next_target())
                # Use sim_hours for apples-to-apples comparison
                time_remaining = dest_hour - clock.sim_hours
                time_after_travel = time_remaining - travel_hours

                # Only consider early departure if deadline is actually in the future.
                # If time_remaining <= 0, the deadline already passed (stale from
                # a previous day/cycle), so just keep charging to full.
                if (
                    time_remaining > 0
                    and time_after_travel <= 0.25
                    and agent.current_soc < target_soc_for_charge - 0.05
                ):
                    must_leave_early = True
                    print(
                        f"[{t}][{name}][CHARGING] ⏰ Must leave now for \"{dest['name']}\"! "
                        f"SoC: {agent.current_soc:.0%} (wanted {target_soc_for_charge:.0%} "
                        f"but only {time_remaining:.1f}h until deadline, {travel_hours:.1f}h travel needed)"
                    )

        print(
            f"[{t}][{name}][CHARGING] SoC: {agent.current_soc:.0%} "
            f"(+{energy_added:.1f} kWh) | Target: {target_soc_for_charge:.0%}"
        )

        if agent.current_soc >= target_soc_for_charge - 0.05 or must_leave_early:
            if not must_leave_early:
                print(f"[{t}][{name}][CHARGING] Charged to target! Resuming driving.")

            # ── metric: charging session complete ──
            session_kwh = agent._session_kwh
            session_cost = session_kwh * float(
                getattr(agent, "current_station_price_per_kwh", agent.electricity_price)
            )
            await send_stat(
                self,
                getattr(agent, "world_jid", None),
                {
                    "event": "charging_complete",
                    "kwh": round(session_kwh, 3),
                    "cost": round(session_cost, 4),
                    "renewable": agent.renewable_available,
                },
            )
            agent._session_kwh = 0.0

            # Clear trip-specific target SoC
            if hasattr(agent, "_trip_target_soc"):
                delattr(agent, "_trip_target_soc")

            await agent.messaging_service.send_charge_complete(
                self,
                to_jid=agent.current_cs_jid,
            )
            # Done with this CS; clear reference for next charging event
            agent.current_cs_jid = None
            self.set_next_state(STATE_DRIVING)
            return

        self.set_next_state(STATE_CHARGING)
