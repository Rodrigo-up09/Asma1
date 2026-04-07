import asyncio
import math
import random

from spade.behaviour import State

from ..utils import move_towards
from .constants import (
    STATE_DRIVING,
    STATE_GOING_TO_CHARGER,
    STATE_STOPPED,
    TICK_SLEEP_SECONDS,
    send_stat,
)


class DrivingState(State):
    async def run(self):
        agent = self.agent
        name = str(agent.jid).split("@")[0]

        # Track time at start of tick
        clock = getattr(agent, "world_clock", None)
        if not clock:
            print(f"[{name}][DRIVING] ERROR: No world clock available!")
            await asyncio.sleep(TICK_SLEEP_SECONDS)
            self.set_next_state(STATE_DRIVING)
            return

        time_before = clock.sim_hours
        t = clock.formatted_time()

        # Use the locked-in destination, not next_target() which can change
        target = agent.current_destination

        if target:
            dist = math.hypot(target["x"] - agent.x, target["y"] - agent.y)

            if dist > 1.0:
                # Still traveling to destination
                agent.x, agent.y, remaining = move_towards(
                    agent.x,
                    agent.y,
                    target["x"],
                    target["y"],
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
                    f"[{t}][{name}][DRIVING] → \"{target['name']}\" | SoC: {agent.current_soc:.0%} "
                    f"(-{energy_used:.1f} kWh) | pos=({agent.x:.1f}, {agent.y:.1f}) | dist={remaining:.1f}"
                )

                # ── metric: energy consumed while driving ──
                await send_stat(
                    self,
                    getattr(agent, "world_jid", None),
                    {
                        "event": "energy_used",
                        "kwh": energy_used,
                    },
                )

                # Check if battery is low
                if agent.current_soc <= agent.low_soc_threshold:
                    agent.current_cs_jid = None
                    print(
                        f"[{t}][{name}][DRIVING] SoC below {agent.low_soc_threshold:.0%}, heading to charger..."
                    )
                    self.set_next_state(STATE_GOING_TO_CHARGER)
                    return

                self.set_next_state(STATE_DRIVING)
                return
            else:
                # Arrived at destination → park and wait for next scheduled departure
                agent.current_destination = None  # Clear the destination
                print(
                    f"[{t}][{name}][DRIVING] Arrived at \"{target['name']}\"! "
                    f"pos=({agent.x:.1f}, {agent.y:.1f})"
                )
                self.set_next_state(STATE_STOPPED)
                return
        else:
            # No destination set — random walk (free driving mode)
            angle = random.uniform(0, 2 * math.pi)
            agent.x += agent.velocity * math.cos(angle)
            agent.y += agent.velocity * math.sin(angle)

            # Wait for real time to pass, then calculate actual sim time elapsed
            await asyncio.sleep(TICK_SLEEP_SECONDS)
            time_after = clock.sim_hours
            tick_sim_hours = time_after - time_before

            drain_kw = agent.energy_per_km * agent.velocity
            energy_used = drain_kw * tick_sim_hours
            soc_drop = energy_used / agent.battery_capacity_kwh

            agent.current_soc = max(0.0, agent.current_soc - soc_drop)

            print(
                f"[{t}][{name}][FREE DRIVING] SoC: {agent.current_soc:.0%} "
                f"(-{energy_used:.1f} kWh) | pos=({agent.x:.1f}, {agent.y:.1f})"
            )

            # ── metric: energy consumed while driving ──
            await send_stat(
                self,
                getattr(agent, "world_jid", None),
                {
                    "event": "energy_used",
                    "kwh": energy_used,
                },
            )

            if agent.current_soc <= agent.low_soc_threshold:
                agent.current_cs_jid = None
                agent.free_driving = False
                print(
                    f"[{t}][{name}][FREE DRIVING] SoC below {agent.low_soc_threshold:.0%}, heading to charger..."
                )
                self.set_next_state(STATE_GOING_TO_CHARGER)
                return

            # ── Check if it's time to leave for the next scheduled destination ──
            if agent.free_driving:
                next_stop = agent.next_target()
                # next_target returns the *next* entry after the free_drive one
                # (since free_drive's hour has already passed)
                if next_stop and next_stop.get("type", "destination") == "destination":
                    dist = math.hypot(
                        next_stop["x"] - agent.x, next_stop["y"] - agent.y
                    )
                    # Estimate travel time
                    num_ticks = (
                        dist / agent.velocity if agent.velocity > 0 else float("inf")
                    )
                    travel_hours = num_ticks * tick_sim_hours

                    now = clock.time_of_day
                    target_hour = next_stop["hour"]
                    if target_hour > now:
                        time_until_arrival = target_hour - now
                    else:
                        time_until_arrival = (24.0 - now) + target_hour

                    if time_until_arrival <= travel_hours:
                        agent.free_driving = False
                        agent.current_destination = next_stop
                        print(
                            f"[{t}][{name}][FREE DRIVING] Time to head to \"{next_stop['name']}\"! "
                            f"(travel time ≈ {travel_hours:.1f}h)"
                        )
                        self.set_next_state(STATE_DRIVING)
                        return

            self.set_next_state(STATE_DRIVING)
