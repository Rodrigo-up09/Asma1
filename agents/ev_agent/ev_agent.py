import json

from typing import Optional

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.template import Template

from .messaging import EVMessagingService
from .schedule_manager import ScheduleManager
from .time_constraints import TimeConstraintManager, Priority
from .urgency_model import UrgencyModel
from .states import (
    ChargingState,
    DrivingState,
    EVChargingFSM,
    GoingToChargerState,
    StoppedState,
    WaitingQueueState,
    STATE_CHARGING,
    STATE_DRIVING,
    STATE_GOING_TO_CHARGER,
    STATE_STOPPED,
    STATE_WAITING_QUEUE,
)
from .utils import closest_station, get_station_position


class WorldUpdateBehaviour(CyclicBehaviour):
    """Receive world-update broadcasts from the WorldAgent and update local state."""

    async def run(self) -> None:
        msg = await self.receive(timeout=5)
        if msg is None:
            return
        try:
            data = json.loads(msg.body)
        except (json.JSONDecodeError, TypeError):
            return

        self.agent.electricity_price = data.get(
            "electricity_price",
            data.get("energy_price", self.agent.electricity_price),
        )
        self.agent.grid_load = data.get("grid_load", self.agent.grid_load)
        if "solar_production_rate" in data:
            try:
                self.agent.renewable_available = float(data["solar_production_rate"]) > 0.0
            except (TypeError, ValueError):
                pass
        else:
            self.agent.renewable_available = data.get(
                "renewable_available", self.agent.renewable_available
            )


