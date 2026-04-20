import asyncio
import math

from spade.behaviour import State

from ..utils import closest_station
from ..urgency_model import UrgencyModel
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
    def _check_clock_available(self):
        """Verify world clock is available. Returns (clock, t) or (None, None)."""
        clock = getattr(self.agent, "world_clock", None)
        if not clock:
            print(f"[{str(self.agent.jid).split('@')[0]}][STOPPED] ERROR: No world clock available!")
            return None, None
        return clock, clock.formatted_time()

    async def _handle_low_soc(self, name: str, t: str):
        """Check if SoC is critically low and needs immediate charging."""
        if self.agent.current_soc <= self.agent.low_soc_threshold:
            self.agent.current_cs_jid = None
            print(
                f"[{t}][{name}][STOPPED] SoC below {self.agent.low_soc_threshold:.0%}, heading to charger..."
            )
            self.set_next_state(STATE_GOING_TO_CHARGER)
            return True
        return False

    async def _get_next_stop_and_distances(self, t: str):
        """Get next destination and calculate distances."""
        next_stop = self.agent.next_target() if hasattr(self.agent, "next_target") else None
        
        if not next_stop:
            return None, None, None
        
        dist = math.hypot(next_stop["x"] - self.agent.x, next_stop["y"] - self.agent.y)
        return next_stop, dist, t

    async def _calculate_timing(self, dist: float):
        """Calculate travel time and time-of-day metrics."""
        clock = self.agent.world_clock
        
        # Measure tick duration
        time_before = clock.sim_hours
        await asyncio.sleep(TICK_SLEEP_SECONDS)
        time_after = clock.sim_hours
        tick_sim_hours = time_after - time_before
        
        travel_hours = _estimate_travel_hours(dist, self.agent.velocity, tick_sim_hours)
        
        # Use sim_hours (unbounded) for time calculations, not time_of_day (wrapped)
        now = clock.sim_hours
        return travel_hours, tick_sim_hours, now

    def _calculate_time_until_arrival(self, target_hour: float, now: float):
        """Calculate hours remaining until target arrival time.
        
        With multi-day schedules, target_hour is always 0-24 (time of day).
        We need to adjust by day offset to get actual sim_hours.
        Each day is 24 hours of simulation time.
        """
        # Adjust target hour by day offset
        adjusted_target = target_hour + (self.agent._day_offset * 24)
        return adjusted_target - now

    async def _handle_charging_detour(self, next_stop: dict, dist: float, travel_hours: float, 
                                     tick_sim_hours: float, time_until_arrival: float, t: str, name: str,
                                     current_time: float = None):
        """Determine if a charging detour is needed and calculate its duration."""
        if dist <= 0:
            return False, 0.0
        
        energy_needed = _estimate_energy_for_trip(
            dist, self.agent.velocity, self.agent.energy_per_km, tick_sim_hours
        )
        current_energy = self.agent.current_soc * self.agent.battery_capacity_kwh
        reserve = self.agent.low_soc_threshold * self.agent.battery_capacity_kwh
        
        if current_energy - reserve >= energy_needed:
            return False, 0.0
        
        # Need charging detour - find closest CS
        cs_jid, dist_to_cs = closest_station(self.agent.x, self.agent.y, self.agent.cs_stations)
        
        print(
            f"[{t}][{name}][STOPPED] Searching for CS:\n"
            f"  Current position: ({self.agent.x:.1f}, {self.agent.y:.1f})\n"
            f"  Available stations: {len(self.agent.cs_stations)}\n"
            f"  Closest CS: {cs_jid} at distance {dist_to_cs:.1f}"
        )
        
        if not cs_jid:
            print(f"[{t}][{name}][STOPPED] WARNING: No charging station available, can't plan detour!")
            return False, 0.0
        
        # Calculate detour path
        detour_time = await self._calculate_detour_path(
            next_stop, cs_jid, dist_to_cs, energy_needed, current_energy, 
            time_until_arrival, tick_sim_hours, t, name, current_time
        )
        
        return True, detour_time

    async def _calculate_detour_path(self, next_stop: dict, cs_jid: str, dist_to_cs: float,
                                     energy_needed: float, current_energy: float, time_until_arrival: float,
                                     tick_sim_hours: float, t: str, name: str, current_time: float = None):
        """Calculate the full detour path: home → CS → destination."""
        cs_station = next((s for s in self.agent.cs_stations if s["jid"] == cs_jid), None)
        
        if not cs_station:
            print(f"[{t}][{name}][STOPPED] WARNING: CS {cs_jid} not in station list, can't plan detour!")
            return 0.0
        
        # Distances
        dist_cs_to_dest = math.hypot(
            next_stop["x"] - cs_station["x"],
            next_stop["y"] - cs_station["y"],
        )
        
        # Travel times
        travel_to_cs = _estimate_travel_hours(dist_to_cs, self.agent.velocity, tick_sim_hours)
        travel_cs_to_dest = _estimate_travel_hours(dist_cs_to_dest, self.agent.velocity, tick_sim_hours)
        
        # Energy calculations
        energy_to_reach_cs = _estimate_energy_for_trip(
            dist_to_cs, self.agent.velocity, self.agent.energy_per_km, tick_sim_hours
        )
        energy_cs_to_dest = _estimate_energy_for_trip(
            dist_cs_to_dest, self.agent.velocity, self.agent.energy_per_km, tick_sim_hours
        )
        
        soc_at_cs = self.agent.current_soc - (energy_to_reach_cs / self.agent.battery_capacity_kwh)
        
        # Check if we can reach the CS
        if soc_at_cs < 0:
            print(
                f"[{t}][{name}][STOPPED] WARNING: Not enough battery to reach CS! "
                f"Current: {self.agent.current_soc:.0%}, Need: {(energy_to_reach_cs / self.agent.battery_capacity_kwh):.0%}. "
                f"Will try direct route (may run out of battery)."
            )
            return 0.0
        
        soc_at_cs = max(0.0, soc_at_cs)
        
        # Available charging time
        available_charge_time = time_until_arrival - travel_to_cs - travel_cs_to_dest
        
        # Calculate target SoC with urgency adjustments
        trip_target_soc = self._calculate_target_soc(
            soc_at_cs, available_charge_time, energy_cs_to_dest, t, name,
            destination=next_stop, current_time=current_time
        )
        
        self.agent._trip_target_soc = trip_target_soc
        
        # Calculate charge time needed
        energy_to_charge = (trip_target_soc - soc_at_cs) * self.agent.battery_capacity_kwh
        charge_hours = energy_to_charge / self.agent.max_charge_rate_kw if energy_to_charge > 0 else 0.0
        
        detour_total_hours = travel_to_cs + charge_hours + travel_cs_to_dest
        
        self._log_charging_detour(
            t, name, detour_total_hours, energy_to_reach_cs, energy_cs_to_dest,
            soc_at_cs, available_charge_time, trip_target_soc, charge_hours,
            travel_to_cs, travel_cs_to_dest, dist_to_cs, dist_cs_to_dest
        )
        
        return detour_total_hours

    def _calculate_target_soc(self, soc_at_cs: float, available_charge_time: float,
                               energy_cs_to_dest: float, t: str, name: str,
                               destination: dict = None, current_time: float = None) -> float:
        """Calculate target SoC for this trip given available charging time.
        
        Adjusted by urgency if destination has time constraints.
        """
        min_soc_needed = soc_at_cs + (energy_cs_to_dest / self.agent.battery_capacity_kwh) + self.agent.low_soc_threshold
        min_soc_needed = min(1.0, min_soc_needed)
        
        # Calculate urgency-based adjustments if destination provided
        urgency_boost = 1.0
        if destination and current_time is not None:
            try:
                distance = math.hypot(destination["x"] - self.agent.x, destination["y"] - self.agent.y)
                urgency_metrics = UrgencyModel.calculate_metrics(
                    current_time=current_time,
                    destination=destination,
                    current_soc=soc_at_cs,
                    distance_to_destination=distance,
                    velocity=self.agent.velocity,
                )
                urgency_boost = urgency_metrics.charging_multiplier
                
                # Log urgency adjustment
                if urgency_boost > 1.0:
                    print(
                        f"[{t}][{name}][STOPPED] {UrgencyModel.format_urgency_metrics(urgency_metrics)}"
                    )
            except Exception:
                pass  # Fall back to no urgency adjustment
        
        # Apply urgency boost to min SoC
        min_soc_needed = min(1.0, min_soc_needed * urgency_boost)
        
        if available_charge_time <= 0:
            print(
                f"[{t}][{name}][STOPPED] WARNING: Already late! "
                f"Charging minimum needed ({min_soc_needed:.0%}) and leaving immediately."
            )
            return min_soc_needed
        
        max_energy_can_charge = available_charge_time * self.agent.max_charge_rate_kw
        max_soc_can_reach = soc_at_cs + (max_energy_can_charge / self.agent.battery_capacity_kwh)
        max_soc_can_reach = min(1.0, max_soc_can_reach)
        
        if max_soc_can_reach < min_soc_needed:
            print(
                f"[{t}][{name}][STOPPED] WARNING: Not enough time to charge sufficiently! "
                f"Need {min_soc_needed:.0%} but can only reach {max_soc_can_reach:.0%}"
            )
            return min_soc_needed
        
        return max_soc_can_reach

    def _log_charging_detour(self, t: str, name: str, detour_total_hours: float,
                             energy_to_reach_cs: float, energy_cs_to_dest: float,
                             soc_at_cs: float, available_charge_time: float, trip_target_soc: float,
                             charge_hours: float, travel_to_cs: float, travel_cs_to_dest: float,
                             dist_to_cs: float, dist_cs_to_dest: float):
        """Log detailed charging detour calculations."""
        current_energy = self.agent.current_soc * self.agent.battery_capacity_kwh
        print(
            f"[{t}][{name}][STOPPED] Charging detour calculation:\n"
            f"  Current SoC: {self.agent.current_soc:.0%} ({current_energy:.1f} kWh)\n"
            f"  Distance home→CS: {dist_to_cs:.1f} units\n"
            f"  Distance CS→dest: {dist_cs_to_dest:.1f} units\n"
            f"  Energy to reach CS: {energy_to_reach_cs:.1f} kWh\n"
            f"  SoC at CS: {soc_at_cs:.0%}\n"
            f"  Time available for charging: {available_charge_time:.2f} hours\n"
            f"  Trip target SoC: {trip_target_soc:.0%}\n"
            f"  Charge time: {charge_hours:.2f} hours\n"
            f"  Travel home→CS: {travel_to_cs:.2f} hours\n"
            f"  Travel CS→dest: {travel_cs_to_dest:.2f} hours\n"
            f"  Total detour time: {detour_total_hours:.2f} hours"
        )

    async def _make_departure_decision(self, next_stop: dict, needs_charge_detour: bool, 
                                       travel_hours: float, detour_total_hours: float,
                                       time_until_arrival: float, t: str, name: str):
        """Decide whether to depart now and which route to take.
        
        Returns
        -------
        next_state : str or None
            STATE_DRIVING, STATE_GOING_TO_CHARGER, or None to remain STOPPED.
        """
        total_travel_hours = detour_total_hours if needs_charge_detour else travel_hours
        
        print(
            f"[{t}][{name}][STOPPED] Departure calculation:\n"
            f"  Time until arrival: {time_until_arrival:.2f} hours\n"
            f"  Total travel time needed: {total_travel_hours:.2f} hours\n"
            f"  Needs charge detour: {needs_charge_detour}\n"
            f"  Should leave: {time_until_arrival <= total_travel_hours}"
        )
        
        if time_until_arrival <= total_travel_hours:
            if needs_charge_detour:
                self.agent.current_cs_jid = None
                self.agent.current_destination = next_stop
                extra_time = detour_total_hours - travel_hours
                print(
                    f"[{t}][{name}][STOPPED] Not enough energy for \"{next_stop['name']}\" "
                    f"(need charging detour, +{extra_time:.1f}h). Heading to charger first!"
                )
                return STATE_GOING_TO_CHARGER
            else:
                print(
                    f"[{t}][{name}][STOPPED] Time to leave for \"{next_stop['name']}\" "
                    f"(travel time ≈ {travel_hours:.1f}h)"
                )
                self.agent.current_destination = next_stop
                return STATE_DRIVING
        
        # Still waiting - log status
        time_until_leave = time_until_arrival - total_travel_hours
        charge_note = " ⚡needs charge" if needs_charge_detour else ""
        target_hour = next_stop["hour"]
        # Display time-of-day by wrapping at 24 hours
        display_h = int(target_hour) % 24
        display_m = int((target_hour % 1) * 60)
        print(
            f"[{t}][{name}][STOPPED] Parked | "
            f"SoC: {self.agent.current_soc:.0%} | "
            f"next: \"{next_stop['name']}\" at {display_h:02d}:{display_m:02d} "
            f"(leaving in ~{time_until_leave:.1f}h){charge_note}"
        )
        return None

    def _log_parked_no_schedule(self, t: str, name: str):
        """Log status when parked with no upcoming schedule."""
        print(f"[{t}][{name}][STOPPED] Parked (no schedule) | SoC: {self.agent.current_soc:.0%}")

    async def run(self):
        """Main state loop: check status and decide next action."""
        agent = self.agent
        name = str(agent.jid).split("@")[0]
        
        # Verify clock is available
        clock, t = self._check_clock_available()
        if not clock:
            await asyncio.sleep(TICK_SLEEP_SECONDS)
            self.set_next_state(STATE_STOPPED)
            return
        
        # Check for critical low SoC
        if await self._handle_low_soc(name, t):
            return
        
        # Get next destination
        next_stop, dist, _ = await self._get_next_stop_and_distances(t)
        
        if next_stop:
            # Calculate travel timing
            travel_hours, tick_sim_hours, now = await self._calculate_timing(dist)
            target_hour = next_stop["hour"]
            time_until_arrival = self._calculate_time_until_arrival(target_hour, now)
            
            # Check if charging detour is needed
            needs_charge_detour, detour_total_hours = await self._handle_charging_detour(
                next_stop, dist, travel_hours, tick_sim_hours, time_until_arrival, t, name, now
            )
            
            # Make departure decision
            next_state = await self._make_departure_decision(
                next_stop, needs_charge_detour, travel_hours, detour_total_hours,
                time_until_arrival, t, name
            )
            if next_state is not None:
                self.set_next_state(next_state)
                return
        else:
            # No schedule - just log status
            self._log_parked_no_schedule(t, name)
            await asyncio.sleep(TICK_SLEEP_SECONDS)
        
        self.set_next_state(STATE_STOPPED)
