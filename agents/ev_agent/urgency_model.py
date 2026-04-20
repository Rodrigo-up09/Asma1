"""
Urgency Model System for EV Scheduling

Provides urgency-based decision making for:
- Charging priority adjustment
- Routing decisions
- Time pressure response
- Emergency handling

Integrates with TimeConstraintManager for cohesive scheduling.
"""

from dataclasses import dataclass
from enum import Enum
import math


class UrgencyLevel(Enum):
    """Urgency levels influencing EV behavior."""
    LOW = 1.0  # Flexible, can wait for cheaper charging
    MEDIUM = 2.0  # Regular appointments, balanced behavior
    HIGH = 5.0  # Important meetings, prioritize on-time arrival
    EMERGENCY = 10.0  # Critical, must arrive before deadline


class ChargingStrategy(Enum):
    """Charging strategies based on urgency."""
    OPPORTUNISTIC = "opportunistic"  # Charge only when necessary
    BALANCED = "balanced"  # Charge at optimal times
    AGGRESSIVE = "aggressive"  # Charge whenever possible


@dataclass
class UrgencyMetrics:
    """Calculated urgency metrics for decision making."""
    urgency_level: UrgencyLevel
    time_pressure: float  # 0.0 (relaxed) to 1.0+ (critical)
    charging_multiplier: float  # Factor to adjust charging thresholds
    speed_adjustment: float  # Speed multiplier (0.5x to 2.0x)
    charging_strategy: ChargingStrategy
    priority_score: float  # 0-100 score for priority decisions


