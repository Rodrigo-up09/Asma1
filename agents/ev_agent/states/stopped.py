import asyncio
import math

from spade.behaviour import State

from ..utils import closest_station
from .constants import (
    STATE_DRIVING,
    STATE_GOING_TO_CHARGER,
    STATE_STOPPED,
    TICK_SLEEP_SECONDS,
)


def _estimate_energy_for_trip(
    dist: float, velocity: float, energy_per_km: float, tick_sim_hours: float
) -> float:
    """Estimate total kWh needed to travel a given distance."""
    if velocity <= 0:
        return float("inf")
    num_ticks = dist / velocity
    travel_hours = num_ticks * tick_sim_hours
    drain_kw = energy_per_km * velocity
    return drain_kw * travel_hours


def _estimate_travel_hours(
    dist: float, velocity: float, tick_sim_hours: float
) -> float:
    """Estimate sim-hours to travel a given distance."""
    if velocity <= 0:
        return float("inf")
    return (dist / velocity) * tick_sim_hours


class StoppedState(State):
    async def run(self):
        agent = self.agent
        name = str(agent.jid).split("@")[0]

        clock = getattr(agent, "world_clock", None)
        if not clock:
            print(f"[{name}][STOPPED] ERROR: No world clock available!")
            await asyncio.sleep(TICK_SLEEP_SECONDS)
            self.set_next_state(STATE_STOPPED)
            return

        t = clock.formatted_time()

        # Check low SoC while parked first
        if agent.current_soc <= agent.low_soc_threshold:
            agent.current_cs_jid = None
            print(
                f"[{t}][{name}][STOPPED] SoC below {agent.low_soc_threshold:.0%}, heading to charger..."
            )
            self.set_next_state(STATE_GOING_TO_CHARGER)
            return

        # Get next destination from schedule (only when stopped, not while driving)
        next_stop = agent.next_target() if hasattr(agent, "next_target") else None

        if next_stop:
            stop_type = next_stop.get("type", "destination")

            # Calculate distance and travel time to next destination
            if stop_type == "destination":
                dist = math.hypot(next_stop["x"] - agent.x, next_stop["y"] - agent.y)
            else:
                # free_drive — no real distance to travel, just leave on time
                dist = 0.0

            # Calculate actual travel time based on world clock timing
            time_before = clock.sim_hours
            await asyncio.sleep(TICK_SLEEP_SECONDS)
            time_after = clock.sim_hours
            tick_sim_hours = time_after - time_before

            # Travel time for the direct route
            travel_hours = _estimate_travel_hours(dist, agent.velocity, tick_sim_hours)

            # ── Energy prediction: do we need a charging detour? ──
            needs_charge_detour = False
            detour_extra_hours = 0.0

            if stop_type == "destination" and dist > 0:
                energy_needed = _estimate_energy_for_trip(
                    dist, agent.velocity, agent.energy_per_km, tick_sim_hours
                )
                current_energy = agent.current_soc * agent.battery_capacity_kwh
                # Add safety margin (keep low_soc_threshold worth of energy in reserve)
                reserve = agent.low_soc_threshold * agent.battery_capacity_kwh

                if current_energy - reserve < energy_needed:
                    needs_charge_detour = True

                    # Find closest CS from current position
                    cs_jid, dist_to_cs = closest_station(
                        agent.x, agent.y, agent.cs_stations
                    )
                    if cs_jid:
                        # Estimate: drive to CS + charge up + drive from CS to destination
                        cs_station = next(
                            (s for s in agent.cs_stations if s["jid"] == cs_jid), None
                        )
                        if cs_station:
                            dist_cs_to_dest = math.hypot(
                                next_stop["x"] - cs_station["x"],
                                next_stop["y"] - cs_station["y"],
                            )
                            # Travel time: to CS + CS to destination
                            travel_to_cs = _estimate_travel_hours(
                                dist_to_cs, agent.velocity, tick_sim_hours
                            )
                            travel_cs_to_dest = _estimate_travel_hours(
                                dist_cs_to_dest, agent.velocity, tick_sim_hours
                            )
                            # Charging time: charge enough for the CS→dest leg + reserve
                            energy_for_cs_to_dest = _estimate_energy_for_trip(
                                dist_cs_to_dest,
                                agent.velocity,
                                agent.energy_per_km,
                                tick_sim_hours,
                            )
                            energy_deficit = (
                                energy_for_cs_to_dest + reserve
                            ) - current_energy
                            if energy_deficit > 0:
                                charge_hours = energy_deficit / agent.max_charge_rate_kw
                            else:
                                charge_hours = 0.0

                            detour_extra_hours = (
                                travel_to_cs + charge_hours + travel_cs_to_dest
                            ) - travel_hours  # subtract direct route since we replace it

                            if detour_extra_hours < 0:
                                detour_extra_hours = 0.0

            # Total time needed including potential detour
            total_travel_hours = travel_hours + detour_extra_hours

            now = clock.time_of_day
            target_hour = next_stop["hour"]
            # Time remaining until the next stop's scheduled arrival hour
            if target_hour > now:
                time_until_arrival = target_hour - now
            else:
                # Next stop is tomorrow (day wrap)
                time_until_arrival = (24.0 - now) + target_hour

            # Leave when: time_until_arrival <= total_travel_hours
            # For free_drive: depart within one tick of the scheduled hour
            depart_threshold = (
                total_travel_hours if stop_type == "destination" else tick_sim_hours
            )
            if time_until_arrival <= depart_threshold:
                if stop_type == "free_drive":
                    # Start free-driving (random walk) mode
                    agent.free_driving = True
                    agent.current_destination = None
                    print(
                        f"[{t}][{name}][STOPPED] Starting free drive until next scheduled stop"
                    )
                    self.set_next_state(STATE_DRIVING)
                    return
                elif needs_charge_detour:
                    # Not enough energy — head to charger first
                    agent.current_cs_jid = None  # Let GoingToCharger pick the closest
                    # Remember where we actually need to go after charging
                    agent.current_destination = next_stop
                    print(
                        f"[{t}][{name}][STOPPED] Not enough energy for \"{next_stop['name']}\" "
                        f"(need charging detour, +{detour_extra_hours:.1f}h). "
                        f"Heading to charger first!"
                    )
                    self.set_next_state(STATE_GOING_TO_CHARGER)
                    return
                else:
                    print(
                        f"[{t}][{name}][STOPPED] Time to leave for \"{next_stop['name']}\" "
                        f"(arrival at {int(target_hour):02d}:{int((target_hour % 1) * 60):02d}, "
                        f"travel time ≈ {travel_hours:.1f}h)"
                    )
                    # Lock in the destination before starting to drive
                    agent.current_destination = next_stop
                    self.set_next_state(STATE_DRIVING)
                    return

            time_until_leave = time_until_arrival - total_travel_hours
            charge_note = " ⚡needs charge" if needs_charge_detour else ""
            print(
                f"[{t}][{name}][STOPPED] Parked | "
                f"SoC: {agent.current_soc:.0%} | "
                f"next: \"{next_stop['name']}\" at {int(target_hour):02d}:{int((target_hour % 1) * 60):02d} "
                f"(leaving in ~{time_until_leave:.1f}h){charge_note}"
            )
        else:
            print(
                f"[{t}][{name}][STOPPED] Parked (no schedule) | SoC: {agent.current_soc:.0%}"
            )
            await asyncio.sleep(TICK_SLEEP_SECONDS)

        self.set_next_state(STATE_STOPPED)
