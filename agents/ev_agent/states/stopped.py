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

            # Calculate time until arrival (needed for charging detour calculation)
            now = clock.time_of_day
            target_hour = next_stop["hour"]
            if target_hour > now:
                time_until_arrival = target_hour - now
            else:
                # Next stop is tomorrow (day wrap)
                time_until_arrival = (24.0 - now) + target_hour

            # ── Energy prediction: do we need a charging detour? ──
            needs_charge_detour = False
            detour_total_hours = 0.0  # Initialize to 0

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
                    
                    # Debug: show CS search
                    print(
                        f"[{t}][{name}][STOPPED] Searching for CS:\n"
                        f"  Current position: ({agent.x:.1f}, {agent.y:.1f})\n"
                        f"  Available stations: {len(agent.cs_stations)}\n"
                        f"  Stations: {agent.cs_stations}\n"
                        f"  Closest CS: {cs_jid} at distance {dist_to_cs:.1f}"
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
                            
                            # Calculate energy consumption
                            energy_to_reach_cs = _estimate_energy_for_trip(
                                dist_to_cs,
                                agent.velocity,
                                agent.energy_per_km,
                                tick_sim_hours,
                            )
                            energy_cs_to_dest = _estimate_energy_for_trip(
                                dist_cs_to_dest,
                                agent.velocity,
                                agent.energy_per_km,
                                tick_sim_hours,
                            )
                            
                            # SoC when arriving at CS
                            soc_at_cs = agent.current_soc - (energy_to_reach_cs / agent.battery_capacity_kwh)
                            
                            # Check if we can even reach the CS
                            if soc_at_cs < 0:
                                print(
                                    f"[{t}][{name}][STOPPED] WARNING: Not enough battery to reach CS! "
                                    f"Current: {agent.current_soc:.0%}, Need: {(energy_to_reach_cs / agent.battery_capacity_kwh):.0%}. "
                                    f"Will try direct route (may run out of battery)."
                                )
                                needs_charge_detour = False
                            else:
                                soc_at_cs = max(0.0, soc_at_cs)
                                
                                # Calculate available charging time
                                # Time until destination - travel time to CS - travel time CS to dest
                                available_charge_time = time_until_arrival - travel_to_cs - travel_cs_to_dest
                                
                                # Calculate minimum SoC needed to reach destination from CS
                                min_soc_needed = soc_at_cs + (energy_cs_to_dest / agent.battery_capacity_kwh) + agent.low_soc_threshold
                                min_soc_needed = min(1.0, min_soc_needed)
                                
                                if available_charge_time <= 0:
                                    # Already late - charge minimum needed and leave ASAP
                                    print(
                                        f"[{t}][{name}][STOPPED] WARNING: Already late! "
                                        f"Charging minimum needed ({min_soc_needed:.0%}) and leaving immediately."
                                    )
                                    trip_target_soc = min_soc_needed
                                    energy_to_charge = (trip_target_soc - soc_at_cs) * agent.battery_capacity_kwh
                                    charge_hours = energy_to_charge / agent.max_charge_rate_kw if energy_to_charge > 0 else 0.0
                                else:
                                    # Calculate maximum SoC we can reach with available time
                                    max_energy_can_charge = available_charge_time * agent.max_charge_rate_kw
                                    max_soc_can_reach = soc_at_cs + (max_energy_can_charge / agent.battery_capacity_kwh)
                                    max_soc_can_reach = min(1.0, max_soc_can_reach)  # Cap at 100%
                                    
                                    # Determine target SoC for this trip
                                    # Ideally charge to 100%, but limited by available time
                                    trip_target_soc = max_soc_can_reach
                                    
                                    if trip_target_soc < min_soc_needed:
                                        # Can't charge enough to reach destination on time
                                        print(
                                            f"[{t}][{name}][STOPPED] WARNING: Not enough time to charge sufficiently! "
                                            f"Need {min_soc_needed:.0%} but can only reach {trip_target_soc:.0%}"
                                        )
                                        trip_target_soc = min_soc_needed  # Charge minimum needed (will be late)
                                    
                                    # Calculate actual charging time
                                    energy_to_charge = (trip_target_soc - soc_at_cs) * agent.battery_capacity_kwh
                                    if energy_to_charge > 0:
                                        charge_hours = energy_to_charge / agent.max_charge_rate_kw
                                    else:
                                        charge_hours = 0.0
                            
                                # Store the target SoC for this trip (used by charging state)
                                agent._trip_target_soc = trip_target_soc

                                detour_total_hours = (
                                    travel_to_cs + charge_hours + travel_cs_to_dest
                                )
                                
                                # Debug output
                                print(
                                    f"[{t}][{name}][STOPPED] Charging detour calculation:\n"
                                    f"  Current SoC: {agent.current_soc:.0%} ({current_energy:.1f} kWh)\n"
                                    f"  Distance home→dest: {dist:.1f} units (direct)\n"
                                    f"  Distance home→CS: {dist_to_cs:.1f} units\n"
                                    f"  Distance CS→dest: {dist_cs_to_dest:.1f} units\n"
                                    f"  Energy to reach CS: {energy_to_reach_cs:.1f} kWh\n"
                                    f"  SoC at CS: {soc_at_cs:.0%}\n"
                                    f"  Time available for charging: {available_charge_time:.2f} hours\n"
                                    f"  Max SoC can reach: {max_soc_can_reach:.0%}\n"
                                    f"  Min SoC needed: {min_soc_needed:.0%}\n"
                                    f"  Trip target SoC: {trip_target_soc:.0%}\n"
                                    f"  Energy to charge: {energy_to_charge:.1f} kWh\n"
                                    f"  Charge time: {charge_hours:.2f} hours\n"
                                    f"  Travel home→CS: {travel_to_cs:.2f} hours\n"
                                    f"  Travel CS→dest: {travel_cs_to_dest:.2f} hours\n"
                                    f"  Total detour time: {detour_total_hours:.2f} hours\n"
                                    f"  Direct travel time: {travel_hours:.2f} hours"
                                )
                        else:
                            # CS not found in list - can't calculate detour
                            print(f"[{t}][{name}][STOPPED] WARNING: CS {cs_jid} not in station list, can't plan detour!")
                            needs_charge_detour = False
                    else:
                        # No CS available - can't plan detour
                        print(f"[{t}][{name}][STOPPED] WARNING: No charging station available, can't plan detour!")
                        needs_charge_detour = False

            # Total time needed: use detour time if charging is needed, otherwise direct route
            total_travel_hours = detour_total_hours if needs_charge_detour else travel_hours

            # Debug: show departure calculation
            print(
                f"[{t}][{name}][STOPPED] Departure calculation:\n"
                f"  Current time: {now:.2f} ({t})\n"
                f"  Target arrival: {target_hour:.2f} ({int(target_hour):02d}:{int((target_hour % 1) * 60):02d})\n"
                f"  Time until arrival: {time_until_arrival:.2f} hours\n"
                f"  Total travel time needed: {total_travel_hours:.2f} hours\n"
                f"  Needs charge detour: {needs_charge_detour}\n"
                f"  Should leave: {time_until_arrival <= total_travel_hours}"
            )

            # Leave when: time_until_arrival <= total_travel_hours
            # For free_drive: depart within one tick of the scheduled hour
            depart_threshold = (
                total_travel_hours if stop_type == "destination" else tick_sim_hours
            )
            if time_until_arrival <= depart_threshold:

                if needs_charge_detour:
                    # Not enough energy — head to charger first
                    agent.current_cs_jid = None  # Let GoingToCharger pick the closest
                    # Remember where we actually need to go after charging
                    agent.current_destination = next_stop
                    extra_time = detour_total_hours - travel_hours
                    print(
                        f"[{t}][{name}][STOPPED] Not enough energy for \"{next_stop['name']}\" "
                        f"(need charging detour, +{extra_time:.1f}h). "
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