class UrgencyModel:
    """Manages urgency-based EV decisions."""
    
    @staticmethod
    def get_urgency_level_from_priority(priority_name: str) -> UrgencyLevel:
        """Convert Priority name to UrgencyLevel."""
        priority_map = {
            "LOW": UrgencyLevel.LOW,
            "MEDIUM": UrgencyLevel.MEDIUM,
            "HIGH": UrgencyLevel.HIGH,
            "EMERGENCY": UrgencyLevel.EMERGENCY,
        }
        return priority_map.get(priority_name, UrgencyLevel.MEDIUM)
    
    @staticmethod
    def calculate_time_pressure(
        current_time: float,
        target_time: float,
        hard_deadline: float,
        distance: float,
        velocity: float,
    ) -> float:
        """Calculate time pressure (0.0 to 1.0+).
        
        Measures how urgent the situation is:
        - 0.0: Relaxed, plenty of time
        - 0.5: Normal pressure, should start soon
        - 1.0: Getting tight, hurry up
        - 1.0+: Critical, may miss deadline
        
        Args:
            current_time: Current simulation time
            target_time: Desired arrival time
            hard_deadline: Hard deadline (must not exceed)
            distance: Distance to destination
            velocity: EV velocity
        
        Returns:
            Time pressure score (0.0 to 1.0+)
        """
        if velocity <= 0:
            return 1.0  # Critical if can't move
        
        travel_time = distance / velocity
        time_until_deadline = hard_deadline - current_time
        
        if time_until_deadline <= 0:
            return 2.0  # Already past deadline
        
        # Pressure: how much of the available time is consumed by travel
        if travel_time >= time_until_deadline:
            return 1.0 + (travel_time - time_until_deadline) / time_until_deadline
        
        # Normalize to 0.0-1.0 range
        time_margin = time_until_deadline - travel_time
        time_to_target = max(0.1, target_time - current_time)
        
        return 1.0 - min(1.0, time_margin / (time_to_target + 0.1))
    
    @staticmethod
    def calculate_charging_threshold_adjustment(urgency_metrics: UrgencyMetrics) -> float:
        """Calculate SoC threshold multiplier based on urgency.
        
        Higher urgency → higher charging thresholds (charge more aggressively).
        
        Returns:
            Multiplier (1.0-2.5x) to apply to base charging thresholds.
        """
        base_multiplier = 1.0
        urgency_boost = {
            UrgencyLevel.LOW: 0.8,        # Relax threshold (80% normal)
            UrgencyLevel.MEDIUM: 1.0,    # Normal threshold
            UrgencyLevel.HIGH: 1.5,      # Charge more aggressively
            UrgencyLevel.EMERGENCY: 2.5,  # Charge whenever possible
        }
        return urgency_boost.get(urgency_metrics.urgency_level, 1.0)
    
    @staticmethod
    def calculate_metrics(
        current_time: float,
        destination: dict,
        current_soc: float,
        distance_to_destination: float,
        velocity: float,
    ) -> UrgencyMetrics:
        """Calculate comprehensive urgency metrics for a destination.
        
        Args:
            current_time: Current simulation time
            destination: Destination entry with time_window
            current_soc: Current state of charge (0.0-1.0)
            distance_to_destination: Distance to destination (units)
            velocity: EV velocity (units/hour)
        
        Returns:
            UrgencyMetrics with all decision factors
        """
        # Extract time window info
        time_window = destination.get("time_window", {})
        scheduled_hour = time_window.get("scheduled_hour", current_time + 1)
        deadline_hard = time_window.get("deadline_hard", scheduled_hour + 2)
        priority_name = time_window.get("priority", "MEDIUM")
        
        # Calculate base metrics
        urgency_level = UrgencyModel.get_urgency_level_from_priority(priority_name)
        time_pressure = UrgencyModel.calculate_time_pressure(
            current_time=current_time,
            target_time=scheduled_hour,
            hard_deadline=deadline_hard,
            distance=distance_to_destination,
            velocity=velocity,
        )
        
        # Clamp time pressure
        time_pressure = max(0.0, min(2.0, time_pressure))
        
        # Calculate charging multiplier
        charging_multiplier = UrgencyModel.calculate_charging_threshold_adjustment(
            UrgencyMetrics(
                urgency_level=urgency_level,
                time_pressure=time_pressure,
                charging_multiplier=0,  # Placeholder
                speed_adjustment=0,
                charging_strategy=ChargingStrategy.BALANCED,
                priority_score=0,
            )
        )
        
        # Calculate speed adjustment
        if time_pressure < 0.3:
            speed_adjustment = 0.8  # Relax, can go slow
        elif time_pressure < 0.7:
            speed_adjustment = 1.0  # Normal speed
        elif time_pressure < 1.2:
            speed_adjustment = 1.5  # Speed up
        else:
            speed_adjustment = 2.0  # Maximum speed
        
        # Determine charging strategy
        if urgency_level == UrgencyLevel.LOW:
            charging_strategy = ChargingStrategy.OPPORTUNISTIC
        elif urgency_level == UrgencyLevel.HIGH:
            charging_strategy = ChargingStrategy.AGGRESSIVE
        elif urgency_level == UrgencyLevel.EMERGENCY:
            charging_strategy = ChargingStrategy.AGGRESSIVE
        else:
            charging_strategy = ChargingStrategy.BALANCED
        
        # Calculate priority score (0-100)
        base_priority = urgency_level.value * 10  # 10-100
        time_pressure_bonus = min(30, time_pressure * 30)  # Up to +30
        priority_score = min(100.0, base_priority + time_pressure_bonus)
        
        return UrgencyMetrics(
            urgency_level=urgency_level,
            time_pressure=time_pressure,
            charging_multiplier=charging_multiplier,
            speed_adjustment=speed_adjustment,
            charging_strategy=charging_strategy,
            priority_score=priority_score,
        )
    
    @staticmethod
    def get_charging_threshold(
        base_threshold: float,
        urgency_metrics: UrgencyMetrics,
        max_threshold: float = 1.0,
    ) -> float:
        """Get urgency-adjusted charging threshold.
        
        Args:
            base_threshold: Base SoC threshold (e.g., 0.30)
            urgency_metrics: UrgencyMetrics from calculate_metrics()
            max_threshold: Maximum threshold allowed (e.g., 1.0)
        
        Returns:
            Adjusted threshold (base_threshold * multiplier, clamped to max)
        """
        adjusted = base_threshold * urgency_metrics.charging_multiplier
        return min(max_threshold, adjusted)
    
    @staticmethod
    def should_charge_now(
        current_soc: float,
        adjusted_threshold: float,
        urgency_metrics: UrgencyMetrics,
    ) -> bool:
        """Determine if EV should charge now based on urgency.
        
        Args:
            current_soc: Current state of charge
            adjusted_threshold: Urgency-adjusted charging threshold
            urgency_metrics: UrgencyMetrics
        
        Returns:
            True if should charge, False otherwise
        """
        if urgency_metrics.charging_strategy == ChargingStrategy.OPPORTUNISTIC:
            return current_soc <= adjusted_threshold * 0.8  # Only charge when very low
        elif urgency_metrics.charging_strategy == ChargingStrategy.BALANCED:
            return current_soc <= adjusted_threshold
        else:  # AGGRESSIVE
            return current_soc <= adjusted_threshold * 1.2  # Charge earlier
    
    @staticmethod
    def rank_destinations(
        destinations: list,
        current_time: float,
        current_soc: float,
        current_x: float,
        current_y: float,
        velocity: float,
    ) -> list:
        """Rank destinations by priority based on urgency.
        
        Args:
            destinations: List of destination entries with time_window
            current_time: Current simulation time
            current_soc: Current state of charge
            current_x, current_y: Current position
            velocity: EV velocity
        
        Returns:
            List of (destination, urgency_metrics, priority_score) tuples, sorted by priority
        """
        scored_destinations = []
        
        for dest in destinations:
            distance = math.hypot(dest["x"] - current_x, dest["y"] - current_y)
            metrics = UrgencyModel.calculate_metrics(
                current_time=current_time,
                destination=dest,
                current_soc=current_soc,
                distance_to_destination=distance,
                velocity=velocity,
            )
            scored_destinations.append((dest, metrics, metrics.priority_score))
        
        # Sort by priority score (highest first)
        scored_destinations.sort(key=lambda x: x[2], reverse=True)
        
        return scored_destinations
    
    @staticmethod
    def format_urgency_metrics(metrics: UrgencyMetrics) -> str:
        """Format UrgencyMetrics for logging."""
        return (
            f"[Urgency: {metrics.urgency_level.name} | "
            f"Pressure: {metrics.time_pressure:.2f} | "
            f"Strategy: {metrics.charging_strategy.value} | "
            f"Priority Score: {metrics.priority_score:.0f}]"
        )
