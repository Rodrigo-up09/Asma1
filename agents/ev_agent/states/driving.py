import asyncio
import math

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
                # Advance schedule index to the next stop
                if agent.schedule:
                    old_index = agent.current_target_index
                    agent.current_target_index = (old_index + 1) % len(agent.schedule)
                    # If we wrapped to the first stop, a new day has started
                    if agent.current_target_index == 0:
                        agent._day_offset += 1
                print(
                    f"[{t}][{name}][DRIVING] Arrived at \"{target['name']}\"! "
                    f"pos=({agent.x:.1f}, {agent.y:.1f})"
                )
                self.set_next_state(STATE_STOPPED)
                return
        else:
            # No destination set — get next target from schedule
            next_target = agent.next_target()
            if next_target:
                agent.current_destination = next_target
                print(
                    f"[{t}][{name}][DRIVING] No destination set, picking next from schedule: "
                    f"\"{next_target['name']}\" at ({next_target['x']:.1f}, {next_target['y']:.1f})"
                )
            else:
                # No schedule available — stay stopped
                print(f"[{t}][{name}][DRIVING] No destination or schedule available, going to STOPPED")
                self.set_next_state(STATE_STOPPED)
                return

            self.set_next_state(STATE_DRIVING)
            return

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
                print(
                    f"[{t}][{name}][DRIVING] SoC below {agent.low_soc_threshold:.0%}, heading to charger..."
                )
                self.set_next_state(STATE_GOING_TO_CHARGER)
                return

            self.set_next_state(STATE_DRIVING)
