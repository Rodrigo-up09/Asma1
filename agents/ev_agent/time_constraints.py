"""
Time Constraint Management System for EV Route Segments

Handles time windows, deadlines, and penalties for EV destinations.
Supports soft deadlines (penalties) and hard deadlines (failures).
"""

from enum import Enum
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass


class Priority(Enum):
    """Urgency levels for destinations."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    EMERGENCY = 4
    
    def to_penalty_multiplier(self) -> float:
        """Convert priority to penalty multiplier for deadline violations."""
        return {
            Priority.LOW: 1.0,
            Priority.MEDIUM: 2.0,
            Priority.HIGH: 5.0,
            Priority.EMERGENCY: 10.0,
        }[self]


class ArrivalStatus(Enum):
    """Status of arrival relative to time constraints."""
    EARLY = "early"          # Arrived before time_window_min
    ON_TIME = "on_time"      # Within soft time window
    LATE_SOFT = "late_soft"  # After time_window_max but before hard deadline
    LATE_HARD = "late_hard"  # After hard deadline
    MISSED = "missed"        # Didn't arrive (gave up)


@dataclass
class TimeWindow:
    """Time window for a destination."""
    scheduled_hour: float      # Target arrival time (nominal)
    window_min: float          # Earliest acceptable arrival (soft start)
    window_max: float          # Latest preferred arrival (soft deadline)
    deadline_hard: Optional[float] = None  # Hard deadline (if None, use window_max)
    priority: Priority = Priority.MEDIUM
    
    @property
    def deadline_effective(self) -> float:
        """Get the effective hard deadline."""
        return self.deadline_hard if self.deadline_hard else self.window_max
    
    def get_arrival_status(self, arrival_hour: float) -> ArrivalStatus:
        """Classify arrival time against constraints."""
        if arrival_hour < self.window_min:
            return ArrivalStatus.EARLY
        elif arrival_hour <= self.window_max:
            return ArrivalStatus.ON_TIME
        elif arrival_hour <= self.deadline_effective:
            return ArrivalStatus.LATE_SOFT
        else:
            return ArrivalStatus.LATE_HARD
    
    def calculate_time_penalty(self, arrival_hour: float) -> Tuple[float, str]:
        """Calculate penalty for arriving at a given time.
        
        Returns:
            (penalty_score, penalty_reason)
            - penalty_score: 0.0 (no penalty) to infinity
            - penalty_reason: description of why penalty was applied
        """
        status = self.get_arrival_status(arrival_hour)
        
        if status == ArrivalStatus.EARLY:
            minutes_early = (self.window_min - arrival_hour) * 60
            penalty = max(0.0, (minutes_early / 60) * 0.5)  # Small penalty for being early
            return penalty, f"Early by {minutes_early:.0f}min (penalty: {penalty:.2f})"
        
        elif status == ArrivalStatus.ON_TIME:
            return 0.0, "On time"
        
        elif status == ArrivalStatus.LATE_SOFT:
            minutes_late = (arrival_hour - self.window_max) * 60
            base_penalty = minutes_late * self.priority.to_penalty_multiplier()
            return base_penalty, f"Late by {minutes_late:.0f}min (soft, penalty: {base_penalty:.2f})"
        
        else:  # LATE_HARD
            minutes_over = (arrival_hour - self.deadline_effective) * 60
            base_penalty = 100.0 + (minutes_over * self.priority.to_penalty_multiplier())
            return base_penalty, f"MISSED DEADLINE by {minutes_over:.0f}min (hard, penalty: {base_penalty:.2f})"


class TimeConstraintManager:
    """Manages time constraints for an EV's schedule."""
    
    def __init__(self, home_x: float, home_y: float):
        """Initialize constraint manager.
        
        Args:
            home_x: Home x coordinate
            home_y: Home y coordinate
        """
        self.home_x = home_x
        self.home_y = home_y
        self._constraint_cache: Dict[str, TimeWindow] = {}
    
    @staticmethod
    def enhance_schedule_with_constraints(
        schedule: List[Dict[str, Any]],
        default_window_width: float = 1.0,
        default_priority: Priority = Priority.MEDIUM,
    ) -> List[Dict[str, Any]]:
        """Enhance a schedule with time windows and constraints.
        
        Adds time_window and priority to schedule entries if not present.
        
        Args:
            schedule: List of schedule entries {name, x, y, hour, ...}
            default_window_width: Width of time window in hours (before and after target)
            default_priority: Default priority for destinations
        
        Returns:
            Enhanced schedule with time constraints
        """
        enhanced = []
        
        for entry in schedule:
            entry_copy = entry.copy()
            
            # Skip if already has time windows
            if "time_window" in entry_copy:
                enhanced.append(entry_copy)
                continue
            
            # Create default time window
            target_hour = entry_copy.get("hour", 0.0)
            
            entry_copy["time_window"] = {
                "scheduled_hour": target_hour,
                "window_min": target_hour - default_window_width,
                "window_max": target_hour + default_window_width,
                "deadline_hard": target_hour + (default_window_width * 2),
                "priority": default_priority.name,
            }
            
            enhanced.append(entry_copy)
        
        return enhanced
    
    def get_time_window(
        self,
        destination: Dict[str, Any],
    ) -> TimeWindow:
        """Extract TimeWindow from destination entry.
        
        Args:
            destination: Schedule entry with possible time_window field
        
        Returns:
            TimeWindow object with constraints
        """
        # Check cache
        cache_key = f"{destination['name']}_{destination['hour']}"
        if cache_key in self._constraint_cache:
            return self._constraint_cache[cache_key]
        
        # Parse time_window if present
        if "time_window" in destination:
            tw = destination["time_window"]
            priority = Priority[tw.get("priority", "MEDIUM")]
            
            window = TimeWindow(
                scheduled_hour=tw.get("scheduled_hour", destination["hour"]),
                window_min=tw.get("window_min", destination["hour"] - 1.0),
                window_max=tw.get("window_max", destination["hour"] + 1.0),
                deadline_hard=tw.get("deadline_hard", None),
                priority=priority,
            )
        else:
            # Use defaults based on destination name
            hour = destination.get("hour", 0.0)
            if destination["name"] == "Home":
                # Home has flexible window
                window = TimeWindow(
                    scheduled_hour=hour,
                    window_min=hour - 2.0,
                    window_max=hour + 2.0,
                    deadline_hard=None,
                    priority=Priority.LOW,
                )
            else:
                # Regular appointment
                window = TimeWindow(
                    scheduled_hour=hour,
                    window_min=hour - 0.5,
                    window_max=hour + 0.5,
                    deadline_hard=hour + 1.0,
                    priority=Priority.MEDIUM,
                )
        
        # Cache it
        self._constraint_cache[cache_key] = window
        return window
    
    def will_make_deadline(
        self,
        current_time: float,
        distance_to_destination: float,
        velocity: float,
        destination: Dict[str, Any],
    ) -> Tuple[bool, float, str]:
        """Check if EV can reach destination before hard deadline.
        
        Args:
            current_time: Current simulation time (hours)
            distance_to_destination: Distance to travel (units)
            velocity: EV velocity (units/hour)
            destination: Target destination entry
        
        Returns:
            (can_make_deadline, projected_arrival_time, reason_string)
        """
        if velocity <= 0:
            return False, float('inf'), "Zero velocity - cannot move"
        
        time_to_travel = distance_to_destination / velocity
        projected_arrival = current_time + time_to_travel
        
        window = self.get_time_window(destination)
        
        if projected_arrival <= window.deadline_effective:
            minutes_margin = (window.deadline_effective - projected_arrival) * 60
            return True, projected_arrival, f"Will arrive with {minutes_margin:.0f}min margin"
        else:
            minutes_over = (projected_arrival - window.deadline_effective) * 60
            return False, projected_arrival, f"Will miss deadline by {minutes_over:.0f}min"
    
    def calculate_energy_time_tradeoff(
        self,
        current_time: float,
        current_soc: float,
        distance_to_destination: float,
        battery_capacity: float,
        energy_per_km: float,
        base_velocity: float,
        destination: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Calculate energy vs time trade-off options.
        
        Computes several scenarios:
        - Normal speed (base_velocity)
        - Slow speed (energy efficient)
        - Fast speed (deadline-safe)
        
        Args:
            current_time: Current simulation time
            current_soc: Current state of charge
            distance_to_destination: Distance to travel
            battery_capacity: Battery capacity (kWh)
            energy_per_km: Energy consumption (kWh/km)
            base_velocity: Normal velocity (units/hour)
            destination: Target destination
        
        Returns:
            Dict with analysis of trade-off options
        """
        window = self.get_time_window(destination)
        time_available = window.deadline_effective - current_time
        
        analysis = {
            "destination": destination["name"],
            "current_time": current_time,
            "deadline": window.deadline_effective,
            "time_available_hours": time_available,
            "distance": distance_to_destination,
            "scenarios": [],
        }
        
        # Scenario 1: Normal speed
        if base_velocity > 0:
            travel_time = distance_to_destination / base_velocity
            arrival_time = current_time + travel_time
            energy_needed = (distance_to_destination / 1000.0) * energy_per_km  # Assuming distance in units=km
            soc_needed = energy_needed / battery_capacity
            status = window.get_arrival_status(arrival_time)
            penalty, penalty_reason = window.calculate_time_penalty(arrival_time)
            
            analysis["scenarios"].append({
                "speed_type": "normal",
                "velocity_multiplier": 1.0,
                "travel_time_hours": travel_time,
                "arrival_time": arrival_time,
                "energy_needed_kwh": energy_needed,
                "soc_needed": soc_needed,
                "feasible": soc_needed <= current_soc,
                "arrival_status": status.value,
                "time_penalty": penalty,
                "penalty_reason": penalty_reason,
            })
        
        # Scenario 2: Slow speed (1/2 velocity - energy efficient)
        if base_velocity > 0:
            slow_velocity = base_velocity * 0.5
            travel_time = distance_to_destination / slow_velocity
            arrival_time = current_time + travel_time
            # Energy drain is proportional to distance, not speed (simplified)
            energy_needed = (distance_to_destination / 1000.0) * energy_per_km * 0.7  # 30% savings
            soc_needed = energy_needed / battery_capacity
            status = window.get_arrival_status(arrival_time)
            penalty, penalty_reason = window.calculate_time_penalty(arrival_time)
            
            analysis["scenarios"].append({
                "speed_type": "slow_efficient",
                "velocity_multiplier": 0.5,
                "travel_time_hours": travel_time,
                "arrival_time": arrival_time,
                "energy_needed_kwh": energy_needed,
                "soc_needed": soc_needed,
                "feasible": soc_needed <= current_soc and arrival_time <= window.deadline_effective,
                "arrival_status": status.value,
                "time_penalty": penalty,
                "penalty_reason": penalty_reason,
            })
        
        # Scenario 3: Fast speed (2x velocity - deadline safe)
        if base_velocity > 0 and time_available > 0:
            fast_velocity = min(base_velocity * 2.0, distance_to_destination / max(time_available, 0.1))
            travel_time = distance_to_destination / fast_velocity
            arrival_time = current_time + travel_time
            # Fast driving uses more energy
            energy_needed = (distance_to_destination / 1000.0) * energy_per_km * 1.3  # 30% penalty
            soc_needed = energy_needed / battery_capacity
            status = window.get_arrival_status(arrival_time)
            penalty, penalty_reason = window.calculate_time_penalty(arrival_time)
            
            analysis["scenarios"].append({
                "speed_type": "fast_deadline_safe",
                "velocity_multiplier": 2.0,
                "travel_time_hours": travel_time,
                "arrival_time": arrival_time,
                "energy_needed_kwh": energy_needed,
                "soc_needed": soc_needed,
                "feasible": soc_needed <= current_soc and arrival_time <= window.deadline_effective,
                "arrival_status": status.value,
                "time_penalty": penalty,
                "penalty_reason": penalty_reason,
            })
        
        return analysis
    
    def recommend_speed(
        self,
        analysis: Dict[str, Any],
        prefer_on_time: bool = True,
    ) -> Tuple[float, str]:
        """Recommend optimal speed multiplier based on analysis.
        
        Args:
            analysis: Output from calculate_energy_time_tradeoff
            prefer_on_time: If True, prioritize deadline compliance
        
        Returns:
            (velocity_multiplier, recommendation_reason)
        """
        scenarios = analysis["scenarios"]
        
        if not scenarios:
            return 1.0, "No scenarios available"
        
        # Filter feasible scenarios
        feasible = [s for s in scenarios if s["feasible"]]
        
        if not feasible:
            # All infeasible - pick the one that gets closest
            best = min(scenarios, key=lambda s: s["time_penalty"])
            return best["velocity_multiplier"], f"Choosing least-bad option: {best['penalty_reason']}"
        
        if prefer_on_time:
            # Prioritize on-time delivery
            on_time = [s for s in feasible if s["arrival_status"] == "on_time"]
            if on_time:
                best = min(on_time, key=lambda s: s["energy_needed_kwh"])
                return best["velocity_multiplier"], "On-time + energy efficient"
            
            # Next best: within soft deadline
            soft_ok = [s for s in feasible if s["arrival_status"] in ["on_time", "late_soft"]]
            if soft_ok:
                best = min(soft_ok, key=lambda s: s["time_penalty"])
                return best["velocity_multiplier"], f"Meet soft deadline: {best['penalty_reason']}"
        
        # Prefer energy efficient
        best_energy = min(feasible, key=lambda s: s["energy_needed_kwh"])
        return best_energy["velocity_multiplier"], f"Energy efficient: {best_energy['penalty_reason']}"
