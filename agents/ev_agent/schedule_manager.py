"""
Dynamic schedule manager for EV agents.

Handles regeneration of schedules on daily cycles.
Keeps fixed time slots but changes destination midpoints every 24 hours.
"""

import random
from typing import List, Dict, Any, Optional


class ScheduleManager:
    """Manages dynamic daily schedule regeneration for EVs.
    
    The schedule repeats on a 24-hour cycle with fixed appointment times,
    but the midpoint destinations change each day for variability.
    
    Structure:
    - Fixed time slots per day: 8:00, 11:30, 15:00, 18:30, 20:00 (return home)
    - Daily midpoints: randomly selected from available spots
    - Each day's schedule is cached until the next day boundary
    """
    
    # Fixed daily schedule times (in simulation hours)
    DAILY_TIMES = [8.0, 11.5, 15.0, 18.5]  # Appointment times
    HOME_TIME = 20.0                         # Return home time
    
    def __init__(
        self,
        home_x: float,
        home_y: float,
        available_spots: List[Dict[str, Any]],
        num_stops: int = 4,
    ):
        """Initialize schedule manager.
        
        Args:
            home_x: Home x coordinate
            home_y: Home y coordinate
            available_spots: List of spots with structure: {"name": str, "x": float, "y": float}
            num_stops: Number of stops per day (before returning home)
        """
        self.home_x = home_x
        self.home_y = home_y
        self.available_spots = available_spots
        self.num_stops = min(num_stops, len(self.DAILY_TIMES))
        
        # Cache for current day's schedule
        self._current_day = -1
        self._current_day_schedule: List[Dict[str, Any]] = []
    
    def generate_initial_schedule(self) -> List[Dict[str, Any]]:
        """Generate the initial repeating schedule template (one day).
        
        Returns:
            List of schedule destinations for one day with local hours (0-24).
        """
        return self._generate_day_schedule(day=0)
    
    def get_schedule_for_day(self, day: int) -> List[Dict[str, Any]]:
        """Get the schedule for a specific simulation day.
        
        Generates a new schedule if this day hasn't been generated yet.
        Midpoints are randomly selected daily; times are fixed.
        
        Args:
            day: Simulation day (0-indexed)
        
        Returns:
            List of schedule destinations with absolute hours for this day.
        """
        if day != self._current_day:
            # New day — regenerate with new random destinations
            self._current_day = day
            schedule_with_local_hours = self._generate_day_schedule(day)
            
            # Convert to absolute hours for this day
            with_absolute_hours = []
            for stop in schedule_with_local_hours:
                stop_copy = stop.copy()
                stop_copy["hour"] = stop["hour"] + (day * 24)
                with_absolute_hours.append(stop_copy)
            
            self._current_day_schedule = with_absolute_hours
        
        return self._current_day_schedule
    
    def _generate_day_schedule(self, day: int) -> List[Dict[str, Any]]:
        """Generate schedule for a specific day with random destinations.
        
        Picks random spots for each time slot; returns local hours (0-24).
        
        Args:
            day: Day number (used for deterministic randomness if desired)
        
        Returns:
            List of schedule destinations with local hours.
        """
        if not self.available_spots:
            # Fallback: just return home
            return [{
                "name": "Home",
                "x": self.home_x,
                "y": self.home_y,
                "hour": self.HOME_TIME,
                "type": "destination",
            }]
        
        schedule = []
        
        # Pick random midpoint destinations for today's appointments
        num_to_pick = min(self.num_stops, len(self.DAILY_TIMES))
        for time_slot in self.DAILY_TIMES[:num_to_pick]:
            spot = random.choice(self.available_spots)
            schedule.append({
                "name": spot["name"],
                "x": spot["x"],
                "y": spot["y"],
                "hour": time_slot,
                "type": "destination",
            })
        
        # Always return home at end of day
        schedule.append({
            "name": "Home",
            "x": self.home_x,
            "y": self.home_y,
            "hour": self.HOME_TIME,
            "type": "destination",
        })
        
        return schedule
    
    def get_stop_at_hour(
        self,
        current_hour: float,
        day: int,
    ) -> Optional[Dict[str, Any]]:
        """Get the scheduled stop that should be active at a given hour.
        
        Args:
            current_hour: Current simulation hour (0-24 within the day)
            day: Current day number
        
        Returns:
            Schedule entry for this hour, or None if between appointments.
        """
        schedule = self.get_schedule_for_day(day)
        
        # Find stop matching this hour (with small tolerance for floating point)
        for stop in schedule:
            local_hour = stop["hour"] % 24  # Get hour within day
            if abs(local_hour - current_hour) < 0.1:
                return stop
        
        return None
    
    def get_all_midpoints_for_day(self, day: int) -> List[Dict[str, Any]]:
        """Get all midpoint destinations (excluding home) for a specific day.
        
        Args:
            day: Day number
        
        Returns:
            List of non-home destinations for this day.
        """
        schedule = self.get_schedule_for_day(day)
        return [s for s in schedule if s["name"] != "Home"]
