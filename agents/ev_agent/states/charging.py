import asyncio

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

        # Check if deadline has been missed
        target = agent.current_destination
        if target and target.get("hour") is not None:
            if target["hour"] <= clock.sim_hours:
                # Deadline has passed — stop charging and abandon
                print(
                    f"[{t}][{name}][CHARGING] Deadline for \"{target['name']}\" at "
                    f"{int(target['hour']):02d}:{int((target['hour'] % 1) * 60):02d} has passed! "
                    "Stopping charge early and returning to STOPPED."
                )
                agent.current_destination = None
                agent.current_cs_jid = None
                self.set_next_state(STATE_STOPPED)
                return

        # Wait for real time to pass, then calculate actual sim time elapsed
        await asyncio.sleep(TICK_SLEEP_SECONDS)
        time_after = clock.sim_hours
        tick_sim_hours = time_after - time_before

        energy_added = agent.max_charge_rate_kw * tick_sim_hours
        soc_gain = energy_added / agent.battery_capacity_kwh
        agent.current_soc = min(1.0, agent.current_soc + soc_gain)

        # Accumulate kWh for this session
        agent._session_kwh = getattr(agent, "_session_kwh", 0.0) + energy_added

        # Use trip-specific target SoC if set, otherwise use default target_soc
        target_soc_for_charge = getattr(agent, "_trip_target_soc", agent.target_soc)

        print(
            f"[{t}][{name}][CHARGING] SoC: {agent.current_soc:.0%} "
            f"(+{energy_added:.1f} kWh) | Target: {target_soc_for_charge:.0%}"
        )

        if agent.current_soc >= target_soc_for_charge - 0.05:
            print(f"[{t}][{name}][CHARGING] Charged to target! Resuming driving.")

            # ── metric: charging session complete ──
            session_kwh = agent._session_kwh
            session_cost = session_kwh * agent.electricity_price
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
            self.set_next_state(STATE_DRIVING)
            return

        self.set_next_state(STATE_CHARGING)