class EVAgent(Agent):
    def __init__(
        self,
        jid,
        password,
        ev_config=None,
        *args,
        **kwargs,
    ):
        super().__init__(jid, password, *args, **kwargs)

        config = ev_config or {}

        self.battery_capacity_kwh = config.get("battery_capacity_kwh", 60.0)
        self.current_soc = config.get("current_soc", 0.20)
        self.low_soc_threshold = config.get("low_soc_threshold", 0.20)
        self.target_soc = config.get("target_soc", 0.80)

        self.departure_time = config.get("departure_time", "08:00")
        self.arrival_time = config.get("arrival_time", "22:00")

        self.max_charge_rate_kw = config.get("max_charge_rate_kw", 22.0)
        self.current_charge_rate_kw = 0.0

        self.x = config.get("x", 0.0)
        self.y = config.get("y", 0.0)
        self.velocity = config.get("velocity", 1.0)
        self.energy_per_km = config.get("energy_per_km", 1)

        self.cs_stations = config.get("cs_stations", [])
        self.current_cs_jid = None

        self.electricity_price = config.get("electricity_price", 0.15)
        self.grid_load = config.get("grid_load", 0.5)
        self.renewable_available = config.get("renewable_available", False)

        # Schedule: list of {"name": str, "x": float, "y": float, "hour": float}
        base_schedule = config.get("schedule", [])
        self.schedule = sorted(
            base_schedule,
            key=lambda s: s["hour"],
        )
        self.current_target_index = 0
        self._day_offset = 0  # whole days elapsed since start (for recurring schedule)
        
        # Dynamic schedule manager (optional) — if available_spots provided, enable dynamic regen
        available_spots = config.get("available_spots", [])
        self.schedule_manager: Optional[ScheduleManager] = None
        if available_spots:
            self.schedule_manager = ScheduleManager(
                home_x=self.x,
                home_y=self.y,
                available_spots=available_spots,
                num_stops=config.get("num_schedule_stops", 4),
            )
            # Initialize static schedule from generator if it's the first day
            if not self.schedule:
                self.schedule = self.schedule_manager.generate_initial_schedule()
        
        # Time constraint manager for deadline checking and energy-time trade-offs
        self.time_constraint_manager = TimeConstraintManager(home_x=self.x, home_y=self.y)
        
        # Enhance schedule with time constraints if not already present
        enable_time_constraints = config.get("enable_time_constraints", True)
        if enable_time_constraints:
            constraint_window_width = config.get("time_constraint_window_width", 1.0)
            default_priority_name = config.get("default_priority", "MEDIUM")
            default_priority = Priority[default_priority_name]
            self.schedule = self.time_constraint_manager.enhance_schedule_with_constraints(
                self.schedule,
                default_window_width=constraint_window_width,
                default_priority=default_priority,
            )
        
        self.current_destination = None  # The destination we're currently heading to
        # WorldAgent JID — set by main.py after construction
        self.world_jid: str = config.get("world_jid", "")

        # Session tracking (used by states for metric reporting)
        self._session_kwh: float = 0.0
        self._queue_entry_time: float = 0.0
        
        # Time constraint tracking
        self._deadline_misses: int = 0
        self._deadline_meets: int = 0
        self._total_time_penalty: float = 0.0

        self.messaging_service = EVMessagingService()
        self.world_clock = None

    def mark_deadline_missed(self):
        """Advance schedule index to skip the destination that was just missed."""
        if self.schedule:
            self.current_target_index = (self.current_target_index + 1) % len(self.schedule)
        # Clear any trip-specific charging target associated with the missed trip
        if hasattr(self, "_trip_target_soc"):
            delattr(self, "_trip_target_soc")

    def next_target(self):
        """Return the next scheduled destination (current_target_index) with absolute hour.
        
        If dynamic scheduling is enabled via schedule_manager, the midpoint destinations
        change daily. The schedule repeats daily; the returned stop's hour is adjusted by
        the current day offset to give an absolute simulation time.
        """
        if not self.schedule:
            return None
        
        # If dynamic scheduling is enabled, get the day-specific schedule
        if self.schedule_manager:
            current_day_schedule = self.schedule_manager.get_schedule_for_day(self._day_offset)
            if current_day_schedule and self.current_target_index < len(current_day_schedule):
                return current_day_schedule[self.current_target_index].copy()
            return None
        
        # Static schedule fallback (no dynamic generator)
        stop = self.schedule[self.current_target_index]
        result = stop.copy()
        # Apply day offset to get absolute hour
        result["hour"] = stop["hour"] + 24 * self._day_offset
        return result



    def next_after(self, target):
        """Return the schedule entry that comes after `target`.
        Wraps around to the first entry if target is the last one."""
        if not self.schedule or not target:
            return None
        try:
            idx = self.schedule.index(target)
        except ValueError:
            return None
        return self.schedule[(idx + 1) % len(self.schedule)]

    def get_current_day_schedule(self):
        """Get the full schedule for the current day.
        
        If dynamic scheduling is enabled, returns the day-specific schedule
        with randomly selected midpoints. Otherwise returns the static schedule.
        
        Returns:
            List of schedule entries for today or None.
        """
        if self.schedule_manager:
            return self.schedule_manager.get_schedule_for_day(self._day_offset)
        return self.schedule if self.schedule else None
    
    def can_make_deadline(self, destination, current_time: float) -> tuple[bool, str]:
        """Check if EV can reach destination before hard deadline.
        
        Args:
            destination: Target destination entry
            current_time: Current simulation time
        
        Returns:
            (can_make_deadline, reason_string)
        """
        import math
        distance = math.hypot(destination["x"] - self.x, destination["y"] - self.y)
        can_make, projected_arrival, reason = self.time_constraint_manager.will_make_deadline(
            current_time=current_time,
            distance_to_destination=distance,
            velocity=self.velocity,
            destination=destination,
        )
        return can_make, reason
    
    def analyze_energy_time_tradeoff(self, destination, current_time: float) -> dict:
        """Analyze energy vs time trade-off for reaching a destination.
        
        Args:
            destination: Target destination entry
            current_time: Current simulation time
        
        Returns:
            Dict with scenario analysis and recommendations
        """
        import math
        distance = math.hypot(destination["x"] - self.x, destination["y"] - self.y)
        
        analysis = self.time_constraint_manager.calculate_energy_time_tradeoff(
            current_time=current_time,
            current_soc=self.current_soc,
            distance_to_destination=distance,
            battery_capacity=self.battery_capacity_kwh,
            energy_per_km=self.energy_per_km,
            base_velocity=self.velocity,
            destination=destination,
        )
        return analysis
    
    def get_recommended_speed_multiplier(self, destination, current_time: float) -> tuple[float, str]:
        """Get recommended speed multiplier based on time constraints.
        
        Args:
            destination: Target destination entry
            current_time: Current simulation time
        
        Returns:
            (speed_multiplier, reason_string)
        """
        analysis = self.analyze_energy_time_tradeoff(destination, current_time)
        multiplier, reason = self.time_constraint_manager.recommend_speed(analysis, prefer_on_time=True)
        return multiplier, reason

    def _closest_cs(self):
        return closest_station(self.x, self.y, self.cs_stations)

    def _get_cs_position(self, cs_jid):
        return get_station_position(self.cs_stations, cs_jid)

    async def setup(self):
        print(f"[EV Agent] {self.jid} starting...")
        print(
            f"[EV Agent] Battery: {self.battery_capacity_kwh} kWh | "
            f"Current SoC: {self.current_soc:.0%} | "
            f"Max charge rate: {self.max_charge_rate_kw} kW | "
            f"Position: ({self.x}, {self.y})"
        )
        if self.schedule:
            stops = ", ".join(
                f"{int(s['hour']):02d}:{int((s['hour'] % 1) * 60):02d} → {s['name']}"
                for s in self.schedule
            )
            print(f"[EV Agent] Schedule: {stops}")

        fsm = EVChargingFSM()

        fsm.add_state(name=STATE_STOPPED, state=StoppedState(), initial=True)
        fsm.add_state(name=STATE_DRIVING, state=DrivingState())
        fsm.add_state(name=STATE_GOING_TO_CHARGER, state=GoingToChargerState())
        fsm.add_state(name=STATE_WAITING_QUEUE, state=WaitingQueueState())
        fsm.add_state(name=STATE_CHARGING, state=ChargingState())

        fsm.add_transition(source=STATE_DRIVING, dest=STATE_DRIVING)
        fsm.add_transition(source=STATE_DRIVING, dest=STATE_GOING_TO_CHARGER)
        fsm.add_transition(source=STATE_GOING_TO_CHARGER, dest=STATE_CHARGING)
        fsm.add_transition(source=STATE_GOING_TO_CHARGER, dest=STATE_WAITING_QUEUE)
        fsm.add_transition(source=STATE_GOING_TO_CHARGER, dest=STATE_GOING_TO_CHARGER)
        fsm.add_transition(source=STATE_WAITING_QUEUE, dest=STATE_WAITING_QUEUE)
        fsm.add_transition(source=STATE_WAITING_QUEUE, dest=STATE_CHARGING)
        fsm.add_transition(source=STATE_CHARGING, dest=STATE_CHARGING)
        fsm.add_transition(source=STATE_CHARGING, dest=STATE_DRIVING)
        fsm.add_transition(source=STATE_DRIVING, dest=STATE_STOPPED)
        fsm.add_transition(source=STATE_STOPPED, dest=STATE_STOPPED)
        fsm.add_transition(source=STATE_STOPPED, dest=STATE_DRIVING)
        fsm.add_transition(source=STATE_STOPPED, dest=STATE_GOING_TO_CHARGER)

        template = Template()
        template.set_metadata("protocol", "ev-charging")

        self.add_behaviour(fsm, template)

        world_update_template = Template()
        world_update_template.set_metadata("protocol", "world-update")
        self.add_behaviour(WorldUpdateBehaviour(), world_update_template)
