"""
Dynamic Schedule Regeneration System
=====================================

## Overview

The dynamic scheduling system enables EV agents to have realistic, varying schedules
where the *midpoint destinations* change randomly every 24-hour cycle, while keeping
fixed appointment times consistent.

This simulates real-world scenarios where EVs have routine patterns (e.g., commute
during business hours) but visit different destinations based on daily needs.


## Architecture

### Components

1. **ScheduleManager** (schedule_manager.py)
   - Manages daily schedule generation
   - Caches the current day's schedule
   - Regenerates when crossing day boundaries
   - Fixed times: 8:00, 11:30, 15:00, 18:30, 20:00 (home)

2. **EVAgent** (ev_agent.py)
   - Stores `schedule_manager` instance if dynamic scheduling is enabled
   - Tracks `_day_offset` to know current day
   - `next_target()` calls schedule_manager for regenerated schedules

3. **Scenarios**
   - NEW: DynamicScheduling scenario demonstrates the feature
   - Existing scenarios still work (backward compatible)


## How It Works

### Static Schedule (Original)
```
Day 0: Home → Office A → Mall → Park → Gym → Home
Day 1: Home → Office A → Mall → Park → Gym → Home  (same)
Day 2: Home → Office A → Mall → Park → Gym → Home  (same)
```

### Dynamic Schedule (New)
```
Day 0: Home → Office A → Mall → Park → Gym → Home
Day 1: Home → University → Harbor → Tech Park → Downtown → Home  (new!)
Day 2: Home → Hospital → Airport → Shopping Center → Industrial → Home (new!)
```

Times remain fixed (08:00, 11:30, 15:00, 18:30, 20:00)
But destinations are randomly selected each day.


## Usage

### 1. Enable Dynamic Scheduling in EVAgent Config

Pass `available_spots` in the EV config:

```python
ev_config = {
    "battery_capacity_kwh": 60.0,
    "current_soc": 0.50,
    "x": 10.0,
    "y": 5.0,
    "schedule": initial_schedule,  # Still used for Day 0
    "available_spots": [           # NEW: For daily regeneration
        {"name": "Downtown", "x": 15.0, "y": 15.0},
        {"name": "Harbor", "x": -20.0, "y": -15.0},
        # ... more spots ...
    ],
    "num_schedule_stops": 4,  # Stops per day before returning home
    # ... other config ...
}
```

### 2. Use the DynamicScheduling Scenario

In scenarios/__init__.py, DynamicScheduling is registered:
```python
SCENARIOS = [
    PriceComparison(),
    CSAvailability(),
    RandomScenario(),
    DynamicScheduling(),  # NEW: Demonstrates dynamic scheduling
]
```

Select it from the scenario menu when running main.py.

### 3. Access Current Day Schedule

In your code:
```python
# Get the entire schedule for the current day
current_day_schedule = ev_agent.get_current_day_schedule()
for stop in current_day_schedule:
    print(f"{stop['hour']:0.1f}: {stop['name']}")

# Returns Day 1's regenerated schedule (new midpoints each day)
```


## Implementation Details

### ScheduleManager

**Constructor:**
```python
ScheduleManager(
    home_x: float,
    home_y: float,
    available_spots: List[Dict],
    num_stops: int = 4
)
```

**Key Methods:**

- `generate_initial_schedule()` → List[Dict]
  Returns the Day 0 schedule

- `get_schedule_for_day(day: int)` → List[Dict]
  Returns schedule for specific day (regenerates if needed)
  Times are in absolute hours: 8.0 + 24*day, 11.5 + 24*day, etc.

- `get_all_midpoints_for_day(day: int)` → List[Dict]
  Returns non-home destinations for a day


### EVAgent Changes

**New Attributes:**
```python
self.schedule_manager: Optional[ScheduleManager] = None
self.available_spots = config.get("available_spots", [])
```

**Modified Methods:**

`next_target()`:
- If schedule_manager exists, calls `get_schedule_for_day(self._day_offset)`
- Falls back to static schedule if no manager
- Maintains backward compatibility

`get_current_day_schedule()`:
- NEW: Convenience method to get full day's schedule
- Returns dynamic or static schedule


### Integration with main.py

The deployment function now passes `scenario.spots` to each EV:

```python
"config": {
    # ... existing fields ...
    "available_spots": scenario.spots,  # Added this line
}
```

This enables dynamic scheduling for EVs in all scenarios that define spots.


## Backward Compatibility

✅ **Fully backward compatible**
- EVs without `available_spots` use static schedules
- Existing scenarios continue to work unchanged
- `next_target()` gracefully falls back to static mode


## Day Boundary Detection

The system regenerates schedules automatically when:
- EV completes its final destination (Home) and starts a new cycle
- `_day_offset` increments (happens in driving.py state machine)
- `next_target()` detects change and calls ScheduleManager with new day

Example flow:
1. Day 0: hours 0-24 (schedule_manager.get_schedule_for_day(0))
2. EV arrives home, switches to STOPPED state
3. Driving state detects new day, _day_offset → 1
4. Day 1: hours 24-48 (schedule_manager.get_schedule_for_day(1) with NEW destinations)


## Visualization

The visualization already supports seeing targets (destinations) for all EVs.
With dynamic scheduling, you'll see:
- Day 0: First set of destinations visualized as diamonds
- Day 1: Different set of destinations on the map (regenerated)
- etc.

This makes it visually apparent that the schedule is changing.


## Example: DynamicScheduling Scenario

```python
# File: scenarios/dynamic_scheduling.py
class DynamicScheduling(Scenario):
    def __init__(self):
        # 10 available spots across the map
        self.spots = [
            {"name": "Downtown Plaza", "x": 15.0, "y": 15.0},
            {"name": "University", "x": -12.0, "y": 18.0},
            # ... 8 more spots ...
        ]
        
        # Each EV will:
        # - Start with day 0 static schedule
        # - Day 1+: Get 4 random destinations from self.spots daily
        # - Same times, different places each day
```


## Future Extensions

Possible enhancements:
1. **Time constraints**: Add deadline flexibility per destination
2. **Urgency levels**: Mark destinations as high/medium/low priority
3. **Seasonal patterns**: Different spot pools by season
4. **Traffic modeling**: Different routes based on time of day
5. **Persistent storage**: Save actual routes for analysis


## Debugging / Logging

To see when schedules regenerate, check EV agent logs:
- "Schedule regenerated for day N with destinations: [...]"
- Print `ev_agent.get_current_day_schedule()` to inspect

Add logging to schedule_manager.py `_generate_day_schedule()` for detailed info.
"""

# Implementation note:
# This is a reference document. The actual implementation spans:
# - agents/ev_agent/schedule_manager.py (core logic)
# - agents/ev_agent/ev_agent.py (integration)
# - scenarios/dynamic_scheduling.py (example scenario)
# - main.py (deployment integration)
